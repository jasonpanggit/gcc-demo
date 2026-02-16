"""SRE Interaction Handler - Manages user interactions for parameter discovery.

This module provides utilities for:
1. Detecting when user input is needed (ambiguous selections)
2. Discovering available resources (VMs, resource groups, workspaces)
3. Presenting options to users in a clear format
4. Validating and processing user selections
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from app.agentic.eol.utils.logger import get_logger
    from app.agentic.eol.utils.sre_response_formatter import (
        SREResponseFormatter,
        format_resource_selection,
    )
except ModuleNotFoundError:
    from utils.logger import get_logger
    from utils.sre_response_formatter import (
        SREResponseFormatter,
        format_resource_selection,
    )


logger = get_logger(__name__)


class SREInteractionHandler:
    """Handles user interactions for SRE operations."""

    # Required parameters for different tool types
    TOOL_REQUIRED_PARAMS = {
        "check_resource_health": ["resource_id"],
        "check_container_app_health": ["container_app_name", "resource_group"],
        "check_aks_cluster_health": ["cluster_name", "resource_group"],
        "get_diagnostic_logs": ["resource_id"],
        "get_performance_metrics": ["resource_id"],
        "triage_incident": ["incident_id", "resource_ids"],
        "plan_remediation": ["resource_id"],
        "execute_safe_restart": ["resource_id"],
        "scale_resource": ["resource_id", "new_capacity"],
        "get_cost_analysis": ["subscription_id"],
        "identify_orphaned_resources": ["subscription_id"],
    }

    def __init__(self, azure_cli_executor: Optional[Any] = None):
        """Initialize interaction handler.

        Args:
            azure_cli_executor: Optional Azure CLI executor function
        """
        self.formatter = SREResponseFormatter()
        self.azure_cli_executor = azure_cli_executor

    def check_required_params(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Check if all required parameters are present for a tool.

        Args:
            tool_name: Name of the tool
            params: Parameters provided

        Returns:
            None if all params present, otherwise a dict with missing params info
        """
        required = self.TOOL_REQUIRED_PARAMS.get(tool_name)
        if not required:
            return None  # No required params defined

        missing = []
        for param in required:
            value = params.get(param)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(param)

        if not missing:
            return None  # All params present

        return {
            "status": "needs_user_input",
            "missing_params": missing,
            "tool_name": tool_name,
            "message": self._format_missing_params_message(tool_name, missing),
        }

    def _format_missing_params_message(
        self,
        tool_name: str,
        missing_params: List[str]
    ) -> str:
        """Format a user-friendly message about missing parameters.

        Args:
            tool_name: Name of the tool
            missing_params: List of missing parameter names

        Returns:
            HTML-formatted message
        """
        param_labels = {
            "resource_id": "Resource ID",
            "container_app_name": "Container App name",
            "resource_group": "Resource Group name",
            "cluster_name": "AKS Cluster name",
            "incident_id": "Incident ID",
            "resource_ids": "Affected Resource IDs",
            "subscription_id": "Subscription ID",
            "new_capacity": "New capacity/scale",
        }

        html_parts = [
            "<p>To complete this operation, I need some additional information:</p>",
            "<ul>",
        ]

        for param in missing_params:
            label = param_labels.get(param, param.replace("_", " ").title())
            html_parts.append(f"<li><strong>{label}</strong></li>")

        html_parts.append("</ul>")

        # Add helpful suggestions based on parameter types
        if "resource_group" in missing_params:
            html_parts.append(
                "<p>💡 I can look up available resource groups for you. "
                "Just say <em>'list resource groups'</em></p>"
            )

        if "resource_id" in missing_params:
            html_parts.append(
                "<p>💡 I can search for resources. Try: "
                "<em>'find container apps in [resource-group]'</em></p>"
            )

        return "\n".join(html_parts)

    async def discover_resource_groups(
        self,
        subscription_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover available resource groups.

        Args:
            subscription_id: Optional subscription ID to filter by

        Returns:
            List of resource group dictionaries
        """
        if not self.azure_cli_executor:
            logger.warning("Azure CLI executor not available")
            return []

        try:
            command = (
                'az group list '
                '--query "[].{name:name, location:location, '
                'provisioning_state:properties.provisioningState}" '
                '-o json'
            )

            if subscription_id:
                command = f'az account set --subscription {subscription_id} && {command}'

            result = await self.azure_cli_executor(command)

            if isinstance(result, dict):
                output = result.get("output") or result.get("result", [])
                if isinstance(output, str):
                    import json
                    try:
                        return json.loads(output)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse resource groups JSON")
                        return []
                return output if isinstance(output, list) else []

            return []

        except Exception as exc:
            logger.error(f"Failed to discover resource groups: {exc}")
            return []

    async def discover_container_apps(
        self,
        resource_group: Optional[str] = None,
        name_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover available container apps.

        Args:
            resource_group: Optional resource group to filter by
            name_filter: Optional name filter (partial match)

        Returns:
            List of container app dictionaries
        """
        if not self.azure_cli_executor:
            logger.warning("Azure CLI executor not available")
            return []

        try:
            command = (
                'az containerapp list '
                '--query "[].{name:name, resource_group:resourceGroup, '
                'location:location, provisioning_state:properties.provisioningState, '
                'fqdn:properties.configuration.ingress.fqdn, '
                'id:id}" '
                '-o json'
            )

            if resource_group:
                command = command.replace('list', f'list --resource-group {resource_group}')

            result = await self.azure_cli_executor(command)

            container_apps = []
            if isinstance(result, dict):
                output = result.get("output") or result.get("result", [])
                if isinstance(output, str):
                    import json
                    try:
                        container_apps = json.loads(output)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse container apps JSON")
                        return []
                elif isinstance(output, list):
                    container_apps = output

            # Apply name filter if provided
            if name_filter and container_apps:
                name_lower = name_filter.lower()
                container_apps = [
                    app for app in container_apps
                    if name_lower in app.get("name", "").lower()
                ]

            return container_apps

        except Exception as exc:
            logger.error(f"Failed to discover container apps: {exc}")
            return []

    async def discover_virtual_machines(
        self,
        resource_group: Optional[str] = None,
        name_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover available virtual machines.

        Args:
            resource_group: Optional resource group to filter by
            name_filter: Optional name filter (partial match)

        Returns:
            List of VM dictionaries
        """
        if not self.azure_cli_executor:
            logger.warning("Azure CLI executor not available")
            return []

        try:
            command_parts = ['az vm list']

            if resource_group:
                command_parts.append(f'--resource-group {resource_group}')

            command_parts.append(
                '--query "[].{name:name, resource_group:resourceGroup, '
                'location:location, vm_size:hardwareProfile.vmSize, '
                'status:provisioningState, id:id}" '
                '-o json'
            )

            command = ' '.join(command_parts)
            result = await self.azure_cli_executor(command)

            vms = []
            if isinstance(result, dict):
                output = result.get("output") or result.get("result", [])
                if isinstance(output, str):
                    import json
                    try:
                        vms = json.loads(output)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse VMs JSON")
                        return []
                elif isinstance(output, list):
                    vms = output

            # Apply name filter if provided
            if name_filter and vms:
                name_lower = name_filter.lower()
                vms = [
                    vm for vm in vms
                    if name_lower in vm.get("name", "").lower()
                ]

            return vms

        except Exception as exc:
            logger.error(f"Failed to discover VMs: {exc}")
            return []

    async def discover_log_analytics_workspaces(
        self,
        resource_group: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover available Log Analytics workspaces.

        Args:
            resource_group: Optional resource group to filter by

        Returns:
            List of workspace dictionaries
        """
        if not self.azure_cli_executor:
            logger.warning("Azure CLI executor not available")
            return []

        try:
            command_parts = ['az monitor log-analytics workspace list']

            if resource_group:
                command_parts.append(f'--resource-group {resource_group}')

            command_parts.append(
                '--query "[].{name:name, resource_group:resourceGroup, '
                'location:location, sku:sku.name, id:id}" '
                '-o json'
            )

            command = ' '.join(command_parts)
            result = await self.azure_cli_executor(command)

            workspaces = []
            if isinstance(result, dict):
                output = result.get("output") or result.get("result", [])
                if isinstance(output, str):
                    import json
                    try:
                        workspaces = json.loads(output)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse workspaces JSON")
                        return []
                elif isinstance(output, list):
                    workspaces = output

            return workspaces

        except Exception as exc:
            logger.error(f"Failed to discover workspaces: {exc}")
            return []

    def format_selection_prompt(
        self,
        resources: List[Dict[str, Any]],
        resource_type: str,
        action: str = "use"
    ) -> Dict[str, Any]:
        """Format a selection prompt for the user.

        Args:
            resources: List of resources to choose from
            resource_type: Type of resource (VM, Container App, etc.)
            action: Action to perform on the selected resource

        Returns:
            Dictionary with formatted prompt and metadata
        """
        return format_resource_selection(resources, resource_type, action)

    def parse_user_selection(
        self,
        user_input: str,
        options: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Parse user selection from input.

        Args:
            user_input: User's input (e.g., "1", "use #2", "the first one")
            options: List of available options

        Returns:
            Selected option dictionary or None if invalid
        """
        input_lower = user_input.lower().strip()

        # Try to extract a number
        import re
        numbers = re.findall(r'\d+', input_lower)

        if numbers:
            try:
                index = int(numbers[0])
                if 1 <= index <= len(options):
                    return options[index - 1]
            except (ValueError, IndexError):
                pass

        # Try keyword matching
        keywords_first = ["first", "1st", "top"]
        keywords_last = ["last", "bottom"]

        if any(kw in input_lower for kw in keywords_first) and options:
            return options[0]

        if any(kw in input_lower for kw in keywords_last) and options:
            return options[-1]

        # Try name matching
        for option in options:
            name = option.get("name", "").lower()
            if name and name in input_lower:
                return option

        return None

    def needs_resource_discovery(
        self,
        tool_name: str,
        params: Dict[str, Any],
        query: str
    ) -> Optional[str]:
        """Determine if resource discovery is needed based on the query.

        Args:
            tool_name: Name of the tool being called
            params: Current parameters
            query: User's original query

        Returns:
            Resource type to discover (e.g., "container_app", "vm") or None
        """
        query_lower = query.lower()

        # Check for ambiguous references in the query
        ambiguous_indicators = {
            "container_app": [
                "container app", "containerapp",
                "app service", "webapp"
            ],
            "vm": [
                "virtual machine", "vm ", "vms"
            ],
            "resource_group": [
                "resource group", "rg "
            ],
            "workspace": [
                "log analytics", "workspace"
            ],
        }

        # If resource_id is missing and query has ambiguous references
        if not params.get("resource_id") and not params.get("container_app_name"):
            for resource_type, indicators in ambiguous_indicators.items():
                if any(ind in query_lower for ind in indicators):
                    # Check if there's a specific name mentioned
                    # If not, we need discovery
                    if not self._has_specific_resource_name(query, resource_type):
                        return resource_type

        return None

    def _has_specific_resource_name(self, query: str, resource_type: str) -> bool:
        """Check if the query contains a specific resource name.

        Args:
            query: User's query
            resource_type: Type of resource

        Returns:
            True if a specific name is mentioned
        """
        # This is a heuristic - look for patterns like:
        # "check health of my-app"
        # "restart vm-production"
        # etc.

        import re

        # Look for quoted names
        if re.search(r'["\'][\w-]+["\']', query):
            return True

        # Look for hyphenated or underscored names (common in Azure)
        if re.search(r'\b[\w]+-[\w-]+\b', query):
            return True

        # For now, assume if query is long and specific, it has a name
        query_lower = query.lower()
        specific_phrases = [
            "named", "called", "for resource", "specific",
            "the app", "the vm", "my app", "my vm"
        ]

        return any(phrase in query_lower for phrase in specific_phrases)


# Singleton instance
_interaction_handler = None


def get_interaction_handler(
    azure_cli_executor: Optional[Any] = None
) -> SREInteractionHandler:
    """Get the global interaction handler instance.

    Args:
        azure_cli_executor: Optional Azure CLI executor

    Returns:
        SREInteractionHandler instance
    """
    global _interaction_handler

    if _interaction_handler is None:
        _interaction_handler = SREInteractionHandler(azure_cli_executor)
    elif azure_cli_executor is not None:
        _interaction_handler.azure_cli_executor = azure_cli_executor

    return _interaction_handler
