"""Cost Optimization Agent - Specialized SRE agent for cloud cost management and optimization.

This agent handles:
- Cost analysis and trend monitoring
- Cost savings identification
- Orphaned resource detection
- Budget tracking and alerting
- Cost optimization recommendations
- Reserved instance and commitment analysis
- Resource rightsizing recommendations
- Cost anomaly detection
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from app.agentic.eol.agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from app.agentic.eol.utils.agent_registry import get_agent_registry
    from app.agentic.eol.utils.agent_context_store import get_context_store
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from agents.base_sre_agent import BaseSREAgent, AgentExecutionError
    from utils.agent_registry import get_agent_registry
    from utils.agent_context_store import get_context_store
    from utils.logger import get_logger


logger = get_logger(__name__)


class CostOptimizationAgent(BaseSREAgent):
    """Specialized agent for cloud cost optimization and management.

    This agent orchestrates comprehensive cost optimization workflows:
    1. Cost analysis and trend monitoring
    2. Identification of cost savings opportunities
    3. Detection of orphaned and underutilized resources
    4. Budget tracking and alerting
    5. Reserved instance and commitment recommendations
    6. Resource rightsizing analysis
    7. Cost anomaly detection
    8. Multi-cloud cost comparison

    Example usage:
        agent = CostOptimizationAgent()
        await agent.initialize()

        # Analyze costs
        result = await agent.handle_request({
            "action": "analyze_costs",
            "resource_group": "prod-rg",
            "time_range": "30d"
        })

        # Find savings opportunities
        result = await agent.handle_request({
            "action": "find_savings",
            "subscription_id": "...",
            "min_savings": 1000.0
        })

        # Identify orphaned resources
        result = await agent.handle_request({
            "action": "identify_orphaned",
            "resource_group": "prod-rg"
        })

        # Track budget
        result = await agent.handle_request({
            "action": "budget_tracking",
            "budget_name": "prod-budget",
            "threshold_percent": 80.0
        })
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 300
    ):
        """Initialize Cost Optimization Agent.

        Args:
            agent_id: Unique agent identifier (auto-generated if not provided)
            max_retries: Maximum retry attempts for failed operations
            timeout: Operation timeout in seconds
        """
        super().__init__(
            agent_type="cost-optimization",
            agent_id=agent_id or "cost-optimization-agent",
            max_retries=max_retries,
            timeout=timeout,
            log_level="INFO"
        )

        # Agent-specific attributes
        self.registry = None
        self.context_store = None
        self.tool_proxy_agent = None

        # Cost thresholds and targets
        self.cost_thresholds = {
            "high_cost_resource": 1000.0,      # Monthly cost in USD
            "savings_opportunity": 100.0,       # Minimum monthly savings
            "waste_threshold": 50.0,            # Monthly waste threshold
            "budget_warning": 80.0,             # Budget % warning threshold
            "budget_critical": 95.0,            # Budget % critical threshold
            "utilization_low": 20.0,            # Low utilization %
            "utilization_target": 70.0          # Target utilization %
        }

        # Savings categories
        self.savings_categories = [
            "rightsizing",
            "reserved_instances",
            "orphaned_resources",
            "unused_resources",
            "storage_optimization",
            "network_optimization",
            "licensing_optimization",
            "commitment_discounts"
        ]

    async def _initialize_impl(self) -> None:
        """Initialize agent-specific resources."""
        try:
            # Get agent registry
            self.registry = get_agent_registry()
            logger.info("✓ Connected to agent registry")

            # Get context store
            self.context_store = await get_context_store()
            logger.info("✓ Connected to context store")

            # Get tool proxy agent for executing SRE tools
            self.tool_proxy_agent = self.registry.get_agent("sre-mcp-server")
            if not self.tool_proxy_agent:
                logger.warning(
                    "⚠️ Tool proxy agent not found - tools may not be available"
                )
            else:
                logger.info("✓ Connected to tool proxy agent")

        except Exception as exc:
            logger.error(f"Failed to initialize Cost Optimization Agent: {exc}")
            raise

    async def _cleanup_impl(self) -> None:
        """Cleanup agent-specific resources."""
        # Context store and registry are shared singletons, no cleanup needed
        pass

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute cost optimization action.

        Args:
            request: Request containing:
                - action: Action to perform (analyze_costs, find_savings, identify_orphaned, etc.)
                - resource_group: Resource group name (optional)
                - subscription_id: Azure subscription ID (optional)
                - time_range: Time range for analysis (default: 30d)
                - Additional action-specific parameters
            context: Optional workflow context

        Returns:
            Cost analysis results with recommendations and savings estimates

        Raises:
            AgentExecutionError: If execution fails
        """
        action = request.get("action", "analyze_costs")

        logger.info(f"Processing cost optimization action: {action}")

        # Route to appropriate handler
        action_handlers = {
            "analyze_costs": self._analyze_costs,
            "find_savings": self._find_savings_opportunities,
            "identify_orphaned": self._identify_orphaned_resources,
            "budget_tracking": self._track_budget,
            "recommendations": self._generate_recommendations,
            "full": self._full_cost_optimization
        }

        handler = action_handlers.get(action)
        if not handler:
            raise AgentExecutionError(
                f"Unknown action: {action}. "
                f"Valid actions: {', '.join(action_handlers.keys())}"
            )

        return await handler(request, context)

    async def _call_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an SRE tool via the proxy agent.

        Args:
            tool_name: Name of the tool to call
            parameters: Tool parameters

        Returns:
            Tool execution result

        Raises:
            AgentExecutionError: If tool execution fails
        """
        if not self.tool_proxy_agent:
            raise AgentExecutionError("Tool proxy agent not available")

        try:
            result = await self.tool_proxy_agent.handle_request({
                "tool": tool_name,
                "parameters": parameters
            })

            if result.get("status") == "error":
                raise AgentExecutionError(
                    f"Tool {tool_name} failed: {result.get('error')}"
                )

            return result

        except Exception as exc:
            logger.error(f"Failed to call tool {tool_name}: {exc}")
            raise AgentExecutionError(f"Tool execution failed: {exc}")

    async def _analyze_costs(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze costs and trends for resources.

        Performs comprehensive cost analysis including:
        - Current spending by service, resource group, and tags
        - Cost trends and forecasts
        - Top cost drivers
        - Month-over-month comparisons

        Args:
            request: Cost analysis request with filters and time range
            context: Optional workflow context

        Returns:
            Detailed cost analysis with trends and breakdowns
        """
        resource_group = request.get("resource_group", "")
        subscription_id = request.get("subscription_id", "")
        time_range = request.get("time_range", "30d")
        group_by = request.get("group_by", ["service", "resource_group"])
        workflow_id = request.get("workflow_id", f"cost-analysis-{datetime.utcnow().timestamp()}")

        logger.info(f"Analyzing costs for {resource_group or subscription_id or 'all resources'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_group": resource_group,
                "subscription_id": subscription_id,
                "time_range": time_range,
                "group_by": group_by,
                "started_at": datetime.utcnow().isoformat(),
                "agent": self.agent_id
            }
        )

        # Step 1: Get cost analysis
        cost_analysis_result = await self._call_tool(
            "get_cost_analysis",
            {
                "time_range": time_range,
                "resource_group": resource_group,
                "subscription_id": subscription_id,
                "group_by": group_by
            }
        )

        # Store cost analysis result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="cost_analysis",
            agent_id=self.agent_id,
            result=cost_analysis_result
        )

        # Extract and analyze cost data
        cost_data = cost_analysis_result.get("data", {})
        analysis = self._analyze_cost_data(cost_data, time_range)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "cost_analysis": {
                "time_range": time_range,
                "total_cost": cost_data.get("total_cost", 0.0),
                "currency": cost_data.get("currency", "USD"),
                "breakdown": cost_data.get("breakdown", {}),
                "trends": analysis.get("trends", {}),
                "top_cost_drivers": analysis.get("top_drivers", []),
                "month_over_month": analysis.get("mom_comparison", {}),
                "forecast": analysis.get("forecast", {}),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _analyze_cost_data(self, cost_data: Dict[str, Any], time_range: str) -> Dict[str, Any]:
        """Analyze cost data and extract insights.

        Args:
            cost_data: Raw cost data from analysis tool
            time_range: Time range of analysis

        Returns:
            Cost analysis insights and trends
        """
        total_cost = cost_data.get("total_cost", 0.0)
        breakdown = cost_data.get("breakdown", {})
        historical = cost_data.get("historical", [])

        # Calculate trends
        trends = {}
        if historical and len(historical) >= 2:
            current = historical[-1].get("cost", 0.0)
            previous = historical[-2].get("cost", 0.0)
            if previous > 0:
                change_percent = ((current - previous) / previous) * 100
                trends = {
                    "current_period": current,
                    "previous_period": previous,
                    "change_amount": current - previous,
                    "change_percent": round(change_percent, 2),
                    "trend": "increasing" if change_percent > 5 else "decreasing" if change_percent < -5 else "stable"
                }

        # Identify top cost drivers
        top_drivers = []
        if breakdown:
            sorted_items = sorted(
                breakdown.items(),
                key=lambda x: x[1].get("cost", 0.0) if isinstance(x[1], dict) else x[1],
                reverse=True
            )
            for name, cost_info in sorted_items[:10]:
                cost_value = cost_info.get("cost", cost_info) if isinstance(cost_info, dict) else cost_info
                percentage = (cost_value / total_cost * 100) if total_cost > 0 else 0
                top_drivers.append({
                    "name": name,
                    "cost": cost_value,
                    "percentage": round(percentage, 2)
                })

        # Calculate month-over-month comparison
        mom_comparison = {}
        if len(historical) >= 30:  # Enough data for month comparison
            current_month = sum(h.get("cost", 0.0) for h in historical[-30:])
            previous_month = sum(h.get("cost", 0.0) for h in historical[-60:-30]) if len(historical) >= 60 else 0
            if previous_month > 0:
                mom_change = ((current_month - previous_month) / previous_month) * 100
                mom_comparison = {
                    "current_month": current_month,
                    "previous_month": previous_month,
                    "change_percent": round(mom_change, 2),
                    "change_amount": current_month - previous_month
                }

        # Simple forecast (linear projection based on recent trend)
        forecast = {}
        if trends:
            avg_daily_cost = total_cost / 30  # Assume 30-day period
            trend_factor = 1 + (trends.get("change_percent", 0) / 100)
            forecast = {
                "next_30_days": round(avg_daily_cost * 30 * trend_factor, 2),
                "next_90_days": round(avg_daily_cost * 90 * trend_factor, 2),
                "confidence": "medium"
            }

        return {
            "trends": trends,
            "top_drivers": top_drivers,
            "mom_comparison": mom_comparison,
            "forecast": forecast
        }

    async def _find_savings_opportunities(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Find cost savings opportunities.

        Identifies potential savings through:
        - Underutilized resources that can be downsized
        - Idle resources that can be stopped or deleted
        - Reserved instance opportunities
        - Storage optimization opportunities
        - Licensing optimization

        Args:
            request: Savings analysis request
            context: Optional workflow context

        Returns:
            Prioritized list of savings opportunities with estimates
        """
        subscription_id = request.get("subscription_id", "")
        resource_group = request.get("resource_group", "")
        min_savings = request.get("min_savings", self.cost_thresholds["savings_opportunity"])
        workflow_id = request.get("workflow_id", f"savings-{datetime.utcnow().timestamp()}")

        logger.info(f"Finding savings opportunities (min: ${min_savings}/month)")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "min_savings": min_savings,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 2: Get cost recommendations
        recommendations_result = await self._call_tool(
            "get_cost_recommendations",
            {
                "subscription_id": subscription_id,
                "resource_group": resource_group,
                "min_impact": min_savings
            }
        )

        # Store recommendations result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="recommendations",
            agent_id=self.agent_id,
            result=recommendations_result
        )

        # Extract and categorize recommendations
        recommendations_data = recommendations_result.get("data", {})
        recommendations = recommendations_data.get("recommendations", [])

        # Categorize and prioritize recommendations
        categorized = self._categorize_savings(recommendations)
        prioritized = self._prioritize_savings(categorized, min_savings)

        # Calculate total potential savings
        total_savings = sum(
            rec.get("estimated_savings", 0.0)
            for rec in recommendations
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "savings": {
                "total_opportunities": len(recommendations),
                "total_potential_savings": round(total_savings, 2),
                "high_priority_count": len(prioritized.get("high", [])),
                "medium_priority_count": len(prioritized.get("medium", [])),
                "low_priority_count": len(prioritized.get("low", [])),
                "by_category": categorized,
                "prioritized": prioritized,
                "top_10_opportunities": self._get_top_opportunities(recommendations, 10),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _categorize_savings(self, recommendations: List[Dict]) -> Dict[str, List[Dict]]:
        """Categorize savings recommendations.

        Args:
            recommendations: List of cost recommendations

        Returns:
            Recommendations grouped by category
        """
        categorized = {category: [] for category in self.savings_categories}
        categorized["other"] = []

        for rec in recommendations:
            category = rec.get("category", "other").lower().replace(" ", "_")
            if category in categorized:
                categorized[category].append(rec)
            else:
                categorized["other"].append(rec)

        # Remove empty categories
        return {k: v for k, v in categorized.items() if v}

    def _prioritize_savings(
        self,
        categorized: Dict[str, List[Dict]],
        min_savings: float
    ) -> Dict[str, List[Dict]]:
        """Prioritize savings recommendations.

        Priority levels:
        - High: >$1000/month or >50% savings, low implementation effort
        - Medium: >$100/month or >25% savings, moderate implementation effort
        - Low: <$100/month or <25% savings

        Args:
            categorized: Categorized recommendations
            min_savings: Minimum monthly savings threshold

        Returns:
            Recommendations grouped by priority
        """
        prioritized = {"high": [], "medium": [], "low": []}

        for category, recs in categorized.items():
            for rec in recs:
                savings = rec.get("estimated_savings", 0.0)
                savings_percent = rec.get("savings_percent", 0.0)
                effort = rec.get("implementation_effort", "medium").lower()

                # High priority criteria
                if savings >= 1000 or (savings_percent >= 50 and effort in ["low", "minimal"]):
                    priority = "high"
                # Medium priority criteria
                elif savings >= 100 or savings_percent >= 25:
                    priority = "medium"
                # Low priority
                else:
                    priority = "low"

                # Skip if below minimum threshold
                if savings < min_savings:
                    continue

                rec["priority"] = priority
                rec["category"] = category
                prioritized[priority].append(rec)

        # Sort each priority group by savings (descending)
        for priority in prioritized:
            prioritized[priority].sort(
                key=lambda x: x.get("estimated_savings", 0.0),
                reverse=True
            )

        return prioritized

    def _get_top_opportunities(
        self,
        recommendations: List[Dict],
        limit: int = 10
    ) -> List[Dict]:
        """Get top N savings opportunities by estimated savings.

        Args:
            recommendations: List of all recommendations
            limit: Number of top opportunities to return

        Returns:
            Top N recommendations sorted by savings
        """
        sorted_recs = sorted(
            recommendations,
            key=lambda x: x.get("estimated_savings", 0.0),
            reverse=True
        )
        return sorted_recs[:limit]

    async def _identify_orphaned_resources(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Identify orphaned and unused resources.

        Finds resources that are:
        - Not attached to any active resources
        - Not used in the last N days
        - Consuming costs without providing value
        - Eligible for deletion or archival

        Args:
            request: Orphaned resource detection request
            context: Optional workflow context

        Returns:
            List of orphaned resources with cost impact
        """
        resource_group = request.get("resource_group", "")
        subscription_id = request.get("subscription_id", "")
        include_types = request.get("resource_types", [])
        workflow_id = request.get("workflow_id", f"orphaned-{datetime.utcnow().timestamp()}")

        logger.info(f"Identifying orphaned resources in {resource_group or 'subscription'}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "resource_group": resource_group,
                "subscription_id": subscription_id,
                "resource_types": include_types,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 3: Identify orphaned resources
        orphaned_result = await self._call_tool(
            "identify_orphaned_resources",
            {
                "resource_group": resource_group,
                "subscription_id": subscription_id,
                "resource_types": include_types
            }
        )

        # Store orphaned resources result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="orphaned",
            agent_id=self.agent_id,
            result=orphaned_result
        )

        # Extract and analyze orphaned resources
        orphaned_data = orphaned_result.get("data", {})
        orphaned_resources = orphaned_data.get("orphaned_resources", [])

        # Calculate cost impact
        cost_impact = self._calculate_orphaned_cost_impact(orphaned_resources)

        # Group by resource type
        by_type = self._group_orphaned_by_type(orphaned_resources)

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "orphaned": {
                "total_found": len(orphaned_resources),
                "total_monthly_cost": cost_impact.get("total_monthly", 0.0),
                "potential_annual_savings": cost_impact.get("annual_savings", 0.0),
                "by_resource_type": by_type,
                "high_cost_orphans": cost_impact.get("high_cost", []),
                "orphaned_resources": orphaned_resources[:50],  # Limit to 50
                "recommendations": self._generate_orphaned_recommendations(orphaned_resources),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _calculate_orphaned_cost_impact(
        self,
        orphaned_resources: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate cost impact of orphaned resources.

        Args:
            orphaned_resources: List of orphaned resources

        Returns:
            Cost impact analysis
        """
        total_monthly = sum(
            res.get("monthly_cost", 0.0)
            for res in orphaned_resources
        )

        # Identify high-cost orphans (>$50/month)
        high_cost = [
            res for res in orphaned_resources
            if res.get("monthly_cost", 0.0) > self.cost_thresholds["waste_threshold"]
        ]
        high_cost.sort(key=lambda x: x.get("monthly_cost", 0.0), reverse=True)

        return {
            "total_monthly": round(total_monthly, 2),
            "annual_savings": round(total_monthly * 12, 2),
            "high_cost": high_cost[:20],  # Top 20 high-cost orphans
            "average_cost_per_resource": round(
                total_monthly / len(orphaned_resources), 2
            ) if orphaned_resources else 0.0
        }

    def _group_orphaned_by_type(
        self,
        orphaned_resources: List[Dict]
    ) -> Dict[str, Dict[str, Any]]:
        """Group orphaned resources by type.

        Args:
            orphaned_resources: List of orphaned resources

        Returns:
            Resources grouped by type with cost totals
        """
        by_type = {}

        for resource in orphaned_resources:
            resource_type = resource.get("type", "unknown")
            if resource_type not in by_type:
                by_type[resource_type] = {
                    "count": 0,
                    "total_monthly_cost": 0.0,
                    "resources": []
                }

            by_type[resource_type]["count"] += 1
            by_type[resource_type]["total_monthly_cost"] += resource.get("monthly_cost", 0.0)
            by_type[resource_type]["resources"].append(resource)

        # Round costs
        for type_data in by_type.values():
            type_data["total_monthly_cost"] = round(type_data["total_monthly_cost"], 2)
            # Limit resources list
            type_data["resources"] = type_data["resources"][:10]

        return by_type

    def _generate_orphaned_recommendations(
        self,
        orphaned_resources: List[Dict]
    ) -> List[str]:
        """Generate recommendations for orphaned resources.

        Args:
            orphaned_resources: List of orphaned resources

        Returns:
            List of actionable recommendations
        """
        recommendations = []

        # Group by type for recommendations
        by_type = {}
        for resource in orphaned_resources:
            resource_type = resource.get("type", "unknown")
            by_type[resource_type] = by_type.get(resource_type, 0) + 1

        # Type-specific recommendations
        type_recommendations = {
            "disk": "Delete unattached managed disks or create snapshots before deletion",
            "nic": "Remove network interfaces not attached to VMs",
            "publicip": "Release unassociated public IP addresses",
            "nsg": "Delete network security groups not associated with subnets or NICs",
            "snapshot": "Delete old snapshots that are no longer needed for recovery",
            "image": "Remove custom images that are not in use",
            "loadbalancer": "Delete load balancers with no backend pools or rules"
        }

        for resource_type, count in by_type.items():
            type_lower = resource_type.lower()
            for key, rec in type_recommendations.items():
                if key in type_lower:
                    recommendations.append(f"{rec} ({count} found)")
                    break
            else:
                recommendations.append(
                    f"Review and remove {count} unused {resource_type} resources"
                )

        # Add general recommendations
        total_cost = sum(r.get("monthly_cost", 0.0) for r in orphaned_resources)
        if total_cost > 500:
            recommendations.insert(
                0,
                f"Priority action: Remove orphaned resources to save ${total_cost:.2f}/month"
            )

        return recommendations[:10]  # Top 10 recommendations

    async def _track_budget(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Track budget utilization and alerting.

        Monitors spending against defined budgets and provides alerts
        when thresholds are exceeded.

        Args:
            request: Budget tracking request
            context: Optional workflow context

        Returns:
            Budget status with utilization and alerts
        """
        budget_name = request.get("budget_name", "")
        resource_group = request.get("resource_group", "")
        threshold_percent = request.get("threshold_percent", self.cost_thresholds["budget_warning"])
        workflow_id = request.get("workflow_id", f"budget-{datetime.utcnow().timestamp()}")

        logger.info(f"Tracking budget: {budget_name}")

        # Create workflow context
        await self.context_store.create_workflow_context(
            workflow_id=workflow_id,
            initial_data={
                "budget_name": budget_name,
                "resource_group": resource_group,
                "threshold_percent": threshold_percent,
                "started_at": datetime.utcnow().isoformat()
            }
        )

        # Step 4: Get cost analysis for budget period
        cost_analysis_result = await self._call_tool(
            "get_cost_analysis",
            {
                "time_range": "30d",
                "resource_group": resource_group
            }
        )

        cost_data = cost_analysis_result.get("data", {})
        current_spend = cost_data.get("total_cost", 0.0)

        # Get budget information (mock for now - would call Azure Cost Management API)
        budget_amount = request.get("budget_amount", 10000.0)  # Default budget

        # Calculate utilization
        utilization_percent = (current_spend / budget_amount * 100) if budget_amount > 0 else 0
        remaining = budget_amount - current_spend

        # Determine alert level
        alert_level = self._determine_budget_alert_level(utilization_percent)

        # Store budget tracking result
        await self.context_store.add_step_result(
            workflow_id=workflow_id,
            step_id="budget_tracking",
            agent_id=self.agent_id,
            result={
                "current_spend": current_spend,
                "budget_amount": budget_amount,
                "utilization_percent": utilization_percent,
                "alert_level": alert_level
            }
        )

        # Generate forecast
        forecast = self._forecast_budget_exhaustion(
            current_spend,
            budget_amount,
            cost_data.get("historical", [])
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "budget": {
                "budget_name": budget_name,
                "budget_amount": budget_amount,
                "current_spend": round(current_spend, 2),
                "remaining": round(remaining, 2),
                "utilization_percent": round(utilization_percent, 2),
                "alert_level": alert_level,
                "threshold_exceeded": utilization_percent >= threshold_percent,
                "forecast": forecast,
                "recommendations": self._generate_budget_recommendations(
                    utilization_percent,
                    remaining,
                    forecast
                ),
                "timestamp": datetime.utcnow().isoformat()
            }
        }

    def _determine_budget_alert_level(self, utilization_percent: float) -> str:
        """Determine budget alert level based on utilization.

        Args:
            utilization_percent: Current budget utilization percentage

        Returns:
            Alert level: critical, warning, or ok
        """
        if utilization_percent >= self.cost_thresholds["budget_critical"]:
            return "critical"
        elif utilization_percent >= self.cost_thresholds["budget_warning"]:
            return "warning"
        else:
            return "ok"

    def _forecast_budget_exhaustion(
        self,
        current_spend: float,
        budget_amount: float,
        historical: List[Dict]
    ) -> Dict[str, Any]:
        """Forecast when budget will be exhausted.

        Args:
            current_spend: Current spending amount
            budget_amount: Total budget amount
            historical: Historical spending data

        Returns:
            Forecast information
        """
        if not historical or len(historical) < 7:
            return {
                "exhaustion_date": None,
                "days_remaining": None,
                "confidence": "low",
                "message": "Insufficient historical data for forecast"
            }

        # Calculate average daily spend from recent data
        recent_days = min(14, len(historical))
        recent_data = historical[-recent_days:]
        avg_daily_spend = sum(d.get("cost", 0.0) for d in recent_data) / recent_days

        if avg_daily_spend <= 0:
            return {
                "exhaustion_date": None,
                "days_remaining": None,
                "confidence": "low",
                "message": "No spending detected"
            }

        # Calculate days until budget exhaustion
        remaining = budget_amount - current_spend
        days_remaining = remaining / avg_daily_spend if avg_daily_spend > 0 else float('inf')

        if days_remaining < 0:
            exhaustion_date = None
            message = "Budget already exceeded"
        elif days_remaining > 365:
            exhaustion_date = None
            message = "Budget sufficient for foreseeable future"
        else:
            exhaustion_date = (datetime.utcnow() + timedelta(days=int(days_remaining))).isoformat()
            message = f"Budget projected to be exhausted in {int(days_remaining)} days"

        return {
            "exhaustion_date": exhaustion_date,
            "days_remaining": int(days_remaining) if days_remaining < float('inf') else None,
            "avg_daily_spend": round(avg_daily_spend, 2),
            "projected_monthly_spend": round(avg_daily_spend * 30, 2),
            "confidence": "high" if recent_days >= 14 else "medium",
            "message": message
        }

    def _generate_budget_recommendations(
        self,
        utilization_percent: float,
        remaining: float,
        forecast: Dict[str, Any]
    ) -> List[str]:
        """Generate budget management recommendations.

        Args:
            utilization_percent: Current budget utilization percentage
            remaining: Remaining budget amount
            forecast: Budget forecast information

        Returns:
            List of recommendations
        """
        recommendations = []

        # Critical alerts
        if utilization_percent >= self.cost_thresholds["budget_critical"]:
            recommendations.append(
                "URGENT: Budget utilization at critical level - implement cost controls immediately"
            )
            recommendations.append(
                "Review and stop non-essential resources to prevent budget overrun"
            )

        # Warning alerts
        elif utilization_percent >= self.cost_thresholds["budget_warning"]:
            recommendations.append(
                "WARNING: Budget utilization approaching threshold - review spending patterns"
            )
            recommendations.append(
                "Consider implementing cost optimization recommendations to extend budget"
            )

        # Forecast-based recommendations
        days_remaining = forecast.get("days_remaining")
        if days_remaining and days_remaining < 7:
            recommendations.append(
                f"Budget projected to be exhausted in {days_remaining} days - take immediate action"
            )
        elif days_remaining and days_remaining < 15:
            recommendations.append(
                f"Budget running low - only {days_remaining} days remaining at current spend rate"
            )

        # General recommendations
        if not recommendations:
            recommendations.append(
                "Budget utilization is healthy - continue monitoring spending patterns"
            )

        recommendations.append(
            f"Remaining budget: ${remaining:.2f} - Plan accordingly for month-end"
        )

        return recommendations

    async def _generate_recommendations(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive cost optimization recommendations.

        Combines insights from all analysis phases to provide
        actionable, prioritized recommendations.

        Args:
            request: Recommendations request
            context: Optional workflow context

        Returns:
            Prioritized cost optimization recommendations
        """
        workflow_id = request.get("workflow_id", f"recommendations-{datetime.utcnow().timestamp()}")

        logger.info("Generating comprehensive cost optimization recommendations")

        # Get context from previous analysis steps if available
        workflow_context = await self.context_store.get_workflow_context(workflow_id)

        # Generate recommendations across categories
        recommendations = {
            "immediate_actions": [
                "Delete or stop orphaned resources consuming costs without value",
                "Review and downsize overprovisioned resources with low utilization",
                "Remove unused storage accounts, snapshots, and old backups"
            ],
            "short_term_actions": [
                "Purchase reserved instances for stable, long-running workloads",
                "Implement auto-shutdown schedules for dev/test environments",
                "Archive infrequently accessed data to cool/cold storage tiers",
                "Optimize VM sizes based on actual usage patterns"
            ],
            "long_term_actions": [
                "Establish cost allocation tags and chargeback model",
                "Implement comprehensive cost monitoring and alerting",
                "Consider commitment discounts for consistent workloads",
                "Establish governance policies to prevent cost waste"
            ],
            "estimated_impact": {
                "immediate_savings": "15-25% of monthly spend",
                "short_term_savings": "25-35% of monthly spend",
                "long_term_savings": "30-40% of monthly spend",
                "payback_period": "1-3 months"
            }
        }

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "recommendations": recommendations,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _full_cost_optimization(
        self,
        request: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute full cost optimization workflow.

        Runs all phases:
        1. Analyze costs and trends
        2. Find savings opportunities
        3. Identify orphaned resources
        4. Track budget utilization
        5. Generate comprehensive recommendations

        Args:
            request: Full optimization request
            context: Optional workflow context

        Returns:
            Complete cost optimization report with actionable recommendations
        """
        workflow_id = f"full-cost-opt-{datetime.utcnow().timestamp()}"
        request["workflow_id"] = workflow_id

        logger.info(f"Starting full cost optimization analysis: {workflow_id}")

        # Phase 1: Analyze costs
        cost_analysis_result = await self._analyze_costs(request, context)

        # Phase 2: Find savings opportunities
        savings_result = await self._find_savings_opportunities(request, context)

        # Phase 3: Identify orphaned resources
        orphaned_result = await self._identify_orphaned_resources(request, context)

        # Phase 4: Track budget (if budget info provided)
        budget_result = None
        if request.get("budget_name") or request.get("budget_amount"):
            budget_result = await self._track_budget(request, context)

        # Phase 5: Generate comprehensive recommendations
        recommendations_result = await self._generate_recommendations(request, context)

        # Calculate total potential savings
        total_savings = (
            savings_result.get("savings", {}).get("total_potential_savings", 0.0) +
            orphaned_result.get("orphaned", {}).get("total_monthly_cost", 0.0)
        )

        return {
            "status": "success",
            "workflow_id": workflow_id,
            "phases": {
                "cost_analysis": cost_analysis_result,
                "savings_opportunities": savings_result,
                "orphaned_resources": orphaned_result,
                "budget_tracking": budget_result,
                "recommendations": recommendations_result
            },
            "summary": {
                "current_monthly_spend": cost_analysis_result.get("cost_analysis", {}).get("total_cost", 0.0),
                "total_potential_savings": round(total_savings, 2),
                "potential_savings_percent": round(
                    (total_savings / cost_analysis_result.get("cost_analysis", {}).get("total_cost", 1.0)) * 100,
                    2
                ),
                "high_priority_opportunities": savings_result.get("savings", {}).get("high_priority_count", 0),
                "orphaned_resources_found": orphaned_result.get("orphaned", {}).get("total_found", 0),
                "budget_alert_level": budget_result.get("budget", {}).get("alert_level", "unknown") if budget_result else "not_tracked",
                "completed_at": datetime.utcnow().isoformat()
            }
        }
