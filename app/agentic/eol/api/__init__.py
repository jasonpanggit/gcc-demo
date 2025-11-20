"""
API Module Package

This package contains modular API route handlers organized by functional area.
Each module provides focused endpoints for specific features.

Modules:
    health: Health check and system status endpoints
    cache: Cache management and statistics endpoints
    inventory: Software and OS inventory endpoints
    inventory_asst: Inventory assistant conversational endpoints
    eol: End-of-Life search and management endpoints
    alerts: Alert configuration and email notification endpoints
    agents: Agent configuration and management endpoints
    communications: Communication logs and agent interaction tracking endpoints
    debug: Debug, diagnostics, validation, and notification endpoints
"""

__all__ = [
    "health",
    "cache",
    "inventory",
    "inventory_asst",
    "eol",
    "alerts",
    "agents",
    "communications",
    "debug"
]
