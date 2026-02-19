"""Singleton Azure CLI Executor.

Provides centralized Azure CLI command execution with service principal authentication.
Shared across MCP Orchestrator, SRE Orchestrator, and other components.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from app.agentic.eol.utils.logger import get_logger
except ModuleNotFoundError:
    from utils.logger import get_logger


logger = get_logger(__name__)


class AzureCLIExecutor:
    """Singleton Azure CLI executor with service principal authentication.
    
    Usage:
        executor = get_azure_cli_executor()
        result = await executor.execute("az vm list")
    """
    
    _instance: Optional[AzureCLIExecutor] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """Initialize Azure CLI executor (use get_azure_cli_executor() instead)."""
        self._login_lock = asyncio.Lock()
        self._login_completed = False
        self._subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        
    @classmethod
    async def get_instance(cls) -> AzureCLIExecutor:
        """Get singleton instance of Azure CLI executor.
        
        Returns:
            AzureCLIExecutor instance
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    logger.info("Azure CLI executor singleton created")
        return cls._instance
    
    async def execute(
        self,
        command: str,
        timeout: int = 30,
        add_subscription: bool = True
    ) -> Dict[str, Any]:
        """Execute Azure CLI command with automatic authentication.
        
        Args:
            command: Azure CLI command to execute (e.g., "az vm list")
            timeout: Command timeout in seconds (default: 30)
            add_subscription: Whether to add --subscription flag automatically
            
        Returns:
            Dict with status, output/error, and metadata
        """
        # Ensure authenticated
        await self._ensure_login()
        
        # Add subscription context if requested
        if add_subscription and self._subscription_id and "--subscription" not in command:
            command = f"{command} --subscription {self._subscription_id}"
        
        logger.debug(f"Executing Azure CLI: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                # Try to parse JSON output
                output = result.stdout.strip()
                try:
                    parsed = json.loads(output)
                    logger.debug(f"Azure CLI success: {len(parsed) if isinstance(parsed, list) else 'non-list'} result(s)")
                    return {
                        "status": "success",
                        "output": parsed,
                        "result": parsed
                    }
                except json.JSONDecodeError:
                    logger.debug("Azure CLI success: text output")
                    return {
                        "status": "success",
                        "output": output,
                        "result": output
                    }
            else:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Command failed"
                logger.warning(f"Azure CLI failed: {error_msg[:200]}")
                return {
                    "status": "error",
                    "error": error_msg,
                    "returncode": result.returncode
                }
                
        except subprocess.TimeoutExpired:
            logger.error(f"Azure CLI command timed out after {timeout}s")
            return {
                "status": "error",
                "error": f"Command timed out after {timeout} seconds"
            }
        except Exception as exc:
            logger.error(f"Azure CLI execution failed: {exc}")
            return {
                "status": "error",
                "error": str(exc)
            }
    
    async def _ensure_login(self) -> None:
        """Ensure Azure CLI is authenticated with service principal."""
        if self._login_completed:
            return
            
        async with self._login_lock:
            # Double-check after acquiring lock
            if self._login_completed:
                return
            
            # Check if az CLI is available
            if not shutil.which("az"):
                raise RuntimeError("Azure CLI not installed or not in PATH")
            
            # Setup directories
            home_dir = os.environ.get("HOME")
            if not home_dir or not os.path.isdir(home_dir):
                home_dir = "/tmp"
                os.environ["HOME"] = home_dir
                logger.warning(f"HOME not set, using {home_dir}")
            Path(home_dir).mkdir(parents=True, exist_ok=True)
            
            config_dir = os.environ.get("AZURE_CONFIG_DIR")
            if not config_dir:
                config_dir = os.path.join(home_dir, ".azure")
                os.environ["AZURE_CONFIG_DIR"] = config_dir
                logger.info(f"AZURE_CONFIG_DIR set to {config_dir}")
            Path(config_dir).mkdir(parents=True, exist_ok=True)
            
            # Get service principal credentials
            client_id = os.getenv("AZURE_SP_CLIENT_ID")
            client_secret = os.getenv("AZURE_SP_CLIENT_SECRET")
            tenant_id = os.getenv("AZURE_TENANT_ID")
            
            if not all([client_id, client_secret, tenant_id]):
                raise RuntimeError(
                    "Service principal credentials not configured. "
                    "Set AZURE_SP_CLIENT_ID, AZURE_SP_CLIENT_SECRET, and AZURE_TENANT_ID"
                )
            
            # Perform service principal login
            logger.info(f"Authenticating Azure CLI with service principal ({client_id[:8]}...)")
            
            login_cmd = [
                "az", "login", "--service-principal",
                "-u", client_id,
                "-p", client_secret,
                "--tenant", tenant_id
            ]
            
            result = subprocess.run(
                login_cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                logger.error(f"Azure CLI login failed: {error_msg}")
                raise RuntimeError(f"Azure CLI login failed: {error_msg}")
            
            # Set subscription if configured
            if self._subscription_id:
                logger.info(f"Setting Azure subscription to {self._subscription_id}")
                subprocess.run(
                    ["az", "account", "set", "--subscription", self._subscription_id],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True
                )
            
            logger.info("✓ Azure CLI authentication completed")
            self._login_completed = True
    
    def reset_login(self) -> None:
        """Reset login state (for testing or re-authentication)."""
        self._login_completed = False
        logger.info("Azure CLI login state reset")


# Global singleton accessor
_executor_instance: Optional[AzureCLIExecutor] = None


async def get_azure_cli_executor() -> AzureCLIExecutor:
    """Get the singleton Azure CLI executor instance.
    
    Returns:
        AzureCLIExecutor instance
    """
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = await AzureCLIExecutor.get_instance()
    return _executor_instance
