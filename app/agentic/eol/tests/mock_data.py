"""
Mock Data Generator for Local Testing
Generates realistic sample data matching Azure Log Analytics response formats
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
import random


class MockDataGenerator:
    """Generates mock data for testing without Azure dependencies"""
    
    # Sample data pools
    PUBLISHERS = [
        "Microsoft Corporation",
        "Oracle Corporation",
        "Google LLC",
        "Adobe Inc.",
        "Mozilla Foundation",
        "Python Software Foundation",
        "Node.js Foundation",
        "Apache Software Foundation",
        "PostgreSQL Global Development Group",
        "Red Hat Inc.",
        "Canonical Ltd.",
        "Unknown"
    ]
    
    SOFTWARE_NAMES = [
        # Microsoft products
        ("Microsoft Visual Studio Code", "Microsoft Corporation", ["1.85.0", "1.84.2", "1.83.1"]),
        ("Microsoft SQL Server", "Microsoft Corporation", ["2019", "2017", "2016"]),
        ("Microsoft .NET Framework", "Microsoft Corporation", ["4.8", "4.7.2", "4.6.1"]),
        ("Microsoft Office", "Microsoft Corporation", ["2021", "2019", "2016"]),
        
        # Programming languages & runtimes
        ("Python", "Python Software Foundation", ["3.11.5", "3.10.8", "3.9.13", "3.8.10", "2.7.18"]),
        ("Node.js", "Node.js Foundation", ["20.10.0", "18.19.0", "16.20.2", "14.21.3"]),
        ("Java Runtime Environment", "Oracle Corporation", ["17.0.9", "11.0.21", "8u391"]),
        ("PHP", "The PHP Group", ["8.2.13", "8.1.26", "7.4.33", "5.6.40"]),
        
        # Databases
        ("PostgreSQL", "PostgreSQL Global Development Group", ["16.1", "15.5", "14.10", "13.13", "12.17", "11.22", "10.23", "9.6.24"]),
        ("MySQL", "Oracle Corporation", ["8.0.35", "5.7.44", "5.6.51"]),
        ("MongoDB", "MongoDB Inc.", ["7.0.4", "6.0.12", "5.0.23"]),
        
        # Web servers
        ("Apache HTTP Server", "Apache Software Foundation", ["2.4.58", "2.4.57", "2.4.54"]),
        ("nginx", "F5 Networks", ["1.25.3", "1.24.0", "1.22.1"]),
        
        # Other common software
        ("Google Chrome", "Google LLC", ["120.0.6099.109", "119.0.6045.199"]),
        ("Mozilla Firefox", "Mozilla Foundation", ["121.0", "120.0.1", "115.6.0"]),
        ("Adobe Acrobat Reader", "Adobe Inc.", ["23.008.20470", "23.006.20380"]),
        ("7-Zip", "Igor Pavlov", ["23.01", "22.01", "21.07"]),
        ("Git", "Software Freedom Conservancy", ["2.43.0", "2.42.0", "2.41.0"]),
        ("Docker Desktop", "Docker Inc.", ["4.26.1", "4.25.0", "4.24.0"]),
    ]
    
    WINDOWS_OS = [
        ("Windows Server 2022", "10.0", "Microsoft Corporation", "Azure VM"),
        ("Windows Server 2019", "10.0", "Microsoft Corporation", "Azure VM"),
        ("Windows Server 2016", "10.0", "Microsoft Corporation", "Arc-enabled Server"),
        ("Windows Server 2012 R2", "6.3", "Microsoft Corporation", "Arc-enabled Server"),
        ("Windows 11", "10.0", "Microsoft Corporation", "Arc-enabled Server"),
        ("Windows 10", "10.0", "Microsoft Corporation", "Arc-enabled Server"),
    ]
    
    LINUX_OS = [
        ("Ubuntu", "22.04", "Canonical Ltd.", "Azure VM"),
        ("Ubuntu", "20.04", "Canonical Ltd.", "Azure VM"),
        ("Ubuntu", "18.04", "Canonical Ltd.", "Arc-enabled Server"),
        ("Red Hat Enterprise Linux", "9.3", "Red Hat Inc.", "Azure VM"),
        ("Red Hat Enterprise Linux", "8.9", "Red Hat Inc.", "Arc-enabled Server"),
        ("Red Hat Enterprise Linux", "7.9", "Red Hat Inc.", "Arc-enabled Server"),
        ("CentOS Linux", "8", "CentOS Project", "Arc-enabled Server"),
        ("CentOS Linux", "7", "CentOS Project", "Arc-enabled Server"),
        ("Debian GNU/Linux", "12", "Debian Project", "Azure VM"),
        ("Debian GNU/Linux", "11", "Debian Project", "Azure VM"),
        ("SUSE Linux Enterprise Server", "15", "SUSE", "Arc-enabled Server"),
    ]
    
    COMPUTER_NAMES = [
        "WEBSRV-{region}-{num:03d}",
        "APPSRV-{region}-{num:03d}",
        "DBSRV-{region}-{num:03d}",
        "FILESRV-{region}-{num:03d}",
        "DC-{region}-{num:03d}",
        "{region}-WEB-{num:02d}",
        "{region}-APP-{num:02d}",
        "{region}-DB-{num:02d}",
    ]
    
    REGIONS = ["EUS", "WUS", "NEU", "WEU", "SEA", "JPN"]
    
    def __init__(self, seed: int = 42):
        """Initialize with optional seed for reproducible results"""
        random.seed(seed)
        self._generated_computers = []
    
    def _generate_computer_name(self) -> str:
        """Generate a realistic computer name"""
        template = random.choice(self.COMPUTER_NAMES)
        return template.format(
            region=random.choice(self.REGIONS),
            num=random.randint(1, 100)
        )
    
    def _generate_resource_id(self, computer_name: str, computer_type: str) -> str:
        """Generate Azure resource ID"""
        subscription_id = f"sub-{''.join(random.choices('0123456789abcdef', k=8))}"
        rg_name = f"rg-{computer_name.split('-')[0].lower()}"
        
        if computer_type == "Azure VM":
            return f"/subscriptions/{subscription_id}/resourceGroups/{rg_name}/providers/Microsoft.Compute/virtualMachines/{computer_name}"
        else:  # Arc-enabled Server
            return f"/subscriptions/{subscription_id}/resourceGroups/{rg_name}/providers/Microsoft.HybridCompute/machines/{computer_name}"
    
    def generate_software_inventory(
        self, 
        num_computers: int = 50,
        software_per_computer_range: tuple = (5, 20)
    ) -> List[Dict[str, Any]]:
        """
        Generate mock software inventory data
        
        Args:
            num_computers: Number of unique computers
            software_per_computer_range: (min, max) software items per computer
            
        Returns:
            List of software inventory items matching real API format
        """
        results = []
        
        # Generate computers
        computers = [self._generate_computer_name() for _ in range(num_computers)]
        self._generated_computers = computers
        
        for computer in computers:
            # Each computer has random software installed
            num_software = random.randint(*software_per_computer_range)
            installed_software = random.sample(self.SOFTWARE_NAMES, min(num_software, len(self.SOFTWARE_NAMES)))
            
            for software_name, publisher, versions in installed_software:
                version = random.choice(versions)
                last_seen = datetime.utcnow() - timedelta(
                    hours=random.randint(0, 48)
                )
                
                # Determine software type
                if any(db in software_name.lower() for db in ["sql", "mysql", "postgres", "mongodb", "oracle"]):
                    software_type = "Database"
                elif any(srv in software_name.lower() for srv in ["server", "apache", "nginx", "iis"]):
                    software_type = "Server Application"
                elif any(lang in software_name.lower() for lang in ["python", "node", "java", "php", "ruby"]):
                    software_type = "Development Tool"
                else:
                    software_type = "Application"
                
                item = {
                    "computer": computer,
                    "name": software_name,
                    "version": version,
                    "publisher": publisher,
                    "software_type": software_type,
                    "install_date": None,
                    "last_seen": last_seen.isoformat(),
                    "computer_count": 1,
                    "source": "log_analytics_configurationdata",
                }
                results.append(item)
        
        return results
    
    def generate_os_inventory(
        self, 
        num_computers: int = 50,
        windows_ratio: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Generate mock OS inventory data
        
        Args:
            num_computers: Number of unique computers
            windows_ratio: Ratio of Windows to Linux computers (0.0 - 1.0)
            
        Returns:
            List of OS inventory items matching real API format
        """
        results = []
        
        # Use same computers as software inventory if available
        if self._generated_computers:
            computers = self._generated_computers
        else:
            computers = [self._generate_computer_name() for _ in range(num_computers)]
            self._generated_computers = computers
        
        for computer in computers:
            # Determine OS type
            is_windows = random.random() < windows_ratio
            
            if is_windows:
                os_name, os_version, vendor, computer_type = random.choice(self.WINDOWS_OS)
                os_type = "Windows"
                computer_env = "Azure" if computer_type == "Azure VM" else "Non-Azure"
            else:
                os_name, os_version, vendor, computer_type = random.choice(self.LINUX_OS)
                os_type = "Linux"
                computer_env = "Azure" if computer_type == "Azure VM" else "Non-Azure"
            
            last_heartbeat = datetime.utcnow() - timedelta(
                minutes=random.randint(1, 30)
            )
            
            resource_id = self._generate_resource_id(computer, computer_type)
            
            item = {
                "computer_name": computer,
                "os_name": os_name,
                "os_version": os_version,
                "os_type": os_type,
                "vendor": vendor,
                "computer_environment": computer_env,
                "computer_type": computer_type,
                "resource_id": resource_id,
                "last_heartbeat": last_heartbeat.isoformat(),
                "source": "log_analytics_heartbeat",
                # Backward compatibility fields
                "computer": computer,
                "name": os_name,
                "version": os_version,
                "software_type": "operating system",
            }
            results.append(item)
        
        return results
    
    def generate_eol_data(self) -> Dict[str, Any]:
        """Generate mock EOL date data for common software"""
        return {
            "Python": {
                "3.11": {"eol": "2027-10-04", "lts": False},
                "3.10": {"eol": "2026-10-04", "lts": False},
                "3.9": {"eol": "2025-10-05", "lts": False},
                "3.8": {"eol": "2024-10-07", "lts": False},
                "2.7": {"eol": "2020-01-01", "lts": False},  # Already EOL
            },
            "Node.js": {
                "20": {"eol": "2026-04-30", "lts": True},
                "18": {"eol": "2025-04-30", "lts": True},
                "16": {"eol": "2023-09-11", "lts": True},  # Already EOL
                "14": {"eol": "2023-04-30", "lts": True},  # Already EOL
            },
            "PostgreSQL": {
                "16": {"eol": "2028-11-09", "lts": False},
                "15": {"eol": "2027-11-11", "lts": False},
                "14": {"eol": "2026-11-12", "lts": False},
                "13": {"eol": "2025-11-13", "lts": False},
                "12": {"eol": "2024-11-14", "lts": False},
                "11": {"eol": "2023-11-09", "lts": False},  # Already EOL
                "10": {"eol": "2022-11-10", "lts": False},  # Already EOL
                "9.6": {"eol": "2021-11-11", "lts": False},  # Already EOL
            },
            "PHP": {
                "8.2": {"eol": "2025-12-31", "lts": False},
                "8.1": {"eol": "2024-11-25", "lts": False},
                "7.4": {"eol": "2022-11-28", "lts": False},  # Already EOL
                "5.6": {"eol": "2018-12-31", "lts": False},  # Already EOL
            },
            "Windows Server": {
                "2022": {"eol": "2031-10-13", "lts": True},
                "2019": {"eol": "2029-01-09", "lts": True},
                "2016": {"eol": "2027-01-11", "lts": True},
                "2012 R2": {"eol": "2023-10-10", "lts": True},  # Already EOL
            },
            "Ubuntu": {
                "22.04": {"eol": "2032-04-01", "lts": True},
                "20.04": {"eol": "2030-04-01", "lts": True},
                "18.04": {"eol": "2028-04-01", "lts": True},
            },
        }


