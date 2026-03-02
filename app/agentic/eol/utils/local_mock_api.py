"""Local mock API fallbacks for UI endpoints.

When running with USE_MOCK_DATA=true, some API routes can still fail if they
depend on cloud services unavailable in local environments. This module
provides lightweight fallback payloads so UI pages can load consistently.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs


def mock_mode_enabled() -> bool:
    import os

    return os.getenv("USE_MOCK_DATA", "false").lower() == "true"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _software_items() -> List[Dict[str, Any]]:
    return [
        {
            "computer": "vm-app-01",
            "name": "Microsoft SQL Server",
            "version": "15.0",
            "publisher": "Microsoft Corporation",
            "software_type": "Application",
            "source": "mock",
            "last_seen": _now_iso(),
        },
        {
            "computer": "vm-web-01",
            "name": "IIS",
            "version": "10.0",
            "publisher": "Microsoft Corporation",
            "software_type": "Application",
            "source": "mock",
            "last_seen": _now_iso(),
        },
    ]


def _os_items() -> List[Dict[str, Any]]:
    return [
        {
            "computer_name": "vm-app-01",
            "computer": "vm-app-01",
            "os_name": "Windows Server 2019",
            "os_version": "10.0.17763",
            "publisher": "Microsoft",
            "computer_type": "Azure VM",
            "computer_environment": "Azure",
            "last_heartbeat": _now_iso(),
            "eol_status": "Supported",
            "eol_date": "2029-01-09",
            "source": "mock",
        },
        {
            "computer_name": "vm-web-01",
            "computer": "vm-web-01",
            "os_name": "Ubuntu 22.04",
            "os_version": "22.04",
            "publisher": "Canonical",
            "computer_type": "Azure VM",
            "computer_environment": "Azure",
            "last_heartbeat": _now_iso(),
            "eol_status": "Supported",
            "eol_date": "2027-04-30",
            "source": "mock",
        },
    ]


def _resource_inventory_items() -> List[Dict[str, Any]]:
    now = _now_iso()
    return [
        {
            "resource_name": "vm-app-01",
            "name": "vm-app-01",
            "resource_type": "Microsoft.Compute/virtualMachines",
            "resource_group": "rg-app-prod",
            "location": "eastus",
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            "tags": {"env": "prod", "owner": "platform"},
            "selected_properties": {"powerState": "running", "osType": "Windows"},
            "discovered_at": now,
            "last_seen": now,
            "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-app-prod/providers/Microsoft.Compute/virtualMachines/vm-app-01",
        },
        {
            "resource_name": "vnet-hub-01",
            "name": "vnet-hub-01",
            "resource_type": "Microsoft.Network/virtualNetworks",
            "resource_group": "rg-network-core",
            "location": "westus2",
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            "tags": {"env": "shared", "tier": "network"},
            "selected_properties": {"addressSpace": "10.10.0.0/16"},
            "discovered_at": now,
            "last_seen": now,
            "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-network-core/providers/Microsoft.Network/virtualNetworks/vnet-hub-01",
        },
        {
            "resource_name": "stlogsprod01",
            "name": "stlogsprod01",
            "resource_type": "Microsoft.Storage/storageAccounts",
            "resource_group": "rg-observability",
            "location": "eastus",
            "subscription_id": "00000000-0000-0000-0000-000000000002",
            "tags": {"env": "prod", "data": "logs"},
            "selected_properties": {"sku": "Standard_LRS", "kind": "StorageV2"},
            "discovered_at": now,
            "last_seen": now,
            "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-observability/providers/Microsoft.Storage/storageAccounts/stlogsprod01",
        },
        {
            "resource_name": "ca-eol-demo",
            "name": "ca-eol-demo",
            "resource_type": "Microsoft.App/containerApps",
            "resource_group": "rg-agentic-eol",
            "location": "westeurope",
            "subscription_id": "00000000-0000-0000-0000-000000000002",
            "tags": {"env": "demo", "app": "eol"},
            "selected_properties": {"revisionMode": "Single"},
            "discovered_at": now,
            "last_seen": now,
            "resource_id": "/subscriptions/00000000-0000-0000-0000-000000000002/resourceGroups/rg-agentic-eol/providers/Microsoft.App/containerApps/ca-eol-demo",
        },
    ]


def _mock_patch_list() -> Dict[str, Any]:
    return {
        "available_patches": [
            {
                "patchName": "2026-02 Cumulative Update for Windows Server 2019",
                "kbId": "KB5039991",
                "classifications": ["Security", "Critical"],
                "rebootBehavior": "CanRequestReboot",
                "assessmentState": "Available",
                "publishedDate": "2026-02-20T00:00:00Z",
            },
            {
                "patchName": "Windows Defender Definition Update",
                "kbId": "KB2267602",
                "classifications": ["Definition"],
                "rebootBehavior": "NeverReboots",
                "assessmentState": "Available",
                "publishedDate": "2026-03-01T00:00:00Z",
            },
        ],
        "critical_and_security_count": 1,
        "other_count": 1,
        "total_count": 2,
        "last_assessed": _now_iso(),
        "status": "Succeeded",
        "source": "local-mock",
    }


def build_mock_response(path: str, method: str, query_string: str = "") -> Optional[Dict[str, Any]]:
    """Return fallback payload for an API path, or None if no fallback exists."""
    method = method.upper()
    query = parse_qs(query_string or "")

    if path == "/api/inventory/raw/software":
        data = _software_items()
        limit = int(query.get("limit", [len(data)])[0])
        return {
            "success": True,
            "data": data[:limit],
            "count": min(limit, len(data)),
            "from_cache": False,
            "source": "local-mock",
        }

    if path == "/api/inventory/raw/os":
        data = _os_items()
        limit = int(query.get("limit", [len(data)])[0])
        return {
            "success": True,
            "data": data[:limit],
            "count": min(limit, len(data)),
            "from_cache": False,
            "source": "local-mock",
        }

    if path == "/api/inventory":
        data = _software_items()
        return {"success": True, "data": data, "count": len(data), "source": "local-mock"}

    if path == "/api/os":
        data = _os_items()
        return {"success": True, "data": data, "count": len(data), "source": "local-mock"}

    if path == "/api/os/summary":
        return {
            "success": True,
            "status": "ok",
            "summary": {
                "total_systems": len(_os_items()),
                "os_families": {"Windows Server": 1, "Ubuntu": 1},
                "eol_risk": {"high": 0, "medium": 0, "low": 2},
            },
            "source": "local-mock",
        }

    if path == "/api/inventory/status":
        return {
            "success": True,
            "status": "ok",
            "log_analytics_available": False,
            "summary": {
                "total_software": len(_software_items()),
                "total_os": len(_os_items()),
                "last_update": _now_iso(),
            },
            "source": "local-mock",
        }

    if path == "/api/resource-inventory/subscriptions":
        return {
            "success": True,
            "data": {
                "subscriptions": [
                    {
                        "subscription_id": "00000000-0000-0000-0000-000000000001",
                        "display_name": "Mock Platform Subscription",
                    },
                    {
                        "subscription_id": "00000000-0000-0000-0000-000000000002",
                        "display_name": "Mock Demo Subscription",
                    },
                ],
                "count": 2,
            },
            "message": "Discovered 2 subscriptions",
            "source": "local-mock",
        }

    if path == "/api/resource-inventory/stats":
        return {
            "success": True,
            "data": {
                "cache": {
                    "l1_entries": 128,
                    "l1_valid_entries": 116,
                    "l2_ready": True,
                    "hit_rate_percent": 91,
                    "l1_hit_rate_percent": 78,
                    "l2_hit_rate_percent": 13,
                    "miss_rate_percent": 9,
                    "total_requests": 1840,
                    "writes": 242,
                }
            },
            "message": "Cache statistics retrieved",
            "source": "local-mock",
        }

    if path == "/api/resource-inventory/metrics":
        return {
            "success": True,
            "data": {
                "cache": {
                    "l1_hits": 1420,
                    "l1_misses": 240,
                    "l2_hits": 140,
                    "l2_misses": 40,
                    "l1_hit_rate": 0.86,
                    "l2_hit_rate": 0.78,
                    "overall_hit_rate": 0.90,
                    "total_sets": 260,
                    "api_calls_saved": 1560,
                },
                "resources": {
                    "total_resources": 412,
                    "subscriptions": 2,
                    "by_type": {
                        "Microsoft.Compute/virtualMachines": 96,
                        "Microsoft.Network/virtualNetworks": 44,
                        "Microsoft.Storage/storageAccounts": 88,
                        "Microsoft.App/containerApps": 36,
                        "Microsoft.Web/sites": 52,
                        "Microsoft.KeyVault/vaults": 24,
                    },
                    "by_location": {
                        "eastus": 178,
                        "westus2": 122,
                        "westeurope": 112,
                    },
                },
                "queries": {
                    "total_queries": 304,
                },
                "discovery": {
                    "total_discoveries": 34,
                    "success_rate": 0.94,
                    "avg_duration_seconds": 7.8,
                    "last_discovery": _now_iso(),
                    "last_status": "success",
                },
            },
            "message": "Inventory metrics retrieved",
            "source": "local-mock",
        }

    if path == "/api/resource-inventory/resources":
        items = _resource_inventory_items()
        resource_type = query.get("resource_type", [None])[0]
        subscription_id = query.get("subscription_id", [None])[0]
        location = query.get("location", [None])[0]
        resource_group = query.get("resource_group", [None])[0]
        name = query.get("name", [None])[0]

        if resource_type:
            items = [i for i in items if i.get("resource_type", "").lower() == resource_type.lower()]
        if subscription_id:
            items = [i for i in items if i.get("subscription_id") == subscription_id]
        if location:
            items = [i for i in items if i.get("location", "").lower() == location.lower()]
        if resource_group:
            items = [i for i in items if i.get("resource_group", "").lower() == resource_group.lower()]
        if name:
            items = [i for i in items if name.lower() in i.get("resource_name", "").lower()]

        offset = int(query.get("offset", [0])[0])
        limit = int(query.get("limit", [50])[0])
        total = len(items)
        page = items[offset : offset + limit]

        return {
            "success": True,
            "data": {
                "items": page,
                "total": total,
                "offset": offset,
                "limit": limit,
                "has_more": offset + limit < total,
            },
            "message": f"Found {total} resources",
            "duration_ms": 18.3,
            "source": "local-mock",
        }

    if path == "/api/resource-inventory/refresh":
        mode = query.get("mode", ["full"])[0]
        return {
            "success": True,
            "data": {
                "mode": mode,
                "subscription_id": query.get("subscription_id", ["00000000-0000-0000-0000-000000000001"])[0],
                "resources_discovered": 57,
                "resource_types": 6,
                "type_breakdown": {
                    "Microsoft.Compute/virtualMachines": 14,
                    "Microsoft.Storage/storageAccounts": 12,
                    "Microsoft.Web/sites": 8,
                    "Microsoft.Network/virtualNetworks": 6,
                    "Microsoft.App/containerApps": 7,
                    "Microsoft.KeyVault/vaults": 10,
                },
            },
            "message": "Mock discovery refresh completed",
            "source": "local-mock",
        }

    if path == "/healthz/inventory":
        return {
            "success": True,
            "data": {
                "status": "healthy",
                "engine_available": True,
                "cache": {
                    "l1_entries": 128,
                    "l1_valid": 116,
                    "l2_ready": True,
                    "hit_rate_percent": 91,
                },
                "config": {
                    "enable_inventory": True,
                    "default_l1_ttl": 300,
                    "default_l2_ttl": 3600,
                    "full_scan_schedule": "0 */6 * * *",
                    "incremental_interval_min": 15,
                },
            },
            "message": "Resource inventory health check",
            "source": "local-mock",
        }

    if path.startswith("/api/cache"):
        if path.endswith("/status"):
            return {
                "success": True,
                "data": [
                    {
                        "agents_with_cache": [],
                        "inventory_context_cache": {
                            "cached": True,
                            "timestamp": _now_iso(),
                            "ttl_seconds": 3600,
                            "items_count": 4,
                        },
                        "enhanced_stats": {
                            "agent_stats": {},
                            "inventory_stats": {},
                            "cosmos_stats": {},
                            "performance_summary": {},
                            "last_updated": _now_iso(),
                        },
                    }
                ],
                "source": "local-mock",
            }

        if "/stats" in path or "/cosmos" in path or path.endswith("/clear") or path.endswith("/purge"):
            return {"success": True, "data": [], "message": "Mock cache operation completed", "source": "local-mock"}

    if path.startswith("/api/alerts"):
        if path.endswith("/config") or path.endswith("/config/reload"):
            return {
                "success": True,
                "data": [
                    {
                        "configuration": {
                            "enabled": True,
                            "critical": {"period": 3, "unit": "months", "frequency": "weekly"},
                            "warning": {"period": 6, "unit": "months", "frequency": "monthly"},
                            "info": {"period": 12, "unit": "months", "frequency": "quarterly"},
                            "email_recipients": ["admin@example.com"],
                        }
                    }
                ],
                "source": "local-mock",
            }

        return {"success": True, "message": "Mock alerts operation completed", "data": [], "source": "local-mock"}

    if path == "/api/notifications/history":
        return {
            "success": True,
            "data": [
                {
                    "id": "mock-notification-1",
                    "timestamp": _now_iso(),
                    "status": "sent",
                    "alert_type": "critical",
                    "items_count": 1,
                    "recipients": ["admin@example.com"],
                }
            ],
            "count": 1,
            "source": "local-mock",
        }

    if path.startswith("/api/communications"):
        if method == "POST" and path.endswith("/clear"):
            return {"success": True, "message": "Conversation cleared (mock)", "source": "local-mock"}
        return {
            "success": True,
            "response": "This is a local mock response. Live services are unavailable.",
            "data": {"response": "This is a local mock response. Live services are unavailable."},
            "source": "local-mock",
        }

    if path.startswith("/api/inventory-assistant"):
        return {
            "success": True,
            "response": "Inventory assistant mock response from local mode.",
            "data": {"response": "Inventory assistant mock response from local mode."},
            "source": "local-mock",
        }

    if path.startswith("/api/search/eol"):
        return {
            "success": True,
            "data": [
                {
                    "software_name": "Windows Server",
                    "version": "2019",
                    "eol_date": "2029-01-09",
                    "support_status": "supported",
                    "agent_used": "mock",
                }
            ],
            "source": "local-mock",
        }

    if path == "/api/agents/list":
        return {
            "success": True,
            "data": [
                {"name": "microsoft", "status": "available", "source": "mock"},
                {"name": "endoflife", "status": "available", "source": "mock"},
            ],
            "source": "local-mock",
        }

    if path.startswith("/api/azure-mcp"):
        if path.endswith("/status"):
            return {
                "success": True,
                "data": [
                    {
                        "initialized": False,
                        "connection_status": "mock",
                        "available_tools_count": 0,
                        "active_clients": [],
                    }
                ],
                "source": "local-mock",
            }
        return {"success": True, "data": [], "message": "Azure MCP mock response", "source": "local-mock"}

    if path.startswith("/api/monitor-community"):
        return {"success": True, "data": [], "count": 0, "source": "local-mock"}

    if path.startswith("/api/patch-management") or path.startswith("/api/mcp-orchestrator"):
        if path.endswith("/machines"):
            return {
                "success": True,
                "data": [
                    {
                        "computer": "vm-app-01",
                        "name": "vm-app-01",
                        "resource_id": "/subscriptions/mock/resourceGroups/mock-rg/providers/Microsoft.Compute/virtualMachines/vm-app-01",
                        "subscription_id": "00000000-0000-0000-0000-000000000001",
                        "resource_group": "mock-rg",
                        "location": "eastus",
                        "os_name": "Windows Server 2019",
                        "vm_type": "azure-vm",
                        "os_type": "Windows",
                    },
                    {
                        "computer": "arc-sql-01",
                        "name": "arc-sql-01",
                        "resource_id": "/subscriptions/mock/resourceGroups/mock-rg/providers/Microsoft.HybridCompute/machines/arc-sql-01",
                        "subscription_id": "00000000-0000-0000-0000-000000000001",
                        "resource_group": "mock-rg",
                        "location": "westus2",
                        "os_name": "Windows Server 2022",
                        "vm_type": "arc",
                        "os_type": "Windows",
                    }
                ],
                "count": 2,
                "source": "local-mock",
            }

        if path.endswith("/arg-patch-data"):
            return {
                "success": True,
                "data": [
                    {
                        "machine_name": "vm-app-01",
                        "subscription_id": "00000000-0000-0000-0000-000000000001",
                        "resource_group": "mock-rg",
                        "os_type": "Windows",
                        "reboot_pending": False,
                        "patches": _mock_patch_list(),
                    }
                ],
                "count": 1,
                "source": "local-mock",
            }

        if path.endswith("/last-assessment"):
            machine_name = query.get("machine_name", ["mock-machine"])[0]
            vm_type = query.get("vm_type", ["arc"])[0]
            return {
                "success": True,
                "found": True,
                "machine_name": machine_name,
                "resource_id": f"/subscriptions/mock/resourceGroups/mock-rg/providers/{'Microsoft.Compute/virtualMachines' if vm_type == 'azure-vm' else 'Microsoft.HybridCompute/machines'}/{machine_name}",
                "resource_group": "mock-rg",
                "subscription_id": query.get("subscription_id", ["00000000-0000-0000-0000-000000000001"])[0],
                "os_type": "Windows",
                "reboot_pending": False,
                "vm_type": vm_type,
                "patches": _mock_patch_list(),
                "source": "local-mock",
            }

        if path.endswith("/assess"):
            return {
                "success": True,
                "triggered": True,
                "machine": "mock-machine",
                "subscription_id": "00000000-0000-0000-0000-000000000001",
                "resource_group": "mock-rg",
                "vm_type": "arc",
                "operation_url": "https://mock.local/patch/assessment/operations/1",
                "message": "Assessment triggered in local mock mode.",
                "source": "local-mock",
            }

        if path.endswith("/install"):
            return {
                "success": True,
                "machine": "mock-machine",
                "subscription_id": "00000000-0000-0000-0000-000000000001",
                "resource_group": "mock-rg",
                "status": "InProgress",
                "operation_url": "https://mock.local/patch/install/operations/1",
                "message": "Patch installation started (mock).",
                "source": "local-mock",
            }

        if path.endswith("/install-status"):
            return {
                "success": True,
                "status": "Succeeded",
                "is_done": True,
                "data": {
                    "status": "Succeeded",
                    "installed_patch_count": 2,
                    "failed_patch_count": 0,
                    "pending_patch_count": 0,
                    "not_selected_patch_count": 0,
                    "excluded_patch_count": 0,
                    "reboot_status": "NotNeeded",
                    "maintenance_window_exceeded": False,
                    "start_date_time": _now_iso(),
                    "last_modified": _now_iso(),
                    "patches": _mock_patch_list().get("available_patches", []),
                    "error": None,
                },
                "error": None,
                "source": "local-mock",
            }

        return {"success": True, "data": [], "message": "Patch management mock response", "source": "local-mock"}

    if path.startswith("/api/sre-orchestrator"):
        if path.endswith("/health"):
            return {"success": True, "status": "healthy", "source": "local-mock"}
        if path.endswith("/capabilities"):
            return {"success": True, "data": {"agents": [], "tools": []}, "source": "local-mock"}
        return {"success": True, "data": [], "source": "local-mock"}

    if path.startswith("/api/eol-agent-responses"):
        if method == "POST" and path.endswith("/clear"):
            return {"success": True, "message": "History cleared (mock)", "source": "local-mock"}
        return {"success": True, "data": [], "count": 0, "source": "local-mock"}

    if path.startswith("/api/eol-inventory"):
        return {"success": True, "data": [], "count": 0, "message": "EOL inventory mock response", "source": "local-mock"}

    return None
