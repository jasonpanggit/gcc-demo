"""
Authentication middleware for FastAPI.

Supports simple API key mode (recommended for initial deployment) and a
placeholder for Azure AD JWT validation (expandable). Behavior controlled
by environment variables:

- AUTH_MODE: 'none' (default), 'api-key'
- API_KEYS: comma-separated API keys to accept when AUTH_MODE=api-key

The middleware protects API routes (paths starting with /api/) by default,
while allowing a configurable whitelist (health checks, metrics, docs).
"""
import os
import logging
from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def _get_api_keys() -> List[str]:
    raw = os.getenv("API_KEYS", "")
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, whitelist_paths: List[str] = None):
        super().__init__(app)
        self.auth_mode = os.getenv("AUTH_MODE", "none").lower()
        self.api_keys = _get_api_keys()
        self.whitelist_paths = whitelist_paths or [
            "/health",
            "/api/health",
            "/api/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/static",
            "/",
        ]

    async def dispatch(self, request: Request, call_next):
        # Allow preflight and static resources
        path = request.url.path
        for prefix in self.whitelist_paths:
            if path == prefix or path.startswith(prefix + "/"):
                return await call_next(request)

        if self.auth_mode == "none":
            return await call_next(request)

        if self.auth_mode == "api-key":
            # Accept API key from X-API-Key header or Authorization: ApiKey <key>
            incoming_key = None
            if "x-api-key" in request.headers:
                incoming_key = request.headers.get("x-api-key")
            else:
                auth = request.headers.get("authorization")
                if auth:
                    if auth.startswith("ApiKey "):
                        incoming_key = auth[len("ApiKey "):].strip()
                    elif auth.startswith("Bearer "):
                        # Some clients may send API key as Bearer token
                        incoming_key = auth[len("Bearer "):].strip()

            if not incoming_key:
                logger.warning("Unauthorized request - missing API key")
                return Response(content="Unauthorized", status_code=401)

            if incoming_key in self.api_keys:
                return await call_next(request)

            logger.warning("Unauthorized request - invalid API key")
            return Response(content="Unauthorized", status_code=401)

        # Placeholder for Azure AD mode
        if self.auth_mode == "azure-ad":
            # Proper Azure AD JWT validation requires fetching JWKS and verifying
            # signatures and claims. Implementing full validation here introduces
            # an external dependency (python-jose or PyJWT + cryptography).
            # For now, reject requests to avoid accidental exposure.
            logger.error("Azure AD auth mode requested but not implemented in middleware")
            return Response(content="Unauthorized - Azure AD validation not configured", status_code=401)

        # Default: deny
        return Response(content="Unauthorized", status_code=401)
