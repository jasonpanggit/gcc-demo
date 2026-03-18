"""
CVE Alert Rule Manager

Manages CVE alert rules with in-memory persistence.
Provides CRUD operations for alert rule configuration.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from models.cve_alert_models import CVEAlertRule
from utils.logger import get_logger
from utils.config import config


class CVEAlertRuleManager:
    """
    Manages CVE alert rules with in-memory persistence.

    Partition Key: /rule_type
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger(__name__, config.app.log_level)

    async def create_rule(self, rule: CVEAlertRule) -> CVEAlertRule:
        """Create new alert rule."""
        # Check for duplicate name
        existing = await self.get_rule_by_name(rule.name)
        if existing:
            raise ValueError(f"Alert rule with name '{rule.name}' already exists")

        # Set timestamps
        now = datetime.now(timezone.utc).isoformat()
        rule.created_at = now
        rule.updated_at = now

        try:
            self._store[rule.id] = rule.to_dict()
            self.logger.info(f"Created alert rule: {rule.id} ({rule.name})")
            return rule
        except Exception as e:
            self.logger.error(f"Failed to create alert rule: {e}")
            raise

    async def get_rule(self, rule_id: str) -> Optional[CVEAlertRule]:
        """Fetch rule by ID"""
        try:
            doc = self._store.get(rule_id)
            if not doc:
                return None
            return CVEAlertRule.from_dict(doc)
        except Exception as e:
            self.logger.error(f"Failed to get rule {rule_id}: {e}")
            return None

    async def get_rule_by_name(self, name: str) -> Optional[CVEAlertRule]:
        """Fetch rule by name (for duplicate check)"""
        try:
            for doc in self._store.values():
                if doc.get("name") == name:
                    return CVEAlertRule.from_dict(doc)
            return None
        except Exception as e:
            self.logger.error(f"Failed to get rule by name '{name}': {e}")
            return None

    async def list_rules(self, enabled_only: bool = False) -> List[CVEAlertRule]:
        """List all alert rules."""
        try:
            items = list(self._store.values())
            if enabled_only:
                items = [i for i in items if i.get("enabled") is True]
            items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return [CVEAlertRule.from_dict(item) for item in items]
        except Exception as e:
            self.logger.error(f"Failed to list rules: {e}")
            return []

    async def update_rule(self, rule: CVEAlertRule) -> CVEAlertRule:
        """Update existing alert rule."""
        existing = await self.get_rule(rule.id)
        if not existing:
            raise ValueError(f"Alert rule {rule.id} not found")

        rule.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            self._store[rule.id] = rule.to_dict()
            self.logger.info(f"Updated alert rule: {rule.id} ({rule.name})")
            return rule
        except Exception as e:
            self.logger.error(f"Failed to update alert rule: {e}")
            raise

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete alert rule by ID."""
        try:
            rule = await self.get_rule(rule_id)
            if not rule:
                self.logger.warning(f"Rule {rule_id} not found for deletion")
                return False

            del self._store[rule_id]
            self.logger.info(f"Deleted alert rule: {rule_id} ({rule.name})")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete rule {rule_id}: {e}")
            return False

    async def update_last_triggered(self, rule_id: str, timestamp: str):
        """Update last_triggered timestamp after alert sent"""
        rule = await self.get_rule(rule_id)
        if rule:
            rule.last_triggered = timestamp
            await self.update_rule(rule)


# Singleton factory
_alert_rule_manager: Optional[CVEAlertRuleManager] = None


def get_cve_alert_rule_manager() -> CVEAlertRuleManager:
    """Singleton factory for alert rule manager"""
    global _alert_rule_manager
    if _alert_rule_manager is None:
        _alert_rule_manager = CVEAlertRuleManager()
    return _alert_rule_manager
