"""
CVE Alert Rule Manager

Manages CVE alert rules with Cosmos DB persistence.
Provides CRUD operations for alert rule configuration.
"""

from typing import Optional, List
from datetime import datetime, timezone

from models.cve_alert_models import CVEAlertRule
from utils.cosmos_cache.base_cosmos import get_cosmos_client
from utils.logger import get_logger
from utils.config import config


class CVEAlertRuleManager:
    """
    Manages CVE alert rules with Cosmos DB persistence.

    Container: cve_alert_rules
    Partition Key: /rule_type
    """

    def __init__(self):
        self.cosmos_client = get_cosmos_client()
        self.container = self.cosmos_client.get_container_client(
            database="eol_db",
            container="cve_alert_rules"
        )
        self.logger = get_logger(__name__, config.app.log_level)

    async def create_rule(self, rule: CVEAlertRule) -> CVEAlertRule:
        """
        Create new alert rule in Cosmos DB.

        Args:
            rule: CVEAlertRule to persist

        Returns:
            Created rule with ID

        Raises:
            ValueError if rule with same name exists
        """
        # Check for duplicate name
        existing = await self.get_rule_by_name(rule.name)
        if existing:
            raise ValueError(f"Alert rule with name '{rule.name}' already exists")

        # Set timestamps
        now = datetime.now(timezone.utc).isoformat()
        rule.created_at = now
        rule.updated_at = now

        # Persist to Cosmos
        try:
            await self.container.create_item(body=rule.to_dict())
            self.logger.info(f"Created alert rule: {rule.id} ({rule.name})")
            return rule
        except Exception as e:
            self.logger.error(f"Failed to create alert rule: {e}")
            raise

    async def get_rule(self, rule_id: str) -> Optional[CVEAlertRule]:
        """Fetch rule by ID"""
        try:
            query = "SELECT * FROM c WHERE c.id = @rule_id"
            params = [{"name": "@rule_id", "value": rule_id}]

            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))

            if not items:
                return None

            return CVEAlertRule.from_dict(items[0])
        except Exception as e:
            self.logger.error(f"Failed to get rule {rule_id}: {e}")
            return None

    async def get_rule_by_name(self, name: str) -> Optional[CVEAlertRule]:
        """Fetch rule by name (for duplicate check)"""
        try:
            query = "SELECT * FROM c WHERE c.name = @name"
            params = [{"name": "@name", "value": name}]

            items = list(self.container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))

            if not items:
                return None

            return CVEAlertRule.from_dict(items[0])
        except Exception as e:
            self.logger.error(f"Failed to get rule by name '{name}': {e}")
            return None

    async def list_rules(self, enabled_only: bool = False) -> List[CVEAlertRule]:
        """
        List all alert rules.

        Args:
            enabled_only: If True, only return enabled rules

        Returns:
            List of alert rules sorted by created_at DESC
        """
        try:
            if enabled_only:
                query = "SELECT * FROM c WHERE c.enabled = true ORDER BY c.created_at DESC"
            else:
                query = "SELECT * FROM c ORDER BY c.created_at DESC"

            items = list(self.container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))

            return [CVEAlertRule.from_dict(item) for item in items]
        except Exception as e:
            self.logger.error(f"Failed to list rules: {e}")
            return []

    async def update_rule(self, rule: CVEAlertRule) -> CVEAlertRule:
        """
        Update existing alert rule.

        Args:
            rule: Updated rule (must have existing ID)

        Returns:
            Updated rule

        Raises:
            ValueError if rule doesn't exist
        """
        # Verify rule exists
        existing = await self.get_rule(rule.id)
        if not existing:
            raise ValueError(f"Alert rule {rule.id} not found")

        # Update timestamp
        rule.updated_at = datetime.now(timezone.utc).isoformat()

        # Persist to Cosmos
        try:
            await self.container.replace_item(
                item=rule.id,
                body=rule.to_dict()
            )
            self.logger.info(f"Updated alert rule: {rule.id} ({rule.name})")
            return rule
        except Exception as e:
            self.logger.error(f"Failed to update alert rule: {e}")
            raise

    async def delete_rule(self, rule_id: str) -> bool:
        """
        Delete alert rule by ID.

        Args:
            rule_id: Rule to delete

        Returns:
            True if deleted, False if not found
        """
        try:
            # Get rule to determine partition key
            rule = await self.get_rule(rule_id)
            if not rule:
                self.logger.warning(f"Rule {rule_id} not found for deletion")
                return False

            # Delete from Cosmos
            await self.container.delete_item(
                item=rule_id,
                partition_key=rule.rule_type
            )
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
