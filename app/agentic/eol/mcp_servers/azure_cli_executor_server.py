"""Azure CLI MCP Server

Provides an MCP-compliant tool that can execute Azure CLI commands using
service principal credentials supplied via environment variables.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from typing import Annotated, Optional

import logging
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import TextContent


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class CliExecutionResult:
    """Container for Azure CLI execution results."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

    def as_text_content(self) -> TextContent:
        """Convert the result into MCP text content."""
        payload = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        return TextContent(type="text", text=payload)


_server = FastMCP(name="azure-cli-executor")
_login_lock = asyncio.Lock()
_login_completed = False


def _build_cli_command(command: str) -> list[str]:
    """Validate and split an Azure CLI command string."""
    if not command:
        raise ValueError("Command must be provided and start with 'az'.")

    parts = shlex.split(command)
    if not parts:
        raise ValueError("Command must contain at least the 'az' executable.")
    if parts[0] != "az":
        raise ValueError("Only Azure CLI commands are permitted (must start with 'az').")
    return parts


async def _run_subprocess(command: list[str], *, cwd: Optional[str] = None, timeout: int = 300) -> CliExecutionResult:
    """Run a subprocess asynchronously and capture stdout/stderr."""
    start = time.perf_counter()
    logger.info("Executing command: %s", " ".join(command))
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise TimeoutError(f"Command timed out after {timeout} seconds")

    duration = time.perf_counter() - start
    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

    return CliExecutionResult(
        command=" ".join(command),
        exit_code=proc.returncode,
        stdout=stdout.strip(),
        stderr=stderr.strip(),
        duration_seconds=duration,
    )


async def _ensure_login() -> None:
    """Ensure a successful az login using the configured service principal."""
    global _login_completed

    if _login_completed:
        return

    async with _login_lock:
        if _login_completed:
            return

        if not shutil.which("az"):
            raise RuntimeError(
                "Azure CLI executable not found on PATH. Install Azure CLI in the container image "
                "or attach the azure-cli extension before starting the server."
            )

        home_dir = os.environ.get("HOME")
        if not home_dir or not os.path.isdir(home_dir):
            home_dir = "/tmp"
            os.environ["HOME"] = home_dir
            logger.warning("HOME not set or inaccessible; defaulting to %s", home_dir)
        Path(home_dir).mkdir(parents=True, exist_ok=True)

        config_dir = os.environ.get("AZURE_CONFIG_DIR")
        if not config_dir:
            config_dir = os.path.join(home_dir, ".azure")
            os.environ["AZURE_CONFIG_DIR"] = config_dir
            logger.info("AZURE_CONFIG_DIR not set; using %s", config_dir)
        Path(config_dir).mkdir(parents=True, exist_ok=True)

        client_id = os.getenv("AZURE_SP_CLIENT_ID")
        client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")

        if not all([client_id, client_secret, tenant_id]):
            raise RuntimeError(
                "Missing service principal credentials. Please set AZURE_SP_CLIENT_ID, "
                "AZURE_SP_CLIENT_SECRET, and AZURE_TENANT_ID before starting the server."
            )

        login_command = [
            "az",
            "login",
            "--service-principal",
            "-u",
            client_id,
            "-p",
            client_secret,
            "--tenant",
            tenant_id,
        ]

        result = await _run_subprocess(login_command, timeout=120)
        if result.exit_code != 0:
            raise RuntimeError(f"az login failed: {result.stderr or result.stdout}")

        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        if subscription_id:
            await _run_subprocess(
                ["az", "account", "set", "--subscription", subscription_id],
                timeout=60,
            )

        _login_completed = True


@_server.tool(
    name="azure_cli-execute-command",
    description=(
        "Execute an Azure CLI command using the configured service principal. "
        "The command must start with 'az'. The tool returns JSON with stdout, stderr, "
        "exit code, duration, and the executed command."
    ),
)
async def execute_azure_cli_command(
    context: Context,
    command: Annotated[str, "Complete Azure CLI command beginning with 'az'."],
    working_directory: Annotated[
        Optional[str],
        "Optional working directory for the command. Defaults to the current directory.",
    ] = None,
    timeout_seconds: Annotated[
        int,
        "Maximum time (seconds) to wait for the command to finish. Defaults to 300 seconds.",
    ] = 300,
) -> list[TextContent]:
    """Run the requested Azure CLI command and return the captured output."""
    await _ensure_login()
    validated_command = _build_cli_command(command)
    result = await _run_subprocess(validated_command, cwd=working_directory, timeout=timeout_seconds)

    if result.exit_code != 0 and not result.stderr:
        result.stderr = "Azure CLI command exited with a non-zero status code."

    return [result.as_text_content()]


def main() -> None:
    """Entry point for the MCP server."""
    if "PYTHONPATH" not in os.environ:
        # Ensure the current working directory (workspace root) is on sys.path when started via subprocess.
        os.environ["PYTHONPATH"] = os.getcwd()

    try:
        _server.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
