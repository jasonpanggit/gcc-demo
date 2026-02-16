"""SRE Response Formatter - Converts raw tool outputs to user-friendly messages.

This module provides utilities for:
1. Converting JSON responses to human-readable messages
2. Formatting structured data (tables, lists, summaries)
3. Adding contextual explanations and next-step suggestions
4. Handling selection prompts for ambiguous resources
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger


logger = get_logger(__name__)


class SREResponseFormatter:
    """Formats SRE agent responses into user-friendly HTML messages."""

    # Emoji mappings for visual feedback
    STATUS_ICONS = {
        "healthy": "✅",
        "available": "✅",
        "success": "✅",
        "unhealthy": "⚠️",
        "degraded": "⚠️",
        "warning": "⚠️",
        "error": "❌",
        "critical": "🔴",
        "unknown": "❓",
        "info": "ℹ️",
    }

    def format_resource_list(
        self,
        resources: List[Dict[str, Any]],
        resource_type: str,
        context: Optional[str] = None
    ) -> str:
        """Format a list of resources as an HTML table for user selection.

        Args:
            resources: List of resource dictionaries
            resource_type: Type of resource (e.g., "Virtual Machine", "Container App")
            context: Optional context message to display before the table

        Returns:
            HTML-formatted table with resources
        """
        if not resources:
            return f"<p>No {resource_type}s found.</p>"

        count = len(resources)
        plural = resource_type if count == 1 else f"{resource_type}s"

        html_parts = []

        # Add context message if provided
        if context:
            html_parts.append(f"<p>{html.escape(context)}</p>")
        else:
            html_parts.append(
                f"<p>Found <strong>{count}</strong> {plural}. "
                f"Please select one from the list below:</p>"
            )

        # Build table based on resource type
        html_parts.append(self._build_resource_table(resources, resource_type))

        return "\n".join(html_parts)

    def _build_resource_table(
        self,
        resources: List[Dict[str, Any]],
        resource_type: str
    ) -> str:
        """Build an HTML table for resources with relevant columns.

        Args:
            resources: List of resource dictionaries
            resource_type: Type of resource

        Returns:
            HTML table string
        """
        # Determine columns based on resource type
        columns = self._get_columns_for_resource_type(resource_type)

        table_parts = [
            '<table class="table table-sm table-striped">',
            '<thead>',
            '<tr>',
        ]

        # Add column headers
        for col in columns:
            table_parts.append(f'<th>{html.escape(col["label"])}</th>')

        table_parts.extend(['</tr>', '</thead>', '<tbody>'])

        # Add rows
        for idx, resource in enumerate(resources, 1):
            table_parts.append('<tr>')

            for col in columns:
                field = col["field"]
                value = self._extract_field_value(resource, field)

                # Format value based on column type
                formatted_value = self._format_cell_value(
                    value,
                    col.get("type", "text")
                )

                table_parts.append(f'<td>{formatted_value}</td>')

            table_parts.append('</tr>')

        table_parts.extend(['</tbody>', '</table>'])

        return "\n".join(table_parts)

    def _get_columns_for_resource_type(self, resource_type: str) -> List[Dict[str, Any]]:
        """Get appropriate columns for a resource type.

        Args:
            resource_type: Type of resource

        Returns:
            List of column definitions
        """
        # Default columns for all resources
        default_columns = [
            {"label": "#", "field": "_index", "type": "index"},
            {"label": "Name", "field": "name", "type": "text"},
            {"label": "Location", "field": "location", "type": "text"},
            {"label": "Resource Group", "field": "resource_group", "type": "text"},
        ]

        # Resource-specific column mappings
        type_specific = {
            "Virtual Machine": [
                {"label": "#", "field": "_index", "type": "index"},
                {"label": "Name", "field": "name", "type": "text"},
                {"label": "Status", "field": "status", "type": "status"},
                {"label": "Location", "field": "location", "type": "text"},
                {"label": "Resource Group", "field": "resource_group", "type": "text"},
                {"label": "Size", "field": "vm_size", "type": "text"},
            ],
            "Container App": [
                {"label": "#", "field": "_index", "type": "index"},
                {"label": "Name", "field": "name", "type": "text"},
                {"label": "Status", "field": "provisioning_state", "type": "status"},
                {"label": "Location", "field": "location", "type": "text"},
                {"label": "Resource Group", "field": "resource_group", "type": "text"},
                {"label": "FQDN", "field": "fqdn", "type": "text"},
            ],
            "Resource Group": [
                {"label": "#", "field": "_index", "type": "index"},
                {"label": "Name", "field": "name", "type": "text"},
                {"label": "Location", "field": "location", "type": "text"},
                {"label": "Status", "field": "provisioning_state", "type": "status"},
            ],
            "Log Analytics Workspace": [
                {"label": "#", "field": "_index", "type": "index"},
                {"label": "Name", "field": "name", "type": "text"},
                {"label": "Resource Group", "field": "resource_group", "type": "text"},
                {"label": "Location", "field": "location", "type": "text"},
                {"label": "SKU", "field": "sku", "type": "text"},
            ],
        }

        return type_specific.get(resource_type, default_columns)

    def _extract_field_value(
        self,
        resource: Dict[str, Any],
        field: str
    ) -> Any:
        """Extract a field value from a resource, handling nested fields.

        Args:
            resource: Resource dictionary
            field: Field name (supports dot notation)

        Returns:
            Field value or None
        """
        if field == "_index":
            return resource.get("_index", "")

        # Handle dot notation (e.g., "properties.provisioningState")
        parts = field.split(".")
        value = resource

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        return value

    def _format_cell_value(self, value: Any, cell_type: str) -> str:
        """Format a cell value based on its type.

        Args:
            value: Cell value
            cell_type: Type of cell (text, status, date, etc.)

        Returns:
            HTML-formatted cell value
        """
        if value is None or value == "":
            return '<span class="text-muted">—</span>'

        if cell_type == "index":
            return f'<strong>{value}</strong>'

        if cell_type == "status":
            status_str = str(value).lower()
            icon = self.STATUS_ICONS.get(status_str, "")
            return f'{icon} {html.escape(str(value))}'

        if cell_type == "date":
            try:
                if isinstance(value, str):
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return html.escape(dt.strftime("%Y-%m-%d %H:%M"))
            except Exception:
                pass

        return html.escape(str(value))

    def format_health_status(
        self,
        resource_name: str,
        health_data: Dict[str, Any]
    ) -> str:
        """Format health check results into a user-friendly message.

        Args:
            resource_name: Name of the resource
            health_data: Health check data

        Returns:
            HTML-formatted health status message
        """
        availability = health_data.get("availability_state", "Unknown")
        reason = health_data.get("reason_type", "")
        summary = health_data.get("summary", "")

        icon = self.STATUS_ICONS.get(availability.lower(), "❓")

        html_parts = [
            f"<h4>{icon} Health Status: {html.escape(resource_name)}</h4>",
            f"<p><strong>Status:</strong> {html.escape(availability)}</p>"
        ]

        if reason:
            html_parts.append(f"<p><strong>Reason:</strong> {html.escape(reason)}</p>")

        if summary:
            html_parts.append(f"<p><strong>Details:</strong> {html.escape(summary)}</p>")

        # Add next steps
        if availability.lower() in ["unhealthy", "degraded"]:
            html_parts.append(
                "<p><strong>Next Steps:</strong></p>"
                "<ul>"
                "<li>Check diagnostic logs for errors</li>"
                "<li>Review recent configuration changes</li>"
                "<li>Verify resource dependencies are healthy</li>"
                "</ul>"
            )

        return "\n".join(html_parts)

    def format_cost_summary(
        self,
        cost_data: Dict[str, Any]
    ) -> str:
        """Format cost analysis results into a user-friendly message.

        Args:
            cost_data: Cost analysis data

        Returns:
            HTML-formatted cost summary
        """
        total_cost = cost_data.get("total_cost", 0.0)
        currency = cost_data.get("currency", "USD")
        time_period = cost_data.get("time_period", "current month")

        html_parts = [
            "<h4>💰 Cost Analysis Summary</h4>",
            f"<p><strong>Total Spending ({time_period}):</strong> "
            f"{currency} ${total_cost:,.2f}</p>"
        ]

        # Breakdown by service
        breakdown = cost_data.get("breakdown", [])
        if breakdown:
            html_parts.append("<h5>Top Services:</h5>")
            html_parts.append('<table class="table table-sm">')
            html_parts.append(
                '<thead><tr><th>Service</th><th>Cost</th><th>%</th></tr></thead>'
            )
            html_parts.append('<tbody>')

            for item in breakdown[:5]:  # Top 5
                service = item.get("service", "Unknown")
                cost = item.get("cost", 0.0)
                percentage = item.get("percentage", 0.0)
                html_parts.append(
                    f'<tr><td>{html.escape(service)}</td>'
                    f'<td>${cost:,.2f}</td><td>{percentage:.1f}%</td></tr>'
                )

            html_parts.append('</tbody></table>')

        # Savings recommendations
        savings = cost_data.get("potential_savings", 0.0)
        if savings > 0:
            html_parts.append(
                f"<p>✨ <strong>Potential Savings:</strong> ${savings:,.2f}</p>"
                "<p><strong>Recommendations:</strong></p>"
                "<ul>"
                "<li>Review orphaned resources (unattached disks, idle IPs)</li>"
                "<li>Right-size underutilized resources</li>"
                "<li>Consider reserved instances for stable workloads</li>"
                "</ul>"
            )

        return "\n".join(html_parts)

    def format_performance_metrics(
        self,
        resource_name: str,
        metrics: Dict[str, Any]
    ) -> str:
        """Format performance metrics into a user-friendly message.

        Args:
            resource_name: Name of the resource
            metrics: Performance metrics data

        Returns:
            HTML-formatted performance summary
        """
        html_parts = [
            f"<h4>📊 Performance Metrics: {html.escape(resource_name)}</h4>",
        ]

        # CPU metrics
        cpu = metrics.get("cpu_percent")
        if cpu is not None:
            icon = "⚠️" if cpu > 80 else "✅" if cpu < 60 else "ℹ️"
            html_parts.append(f"<p>{icon} <strong>CPU:</strong> {cpu:.1f}%</p>")

        # Memory metrics
        memory = metrics.get("memory_percent")
        if memory is not None:
            icon = "⚠️" if memory > 80 else "✅" if memory < 60 else "ℹ️"
            html_parts.append(f"<p>{icon} <strong>Memory:</strong> {memory:.1f}%</p>")

        # Bottlenecks
        bottlenecks = metrics.get("bottlenecks", [])
        if bottlenecks:
            html_parts.append("<p><strong>⚠️ Bottlenecks Detected:</strong></p><ul>")
            for bottleneck in bottlenecks:
                html_parts.append(f"<li>{html.escape(bottleneck)}</li>")
            html_parts.append("</ul>")

        # Recommendations
        recommendations = metrics.get("recommendations", [])
        if recommendations:
            html_parts.append("<p><strong>💡 Recommendations:</strong></p><ul>")
            for rec in recommendations:
                html_parts.append(f"<li>{html.escape(rec)}</li>")
            html_parts.append("</ul>")
        elif not bottlenecks:
            html_parts.append(
                "<p>✅ Performance looks good! No immediate issues detected.</p>"
            )

        return "\n".join(html_parts)

    def format_incident_summary(
        self,
        incident_id: str,
        incident_data: Dict[str, Any]
    ) -> str:
        """Format incident triage results into a user-friendly message.

        Args:
            incident_id: Incident identifier
            incident_data: Incident data

        Returns:
            HTML-formatted incident summary
        """
        severity = incident_data.get("severity", "medium").upper()
        status = incident_data.get("status", "active")
        affected_resources = incident_data.get("affected_resources", [])

        severity_icons = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }
        icon = severity_icons.get(severity, "ℹ️")

        html_parts = [
            f"<h4>{icon} Incident Report: {html.escape(incident_id)}</h4>",
            f"<p><strong>Severity:</strong> {severity}</p>",
            f"<p><strong>Status:</strong> {html.escape(status)}</p>",
        ]

        # Affected resources
        if affected_resources:
            html_parts.append(
                f"<p><strong>Affected Resources ({len(affected_resources)}):</strong></p>"
            )
            html_parts.append("<ul>")
            for resource in affected_resources[:5]:  # Show first 5
                html_parts.append(f"<li>{html.escape(resource)}</li>")
            if len(affected_resources) > 5:
                html_parts.append(
                    f"<li><em>...and {len(affected_resources) - 5} more</em></li>"
                )
            html_parts.append("</ul>")

        # Root cause
        root_cause = incident_data.get("root_cause")
        if root_cause:
            html_parts.append(
                f"<p><strong>Root Cause:</strong> {html.escape(root_cause)}</p>"
            )

        # Remediation steps
        remediation_steps = incident_data.get("remediation_steps", [])
        if remediation_steps:
            html_parts.append("<p><strong>Remediation Steps:</strong></p><ol>")
            for step in remediation_steps:
                html_parts.append(f"<li>{html.escape(step)}</li>")
            html_parts.append("</ol>")

        return "\n".join(html_parts)

    def format_success_message(
        self,
        action: str,
        details: Optional[str] = None,
        next_steps: Optional[List[str]] = None
    ) -> str:
        """Format a success message with optional details and next steps.

        Args:
            action: Description of the successful action
            details: Optional details about the action
            next_steps: Optional list of suggested next steps

        Returns:
            HTML-formatted success message
        """
        html_parts = [
            f"<p>✅ <strong>Success!</strong> {html.escape(action)}</p>"
        ]

        if details:
            html_parts.append(f"<p>{html.escape(details)}</p>")

        if next_steps:
            html_parts.append("<p><strong>Next Steps:</strong></p><ul>")
            for step in next_steps:
                html_parts.append(f"<li>{html.escape(step)}</li>")
            html_parts.append("</ul>")

        return "\n".join(html_parts)

    def format_error_message(
        self,
        error: str,
        suggestions: Optional[List[str]] = None
    ) -> str:
        """Format an error message with optional suggestions.

        Args:
            error: Error description
            suggestions: Optional list of suggestions to resolve the error

        Returns:
            HTML-formatted error message
        """
        html_parts = [
            f"<p>❌ <strong>Error:</strong> {html.escape(error)}</p>"
        ]

        if suggestions:
            html_parts.append(
                "<p><strong>Try the following:</strong></p><ul>"
            )
            for suggestion in suggestions:
                html_parts.append(f"<li>{html.escape(suggestion)}</li>")
            html_parts.append("</ul>")

        return "\n".join(html_parts)

    def format_selection_prompt(
        self,
        resources: List[Dict[str, Any]],
        resource_type: str,
        action: str
    ) -> Dict[str, Any]:
        """Format a selection prompt for user interaction.

        Args:
            resources: List of resources to choose from
            resource_type: Type of resource
            action: Action to perform on selected resource

        Returns:
            Dictionary with formatted message and selection metadata
        """
        # Add index to resources for selection
        indexed_resources = []
        for idx, resource in enumerate(resources, 1):
            resource_copy = resource.copy()
            resource_copy["_index"] = idx
            indexed_resources.append(resource_copy)

        message = self.format_resource_list(
            indexed_resources,
            resource_type,
            context=f"Found {len(resources)} {resource_type}(s). "
                    f"Which one would you like to {action}?"
        )

        return {
            "message": message,
            "requires_selection": True,
            "selection_type": "resource",
            "resource_type": resource_type,
            "action": action,
            "options": [
                {
                    "index": idx,
                    "name": r.get("name", f"{resource_type} {idx}"),
                    "id": r.get("id", r.get("resource_id", "")),
                }
                for idx, r in enumerate(indexed_resources, 1)
            ],
        }


# Global formatter instance
_formatter = SREResponseFormatter()


def format_resource_selection(
    resources: List[Dict[str, Any]],
    resource_type: str,
    action: str = "use"
) -> Dict[str, Any]:
    """Format a resource selection prompt.

    Args:
        resources: List of resources
        resource_type: Type of resource
        action: Action to perform

    Returns:
        Formatted selection prompt
    """
    return _formatter.format_selection_prompt(resources, resource_type, action)


def format_tool_result(
    tool_name: str,
    result: Dict[str, Any]
) -> str:
    """Format a tool result based on the tool type.

    Args:
        tool_name: Name of the tool
        result: Tool result data

    Returns:
        HTML-formatted message
    """
    # Health check tools
    if "health" in tool_name.lower():
        resource_name = result.get("resource_name", "Unknown Resource")
        health_data = result.get("health_status", result)
        return _formatter.format_health_status(resource_name, health_data)

    # Cost tools
    if "cost" in tool_name.lower():
        return _formatter.format_cost_summary(result)

    # Performance tools
    if "performance" in tool_name.lower() or "metrics" in tool_name.lower():
        resource_name = result.get("resource_name", "Unknown Resource")
        return _formatter.format_performance_metrics(resource_name, result)

    # Incident tools
    if "incident" in tool_name.lower() or "triage" in tool_name.lower():
        incident_id = result.get("incident_id", "Unknown Incident")
        return _formatter.format_incident_summary(incident_id, result)

    # Generic success message
    if result.get("status") == "success":
        action = result.get("message", "Operation completed successfully")
        details = result.get("details")
        return _formatter.format_success_message(action, details)

    # Generic error message
    if result.get("status") == "error":
        error = result.get("error", "An error occurred")
        suggestions = result.get("suggestions")
        return _formatter.format_error_message(error, suggestions)

    # Fallback: format as JSON in a code block
    import json
    json_str = json.dumps(result, indent=2)
    return f'<pre><code>{html.escape(json_str)}</code></pre>'