# Singleton instance for easy access
mock_generator = MockDataGenerator()


def get_mock_software_inventory(num_computers: int = 50) -> Dict[str, Any]:
    """
    Get mock software inventory in the format returned by SoftwareInventoryAgent
    
    Returns:
        Dict with success, data, count, query_params, from_cache, cached_at
    """
    data = mock_generator.generate_software_inventory(num_computers=num_computers)
    return {
        "success": True,
        "data": data,
        "count": len(data),
        "query_params": {
            "days": 90,
            "software_filter": None,
            "limit": 10000
        },
        "from_cache": False,
        "cached_at": datetime.utcnow().isoformat()
    }


def get_mock_os_inventory(num_computers: int = 50) -> Dict[str, Any]:
    """
    Get mock OS inventory in the format returned by OSInventoryAgent
    
    Returns:
        Dict with success, data, count, query_params, from_cache, cached_at
    """
    data = mock_generator.generate_os_inventory(num_computers=num_computers)
    return {
        "success": True,
        "data": data,
        "count": len(data),
        "query_params": {
            "days": 7,
            "limit": 10000
        },
        "from_cache": False,
        "cached_at": datetime.utcnow().isoformat()
    }


def get_mock_eol_data() -> Dict[str, Any]:
    """Get mock EOL data for testing"""
    return mock_generator.generate_eol_data()


