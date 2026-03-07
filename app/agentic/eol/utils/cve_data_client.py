"""
Base CVE data client with retry logic and rate limiting.

Provides abstract base class for CVE data sources (CVE.org, NVD, vendor feeds).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, List
import aiohttp
import asyncio
from dataclasses import dataclass

try:
    from utils.retry import retry_async
    from utils.logging_config import get_logger
    from utils.config import get_config
except ModuleNotFoundError:
    from app.agentic.eol.utils.retry import retry_async
    from app.agentic.eol.utils.logging_config import get_logger
    from app.agentic.eol.utils.config import get_config


logger = get_logger(__name__)


@dataclass
class RateLimiter:
    """Simple token bucket rate limiter for API requests."""

    tokens_per_second: float
    max_tokens: float
    _tokens: float = None
    _last_update: float = None

    def __post_init__(self):
        self._tokens = self.max_tokens
        self._last_update = asyncio.get_event_loop().time()

    async def acquire(self):
        """Acquire a token, waiting if necessary."""
        while True:
            now = asyncio.get_event_loop().time()
            time_passed = now - self._last_update
            self._tokens = min(self.max_tokens, self._tokens + time_passed * self.tokens_per_second)
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            # Wait until we have a token
            wait_time = (1 - self._tokens) / self.tokens_per_second
            await asyncio.sleep(wait_time)


class BaseCVEClient(ABC):
    """Abstract base class for CVE data clients.

    Provides common functionality:
    - Async HTTP requests with aiohttp
    - Retry logic with exponential backoff
    - Rate limiting
    - Error handling
    """

    def __init__(
        self,
        base_url: str,
        rate_limit_per_second: float = 5.0,
        request_timeout: int = 30,
        max_retries: int = 3
    ):
        self.base_url = base_url.rstrip('/')
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(
            tokens_per_second=rate_limit_per_second,
            max_tokens=rate_limit_per_second * 2  # Allow burst
        )
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic and rate limiting.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            **kwargs: Additional arguments for aiohttp request

        Returns:
            JSON response as dict

        Raises:
            aiohttp.ClientError: On HTTP errors after retries exhausted
        """
        await self.rate_limiter.acquire()

        async def _do_request():
            session = await self._get_session()
            logger.debug(f"{method} {url}")
            start_time = asyncio.get_event_loop().time()

            async with session.request(method, url, **kwargs) as response:
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(
                    f"{method} {url} -> {response.status} ({elapsed:.2f}s)"
                )

                if response.status == 404:
                    logger.warning(f"Resource not found: {url}")
                    return None

                if response.status == 429:
                    # Rate limited - let retry logic handle backoff
                    retry_after = response.headers.get('Retry-After', '60')
                    logger.warning(f"Rate limited, retry after {retry_after}s")
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"Rate limited (429)",
                        headers=response.headers
                    )

                response.raise_for_status()
                return await response.json()

        # Use retry_async from existing utility
        try:
            result = await retry_async(
                _do_request,
                retries=self.max_retries,
                exceptions=(
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                )
            )
            return result
        except Exception as e:
            logger.error(f"Request failed after {self.max_retries} retries: {url} - {e}")
            raise

    @abstractmethod
    async def fetch_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single CVE by ID.

        Args:
            cve_id: CVE identifier (e.g., "CVE-2024-0001")

        Returns:
            CVE data as dict, or None if not found
        """
        pass

    @abstractmethod
    async def fetch_cves_since(
        self,
        since_date: datetime,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch CVEs modified since a given date.

        Args:
            since_date: Fetch CVEs modified after this date
            limit: Maximum number of CVEs to return

        Returns:
            List of CVE data dicts
        """
        pass

    @abstractmethod
    async def search_cves(
        self,
        query: Optional[str] = None,
        **filters
    ) -> List[Dict[str, Any]]:
        """Search CVEs with filters.

        Args:
            query: Search query string
            **filters: Additional filters (severity, date range, etc.)

        Returns:
            List of CVE data dicts
        """
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
