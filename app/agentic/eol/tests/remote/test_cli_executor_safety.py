"""Unit tests for Azure CLI executor safety classification.

Tests that:
- _classify_command correctly classifies read/write/blocked commands
- execute_azure_cli_command returns plan-not-execute for write commands without confirmed
- execute_azure_cli_command hard-blocks always-block commands regardless of confirmed
- execute_azure_cli_command passes through for read commands (mocked execution)
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from app.agentic.eol.mcp_servers.azure_cli_executor_server import _classify_command
    _MODULE = "app.agentic.eol.mcp_servers.azure_cli_executor_server"
except ModuleNotFoundError:
    from mcp_servers.azure_cli_executor_server import _classify_command  # type: ignore[import-not-found]
    _MODULE = "mcp_servers.azure_cli_executor_server"


# ---------------------------------------------------------------------------
# _classify_command unit tests (pure, no I/O)
# ---------------------------------------------------------------------------


class TestClassifyCommand:
    def test_read_commands_pass(self):
        assert _classify_command("az network nsg list") == "read"
        assert _classify_command("az vm list") == "read"
        assert _classify_command("az storage account show --name foo") == "read"
        assert _classify_command("az containerapp list --resource-group rg-prod") == "read"
        assert _classify_command("az account list") == "read"

    def test_write_commands_flagged(self):
        assert _classify_command("az storage account delete --name foo") == "write"
        assert _classify_command("az vm start --name myvm --resource-group rg") == "write"
        assert _classify_command("az vm stop --name myvm --resource-group rg") == "write"
        assert _classify_command("az containerapp update --name app --resource-group rg") == "write"
        assert _classify_command("az keyvault secret set --vault-name kv --name secret --value val") == "write"
        assert _classify_command("az aks scale --resource-group rg --name aks --node-count 5") == "write"

    def test_always_block_commands(self):
        assert _classify_command("az group delete --name rg-prod") == "blocked"
        assert _classify_command("az ad user create --display-name foo") == "blocked"
        assert _classify_command("az role assignment create --role Contributor --assignee user") == "blocked"
        assert _classify_command("az lock delete --name mylock") == "blocked"

    def test_always_block_takes_priority_over_write(self):
        # Even if both patterns match, blocked should win
        assert _classify_command("az group delete --name rg --yes") == "blocked"

    def test_case_insensitive_verb_matching(self):
        # Command may have mixed case (unlikely in practice but defensive)
        assert _classify_command("az VM START --name myvm") == "write"

    def test_empty_and_read_only_patterns(self):
        assert _classify_command("az monitor metrics list --resource /subscriptions/sub/...") == "read"
        assert _classify_command("az network vnet show --name vnet --resource-group rg") == "read"


# ---------------------------------------------------------------------------
# execute_azure_cli_command integration tests (mocked)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestExecuteAzureCliCommand:
    async def _import_tool(self):
        try:
            from app.agentic.eol.mcp_servers.azure_cli_executor_server import execute_azure_cli_command
        except ModuleNotFoundError:
            from mcp_servers.azure_cli_executor_server import execute_azure_cli_command  # type: ignore[import-not-found]
        return execute_azure_cli_command

    async def _call(self, command: str, confirmed: bool = False):
        """Helper to call the tool function with a mocked context."""
        execute_azure_cli_command = await self._import_tool()
        ctx = MagicMock()
        result = await execute_azure_cli_command(
            context=ctx,
            command=command,
            confirmed=confirmed,
        )
        return json.loads(result[0].text)

    async def test_write_without_confirmed_returns_plan(self):
        data = await self._call("az storage account delete --name foo --resource-group rg")
        assert data["requires_confirmation"] is True
        assert data["success"] is False
        assert "plan" in data

    async def test_blocked_command_always_blocked(self):
        data = await self._call("az group delete --name rg-prod", confirmed=True)
        assert data["blocked"] is True
        assert data["success"] is False

    async def test_blocked_without_confirmed_also_blocked(self):
        data = await self._call("az group delete --name rg-prod", confirmed=False)
        assert data["blocked"] is True
        assert data["success"] is False

    async def test_read_command_executes(self):
        """Read commands should bypass confirmation and attempt execution."""
        mock_result = MagicMock()
        mock_result.as_text_content.return_value = MagicMock(
            type="text", text=json.dumps({"exit_code": 0, "stdout": "[]", "stderr": ""})
        )
        execute_azure_cli_command = await self._import_tool()
        with (
            patch(f"{_MODULE}._ensure_login", new_callable=AsyncMock),
            patch(f"{_MODULE}._run_subprocess", new_callable=AsyncMock, return_value=mock_result),
        ):
            ctx = MagicMock()
            result = await execute_azure_cli_command(context=ctx, command="az vm list")
            data = json.loads(result[0].text)
            assert data["exit_code"] == 0

    async def test_write_with_confirmed_executes(self):
        """Write commands with confirmed=True should proceed to execution."""
        mock_result = MagicMock()
        mock_result.as_text_content.return_value = MagicMock(
            type="text", text=json.dumps({"exit_code": 0, "stdout": "deleted", "stderr": ""})
        )
        execute_azure_cli_command = await self._import_tool()
        with (
            patch(f"{_MODULE}._ensure_login", new_callable=AsyncMock),
            patch(f"{_MODULE}._run_subprocess", new_callable=AsyncMock, return_value=mock_result),
        ):
            ctx = MagicMock()
            result = await execute_azure_cli_command(
                context=ctx,
                command="az storage account delete --name foo",
                confirmed=True,
            )
            data = json.loads(result[0].text)
            assert data["exit_code"] == 0