if __name__ == "__main__":
    # Test data generation
    print("🧪 Generating mock data...\n")
    
    print("=" * 80)
    print("SOFTWARE INVENTORY SAMPLE")
    print("=" * 80)
    software_data = get_mock_software_inventory(num_computers=5)
    print(f"Generated {software_data['count']} software items")
    print(f"\nFirst 3 items:")
    for item in software_data['data'][:3]:
        print(f"  - {item['computer']}: {item['name']} {item['version']} ({item['publisher']})")
    
    print("\n" + "=" * 80)
    print("OS INVENTORY SAMPLE")
    print("=" * 80)
    os_data = get_mock_os_inventory(num_computers=5)
    print(f"Generated {os_data['count']} OS items")
    print(f"\nFirst 3 items:")
    for item in os_data['data'][:3]:
        print(f"  - {item['computer']}: {item['os_name']} {item['os_version']} ({item['computer_type']})")
    
    print("\n" + "=" * 80)
    print("EOL DATA SAMPLE")
    print("=" * 80)
    eol_data = get_mock_eol_data()
    print(f"Generated EOL data for {len(eol_data)} products")
    for product, versions in list(eol_data.items())[:3]:
        print(f"\n{product}:")
        for version, info in list(versions.items())[:3]:
            eol_status = "✅ Supported" if info['eol'] > datetime.utcnow().strftime('%Y-%m-%d') else "⚠️ EOL"
            print(f"  - Version {version}: EOL {info['eol']} {eol_status}")
