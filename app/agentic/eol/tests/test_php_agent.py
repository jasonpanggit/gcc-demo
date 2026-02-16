"""Tests for PHP EOL Agent HTML scraping."""

import pytest
import asyncio
from agents.php_agent import PHPEOLAgent


@pytest.fixture
def php_agent():
    """Create a PHP agent instance for testing."""
    return PHPEOLAgent()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_php_8_3(php_agent):
    """Test PHP 8.3 EOL data retrieval."""
    result = await php_agent.get_eol_data("PHP", "8.3")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "PHP"
    assert "8.3" in data.get("version", "")
    assert data.get("confidence", 0) > 0
    print(f"\n✅ PHP 8.3: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_php_8_2(php_agent):
    """Test PHP 8.2 EOL data retrieval."""
    result = await php_agent.get_eol_data("PHP", "8.2")
    
    assert result is not None
    print(f"\n✅ PHP 8.2: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_symfony_6_4(php_agent):
    """Test Symfony 6.4 LTS EOL data retrieval."""
    result = await php_agent.get_eol_data("Symfony", "6.4")
    
    assert result is not None
    print(f"\n✅ Symfony 6.4: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_laravel_10(php_agent):
    """Test Laravel 10 EOL data retrieval."""
    result = await php_agent.get_eol_data("Laravel", "10")
    
    assert result is not None
    print(f"\n✅ Laravel 10: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wordpress_6_4(php_agent):
    """Test WordPress 6.4 EOL data retrieval."""
    result = await php_agent.get_eol_data("WordPress", "6.4")
    
    assert result is not None
    print(f"\n✅ WordPress 6.4: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_drupal_10(php_agent):
    """Test Drupal 10 EOL data retrieval."""
    result = await php_agent.get_eol_data("Drupal", "10")
    
    assert result is not None
    print(f"\n✅ Drupal 10: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_php_products(php_agent):
    """Scrape and display all PHP ecosystem product versions found via HTML scraping."""
    print("\n" + "="*80)
    print("All PHP Ecosystem Versions Found via HTML Scraping")
    print("="*80)
    
    # Fetch all records from all configured URLs
    all_records = await php_agent.fetch_all_from_url()
    
    print(f"\n📊 Total versions extracted: {len(all_records)}")
    
    # Group records by software
    records_by_software = {}
    for record in all_records:
        software = record.get("software_name", "Unknown")
        if software not in records_by_software:
            records_by_software[software] = []
        records_by_software[software].append(record)
    
    # Print all versions grouped by software
    for software_name in sorted(records_by_software.keys()):
        records = records_by_software[software_name]
        print(f"\n{'='*80}")
        print(f"✅ {software_name} - {len(records)} version(s) found")
        print(f"{'='*80}")
        
        for idx, record in enumerate(records, 1):
            version = record.get("version") or "N/A"
            eol_date = record.get("eol_date") or "N/A"
            support_date = record.get("support_end_date") or "N/A"
            release_date = record.get("release_date") or "N/A"
            source_url = record.get("source_url") or "N/A"
            
            print(f"\n{idx}. {software_name} {version}")
            print(f"   Release Date:   {release_date}")
            print(f"   Support End:    {support_date}")
            print(f"   EOL Date:       {eol_date}")
            print(f"   Source:         {source_url}")
    
    print(f"\n{'='*80}")
    print(f"✅ Summary: Found {len(all_records)} versions across {len(records_by_software)} products")
    print(f"{'='*80}")
    
    # Assert we found at least some data
    assert len(all_records) > 0, "Should have extracted at least some EOL records"


@pytest.mark.integration
def test_php_urls_configuration(php_agent):
    """Test that PHP URLs are properly configured."""
    assert php_agent.eol_urls is not None
    assert len(php_agent.eol_urls) > 0
    
    print("\n" + "="*80)
    print("PHP Ecosystem Sources Configuration")
    print("="*80)
    
    for key, data in sorted(php_agent.eol_urls.items(), key=lambda x: x[1].get("priority", 999)):
        print(f"\n{data.get('priority')}. {data.get('description')}")
        print(f"   URL: {data.get('url')}")
        print(f"   Active: {data.get('active', True)}")


@pytest.mark.integration
def test_php_agent_relevance(php_agent):
    """Test the is_relevant method for various software names."""
    test_cases = [
        ("PHP", True),
        ("Symfony", True),
        ("Laravel", True),
        ("WordPress", True),
        ("Drupal", True),
        ("CodeIgniter", True),
        ("CakePHP", True),
        ("Composer", True),
        ("Python", False),
        ("Java", False),
        ("Node.js", False),
    ]
    
    print("\n" + "="*80)
    print("Testing PHP Agent Relevance")
    print("="*80)
    
    for software_name, expected in test_cases:
        result = php_agent.is_relevant(software_name)
        icon = "✅" if result == expected else "❌"
        print(f"{icon} {software_name}: {result} (expected: {expected})")
        assert result == expected, f"Expected {expected} for {software_name}, got {result}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_all_from_url(php_agent):
    """Test fetching all EOL records from all configured URLs in parallel."""
    print("\n" + "="*80)
    print("Fetching All EOL Records from PHP Ecosystem URLs (Parallel)")
    print("="*80)
    
    # Call fetch_all_from_url which processes all URLs in parallel
    all_records = await php_agent.fetch_all_from_url()
    
    print(f"\n📊 Total records extracted: {len(all_records)}")
    
    # Group records by source/software
    records_by_software = {}
    for record in all_records:
        software = record.get("software_name", "Unknown")
        if software not in records_by_software:
            records_by_software[software] = []
        records_by_software[software].append(record)
    
    # Print summary by software
    print("\n" + "="*80)
    print("Records Grouped by Software")
    print("="*80)
    
    for software_name in sorted(records_by_software.keys()):
        records = records_by_software[software_name]
        print(f"\n📦 {software_name} ({len(records)} versions)")
        print("   " + "-"*76)
        
        # Print each version
        for idx, record in enumerate(records[:10], 1):  # Show first 10
            version = record.get("version") or "N/A"
            eol = record.get("eol_date") or "N/A"
            support = record.get("support_end_date") or "N/A"
            release = record.get("release_date") or "N/A"
            confidence = record.get("confidence", 0)
            source_url = record.get("source_url") or "N/A"
            
            print(f"   {idx:2d}. Version {version:15s} | EOL: {eol:12s} | Support: {support:12s}")
            print(f"       Release: {release:12s} | Confidence: {confidence:.0%} | Source: {source_url[:50]}")
        
        if len(records) > 10:
            print(f"   ... and {len(records) - 10} more versions")
    
    # Print detailed information for all records
    print("\n" + "="*80)
    print("All Extracted EOL Records (Detailed)")
    print("="*80)
    
    for idx, record in enumerate(all_records, 1):
        print(f"\n{idx}. {record.get('software_name') or 'Unknown'} {record.get('version') or 'N/A'}")
        print(f"   Cycle: {record.get('cycle') or 'N/A'}")
        print(f"   Release Date: {record.get('release_date') or 'N/A'}")
        print(f"   Support End: {record.get('support_end_date') or 'N/A'}")
        print(f"   EOL Date: {record.get('eol_date') or 'N/A'}")
        print(f"   Confidence: {record.get('confidence', 0):.0%}")
        print(f"   Source: {record.get('source') or 'N/A'}")
        print(f"   Source URL: {record.get('source_url') or 'N/A'}")
        print(f"   Agent: {record.get('agent') or 'N/A'}")
    
    # Verify we extracted some records
    assert len(all_records) > 0, "Should have extracted at least some records from PHP URLs"
    print(f"\n✅ Successfully extracted {len(all_records)} total records from {len(records_by_software)} software products")
    
    return all_records


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_php_versions(php_agent):
    """Test extraction of PHP versions specifically."""
    import requests
    from bs4 import BeautifulSoup
    
    print("\n" + "="*80)
    print("Extracting PHP Versions from Official Page")
    print("="*80)
    
    url = php_agent.eol_urls["php"]["url"]
    print(f"\n📄 Processing: {url}")
    
    try:
        response = requests.get(url, headers=php_agent.headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Parse all PHP versions
        php_versions = php_agent._parse_php_all_versions(soup)
        
        print(f"\n✅ Found {len(php_versions)} PHP versions")
        print("\n📋 All PHP Versions:")
        
        for idx, version_data in enumerate(php_versions, 1):
            ver = version_data.get("version", "N/A")
            release = version_data.get("release_date", "N/A")
            support = version_data.get("support_end_date", "N/A")
            eol = version_data.get("eol_date", "N/A")
            
            print(f"\n{idx}. PHP {ver}")
            print(f"   Release: {release}")
            print(f"   Active Support End: {support}")
            print(f"   Security Support End (EOL): {eol}")
        
        assert len(php_versions) > 0, "Should have extracted at least one PHP version"
        print(f"\n✅ Successfully extracted {len(php_versions)} PHP versions")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        pytest.fail(f"Failed to extract PHP versions: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_extract_symfony_versions(php_agent):
    """Test extraction of Symfony versions specifically."""
    import requests
    from bs4 import BeautifulSoup
    
    print("\n" + "="*80)
    print("Extracting Symfony Versions from Official Page")
    print("="*80)
    
    url = php_agent.eol_urls["symfony"]["url"]
    print(f"\n📄 Processing: {url}")
    
    try:
        response = requests.get(url, headers=php_agent.headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Parse all Symfony versions
        symfony_versions = php_agent._parse_symfony_all_versions(soup)
        
        print(f"\n✅ Found {len(symfony_versions)} Symfony versions")
        print("\n📋 All Symfony Versions:")
        
        for idx, version_data in enumerate(symfony_versions, 1):
            ver = version_data.get("version", "N/A")
            release = version_data.get("release_date", "N/A")
            support = version_data.get("support_end_date", "N/A")
            eol = version_data.get("eol_date", "N/A")
            
            print(f"\n{idx}. Symfony {ver}")
            print(f"   Release: {release}")
            print(f"   Support End: {support}")
            print(f"   EOL: {eol}")
        
        if len(symfony_versions) > 0:
            print(f"\n✅ Successfully extracted {len(symfony_versions)} Symfony versions")
        else:
            print(f"\n⚠️  No Symfony versions extracted (page format may have changed)")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        pytest.fail(f"Failed to extract Symfony versions: {e}")


if __name__ == "__main__":
    """Run tests directly for quick validation."""
    print("\n" + "="*80)
    print("Running PHP Agent Tests")
    print("="*80)
    
    agent = PHPEOLAgent()
    
    # Test configuration
    print("\n1. Testing URL Configuration...")
    test_php_urls_configuration(agent)
    
    # Test relevance
    print("\n2. Testing Relevance Check...")
    test_php_agent_relevance(agent)
    
    # Test async operations
    print("\n3. Testing EOL Data Retrieval...")
    asyncio.run(test_multiple_php_products(agent))
    
    # Test parallel extraction
    print("\n4. Testing Parallel URL Extraction...")
    asyncio.run(test_fetch_all_from_url(agent))
    
    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80)
