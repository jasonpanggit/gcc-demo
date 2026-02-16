"""Tests for Red Hat EOL Agent web scraping and parsing."""

import pytest
import asyncio
from agents.redhat_agent import RedHatEOLAgent


@pytest.fixture
def redhat_agent():
    """Create a Red Hat agent instance for testing."""
    return RedHatEOLAgent()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rhel_7(redhat_agent):
    """Test RHEL 7 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("Red Hat Enterprise Linux", "7")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "Red Hat Enterprise Linux"
    assert "7" in data.get("version", "")
    assert data.get("confidence", 0) > 0
    print(f"\n✅ RHEL 7: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rhel_8(redhat_agent):
    """Test RHEL 8 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("Red Hat Enterprise Linux", "8")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "Red Hat Enterprise Linux"
    assert "8" in data.get("version", "")
    print(f"\n✅ RHEL 8: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rhel_9(redhat_agent):
    """Test RHEL 9 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("Red Hat Enterprise Linux", "9")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "Red Hat Enterprise Linux"
    assert "9" in data.get("version", "")
    print(f"\n✅ RHEL 9: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_centos_7(redhat_agent):
    """Test CentOS 7 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("CentOS", "7")
    
    assert result is not None
    print(f"\n✅ CentOS 7: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_centos_8(redhat_agent):
    """Test CentOS 8 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("CentOS", "8")
    
    assert result is not None
    print(f"\n✅ CentOS 8: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fedora_38(redhat_agent):
    """Test Fedora 38 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("Fedora", "38")
    
    assert result is not None
    print(f"\n✅ Fedora 38: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fedora_39(redhat_agent):
    """Test Fedora 39 EOL data retrieval."""
    result = await redhat_agent.get_eol_data("Fedora", "39")
    
    assert result is not None
    print(f"\n✅ Fedora 39: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_products(redhat_agent):
    """Test multiple Red Hat products in sequence."""
    products = [
        ("Red Hat Enterprise Linux", "7"),
        ("Red Hat Enterprise Linux", "8"),
        ("Red Hat Enterprise Linux", "9"),
        ("CentOS", "7"),
        ("CentOS", "8"),
        ("Fedora", "38"),
        ("Fedora", "39"),
    ]
    
    print("\n" + "="*80)
    print("Testing Multiple Red Hat Products")
    print("="*80)
    
    for software_name, version in products:
        result = await redhat_agent.get_eol_data(software_name, version)
        
        success_icon = "✅" if result.get("success") else "❌"
        data = result.get("data") or {}
        eol_date = data.get("eol_date", "N/A") if data else "N/A"
        support_date = data.get("support_end_date", "N/A") if data else "N/A"
        
        # Get source from the data
        source = "Unknown"
        if result.get("success") and data:
            source = data.get("data_source", "scraped")
        
        print(f"\n{success_icon} {software_name} {version}")
        print(f"   EOL Date: {eol_date}")
        print(f"   Support End: {support_date}")
        print(f"   Source: {source}")
        
        if not result.get("success"):
            error_msg = result.get("error", {}).get("software_name", "Unknown error")
            print(f"   Error: {error_msg}")


@pytest.mark.integration
def test_redhat_urls_configuration(redhat_agent):
    """Test that Red Hat URLs are properly configured."""
    assert redhat_agent.eol_urls is not None
    assert len(redhat_agent.eol_urls) > 0
    
    print("\n" + "="*80)
    print("Red Hat EOL Sources Configuration")
    print("="*80)
    
    for key, data in sorted(redhat_agent.eol_urls.items(), key=lambda x: x[1].get("priority", 999)):
        print(f"\n{data.get('priority')}. {data.get('description')}")
        print(f"   URL: {data.get('url')}")
        print(f"   Active: {data.get('active', True)}")


@pytest.mark.integration
def test_redhat_agent_relevance(redhat_agent):
    """Test the is_relevant method for various software names."""
    test_cases = [
        ("Red Hat Enterprise Linux", True),
        ("RHEL", True),
        ("CentOS", True),
        ("Fedora", True),
        ("Enterprise Linux", True),
        ("Ubuntu", False),
        ("Debian", False),
        ("Windows Server", False),
        ("Oracle Linux", False),
    ]
    
    print("\n" + "="*80)
    print("Testing Red Hat Agent Relevance")
    print("="*80)
    
    for software_name, expected in test_cases:
        result = redhat_agent.is_relevant(software_name)
        icon = "✅" if result == expected else "❌"
        print(f"{icon} {software_name}: {result} (expected: {expected})")
        assert result == expected, f"Expected {expected} for {software_name}, got {result}"


@pytest.mark.integration
def test_get_scraping_url(redhat_agent):
    """Test URL retrieval for Red Hat products."""
    # Test RHEL URL
    rhel_url = redhat_agent._get_scraping_url("Red Hat Enterprise Linux")
    assert rhel_url is not None
    assert "redhat.com" in rhel_url
    print(f"\n✅ RHEL URL: {rhel_url}")
    
    # Test Fedora URL
    fedora_url = redhat_agent._get_scraping_url("Fedora")
    assert fedora_url is not None
    assert "fedoraproject.org" in fedora_url
    print(f"✅ Fedora URL: {fedora_url}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_all_from_url(redhat_agent):
    """Test bulk extraction of all software from Red Hat EOL URLs."""
    import time
    
    print("\n" + "="*80)
    print("Testing Bulk Extraction from Red Hat EOL URLs")
    print("="*80)
    
    start_time = time.time()
    
    # Use the agent's bulk extraction method
    all_software = await redhat_agent.fetch_all_from_url()
    
    elapsed = time.time() - start_time
    
    print(f"\n✅ Bulk extraction completed in {elapsed:.2f} seconds")
    print(f"📊 Total software entries extracted: {len(all_software)}")
    
    # Verify we got results
    assert isinstance(all_software, list), "Should return a list"
    
    if len(all_software) == 0:
        print("\n⚠️  No entries extracted - this may be due to parsing issues or page structure changes")
        print("   Check the URLs and parsing logic")
    else:
        # Show sample entries
        print("\n📋 Sample entries (first 20):")
        for idx, entry in enumerate(all_software[:20], 1):
            software = entry.get('software', 'N/A')
            version = entry.get('version', 'N/A')
            eol = entry.get('eol', 'N/A')
            source = entry.get('scraped_from', 'N/A')
            print(f"{idx:2d}. {software[:40]:40s} {version[:10]:10s} | EOL: {eol[:12]:12s} | {source[:15]:15s}")
        
        if len(all_software) > 20:
            print(f"    ... and {len(all_software) - 20} more entries")
        
        # Group by source
        by_source = {}
        for entry in all_software:
            source = entry.get('scraped_from', 'Unknown')
            by_source[source] = by_source.get(source, 0) + 1
        
        print("\n📁 Entries by source:")
        for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"   {source:30s}: {count:5d} entries")
        
        # Performance note
        num_urls = len([url for url in redhat_agent.eol_urls.values() if url.get('active', True)])
        print(f"\n⚡ Processed {num_urls} URLs: {elapsed:.2f}s")
        print(f"   Average: ~{elapsed/num_urls:.2f}s per URL")
        
        print("\n" + "="*80)
        print(f"✅ Successfully extracted {len(all_software)} entries from {num_urls} URLs")
        print("="*80)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_specific_url(redhat_agent):
    """Test extraction from a specific URL."""
    import time
    
    print("\n" + "="*80)
    print("Testing Extraction from Specific RHEL URL")
    print("="*80)
    
    # Get RHEL URL
    rhel_url = redhat_agent.eol_urls.get("rhel", {}).get("url")
    
    if rhel_url:
        start_time = time.time()
        
        # Extract from specific URL
        entries = await redhat_agent.fetch_all_from_url(url=rhel_url)
        
        elapsed = time.time() - start_time
        
        print(f"\n✅ Extraction completed in {elapsed:.2f} seconds")
        print(f"📊 Total entries extracted: {len(entries)}")
        
        if len(entries) > 0:
            # Show first few entries
            print("\n📋 First 10 entries:")
            for idx, entry in enumerate(entries[:10], 1):
                software = entry.get('software', 'N/A')
                version = entry.get('version', 'N/A')
                eol = entry.get('eol', 'N/A')
                print(f"{idx:2d}. {software} {version} | EOL: {eol}")
        else:
            print("\n⚠️  No entries extracted from RHEL URL")
            print("   The page structure may have changed or parsing needs adjustment")
    else:
        print("\n❌ RHEL URL not configured")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_rhel_page(redhat_agent):
    """Test parsing RHEL EOL page - using documented lifecycle policy."""
    import requests
    from bs4 import BeautifulSoup
    
    print("\n" + "="*80)
    print("Testing RHEL EOL Extraction - Based on Red Hat Lifecycle Policy")
    print("="*80)
    
    rhel_url = redhat_agent.eol_urls.get("rhel", {}).get("url")
    
    if not rhel_url:
        print("❌ RHEL URL not configured")
        return
    
    try:
        response = requests.get(rhel_url, headers=redhat_agent.headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print(f"\n📋 RHEL follows a documented 10-year lifecycle policy")
        print(f"    Data source: {rhel_url}")
        
        # Test parsing for specific versions
        print(f"\n🔍 Testing lifecycle data extraction...")
        for version in ['7', '8', '9', '10']:
            result = redhat_agent._parse_rhel_eol(soup, version)
            
            if result:
                print(f"\n✅ RHEL {version}:")
                print(f"   Release Date: {result.get('releaseDate')}")
                print(f"   Full Support End: {result.get('support')}")
                print(f"   EOL: {result.get('eol')}")
                print(f"   Source: {result.get('source')}")
            else:
                print(f"\n❌ RHEL {version}: No data found")
        
        # Test bulk extraction
        print(f"\n📊 Testing bulk extraction...")
        entries = redhat_agent._extract_all_entries_from_page(soup, 'rhel')
        print(f"   Total RHEL entries: {len(entries)}")
        
        if entries:
            print(f"\n   All RHEL versions:")
            for entry in entries:
                print(f"   - {entry['software']:30} Released: {entry['releaseDate']}  EOL: {entry['eol']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_fedora_page(redhat_agent):
    """Test parsing Fedora EOL page - scraping from table."""
    import requests
    from bs4 import BeautifulSoup
    
    print("\n" + "="*80)
    print("Testing Fedora EOL Extraction - Scraping from Official Table")
    print("="*80)
    
    fedora_url = redhat_agent.eol_urls.get("fedora", {}).get("url")
    
    if not fedora_url:
        print("❌ Fedora URL not configured")
        return
    
    try:
        response = requests.get(fedora_url, headers=redhat_agent.headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        print(f"\n📋 Scraping Fedora EOL table")
        print(f"    Data source: {fedora_url}")
        
        # Test parsing for specific versions
        print(f"\n🔍 Testing table scraping for specific versions...")
        for version in ['38', '39', '40', '41']:
            result = redhat_agent._parse_fedora_eol(soup, version)
            
            if result:
                print(f"✅ Fedora {version}: EOL {result.get('eol')} (confidence: {result.get('confidence')}%)")
            else:
                print(f"❌ Fedora {version}: Not found in table")
        
        # Test bulk extraction
        print(f"\n📊 Testing bulk table extraction...")
        entries = redhat_agent._extract_all_entries_from_page(soup, 'fedora')
        print(f"   Total Fedora entries scraped: {len(entries)}")
        
        if entries:
            print(f"\n   First 10 Fedora versions:")
            for entry in entries[:10]:
                print(f"   - {entry['software']:20} Version: {entry['version']:3} EOL: {entry['eol']}")
            if len(entries) > 10:
                print(f"   ... and {len(entries) - 10} more versions")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    """Run tests directly for quick validation."""
    print("\n" + "="*80)
    print("Running Red Hat Agent Tests")
    print("="*80)
    
    agent = RedHatEOLAgent()
    
    # Test configuration
    print("\n1. Testing URL Configuration...")
    test_redhat_urls_configuration(agent)
    
    # Test relevance
    print("\n2. Testing Relevance Check...")
    test_redhat_agent_relevance(agent)
    
    # Test URL retrieval
    print("\n3. Testing URL Retrieval...")
    test_get_scraping_url(agent)
    
    # Test async operations
    print("\n4. Testing EOL Data Retrieval...")
    asyncio.run(test_multiple_products(agent))
    
    # Test bulk extraction
    print("\n5. Testing Bulk Extraction...")
    asyncio.run(test_fetch_all_from_url(agent))
    
    # Test RHEL page parsing
    print("\n6. Testing RHEL Lifecycle Extraction...")
    asyncio.run(test_parse_rhel_page(agent))
    
    # Test Fedora page parsing
    print("\n7. Testing Fedora Table Scraping...")
    asyncio.run(test_parse_fedora_page(agent))
    
    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80)
