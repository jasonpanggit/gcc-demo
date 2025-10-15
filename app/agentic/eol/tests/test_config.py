"""
Test Configuration - Enable/Disable Mock Mode
"""
import os
from typing import Optional

# Test mode configuration
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
MOCK_NUM_COMPUTERS = int(os.getenv("MOCK_NUM_COMPUTERS", "50"))
MOCK_WINDOWS_RATIO = float(os.getenv("MOCK_WINDOWS_RATIO", "0.6"))
MOCK_SOFTWARE_PER_COMPUTER_MIN = int(os.getenv("MOCK_SOFTWARE_MIN", "5"))
MOCK_SOFTWARE_PER_COMPUTER_MAX = int(os.getenv("MOCK_SOFTWARE_MAX", "20"))

# Cache behavior in test mode
TEST_CACHE_ENABLED = os.getenv("TEST_CACHE_ENABLED", "false").lower() == "true"
TEST_CACHE_TTL = int(os.getenv("TEST_CACHE_TTL", "300"))  # 5 minutes for testing

# Logging
TEST_LOG_LEVEL = os.getenv("TEST_LOG_LEVEL", "INFO")

# Test data seed for reproducibility
MOCK_DATA_SEED = int(os.getenv("MOCK_DATA_SEED", "42"))


class TestConfig:
    """Test configuration manager"""
    
    def __init__(self):
        self.use_mock_data = USE_MOCK_DATA
        self.num_computers = MOCK_NUM_COMPUTERS
        self.windows_ratio = MOCK_WINDOWS_RATIO
        self.software_range = (MOCK_SOFTWARE_PER_COMPUTER_MIN, MOCK_SOFTWARE_PER_COMPUTER_MAX)
        self.cache_enabled = TEST_CACHE_ENABLED
        self.cache_ttl = TEST_CACHE_TTL
        self.log_level = TEST_LOG_LEVEL
        self.data_seed = MOCK_DATA_SEED
    
    def __repr__(self):
        return (
            f"TestConfig(\n"
            f"  use_mock_data={self.use_mock_data},\n"
            f"  num_computers={self.num_computers},\n"
            f"  windows_ratio={self.windows_ratio},\n"
            f"  software_range={self.software_range},\n"
            f"  cache_enabled={self.cache_enabled},\n"
            f"  cache_ttl={self.cache_ttl}s,\n"
            f"  log_level={self.log_level},\n"
            f"  data_seed={self.data_seed}\n"
            f")"
        )
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "use_mock_data": self.use_mock_data,
            "num_computers": self.num_computers,
            "windows_ratio": self.windows_ratio,
            "software_range": self.software_range,
            "cache_enabled": self.cache_enabled,
            "cache_ttl": self.cache_ttl,
            "log_level": self.log_level,
            "data_seed": self.data_seed
        }


# Singleton instance
test_config = TestConfig()


def enable_mock_mode(
    num_computers: Optional[int] = None,
    windows_ratio: Optional[float] = None,
    cache_enabled: bool = False
):
    """
    Enable mock mode with optional parameters
    
    Args:
        num_computers: Number of computers to generate
        windows_ratio: Ratio of Windows to Linux (0.0 - 1.0)
        cache_enabled: Enable caching in test mode
    """
    test_config.use_mock_data = True
    
    if num_computers is not None:
        test_config.num_computers = num_computers
    
    if windows_ratio is not None:
        test_config.windows_ratio = windows_ratio
    
    test_config.cache_enabled = cache_enabled
    
    print(f"✅ Mock mode enabled with {test_config.num_computers} computers")


def disable_mock_mode():
    """Disable mock mode - use real Azure data"""
    test_config.use_mock_data = False
    print("✅ Mock mode disabled - using real Azure data")


if __name__ == "__main__":
    print("Current Test Configuration:")
    print(test_config)
