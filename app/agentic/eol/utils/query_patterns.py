"""
Centralized Query Pattern Definitions
Single source of truth for all query pattern matching across the application
"""
import re
from typing import List, Dict, Any


class QueryPatterns:
    """Centralized query pattern definitions for EOL analysis"""
    
    # EOL-related patterns
    EOL_PATTERNS = [
        'end of life', 'end-of-life', 'eol', 'support status',
        'lifecycle', 'when does', 'reach end', 'support end',
        'retire', 'deprecated', 'sunset', 'maintenance end',
        'expiry', 'expires', 'expiration'
    ]
    
    # Approaching EOL patterns (more specific)
    APPROACHING_EOL_PATTERNS = [
        'approaching end', 'approaching eol', 'software approaching',
        'expiring soon', 'ending support', 'near end of life',
        'within a year', 'next year', 'soon to expire',
        'what software is approaching', 'which software is ending',
        'software nearing', 'close to eol'
    ]
    
    # Inventory-related regex patterns
    INVENTORY_PATTERNS = [
        r'show\s+(?:me\s+)?(?:the\s+)?inventory',
        r'(?:get|retrieve|fetch)\s+(?:the\s+)?inventory',
        r'what\s+software',
        r'list\s+(?:all\s+)?(?:the\s+)?(?:installed\s+)?software',
        r'inventory\s+(?:of|for)',
        r'software\s+(?:inventory|list)',
        r'show\s+(?:all\s+)?applications',
        r'what\s+(?:is\s+)?installed'
    ]
    
    # OS inventory patterns
    OS_INVENTORY_PATTERNS = [
        r'(?:show|list|get)\s+(?:the\s+)?(?:operating\s+)?systems?',
        r'what\s+(?:operating\s+)?systems?',
        r'os\s+inventory',
        r'operating\s+system\s+(?:list|inventory)'
    ]
    
    @classmethod
    def matches_eol_pattern(cls, query: str) -> bool:
        """
        Check if query matches EOL patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query contains EOL-related terms
        """
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in cls.EOL_PATTERNS)
    
    @classmethod
    def matches_approaching_eol_pattern(cls, query: str) -> bool:
        """
        Check if query matches approaching EOL patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query asks about software approaching EOL
        """
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in cls.APPROACHING_EOL_PATTERNS)
    
    @classmethod
    def matches_inventory_pattern(cls, query: str) -> bool:
        """
        Check if query matches inventory patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query requests software inventory
        """
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in cls.INVENTORY_PATTERNS)
    
    @classmethod
    def matches_os_inventory_pattern(cls, query: str) -> bool:
        """
        Check if query matches OS inventory patterns
        
        Args:
            query: User query string
            
        Returns:
            True if query requests OS inventory
        """
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in cls.OS_INVENTORY_PATTERNS)
    
    @classmethod
    def get_matched_patterns(cls, query: str, pattern_list: List[str], use_regex: bool = False) -> List[str]:
        """
        Get list of patterns that match the query
        
        Args:
            query: User query string
            pattern_list: List of patterns to check
            use_regex: Whether patterns are regex (default False for simple string matching)
            
        Returns:
            List of matched patterns
        """
        if use_regex:
            return [pattern for pattern in pattern_list if re.search(pattern, query, re.IGNORECASE)]
        else:
            query_lower = query.lower()
            return [pattern for pattern in pattern_list if pattern in query_lower]
    
    @classmethod
    def analyze_query_intent(cls, query: str) -> Dict[str, Any]:
        """
        Analyze query and return intent classification
        
        Args:
            query: User query string
            
        Returns:
            Dictionary with intent analysis results
        """
        return {
            "query": query,
            "is_eol_query": cls.matches_eol_pattern(query),
            "is_approaching_eol_query": cls.matches_approaching_eol_pattern(query),
            "is_inventory_query": cls.matches_inventory_pattern(query),
            "is_os_inventory_query": cls.matches_os_inventory_pattern(query),
            "matched_eol_patterns": cls.get_matched_patterns(query, cls.EOL_PATTERNS),
            "matched_approaching_patterns": cls.get_matched_patterns(query, cls.APPROACHING_EOL_PATTERNS),
            "matched_inventory_patterns": cls.get_matched_patterns(query, cls.INVENTORY_PATTERNS, use_regex=True),
            "matched_os_patterns": cls.get_matched_patterns(query, cls.OS_INVENTORY_PATTERNS, use_regex=True)
        }


# Convenience functions for backward compatibility
def matches_eol_pattern(query: str) -> bool:
    """Check if query matches EOL patterns"""
    return QueryPatterns.matches_eol_pattern(query)


def matches_approaching_eol_pattern(query: str) -> bool:
    """Check if query matches approaching EOL patterns"""
    return QueryPatterns.matches_approaching_eol_pattern(query)


def matches_inventory_pattern(query: str) -> bool:
    """Check if query matches inventory patterns"""
    return QueryPatterns.matches_inventory_pattern(query)


def analyze_query_intent(query: str) -> Dict[str, Any]:
    """Analyze query intent"""
    return QueryPatterns.analyze_query_intent(query)
