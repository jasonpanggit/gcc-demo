"""
API Module Package

This package contains modular API route handlers organized by functional area.
Each module provides focused endpoints for specific features.

Modules:
    health: Health check and system status endpoints
    cache: Cache management and statistics endpoints
    inventory: Software and OS inventory endpoints
    eol: End-of-Life search and management endpoints
"""

__all__ = ["health", "cache", "inventory", "eol"]
