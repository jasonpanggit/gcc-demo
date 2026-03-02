"""MCP Server Configuration Loader.

Parses and validates ``config/mcp_servers.yaml`` into typed Pydantic models,
with support for ``${VAR:-default}`` environment variable interpolation.

Typical usage::

    from utils.mcp_config_loader import MCPConfigLoader

    loader = MCPConfigLoader()
    enabled = loader.get_enabled_servers()   # List[MCPServerConfig]

To disable a server at runtime::

    SRE_ENABLED=false uvicorn main:app --reload

"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}")

_DEFAULT_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"
)


def _interpolate_env(text: str) -> str:
    """Replace ``${VAR:-default}`` tokens with their env values or defaults.

    - ``${VAR}`` → ``os.environ['VAR']`` or ``""`` if unset
    - ``${VAR:-default}`` → ``os.environ['VAR']`` or ``"default"`` if unset
    """

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        var_name = m.group(1)
        default = m.group(2) or ""
        return os.environ.get(var_name, default)

    return _ENV_PATTERN.sub(_replace, text)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class MCPServerConfig(BaseModel):
    """Validated configuration for a single MCP server."""

    name: str
    label: str
    command: str
    args: List[str] = []
    domains: List[str] = []
    priority: int = 10
    enabled: bool = True
    env: Dict[str, str] = {}

    @model_validator(mode="after")
    def _validate(self) -> "MCPServerConfig":
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.label.strip():
            raise ValueError("label must not be empty")
        return self


class MCPServersFile(BaseModel):
    """Top-level structure of ``mcp_servers.yaml``."""

    version: str = "1.0"
    servers: List[MCPServerConfig]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class MCPConfigLoader:
    """Loads and caches MCP server configuration from a YAML file.

    Parameters
    ----------
    config_path:
        Path to the YAML file.  Defaults to
        ``<eol-root>/config/mcp_servers.yaml``.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._path: Path = (
            Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        )
        self._loaded: Optional[MCPServersFile] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> MCPServersFile:
        """Parse, interpolate, and validate the YAML config (lazy, cached).

        Returns
        -------
        MCPServersFile
            Validated config object.

        Raises
        ------
        FileNotFoundError
            If the config file does not exist.
        yaml.YAMLError
            If the file contains invalid YAML.
        pydantic.ValidationError
            If the YAML structure fails schema validation.
        """
        if self._loaded is not None:
            return self._loaded

        logger.debug("Loading MCP server config from %s", self._path)
        raw = self._path.read_text(encoding="utf-8")
        interpolated = _interpolate_env(raw)
        data = yaml.safe_load(interpolated)
        self._loaded = MCPServersFile(**data)
        logger.debug(
            "Loaded %d MCP server definitions (version %s)",
            len(self._loaded.servers),
            self._loaded.version,
        )
        return self._loaded

    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """Return only servers where ``enabled=True`` after env interpolation."""
        enabled = [s for s in self.load().servers if s.enabled]
        disabled_count = len(self.load().servers) - len(enabled)
        if disabled_count:
            disabled_labels = [
                s.label for s in self.load().servers if not s.enabled
            ]
            logger.info(
                "MCP config: %d/%d servers enabled (%d disabled: %s)",
                len(enabled),
                len(self.load().servers),
                disabled_count,
                disabled_labels,
            )
        return enabled

    def get_all_servers(self) -> List[MCPServerConfig]:
        """Return all server definitions regardless of enabled flag."""
        return self.load().servers


__all__ = ["MCPConfigLoader", "MCPServerConfig", "MCPServersFile"]
