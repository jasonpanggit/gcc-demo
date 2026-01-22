"""
Enhanced Cache Statistics Manager for EOL Multi-Agent App
Tracks detailed statistics for agent caches and inventory cache
"""
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from collections import defaultdict, deque

@dataclass
class CacheHitMissStats:
    """Statistics for cache hit/miss tracking"""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.hits / self.total_requests) * 100
    
    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate as percentage"""
        return 100.0 - self.hit_rate
    
    def record_hit(self):
        """Record a cache hit"""
        self.hits += 1
        self.total_requests += 1
    
    def record_miss(self):
        """Record a cache miss"""
        self.misses += 1
        self.total_requests += 1

@dataclass
class UrlStats:
    """Statistics for individual URL performance"""
    url: str = ""
    request_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    records_extracted: int = 0
    total_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    max_response_time_ms: float = 0.0
    error_count: int = 0
    last_accessed: Optional[str] = None
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate for this URL"""
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0
    
    @property
    def avg_response_time_ms(self) -> float:
        """Calculate average response time for this URL"""
        return (self.total_response_time_ms / self.request_count) if self.request_count > 0 else 0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate for this URL"""
        return (self.error_count / self.request_count * 100) if self.request_count > 0 else 0

@dataclass
class AgentPerformanceStats:
    """Performance statistics for an agent"""
    request_count: int = 0
    total_response_time_ms: float = 0.0
    min_response_time_ms: float = float('inf')
    max_response_time_ms: float = 0.0
    last_request_time: Optional[str] = None
    error_count: int = 0
    cache_stats: CacheHitMissStats = None
    url_stats: Dict[str, UrlStats] = None
    
    def __post_init__(self):
        if self.cache_stats is None:
            self.cache_stats = CacheHitMissStats()
        if self.url_stats is None:
            self.url_stats = {}
    
    @property
    def avg_response_time_ms(self) -> float:
        """Calculate average response time"""
        if self.request_count == 0:
            return 0.0
        return self.total_response_time_ms / self.request_count
    
    def record_request(self, response_time_ms: float, was_cache_hit: bool = False, 
                      had_error: bool = False, url: str = "", records_extracted: int = 0):
        """Record a request with its performance metrics"""
        self.request_count += 1
        self.total_response_time_ms += response_time_ms
        self.min_response_time_ms = min(self.min_response_time_ms, response_time_ms)
        self.max_response_time_ms = max(self.max_response_time_ms, response_time_ms)
        self.last_request_time = datetime.now(timezone.utc).isoformat()
        
        if had_error:
            self.error_count += 1
        
        if was_cache_hit:
            self.cache_stats.record_hit()
        else:
            self.cache_stats.record_miss()
        
        # Track URL-specific statistics
        if url:
            if url not in self.url_stats:
                self.url_stats[url] = UrlStats(url=url)
            
            url_stat = self.url_stats[url]
            url_stat.request_count += 1
            if records_extracted:
                url_stat.records_extracted += records_extracted
            url_stat.total_response_time_ms += response_time_ms
            url_stat.min_response_time_ms = min(url_stat.min_response_time_ms, response_time_ms)
            url_stat.max_response_time_ms = max(url_stat.max_response_time_ms, response_time_ms)
            url_stat.last_accessed = self.last_request_time
            
            if had_error:
                url_stat.error_count += 1
            
            if was_cache_hit:
                url_stat.cache_hits += 1
            else:
                url_stat.cache_misses += 1

class CacheStatsManager:
    """
    Enhanced cache statistics manager that tracks real-time metrics
    """
    
    def __init__(self):
        self.agent_stats: Dict[str, AgentPerformanceStats] = defaultdict(lambda: AgentPerformanceStats())
        self.inventory_stats = CacheHitMissStats()
        self.cosmos_stats = CacheHitMissStats()
        self.session_start_time = datetime.now(timezone.utc)
        
        # Recent activity tracking (last 100 requests per type)
        self.recent_agent_requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.recent_inventory_requests = deque(maxlen=100)
        self.recent_cosmos_requests = deque(maxlen=100)
        
        # Performance tracking
        self.performance_metrics = {
            "total_requests_served": 0,
            "total_cache_hits": 0,
            "total_cache_misses": 0,
            "total_errors": 0,
            "uptime_seconds": 0
        }
    
    def record_agent_request(self, agent_name: str, *args, **kwargs):
        """Record an agent request with performance metrics (backward compatible)"""
        try:
            # Default values
            url = ""
            response_time_ms = 0.0
            was_cache_hit = False
            had_error = False
            software_name = ""
            version = ""
            error_message = ""
            records_extracted = 0
            
            # Handle different calling patterns
            if len(args) >= 1:
                first_arg = args[0]
                
                if isinstance(first_arg, (int, float)):
                    # Old format: (agent_name, response_time_ms, was_cache_hit, had_error, software_name, version, url)
                    response_time_ms = float(first_arg)
                    if len(args) >= 2:
                        was_cache_hit = args[1] if isinstance(args[1], bool) else False
                    if len(args) >= 3:
                        had_error = args[2] if isinstance(args[2], bool) else False
                    if len(args) >= 4:
                        software_name = args[3] if isinstance(args[3], str) else ""
                    if len(args) >= 5:
                        version = args[4] if isinstance(args[4], str) else ""
                    if len(args) >= 6:
                        url = args[5] if isinstance(args[5], str) else ""
                        
                elif isinstance(first_arg, str):
                    # New format: (agent_name, url, response_time, success, error_message, ...)
                    url = first_arg
                    if len(args) >= 2 and isinstance(args[1], (int, float)):
                        response_time_ms = float(args[1] * 1000)  # Convert from seconds to ms
                    if len(args) >= 3 and isinstance(args[2], bool):
                        success = args[2]
                        had_error = not success
                    if len(args) >= 4 and isinstance(args[3], str):
                        error_message = args[3]
            
            # Handle keyword arguments (both old and new style)
            if 'response_time_ms' in kwargs:
                response_time_ms = float(kwargs['response_time_ms'])
            if 'response_time' in kwargs:
                response_time_ms = float(kwargs['response_time'] * 1000)  # Convert from seconds
            if 'url' in kwargs:
                url = kwargs['url']
            if 'was_cache_hit' in kwargs:
                was_cache_hit = kwargs['was_cache_hit']
            if 'had_error' in kwargs:
                had_error = kwargs['had_error']
            if 'success' in kwargs:
                had_error = not kwargs['success']
            if 'software_name' in kwargs:
                software_name = kwargs['software_name']
            if 'version' in kwargs:
                version = kwargs['version']
            if 'error_message' in kwargs:
                error_message = kwargs['error_message']
            if 'records_extracted' in kwargs:
                try:
                    records_extracted = int(kwargs['records_extracted'])
                except (TypeError, ValueError):
                    records_extracted = 0
            
            # Update agent-specific stats
            self.agent_stats[agent_name].record_request(
                response_time_ms,
                was_cache_hit,
                had_error,
                url,
                records_extracted,
            )
            
            # Update global performance metrics
            self.performance_metrics["total_requests_served"] += 1
            if was_cache_hit:
                self.performance_metrics["total_cache_hits"] += 1
            else:
                self.performance_metrics["total_cache_misses"] += 1
            if had_error:
                self.performance_metrics["total_errors"] += 1
            
            # Track recent activity
            request_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent_name,
                "software": software_name,
                "version": version,
                "url": url,
                "response_time_ms": response_time_ms,
                "cache_hit": was_cache_hit,
                "error": had_error,
                "error_message": error_message if had_error else ""
            }
            self.recent_agent_requests[agent_name].append(request_info)
            
        except Exception as e:
            print(f"Error recording agent request stats: {e}")
            print(f"Parameters: agent_name={agent_name}, args={args}, kwargs={kwargs}")
            import traceback
            traceback.print_exc()
    
    def record_inventory_request(self, response_time_ms: float, was_cache_hit: bool = False, 
                               items_count: int = 0):
        """Record an inventory cache request"""
        try:
            if was_cache_hit:
                self.inventory_stats.record_hit()
            else:
                self.inventory_stats.record_miss()
            
            # Track recent activity
            request_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_time_ms": response_time_ms,
                "cache_hit": was_cache_hit,
                "items_count": items_count
            }
            self.recent_inventory_requests.append(request_info)
            
        except Exception as e:
            print(f"Error recording inventory request stats: {e}")
    
    def record_cosmos_request(self, response_time_ms: float, was_cache_hit: bool = False,
                            operation: str = "query"):
        """Record a Cosmos DB cache request"""
        try:
            if was_cache_hit:
                self.cosmos_stats.record_hit()
            else:
                self.cosmos_stats.record_miss()
            
            # Track recent activity
            request_info = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "response_time_ms": response_time_ms,
                "cache_hit": was_cache_hit
            }
            self.recent_cosmos_requests.append(request_info)
            
        except Exception as e:
            print(f"Error recording cosmos request stats: {e}")
    
    def get_agent_statistics(self) -> Dict[str, Any]:
        """Get comprehensive agent statistics"""
        try:
            agent_data = {}
            total_requests = 0
            total_cache_hits = 0
            total_errors = 0
            
            for agent_name, stats in self.agent_stats.items():
                total_requests += stats.request_count
                total_cache_hits += stats.cache_stats.hits
                total_errors += stats.error_count
                
                agent_data[agent_name] = {
                    "request_count": stats.request_count,
                    "cache_hit_rate": stats.cache_stats.hit_rate,
                    "cache_hits": stats.cache_stats.hits,
                    "cache_misses": stats.cache_stats.misses,
                    "avg_response_time_ms": stats.avg_response_time_ms,
                    "min_response_time_ms": stats.min_response_time_ms if stats.min_response_time_ms != float('inf') else 0,
                    "max_response_time_ms": stats.max_response_time_ms,
                    "error_count": stats.error_count,
                    "error_rate": (stats.error_count / stats.request_count * 100) if stats.request_count > 0 else 0,
                    "last_request_time": stats.last_request_time,
                    "recent_requests": list(self.recent_agent_requests[agent_name])[-10:],  # Last 10 requests
                    "url_stats": {
                        url: {
                            "url": url_stat.url,
                            "request_count": url_stat.request_count,
                            "hit_rate": url_stat.hit_rate,
                            "avg_response_time_ms": url_stat.avg_response_time_ms,
                            "min_response_time_ms": url_stat.min_response_time_ms if url_stat.min_response_time_ms != float('inf') else 0,
                            "max_response_time_ms": url_stat.max_response_time_ms,
                            "error_rate": url_stat.error_rate,
                            "cache_hits": url_stat.cache_hits,
                            "cache_misses": url_stat.cache_misses,
                            "records_extracted": url_stat.records_extracted,
                            "error_count": url_stat.error_count,
                            "last_accessed": url_stat.last_accessed
                        } for url, url_stat in stats.url_stats.items()
                    }
                }
            
            return {
                "agents": agent_data,
                "summary": {
                    "total_agents": len(agent_data),
                    "total_requests": total_requests,
                    "total_cache_hits": total_cache_hits,
                    "total_errors": total_errors,
                    "overall_hit_rate": (total_cache_hits / total_requests * 100) if total_requests > 0 else 0,
                    "session_uptime_seconds": (datetime.now(timezone.utc) - self.session_start_time).total_seconds()
                }
            }
        except Exception as e:
            return {"error": f"Error getting agent statistics: {e}"}
    
    def get_inventory_statistics(self) -> Dict[str, Any]:
        """Get inventory cache statistics"""
        try:
            recent_activity = list(self.recent_inventory_requests)[-20:]  # Last 20 requests
            avg_response_time = sum(r["response_time_ms"] for r in recent_activity) / len(recent_activity) if recent_activity else 0
            
            return {
                "hit_rate": self.inventory_stats.hit_rate,
                "hits": self.inventory_stats.hits,
                "misses": self.inventory_stats.misses,
                "total_requests": self.inventory_stats.total_requests,
                "avg_response_time_ms": avg_response_time,
                "recent_activity": recent_activity
            }
        except Exception as e:
            return {"error": f"Error getting inventory statistics: {e}"}
    
    def get_cosmos_statistics(self) -> Dict[str, Any]:
        """Get Cosmos DB cache statistics"""
        try:
            recent_activity = list(self.recent_cosmos_requests)[-20:]  # Last 20 requests
            avg_response_time = sum(r["response_time_ms"] for r in recent_activity) / len(recent_activity) if recent_activity else 0
            
            return {
                "hit_rate": self.cosmos_stats.hit_rate,
                "hits": self.cosmos_stats.hits,
                "misses": self.cosmos_stats.misses,
                "total_requests": self.cosmos_stats.total_requests,
                "avg_response_time_ms": avg_response_time,
                "recent_activity": recent_activity
            }
        except Exception as e:
            return {"error": f"Error getting cosmos statistics: {e}"}
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary"""
        try:
            uptime_seconds = (datetime.now(timezone.utc) - self.session_start_time).total_seconds()
            
            # Calculate overall average response time across all agents
            total_response_time = 0.0
            total_requests = 0
            for agent_stats in self.agent_stats.values():
                total_response_time += agent_stats.total_response_time_ms
                total_requests += agent_stats.request_count
            
            avg_response_time_ms = (total_response_time / total_requests) if total_requests > 0 else 0
            
            return {
                "uptime_seconds": uptime_seconds,
                "uptime_formatted": self._format_uptime(uptime_seconds),
                "total_requests_served": self.performance_metrics["total_requests_served"],
                "total_requests": total_requests,  # Use calculated total from agent stats
                "total_cache_hits": self.performance_metrics["total_cache_hits"],
                "total_cache_misses": self.performance_metrics["total_cache_misses"],
                "total_errors": self.performance_metrics["total_errors"],
                "overall_hit_rate": (
                    self.performance_metrics["total_cache_hits"] / 
                    (self.performance_metrics["total_cache_hits"] + self.performance_metrics["total_cache_misses"]) * 100
                ) if (self.performance_metrics["total_cache_hits"] + self.performance_metrics["total_cache_misses"]) > 0 else 0,
                "overall_error_rate": (
                    self.performance_metrics["total_errors"] / 
                    self.performance_metrics["total_requests_served"] * 100
                ) if self.performance_metrics["total_requests_served"] > 0 else 0,
                "error_rate": (
                    self.performance_metrics["total_errors"] / 
                    self.performance_metrics["total_requests_served"] * 100
                ) if self.performance_metrics["total_requests_served"] > 0 else 0,  # Alias for compatibility
                "avg_response_time_ms": avg_response_time_ms,
                "requests_per_second": (
                    self.performance_metrics["total_requests_served"] / uptime_seconds
                ) if uptime_seconds > 0 else 0
            }
        except Exception as e:
            return {"error": f"Error getting performance summary: {e}"}
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        try:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m {secs}s"
            elif hours > 0:
                return f"{hours}h {minutes}m {secs}s"
            elif minutes > 0:
                return f"{minutes}m {secs}s"
            else:
                return f"{secs}s"
        except Exception:
            return "Unknown"
    
    def get_all_statistics(self) -> Dict[str, Any]:
        """Get all cache statistics in one call"""
        return {
            "agent_stats": self.get_agent_statistics(),
            "inventory_stats": self.get_inventory_statistics(),
            "cosmos_stats": self.get_cosmos_statistics(),
            "performance_summary": self.get_performance_summary(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def reset_statistics(self):
        """Reset all statistics (useful for testing or fresh start)"""
        self.agent_stats.clear()
        self.inventory_stats = CacheHitMissStats()
        self.cosmos_stats = CacheHitMissStats()
        self.session_start_time = datetime.now(timezone.utc)
        self.performance_metrics = {
            "total_requests_served": 0,
            "total_cache_hits": 0,
            "total_cache_misses": 0,
            "total_errors": 0,
            "uptime_seconds": 0
        }
        for deque_obj in self.recent_agent_requests.values():
            deque_obj.clear()
        self.recent_inventory_requests.clear()
        self.recent_cosmos_requests.clear()

    def reset_all_stats(self) -> None:
        """Backward compatible alias for reset_statistics."""
        self.reset_statistics()

# Global cache statistics manager instance
cache_stats_manager = CacheStatsManager()
