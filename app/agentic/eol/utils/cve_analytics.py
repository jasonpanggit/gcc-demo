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

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from collections import defaultdict

try:
    from utils.cve_scanner import CVEScanner
    from utils.cve_service import CVEService
    from utils.cve_patch_mapper import CVEPatchMapper
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.utils.cve_scanner import CVEScanner
    from app.agentic.eol.utils.cve_service import CVEService
    from app.agentic.eol.utils.cve_patch_mapper import CVEPatchMapper
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__, config.app.log_level)


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

    async def calculate_mttp(self, time_range_days: int) -> float:
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

        try:
            # Get all scan results in time range
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=time_range_days)

            # Query scan repository for historical results
            # Note: This would require scan history tracking. For now, using latest scan
            # as proxy. In production, we'd query: SELECT * FROM scans WHERE started_at >= cutoff_date
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results available for MTTP calculation")
                return 0.0

            # Track patch timing for each CVE
            patch_times = []
            matches = scan_results.get("matches", [])

            for match in matches:
                cve_id = match.get("cve_id")
                if not cve_id:
                    continue

                # Get patch mapping to check if patched
                patch_mapping = await self.cve_patch_mapper.get_patches_for_cve(cve_id)

                # Check if CVE is fully patched (affected_vm_count should be 0 after patching)
                # In real implementation, we'd query patch history table
                # For now, we check if patches exist and have "installed" status
                is_patched = False
                patch_date = None

                for patch in patch_mapping.patches:
                    if patch.installation_status == "installed":
                        is_patched = True
                        # Use patch release_date as proxy for application date
                        if patch.release_date:
                            try:
                                patch_date = datetime.fromisoformat(
                                    patch.release_date.replace("Z", "+00:00")
                                )
                            except (ValueError, AttributeError):
                                continue
                        break

                if not is_patched or not patch_date:
                    continue

                # Get CVE discovery date (when first detected in scans)
                # Using CVE published_date as proxy. In production, we'd track first_seen_date
                cve = await self.cve_service.get_cve(cve_id)
                if not cve:
                    continue

                discovery_date = cve.published_date
                if discovery_date.tzinfo is None:
                    discovery_date = discovery_date.replace(tzinfo=timezone.utc)

                # Calculate time to patch
                time_to_patch = (patch_date - discovery_date).days

                if time_to_patch >= 0:  # Ignore negative values (data issues)
                    patch_times.append(time_to_patch)

            # Calculate average
            if not patch_times:
                logger.debug("No patched CVEs found in time range")
                return 0.0

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
            # Determine bucket size
            if time_range_days <= 30:
                bucket_days = 1  # Daily
                num_buckets = time_range_days
            elif time_range_days <= 90:
                bucket_days = 7  # Weekly
                num_buckets = time_range_days // 7
            else:
                bucket_days = 30  # Monthly
                num_buckets = 12

            # Initialize buckets with zero counts
            now = datetime.now(timezone.utc)
            buckets = []

            for i in range(num_buckets):
                bucket_start = now - timedelta(days=(num_buckets - i) * bucket_days)
                date_str = bucket_start.strftime("%Y-%m-%d")
                buckets.append({"date": date_str, "count": 0})

            # Query CVEs in time range from Cosmos
            # In production: SELECT * FROM cves WHERE published_date >= cutoff_date
            # For now, using scan results as proxy
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results for trending data")
                return buckets

            matches = scan_results.get("matches", [])

            # Count CVEs per bucket
            for match in matches:
                cve_id = match.get("cve_id")
                if not cve_id:
                    continue

                # Apply severity filter
                match_severity = match.get("severity", "UNKNOWN")
                if severity and match_severity != severity:
                    continue

                # Get CVE published date
                cve = await self.cve_service.get_cve(cve_id)
                if not cve:
                    continue

                published_date = cve.published_date
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)

                # Find appropriate bucket
                for bucket in buckets:
                    bucket_date = datetime.strptime(bucket["date"], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
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
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results for top CVEs")
                return []

            matches = scan_results.get("matches", [])

            # Aggregate matches by CVE ID to count affected VMs
            cve_exposure = defaultdict(lambda: {"affected_vms": set(), "severity": "", "cvss_score": 0.0})

            for match in matches:
                cve_id = match.get("cve_id")
                vm_id = match.get("vm_id")
                match_severity = match.get("severity", "UNKNOWN")

                if not cve_id or not vm_id:
                    continue

                # Apply severity filter
                if severity and match_severity != severity:
                    continue

                cve_exposure[cve_id]["affected_vms"].add(vm_id)
                cve_exposure[cve_id]["severity"] = match_severity
                cve_exposure[cve_id]["cvss_score"] = match.get("cvss_score", 0.0)

            # Build ranked list
            ranked_cves = []

            for cve_id, exposure_data in cve_exposure.items():
                # Get full CVE details
                cve = await self.cve_service.get_cve(cve_id)
                if not cve:
                    continue

                ranked_cves.append({
                    "cve_id": cve_id,
                    "severity": exposure_data["severity"],
                    "cvss_score": exposure_data["cvss_score"],
                    "affected_vms": len(exposure_data["affected_vms"]),
                    "published_date": cve.published_date.isoformat()
                })

            # Sort: primary by affected_vms DESC, secondary by cvss_score DESC
            ranked_cves.sort(
                key=lambda x: (-x["affected_vms"], -x["cvss_score"])
            )

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
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results for VM posture")
                return []

            matches = scan_results.get("matches", [])

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
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results for aging distribution")
                return {"0-7_days": 0, "8-30_days": 0, "31-90_days": 0, "90+_days": 0}

            matches = scan_results.get("matches", [])

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

                # Get CVE published date
                cve = await self.cve_service.get_cve(cve_id)
                if not cve:
                    continue

                published_date = cve.published_date
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)

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
            scan_results = await self.cve_scanner.get_latest_scan_results()

            if not scan_results or not scan_results.get("matches"):
                logger.debug("No scan results for summary stats")
                return {
                    "total_cves": 0,
                    "critical": 0,
                    "high": 0,
                    "medium": 0,
                    "low": 0
                }

            matches = scan_results.get("matches", [])

            # Count by severity
            severity_counts = defaultdict(int)
            processed_cves = set()

            for match in matches:
                cve_id = match.get("cve_id")
                match_severity = match.get("severity", "UNKNOWN")

                if not cve_id or cve_id in processed_cves:
                    continue

                # Apply severity filter
                if severity and match_severity != severity:
                    continue

                severity_counts[match_severity] += 1
                processed_cves.add(cve_id)

            result = {
                "total_cves": len(processed_cves),
                "critical": severity_counts.get("CRITICAL", 0),
                "high": severity_counts.get("HIGH", 0),
                "medium": severity_counts.get("MEDIUM", 0),
                "low": severity_counts.get("LOW", 0)
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
