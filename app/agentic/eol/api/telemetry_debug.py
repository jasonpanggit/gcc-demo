"""Diagnostic endpoint for telemetry troubleshooting."""
import os
from fastapi import APIRouter
from pydantic import BaseModel
from utils.response_models import StandardResponse
from utils.endpoint_decorators import readonly_endpoint

router = APIRouter()

class TestQueryRequest(BaseModel):
    """Request to test routing telemetry."""
    query: str = "list container apps"

@router.get("/api/telemetry/debug", response_model=StandardResponse)
@readonly_endpoint(agent_name="telemetry_debug", timeout_seconds=5)
async def debug_telemetry():
    """Debug endpoint to check telemetry configuration."""

    # Read environment variables
    enabled_raw = os.getenv("ROUTING_TELEMETRY_ENABLED", "NOT_SET")
    log_dir = os.getenv("ROUTING_TELEMETRY_LOG_DIR", "NOT_SET")
    sample_rate = os.getenv("ROUTING_TELEMETRY_SAMPLE_RATE", "NOT_SET")

    # Check if telemetry instance exists
    try:
        from utils.routing_telemetry import get_routing_telemetry
        telemetry = get_routing_telemetry()

        debug_info = {
            "environment_variables": {
                "ROUTING_TELEMETRY_ENABLED": enabled_raw,
                "ROUTING_TELEMETRY_LOG_DIR": log_dir,
                "ROUTING_TELEMETRY_SAMPLE_RATE": sample_rate,
            },
            "telemetry_instance": {
                "enabled": telemetry.enabled,
                "log_dir": str(telemetry.log_dir),
                "sample_rate": telemetry.sample_rate,
            },
            "parsing_result": {
                "enabled_parsed": enabled_raw.lower() == "true",
                "is_pytest": os.getenv("PYTEST_CURRENT_TEST") is not None,
            },
            "log_directory_status": {
                "exists": telemetry.log_dir.exists(),
                "writable": os.access(str(telemetry.log_dir.parent), os.W_OK) if telemetry.log_dir.parent.exists() else False,
            }
        }

        return StandardResponse(
            success=True,
            data=debug_info,
            message="Telemetry debug information retrieved"
        )

    except Exception as e:
        return StandardResponse(
            success=False,
            data={"error": str(e)},
            message=f"Error retrieving telemetry debug info: {str(e)}"
        )


@router.post("/api/telemetry/test-routing", response_model=StandardResponse)
@readonly_endpoint(agent_name="test_routing_telemetry", timeout_seconds=10)
async def test_routing_telemetry(request: TestQueryRequest):
    """Test endpoint to trigger routing decision telemetry."""
    try:
        from utils.tool_manifest_index import get_tool_manifest_index
        from utils.routing_telemetry import get_routing_telemetry

        # Get manifest index
        manifest_index = get_tool_manifest_index()
        if not manifest_index:
            return StandardResponse(
                success=False,
                data={"error": "Manifest index not initialized"},
                message="Manifest index unavailable"
            )

        # Call find_tools_matching_query to trigger telemetry
        selected_tools = manifest_index.find_tools_matching_query(request.query)

        # Check telemetry
        telemetry = get_routing_telemetry()

        # Check if log files were created
        import glob
        log_files = {
            "routing": list(telemetry.log_dir.glob("routing_*.jsonl")),
            "execution": list(telemetry.log_dir.glob("execution_*.jsonl")),
            "corrections": list(telemetry.log_dir.glob("corrections_*.jsonl")),
        }

        return StandardResponse(
            success=True,
            data={
                "query": request.query,
                "selected_tools": selected_tools,
                "telemetry_enabled": telemetry.enabled,
                "log_files_created": {
                    "routing": len(log_files["routing"]),
                    "execution": len(log_files["execution"]),
                    "corrections": len(log_files["corrections"]),
                },
                "log_file_paths": {
                    "routing": [str(f) for f in log_files["routing"]],
                    "execution": [str(f) for f in log_files["execution"]],
                    "corrections": [str(f) for f in log_files["corrections"]],
                }
            },
            message=f"Routing test completed - selected {len(selected_tools)} tools"
        )

    except Exception as e:
        import traceback
        return StandardResponse(
            success=False,
            data={"error": str(e), "traceback": traceback.format_exc()},
            message=f"Error testing routing telemetry: {str(e)}"
        )
