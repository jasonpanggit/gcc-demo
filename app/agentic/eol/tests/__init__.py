"""
Tests package initialization
"""
from .mock_data import mock_generator, get_mock_software_inventory, get_mock_os_inventory, get_mock_eol_data
from .mock_agents import MockSoftwareInventoryAgent, MockOSInventoryAgent, get_software_inventory_agent, get_os_inventory_agent

__all__ = [
    'mock_generator',
    'get_mock_software_inventory',
    'get_mock_os_inventory',
    'get_mock_eol_data',
    'MockSoftwareInventoryAgent',
    'MockOSInventoryAgent',
    'get_software_inventory_agent',
    'get_os_inventory_agent',
]
