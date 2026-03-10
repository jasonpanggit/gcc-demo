"""CVE Analytics Service

Provides analytics calculations for CVE dashboard metrics including:
- MTTP (Mean Time to Patch)
- Trending analysis
- Exposure scoring
- Vulnerability posture
- Aging distribution

All functions are async and leverage existing CVE scanner, service, and patch mapper.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict

try:
    from utils.cve_id_utils import is_valid_cve_id
    from utils.cve_scanner import CVEScanner
    from utils.cve_service import CVEService
    from utils.cve_patch_mapper import CVEPatchMapper
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.cve_id_utils import is_valid_cve_id
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_patch_mapper import CVEPatchMapper
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__, config.app.log_level)


def _parse_match_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


class CVEAnalytics:
    """CVE analytics service for dashboard metrics."""

    def __init__(
        self,
        cve_scanner: CVEScanner,
        cve_service: CVEService,
        cve_patch_mapper: CVEPatchMapper
    ):
        self.cve_scanner = cve_scanner
        self.cve_service = cve_service
        self.cve_patch_mapper = cve_patch_mapper
        logger.info("CVEAnalytics initialized")

    async def _get_cve_published_date(self, match: Dict[str, Any]) -> Optional[datetime]:
        """Prefer published_date already embedded in the scan match, then fall back to CVE lookup."""
        published_date = _parse_match_datetime(match.get("published_date"))
        if published_date:
            return published_date

        cve_id = match.get("cve_id")
        if not cve_id or not is_valid_cve_id(cve_id):
            return None

        cve = await self.cve_service.get_cve(cve_id)
        if not cve:
            return None

        if cve.published_date.tzinfo is None:
            return cve.published_date.replace(tzinfo=timezone.utc)
        return cve.published_date.astimezone(timezone.utc)

    async def _get_latest_scan_matches(self) -> List[Dict[str, Any]]:
        """Return normalized match dictionaries from the latest completed scan."""
        try:
            if hasattr(self.cve_scanner, "get_latest_scan_results"):
                scan_results = await self.cve_scanner.get_latest_scan_results()
                if not scan_results:
                    return []

                if isinstance(scan_results, dict):
                    return list(scan_results.get("matches") or [])

                normalized_matches: List[Dict[str, Any]] = []
                for scan in scan_results:
                    matches = getattr(scan, "matches", None) or []
                    for match in matches:
                        if hasattr(match, "model_dump"):
                            normalized_matches.append(match.model_dump())
                        elif hasattr(match, "dict"):
                            normalized_matches.append(match.dict())
                        else:
                            normalized_matches.append(dict(match))
                return normalized_matches

            scan_result = await self.cve_scanner.get_latest_scan_result()
        except Exception as e:
            logger.error(f"Failed to retrieve latest scan result: {e}")
            return []

        if not scan_result or not getattr(scan_result, "matches", None):
            return []

        normalized_matches: List[Dict[str, Any]] = []
        for match in scan_result.matches:
            if hasattr(match, "model_dump"):
                normalized_matches.append(match.model_dump())
            else:
                normalized_matches.append(match.dict())

        return normalized_matches

    async def calculate_mttp(self, time_range_days: int) -> Optional[float]:
        """Calculate Mean Time to Patch across all patched CVEs.

        Args:
            time_range_days: Days to look back for patch history

        Returns:
            Average days from CVE discovery to patch application (float)

        Algorithm:
            1. Query scan results for CVE discovery dates (first scan that detected CVE)
            2. Join with patch history to find application dates
            3. MTTP = SUM(patch_applied_date - cve_discovered_date) / COUNT(patched_cves)
            4. Only include CVEs that have been fully patched (all affected VMs)
        """
        logger.debug(f"Calculating MTTP for {time_range_days} day window")

        supports_install_history = getattr(self.cve_patch_mapper, "supports_install_history", None)
        if isinstance(supports_install_history, bool) and not supports_install_history:
            logger.info("Skipping MTTP calculation because patch install history is unavailable")
            return None

        try:
            # Get all scan results in time range
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

            # Query scan repository for historical results
            # Note: This would require scan history tracking. For now, using latest scan
            # as proxy. In production, we'd query: SELECT * FROM scans WHERE started_at >= cutoff_date
            matches = await self._get_latest_scan_matches()

            if not matches:
                logger.debug("No scan results available for MTTP calculation")
                return 0.0

            # Track patch timing for each unique CVE
            patch_times = []
            processed_cves = set()

            for match in matches:
                cve_id = match.get("cve_id")
                if not cve_id or cve_id in processed_cves:
                    continue
                processed_cves.add(cve_id)

                install_records = await self.cve_patch_mapper.get_install_history_for_cve(
                    cve_id,
                    time_range_days,
                )
                if not install_records:
                    continue

                patch_date = None
                for record in install_records:
                    candidate_date = _parse_match_datetime(record.get("completed_at") or record.get("last_modified"))
                    if candidate_date and (patch_date is None or candidate_date < patch_date):
                        patch_date = candidate_date

                if not patch_date:
                    continue

                # Get CVE discovery date (when first detected in scans)
                # Using CVE published_date as proxy. In production, we'd track first_seen_date
                discovery_date = await self._get_cve_published_date(match)
                if not discovery_date:
                    continue

                # Calculate time to patch
                time_to_patch = (patch_date - discovery_date).days

                if time_to_patch >= 0:  # Ignore negative values (data issues)
                    patch_times.append(time_to_patch)

            # Calculate average
            if not patch_times:
                logger.debug("No patched CVEs found in time range")
                return None

            mttp = sum(patch_times) / len(patch_times)
            logger.info(f"MTTP calculated: {mttp:.1f} days from {len(patch_times)} patched CVEs")
            return round(mttp, 1)

        except Exception as e:
            logger.error(f"Failed to calculate MTTP: {e}")
            return 0.0

    async def get_trending_data(
        self,
        time_range_days: int,
        severity: Optional[str] = None
    ) -> List[Dict]:
        """Get CVE count over time with appropriate bucketing.

        Args:
            time_range_days: Days to look back (30, 90, or 365)
            severity: Optional severity filter (CRITICAL, HIGH, MEDIUM, LOW)

        Returns:
            List of {"date": "2026-02-01", "count": 1198} time series data

        Bucketing strategy:
            - 30 days: daily buckets (30 data points)
            - 90 days: weekly buckets (~13 data points)
            - 365 days: monthly buckets (12 data points)
        """
        logger.debug(f"Getting trending data for {time_range_days} days, severity={severity}")

        try:
            if time_range_days <= 30:
                bucket_days = 1
                num_buckets = time_range_days
            elif time_range_days <= 90:
                bucket_days = 7
                num_buckets = time_range_days // 7
            else:
                bucket_days = 30
                num_buckets = 12

            now = datetime.now(timezone.utc)
            today = now.date()
            buckets = []
            for i in range(num_buckets):
                days_ago = (num_buckets - i - 1) * bucket_days
                bucket_start = datetime.combine(
                    today - timedelta(days=days_ago),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                )
                buckets.append({"date": bucket_start.strftime("%Y-%m-%d"), "count": 0})

            bucket_start_dates = [
                datetime.strptime(bucket["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                for bucket in buckets
            ]
            earliest_bucket_start = bucket_start_dates[0] if bucket_start_dates else now

            try:
                recent_scans = []
                if hasattr(self.cve_scanner, "list_recent_scans"):
                    recent_scans = await self.cve_scanner.list_recent_scans(limit=max(num_buckets * 4, 20))

                scans_with_history = 0
                for scan in recent_scans or []:
                    scan_status = scan.get("status") if isinstance(scan, dict) else getattr(scan, "status", None)
                    if scan_status != "completed":
                        continue

                    raw_started_at = scan.get("started_at") if isinstance(scan, dict) else getattr(scan, "started_at", None)
                    scan_started_at = _parse_match_datetime(raw_started_at)
                    if not scan_started_at or scan_started_at < earliest_bucket_start:
                        continue

                    matches = (scan.get("matches") if isinstance(scan, dict) else getattr(scan, "matches", None)) or []
                    unique_cves = set()
                    for match in matches:
                        if hasattr(match, "model_dump"):
                            match_data = match.model_dump()
                        elif hasattr(match, "dict"):
                            match_data = match.dict()
                        else:
                            match_data = dict(match)

                        match_severity = match_data.get("severity", "UNKNOWN")
                        if severity and match_severity != severity:
                            continue

                        cve_id = match_data.get("cve_id")
                        if cve_id:
                            unique_cves.add(cve_id)

                    for bucket, bucket_date in zip(buckets, bucket_start_dates):
                        bucket_end = bucket_date + timedelta(days=bucket_days)
                        if bucket_date <= scan_started_at < bucket_end:
                            bucket["count"] += len(unique_cves)
                            scans_with_history += 1
                            break

                if scans_with_history > 0:
                    logger.info("Trending data calculated from %d recent scans", scans_with_history)
                    return buckets
            except Exception as e:
                logger.warning(f"Scan-history trending fallback triggered: {e}")

            matches = await self._get_latest_scan_matches()
            if not matches:
                logger.debug("No scan results for trending data")
                return buckets

            for match in matches:
                cve_id = match.get("cve_id")
                if not cve_id:
                    continue

                match_severity = match.get("severity", "UNKNOWN")
                if severity and match_severity != severity:
                    continue

                published_date = await self._get_cve_published_date(match)
                if not published_date:
                    continue

                for bucket, bucket_date in zip(buckets, bucket_start_dates):
                    bucket_end = bucket_date + timedelta(days=bucket_days)
                    if bucket_date <= published_date < bucket_end:
                        bucket["count"] += 1
                        break

            logger.info(f"Trending data calculated: {len(buckets)} buckets")
            return buckets

        except Exception as e:
            logger.error(f"Failed to get trending data: {e}")
            return []

    async def get_top_cves_by_exposure(
        self,
        severity: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get top CVEs ranked by affected VM count.

        Args:
            severity: Optional severity filter
            limit: Maximum number of CVEs to return (default 10)

        Returns:
            List of CVE dictionaries sorted by exposure

        Sorting:
            Primary: affected_vms DESC
            Secondary: cvss_score DESC (tie-breaker)
        """
        logger.debug(f"Getting top {limit} CVEs by exposure, severity={severity}")

        try:
            matches = await self._get_latest_scan_matches()

            if not matches:
                logger.debug("No scan results for top CVEs")
                return []

            cve_exposure = defaultdict(lambda: {
                "affected_vms": set(),
                "severity": "",
                "cvss_score": 0.0,
                "published_date": None,
            })

            for match in matches:
                cve_id = match.get("cve_id")
                vm_id = match.get("vm_id")
                match_severity = match.get("severity", "UNKNOWN")

                if not cve_id or not vm_id:
                    continue

                if severity and match_severity != severity:
                    continue

                cve_exposure[cve_id]["affected_vms"].add(vm_id)
                cve_exposure[cve_id]["severity"] = match_severity
                cve_exposure[cve_id]["cvss_score"] = match.get("cvss_score", 0.0)
                cve_exposure[cve_id]["published_date"] = (
                    cve_exposure[cve_id]["published_date"] or match.get("published_date")
                )

            ranked_cves = []
            for cve_id, exposure_data in cve_exposure.items():
                ranked_cves.append({
                    "cve_id": cve_id,
                    "severity": exposure_data["severity"],
                    "cvss_score": exposure_data["cvss_score"],
                    "affected_vms": len(exposure_data["affected_vms"]),
                    "published_date": exposure_data["published_date"],
                })

            ranked_cves.sort(key=lambda x: (-x["affected_vms"], -x["cvss_score"]))

            result = ranked_cves[:limit]
            logger.info(f"Top CVEs calculated: {len(result)} CVEs returned")
            return result

        except Exception as e:
            logger.error(f"Failed to get top CVEs: {e}")
            return []

    async def get_vm_vulnerability_posture(
        self,
        severity: Optional[str] = None
    ) -> List[Dict]:
        """Get VMs ranked by vulnerability severity and count.

        Args:
            severity: Optional severity filter

        Returns:
            List of VM dictionaries with vulnerability metrics

        Sorting:
            Primary: highest_severity (CRITICAL > HIGH > MEDIUM > LOW)
            Secondary: cve_count DESC

        Limit: Top 20 VMs
        """
        logger.debug(f"Getting VM vulnerability posture, severity={severity}")

        try:
            matches = await self._get_latest_scan_matches()

            if not matches:
                logger.debug("No scan results for VM posture")
                return []

            # Aggregate by VM
            vm_posture = defaultdict(lambda: {
                "cve_ids": set(),
                "severities": set(),
                "vm_name": ""
            })

            severity_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}

            for match in matches:
                vm_id = match.get("vm_id")
                cve_id = match.get("cve_id")
                match_severity = match.get("severity", "UNKNOWN")
                vm_name = match.get("vm_name", vm_id)

                if not vm_id or not cve_id:
                    continue

                # Apply severity filter
                if severity and match_severity != severity:
                    continue

                vm_posture[vm_id]["cve_ids"].add(cve_id)
                vm_posture[vm_id]["severities"].add(match_severity)
                vm_posture[vm_id]["vm_name"] = vm_name

            # Build ranked list
            ranked_vms = []

            for vm_id, posture_data in vm_posture.items():
                # Determine highest severity
                highest_severity = "UNKNOWN"
                highest_rank = 0

                for sev in posture_data["severities"]:
                    rank = severity_rank.get(sev, 0)
                    if rank > highest_rank:
                        highest_rank = rank
                        highest_severity = sev

                ranked_vms.append({
                    "vm_id": vm_id,
                    "vm_name": posture_data["vm_name"],
                    "cve_count": len(posture_data["cve_ids"]),
                    "highest_severity": highest_severity,
                    "severity_rank": highest_rank
                })

            # Sort: primary by severity rank DESC, secondary by cve_count DESC
            ranked_vms.sort(
                key=lambda x: (-x["severity_rank"], -x["cve_count"])
            )

            # Remove internal severity_rank field
            for vm in ranked_vms:
                del vm["severity_rank"]

            result = ranked_vms[:20]  # Top 20 VMs
            logger.info(f"VM posture calculated: {len(result)} VMs returned")
            return result

        except Exception as e:
            logger.error(f"Failed to get VM posture: {e}")
            return []

    async def get_aging_distribution(
        self,
        severity: Optional[str] = None
    ) -> Dict[str, int]:
        """Get CVE aging distribution by exposure duration.

        Args:
            severity: Optional severity filter

        Returns:
            Dictionary with buckets: {"0-7_days": 89, "8-30_days": 234, ...}

        Buckets:
            - 0-7 days: Recently published
            - 8-30 days: Recent
            - 31-90 days: Moderate age
            - 90+ days: Old/stale
        """
        logger.debug(f"Getting aging distribution, severity={severity}")

        try:
            matches = await self._get_latest_scan_matches()

            if not matches:
                logger.debug("No scan results for aging distribution")
                return {"0-7_days": 0, "8-30_days": 0, "31-90_days": 0, "90+_days": 0}

            # Initialize buckets
            buckets = {
                "0-7_days": 0,
                "8-30_days": 0,
                "31-90_days": 0,
                "90+_days": 0
            }

            now = datetime.now(timezone.utc)
            processed_cves = set()  # Track to avoid double counting

            for match in matches:
                cve_id = match.get("cve_id")
                match_severity = match.get("severity", "UNKNOWN")

                if not cve_id or cve_id in processed_cves:
                    continue

                # Apply severity filter
                if severity and match_severity != severity:
                    continue

                published_date = await self._get_cve_published_date(match)
                if not published_date:
                    continue

                # Calculate days exposed
                days_exposed = (now - published_date).days

                # Assign to bucket
                if days_exposed <= 7:
                    buckets["0-7_days"] += 1
                elif days_exposed <= 30:
                    buckets["8-30_days"] += 1
                elif days_exposed <= 90:
                    buckets["31-90_days"] += 1
                else:
                    buckets["90+_days"] += 1

                processed_cves.add(cve_id)

            logger.info(f"Aging distribution calculated: {sum(buckets.values())} total CVEs")
            return buckets

        except Exception as e:
            logger.error(f"Failed to get aging distribution: {e}")
            return {"0-7_days": 0, "8-30_days": 0, "31-90_days": 0, "90+_days": 0}

    async def get_summary_stats(
        self,
        time_range_days: int,
        severity: Optional[str] = None
    ) -> Dict:
        """Get summary statistics for CVEs.

        Args:
            time_range_days: Days to look back
            severity: Optional severity filter

        Returns:
            Dictionary with counts: {"total_cves": 1247, "critical": 89, ...}
        """
        logger.debug(f"Getting summary stats for {time_range_days} days, severity={severity}")

        try:
            published_after = (datetime.now(timezone.utc) - timedelta(days=time_range_days)).isoformat()
            base_filters: Dict[str, Any] = {"published_after": published_after}

            if severity:
                total_count = await self.cve_service.count_cves({**base_filters, "severity": severity})
                result = {
                    "total_cves": total_count,
                    "critical": total_count if severity == "CRITICAL" else 0,
                    "high": total_count if severity == "HIGH" else 0,
                    "medium": total_count if severity == "MEDIUM" else 0,
                    "low": total_count if severity == "LOW" else 0,
                }
            else:
                critical_count, high_count, medium_count, low_count = await asyncio.gather(
                    self.cve_service.count_cves({**base_filters, "severity": "CRITICAL"}),
                    self.cve_service.count_cves({**base_filters, "severity": "HIGH"}),
                    self.cve_service.count_cves({**base_filters, "severity": "MEDIUM"}),
                    self.cve_service.count_cves({**base_filters, "severity": "LOW"}),
                )
                result = {
                    "total_cves": critical_count + high_count + medium_count + low_count,
                    "critical": critical_count,
                    "high": high_count,
                    "medium": medium_count,
                    "low": low_count,
                }

            logger.info(f"Summary stats calculated: {result['total_cves']} total CVEs")
            return result

        except Exception as e:
            logger.error(f"Failed to get summary stats: {e}")
            return {
                "total_cves": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            }
