"""
CVE Monitoring Scheduler

Scheduled CVE scanning and alerting service using APScheduler.
Executes scan-detect-alert workflow on configurable cron schedule.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    AsyncIOScheduler = None  # type: ignore[assignment,misc]
    CronTrigger = None  # type: ignore[assignment,misc]
    APSCHEDULER_AVAILABLE = False

try:
    from models.cve_alert_models import CVEMonitoringStats
    from utils.cve_delta_analyzer import CVEDeltaAnalyzer
    from utils.cve_alert_dispatcher import CVEAlertDispatcher
    from utils.logging_config import get_logger
    from utils.config import config
except ModuleNotFoundError:
    from app.agentic.eol.models.cve_alert_models import CVEMonitoringStats
    from app.agentic.eol.utils.cve_delta_analyzer import CVEDeltaAnalyzer
    from app.agentic.eol.utils.cve_alert_dispatcher import CVEAlertDispatcher
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import config

logger = get_logger(__name__)


class CVEMonitoringScheduler:
    """
    Scheduled CVE scanning and alerting service.

    Features:
    - Configurable cron-based scanning schedule
    - Delta detection against baseline scans
    - Multi-channel alert delivery
    - Job statistics tracking
    - Health check endpoint support
    """

    def __init__(self, cve_scanner, cve_service, patch_mapper):
        """
        Initialize CVE monitoring scheduler.

        Args:
            cve_scanner: CVEScanner instance for scan execution
            cve_service: CVEService for CVE detail lookups
            patch_mapper: CVEPatchMapper for patch availability checks
        """
        self.scanner = cve_scanner
        self.scan_repository = cve_scanner.scan_repository if hasattr(cve_scanner, 'scan_repository') else None
        self.delta_analyzer = CVEDeltaAnalyzer(
            scan_repository=self.scan_repository,
            cve_service=cve_service,
            patch_mapper=patch_mapper
        )
        self.alert_dispatcher = CVEAlertDispatcher()
        self.stats = CVEMonitoringStats()
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    def start(self):
        """
        Start the monitoring scheduler.
        - Register scan job with cron trigger
        - Register escalation check job (every 6 hours)
        - Start APScheduler
        """
        if not config.cve_monitoring.enable_cve_monitoring:
            logger.info("CVE monitoring disabled via config")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler not available - CVE monitoring disabled")
            return

        if self._running:
            logger.warning("CVE monitoring scheduler already running")
            return

        self._scheduler = AsyncIOScheduler(timezone=timezone.utc)

        # Add scan job with cron trigger
        try:
            cron_expr = config.cve_monitoring.scan_schedule_cron
            trigger = CronTrigger.from_crontab(cron_expr, timezone=timezone.utc)

            self._scheduler.add_job(
                self._execute_scan_and_alert,
                trigger=trigger,
                id="cve_scan_job",
                name="CVE Scan and Alert Job",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300  # 5 minutes
            )

            logger.info(f"Scheduled CVE scan job: cron='{cron_expr}'")

        except Exception as e:
            logger.error(f"Failed to schedule CVE scan job: {e}")
            return

        # Add escalation check job (every 6 hours)
        if getattr(config.cve_monitoring, 'enable_escalation', True):
            try:
                escalation_trigger = CronTrigger(hour="*/6", timezone=timezone.utc)

                self._scheduler.add_job(
                    self._check_escalations,
                    trigger=escalation_trigger,
                    id="cve_escalation_job",
                    name="CVE Alert Escalation Check",
                    replace_existing=True,
                    max_instances=1,
                    misfire_grace_time=300
                )

                logger.info("Scheduled CVE escalation job: every 6 hours")

            except Exception as e:
                logger.error(f"Failed to schedule escalation job: {e}")

        # Start scheduler
        self._scheduler.start()
        self._running = True

        # Update next run time
        self._update_next_run_time()

        logger.info("CVE monitoring scheduler started")

    async def _execute_scan_and_alert(self):
        """
        Execute full scan-detect-alert workflow.

        Steps:
        1. Trigger CVE scan
        2. Wait for scan completion (poll status)
        3. Run delta detection
        4. Send alerts if new CVEs found
        5. Update statistics
        6. Log summary
        """
        start_time = time.time()
        logger.info("Starting scheduled CVE scan")

        try:
            # 1. Trigger scan
            scan_response = await self.scanner.scan()
            scan_id = scan_response.scan_id
            logger.info(f"Scan triggered: {scan_id}")

            # 2. Wait for completion (poll every 5 seconds, 10 min timeout)
            scan_result = await self._wait_for_scan_completion(
                scan_id,
                timeout=config.cve_monitoring.scan_timeout_seconds
            )

            # 3. Detect deltas
            delta = await self.delta_analyzer.detect_new_cves(scan_id)

            # 4. Send alerts if not first scan and new CVEs found
            if not delta.is_first_scan and delta.new_cves:
                logger.info(f"Detected {len(delta.new_cves)} new CVEs - sending alerts")

                alert_summary = await self.alert_dispatcher.send_cve_alerts(
                    delta=delta,
                    severity_threshold=config.cve_monitoring.alert_severity_threshold
                )

                self.stats.total_alerts_sent += alert_summary.get("alerts_sent", 0)
                logger.info(f"Alerts sent: {alert_summary}")

            elif delta.is_first_scan:
                logger.info("First scan detected - no baseline for alerting")

            else:
                logger.info("No new CVEs detected")

            # 5. Update stats
            duration = time.time() - start_time
            self.stats.last_scan_time = datetime.now(timezone.utc).isoformat()
            self.stats.last_scan_duration_seconds = duration
            self.stats.total_scans += 1
            self.stats.last_delta_summary = {
                "new": len(delta.new_cves),
                "resolved": len(delta.resolved_cves)
            }

            # Update next run time
            self._update_next_run_time()

            logger.info(f"Scan completed in {duration:.2f}s - {len(delta.new_cves)} new CVEs")

        except Exception as e:
            duration = time.time() - start_time
            self.stats.total_errors += 1
            self.stats.last_error = str(e)
            self.stats.last_scan_duration_seconds = duration
            logger.error(f"Scan job failed after {duration:.2f}s: {e}", exc_info=True)

    async def _check_escalations(self):
        """
        Check for alerts requiring escalation.
        Runs on separate schedule from scans (every 6 hours).
        """
        logger.info("Running escalation check")
        try:
            from utils.cve_escalation_service import check_and_escalate_alerts

            summary = await check_and_escalate_alerts()
            logger.info(f"Escalation check complete: {summary}")

            # Update stats
            if summary["escalations_sent"] > 0:
                self.stats.total_alerts_sent += summary["escalations_sent"]

        except Exception as e:
            self.stats.total_errors += 1
            self.stats.last_error = f"Escalation check failed: {str(e)}"
            logger.error(f"Escalation check failed: {e}", exc_info=True)

    async def _wait_for_scan_completion(
        self,
        scan_id: str,
        timeout: int = 600
    ) -> Any:
        """
        Poll scan status until complete or timeout.

        Args:
            scan_id: Scan identifier
            timeout: Max wait time in seconds

        Returns:
            ScanResult when complete

        Raises:
            TimeoutError if scan doesn't complete
            RuntimeError if scan fails
        """
        start_time = time.time()
        poll_interval = 5  # seconds

        while time.time() - start_time < timeout:
            try:
                # Get scan status
                status_response = await self.scanner.get_scan_status(scan_id)
                status = status_response.get("status")

                if status == "completed":
                    logger.info(f"Scan {scan_id} completed")
                    return await self.scanner.get_scan_results(scan_id)

                if status == "failed":
                    error_msg = status_response.get("error", "Unknown error")
                    raise RuntimeError(f"Scan {scan_id} failed: {error_msg}")

                # Still running - wait before next poll
                logger.debug(f"Scan {scan_id} status: {status} - polling again in {poll_interval}s")
                await asyncio.sleep(poll_interval)

            except (RuntimeError, TimeoutError):
                raise
            except Exception as e:
                logger.warning(f"Error polling scan status: {e}")
                await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Scan {scan_id} timeout after {timeout}s")

    def get_status(self) -> Dict[str, Any]:
        """
        Get scheduler status and statistics.
        Used by health check endpoint.
        """
        self._update_next_run_time()

        # Get next escalation time
        next_escalation = None
        if self._scheduler and self._running:
            jobs = self._scheduler.get_jobs()
            escalation_job = next((j for j in jobs if j.id == "cve_escalation_job"), None)
            if escalation_job and escalation_job.next_run_time:
                next_escalation = escalation_job.next_run_time.isoformat()

        status_dict = {
            "scheduler_running": self._running,
            "apscheduler_available": APSCHEDULER_AVAILABLE,
            "monitoring_enabled": config.cve_monitoring.enable_cve_monitoring,
            "stats": self.stats.to_dict()
        }

        # Add next escalation time if available
        if next_escalation:
            status_dict["stats"]["next_escalation_check"] = next_escalation

        return status_dict

    def shutdown(self):
        """Gracefully shutdown scheduler"""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("CVE monitoring scheduler stopped")

    def _update_next_run_time(self):
        """Update next_scan_time in stats from scheduler"""
        if self._scheduler and self._running:
            jobs = self._scheduler.get_jobs()
            scan_job = next((j for j in jobs if j.id == "cve_scan_job"), None)

            if scan_job and scan_job.next_run_time:
                self.stats.next_scan_time = scan_job.next_run_time.isoformat()
