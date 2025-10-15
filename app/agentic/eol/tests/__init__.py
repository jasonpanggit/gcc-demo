"""
Tests package initialization
"""
from .test_config import test_config, enable_mock_mode, disable_mock_mode
from .mock_data import mock_generator, get_mock_software_inventory, get_mock_os_inventory, get_mock_eol_data
from .mock_agents import MockSoftwareInventoryAgent, MockOSInventoryAgent, get_software_inventory_agent, get_os_inventory_agent

__all__ = [
    'test_config',
    'enable_mock_mode',
    'disable_mock_mode',
    'mock_generator',
    'get_mock_software_inventory',
    'get_mock_os_inventory',
    'get_mock_eol_data',
    'MockSoftwareInventoryAgent',
    'MockOSInventoryAgent',
    'get_software_inventory_agent',
    'get_os_inventory_agent',
]
