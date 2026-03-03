"""
Local-only tests for MCPConfigLoader (NOT committed to git per .gitignore).

Run from app/agentic/eol/:
    pytest tests/test_mcp_config_loader.py -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.mcp_config_loader import MCPConfigLoader, MCPServerConfig, MCPServersFile, _interpolate_env


YAML_DIR = Path(__file__).resolve().parent.parent / "config"


# ---------------------------------------------------------------------------
# _interpolate_env
# ---------------------------------------------------------------------------


def test_interpolate_env_set_var():
    os.environ["_TEST_VAR_A"] = "hello"
    try:
        result = _interpolate_env("prefix_${_TEST_VAR_A}_suffix")
        assert result == "prefix_hello_suffix"
    finally:
        del os.environ["_TEST_VAR_A"]


def test_interpolate_env_default_used_when_unset():
    os.environ.pop("_TEST_VAR_UNSET", None)
    result = _interpolate_env("${_TEST_VAR_UNSET:-mydefault}")
    assert result == "mydefault"


def test_interpolate_env_empty_default():
    os.environ.pop("_TEST_VAR_UNSET", None)
    result = _interpolate_env("${_TEST_VAR_UNSET:-}")
    assert result == ""


def test_interpolate_env_no_default_and_unset_returns_empty():
    os.environ.pop("_TEST_VAR_UNSET", None)
    result = _interpolate_env("${_TEST_VAR_UNSET}")
    assert result == ""


def test_interpolate_env_set_var_overrides_default():
    os.environ["_TEST_VAR_B"] = "override"
    try:
        result = _interpolate_env("${_TEST_VAR_B:-fallback}")
        assert result == "override"
    finally:
        del os.environ["_TEST_VAR_B"]


# ---------------------------------------------------------------------------
# MCPConfigLoader.load()
# ---------------------------------------------------------------------------


def test_load_returns_mcp_servers_file():
    loader = MCPConfigLoader()
    cfg = loader.load()
    assert isinstance(cfg, MCPServersFile)


def test_load_version():
    loader = MCPConfigLoader()
    cfg = loader.load()
    assert cfg.version == "1.0"


def test_load_all_10_servers():
    loader = MCPConfigLoader()
    cfg = loader.load()
    assert len(cfg.servers) == 10


def test_load_all_expected_labels():
    loader = MCPConfigLoader()
    cfg = loader.load()
    labels = {s.label for s in cfg.servers}
    expected = {
        "azure", "sre", "network", "compute", "storage",
        "monitor", "patch", "os_eol", "inventory", "azure_cli_executor",
    }
    assert labels == expected


def test_load_is_cached():
    loader = MCPConfigLoader()
    cfg1 = loader.load()
    cfg2 = loader.load()
    assert cfg1 is cfg2


def test_load_priorities():
    loader = MCPConfigLoader()
    cfg = loader.load()
    by_label = {s.label: s for s in cfg.servers}
    assert by_label["azure"].priority == 5
    assert by_label["azure_cli_executor"].priority == 15
    for label in ("sre", "network", "compute", "storage", "monitor", "patch", "os_eol", "inventory"):
        assert by_label[label].priority == 10


def test_load_azure_command_node():
    loader = MCPConfigLoader()
    cfg = loader.load()
    azure = next(s for s in cfg.servers if s.label == "azure")
    assert azure.command == "node"


def test_load_python_servers_use_python_command():
    loader = MCPConfigLoader()
    cfg = loader.load()
    for s in cfg.servers:
        if s.label != "azure":
            assert s.command == "python", f"{s.label} should use python command"


def test_load_azure_args_contain_npx():
    loader = MCPConfigLoader()
    cfg = loader.load()
    azure = next(s for s in cfg.servers if s.label == "azure")
    assert "npx" in azure.args
    assert "@azure/mcp@latest" in azure.args


def test_load_python_server_args_contain_script_path():
    loader = MCPConfigLoader()
    cfg = loader.load()
    sre = next(s for s in cfg.servers if s.label == "sre")
    assert len(sre.args) == 1
    assert "sre_mcp_server.py" in sre.args[0]


def test_load_sre_domains():
    loader = MCPConfigLoader()
    cfg = loader.load()
    sre = next(s for s in cfg.servers if s.label == "sre")
    assert "sre" in sre.domains
    assert "health" in sre.domains


# ---------------------------------------------------------------------------
# MCPConfigLoader.get_enabled_servers() — env var toggling
# ---------------------------------------------------------------------------


def test_get_enabled_servers_default_all_10():
    # Ensure env vars not set that would disable servers
    for env_var in ("SRE_ENABLED", "NETWORK_MCP_ENABLED", "AZURE_MCP_ENABLED"):
        os.environ.pop(env_var, None)
    loader = MCPConfigLoader()
    enabled = loader.get_enabled_servers()
    assert len(enabled) == 10


def test_get_enabled_servers_sre_disabled():
    os.environ["SRE_ENABLED"] = "false"
    try:
        loader = MCPConfigLoader()
        enabled = loader.get_enabled_servers()
        labels = [s.label for s in enabled]
        assert "sre" not in labels
        assert len(enabled) == 9
    finally:
        del os.environ["SRE_ENABLED"]


def test_get_enabled_servers_monitor_disabled():
    os.environ["MONITOR_MCP_ENABLED"] = "false"
    try:
        loader = MCPConfigLoader()
        enabled = loader.get_enabled_servers()
        labels = [s.label for s in enabled]
        assert "monitor" not in labels
        assert len(enabled) == 9
    finally:
        del os.environ["MONITOR_MCP_ENABLED"]


def test_get_enabled_servers_default_when_env_var_unset():
    """Unset env var → uses default true → server included."""
    os.environ.pop("MONITOR_MCP_ENABLED", None)
    loader = MCPConfigLoader()
    enabled = loader.get_enabled_servers()
    labels = [s.label for s in enabled]
    assert "monitor" in labels


def test_get_enabled_servers_azure_disabled():
    os.environ["AZURE_MCP_ENABLED"] = "false"
    try:
        loader = MCPConfigLoader()
        enabled = loader.get_enabled_servers()
        labels = [s.label for s in enabled]
        assert "azure" not in labels
        assert len(enabled) == 9
    finally:
        del os.environ["AZURE_MCP_ENABLED"]


# ---------------------------------------------------------------------------
# MCPConfigLoader.get_all_servers()
# ---------------------------------------------------------------------------


def test_get_all_servers_always_returns_10():
    os.environ["SRE_ENABLED"] = "false"
    try:
        loader = MCPConfigLoader()
        all_servers = loader.get_all_servers()
        assert len(all_servers) == 10
    finally:
        del os.environ["SRE_ENABLED"]


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_mcp_server_config_rejects_empty_name():
    with pytest.raises(Exception):
        MCPServerConfig(name="", label="sre", command="python")


def test_mcp_server_config_rejects_empty_label():
    with pytest.raises(Exception):
        MCPServerConfig(name="sre_mcp", label="", command="python")


def test_mcp_server_config_defaults():
    cfg = MCPServerConfig(name="test", label="test", command="python")
    assert cfg.args == []
    assert cfg.domains == []
    assert cfg.priority == 10
    assert cfg.enabled is True
    assert cfg.env == {}


def test_mcp_servers_file_defaults():
    svc = MCPServersFile(servers=[
        MCPServerConfig(name="test", label="test", command="python")
    ])
    assert svc.version == "1.0"


# ---------------------------------------------------------------------------
# Default config path
# ---------------------------------------------------------------------------


def test_default_config_path_resolves_correctly():
    loader = MCPConfigLoader()
    assert loader._path.exists(), f"Default config not found: {loader._path}"
    assert loader._path.name == "mcp_servers.yaml"


def test_custom_config_path():
    path = YAML_DIR / "mcp_servers.yaml"
    loader = MCPConfigLoader(config_path=str(path))
    assert loader._path == path
