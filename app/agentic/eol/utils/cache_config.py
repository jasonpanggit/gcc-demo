"""
Cache TTL Configuration — single source of truth for all cache time-to-live values.

Strategy: L1 (in-memory) + L2 (Cosmos DB persistence)
- L1: Fast, ephemeral, per-process. Miss falls through to L2.
- L2: Persistent, shared across instances. Miss triggers fresh data fetch.

TTL Tiers:
  EPHEMERAL    (5 min):  Real-time operational data (metrics, health status, active alerts)
  SHORT_LIVED  (15 min): Frequently changing data (patch status, current inventory snapshots)
  MEDIUM_LIVED (1 hour): Moderately stable data (resource metadata, SRE diagnostics)
  LONG_LIVED   (24 hours): Stable reference data (EOL dates, OS version catalogs)

Override via environment variables:
  CACHE_TTL_EPHEMERAL    (seconds, default: 300)
  CACHE_TTL_SHORT_LIVED  (seconds, default: 900)
  CACHE_TTL_MEDIUM_LIVED (seconds, default: 3600)
  CACHE_TTL_LONG_LIVED   (seconds, default: 86400)

Usage:
    from utils.cache_config import CacheTTLProfile, get_ttl

    ttl = get_ttl(CacheTTLProfile.EPHEMERAL)  # → 300
    ttl = EPHEMERAL_TTL                        # → 300 (module-level constant)
"""
import os
from enum import IntEnum


class CacheTTLProfile(IntEnum):
    """Standard TTL profiles in seconds. Use these instead of magic numbers."""
    EPHEMERAL    = int(os.getenv("CACHE_TTL_EPHEMERAL",    "300"))    # 5 min
    SHORT_LIVED  = int(os.getenv("CACHE_TTL_SHORT_LIVED",  "900"))    # 15 min
    MEDIUM_LIVED = int(os.getenv("CACHE_TTL_MEDIUM_LIVED", "3600"))   # 1 hour
    LONG_LIVED   = int(os.getenv("CACHE_TTL_LONG_LIVED",   "86400"))  # 24 hours


# Module-level constants for direct import (no enum overhead)
EPHEMERAL_TTL:    int = int(CacheTTLProfile.EPHEMERAL)
SHORT_LIVED_TTL:  int = int(CacheTTLProfile.SHORT_LIVED)
MEDIUM_LIVED_TTL: int = int(CacheTTLProfile.MEDIUM_LIVED)
LONG_LIVED_TTL:   int = int(CacheTTLProfile.LONG_LIVED)


def get_ttl(profile: CacheTTLProfile) -> int:
    """Return TTL seconds for the given profile. Convenience alias."""
    return int(profile)


# Profile name → seconds mapping for legacy dict-based lookups.
# Keys cover both the canonical CacheTTLProfile names and the legacy SreCache
# profile names so callers can migrate incrementally.
TTL_PROFILE_MAP: dict = {
    # Canonical names (new style)
    "ephemeral":    EPHEMERAL_TTL,
    "short_lived":  SHORT_LIVED_TTL,
    "medium_lived": MEDIUM_LIVED_TTL,
    "long_lived":   LONG_LIVED_TTL,
    # Legacy SreCache profile names (backward-compatible aliases)
    "real_time": EPHEMERAL_TTL,     # was 60s → now 300s (EPHEMERAL tier, PRF-06)
    "short":     EPHEMERAL_TTL,     # 5 min  — health checks, alerts
    "medium":    SHORT_LIVED_TTL,   # 15 min — config analysis, costs
    "long":      MEDIUM_LIVED_TTL,  # 1 hr   — dependencies, SLOs
    "daily":     LONG_LIVED_TTL,    # 24 hr  — security score, compliance
}
