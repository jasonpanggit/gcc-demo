"""
API Module Package

This package contains FastAPI router modules organized by functional area.
Each module handles a specific set of related endpoints.

Modules:
    health: Health check and diagnostic endpoints
    
Usage:
    from api.health import router as health_router
    app.include_router(health_router)
"""

__all__ = [
    "health",
]
