"""Tests for PostgreSQL EOL Agent HTML parsing."""

import pytest
import asyncio
from agents.postgresql_agent import PostgreSQLEOLAgent


@pytest.fixture
def postgresql_agent():
    """Create a PostgreSQL agent instance for testing."""
    return PostgreSQLEOLAgent()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_17(postgresql_agent):
    """Test PostgreSQL 17 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "17")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "PostgreSQL"
    assert "17" in data.get("version", "")
    assert data.get("confidence", 0) > 0
    print(f"\n✅ PostgreSQL 17: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_16(postgresql_agent):
    """Test PostgreSQL 16 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "16")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "PostgreSQL"
    assert "16" in data.get("version", "")
    print(f"\n✅ PostgreSQL 16: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_15(postgresql_agent):
    """Test PostgreSQL 15 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "15")
    
    assert result is not None
    print(f"\n✅ PostgreSQL 15: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_14(postgresql_agent):
    """Test PostgreSQL 14 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "14")
    
    assert result is not None
    print(f"\n✅ PostgreSQL 14: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_13(postgresql_agent):
    """Test PostgreSQL 13 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "13")
    
    assert result is not None
    print(f"\n✅ PostgreSQL 13: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgresql_12(postgresql_agent):
    """Test PostgreSQL 12 EOL data retrieval."""
    result = await postgresql_agent.get_eol_data("PostgreSQL", "12")
    
    assert result is not None
    print(f"\n✅ PostgreSQL 12: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_products(postgresql_agent):
    """Test multiple PostgreSQL versions in sequence."""
    products = [
        ("PostgreSQL", "18"),
        ("PostgreSQL", "17"),
        ("PostgreSQL", "16"),
        ("PostgreSQL", "15"),
        ("PostgreSQL", "14"),
        ("PostgreSQL", "13"),
    ]
    
    print("\n" + "="*80)
    print("Testing Multiple PostgreSQL Versions")
    print("="*80)
    
    for software_name, version in products:
        result = await postgresql_agent.get_eol_data(software_name, version)
        
        success_icon = "✅" if result.get("success") else "❌"
        data = result.get("data") or {}
        eol_date = data.get("eol_date", "N/A") if data else "N/A"
        support_date = data.get("support_end_date", "N/A") if data else "N/A"
        cycle = data.get("cycle", "N/A") if data else "N/A"
        
        print(f"\n{success_icon} {software_name} {version}")
        print(f"   Cycle: {cycle}")
        print(f"   EOL Date: {eol_date}")
        print(f"   Support End: {support_date}")
        print(f"   Source: postgresql_official")
        
        if not result.get("success"):
            error_msg = result.get("error", {}).get("software_name", "Unknown error")
            print(f"   Error: {error_msg}")


@pytest.mark.integration
def test_postgresql_urls_configuration(postgresql_agent):
    """Test that PostgreSQL URLs are properly configured."""
    assert postgresql_agent.eol_urls is not None
    assert len(postgresql_agent.eol_urls) > 0
    
    print("\n" + "="*80)
    print("PostgreSQL Sources Configuration")
    print("="*80)
    
    for key, data in sorted(postgresql_agent.eol_urls.items(), key=lambda x: x[1].get("priority", 999)):
        print(f"\n{data.get('priority')}. {data.get('description')}")
        print(f"   URL: {data.get('url')}")
        print(f"   Active: {data.get('active', True)}")


@pytest.mark.integration
def test_postgresql_agent_relevance(postgresql_agent):
    """Test the is_relevant method for various software names."""
    test_cases = [
        ("PostgreSQL", True),
        ("Postgres", True),
        ("PostGIS", True),
        ("pgbouncer", True),
        ("psql", True),
        ("Oracle Database", False),
        ("MySQL", False),
        ("SQL Server", False),
        ("MongoDB", False),
    ]
    
    print("\n" + "="*80)
    print("Testing PostgreSQL Agent Relevance")
    print("="*80)
    
    for software_name, expected in test_cases:
        result = postgresql_agent.is_relevant(software_name)
        icon = "✅" if result == expected else "❌"
        print(f"{icon} {software_name}: {result} (expected: {expected})")
        assert result == expected, f"Expected {expected} for {software_name}, got {result}"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skip(reason="Method fetch_all_from_url() not yet implemented in PostgreSQLEOLAgent")
async def test_fetch_all_from_url(postgresql_agent):
    """Test fetching all PostgreSQL versions from the versioning page."""
    print("\n" + "="*80)
    print("Fetching All PostgreSQL Versions")
    print("="*80)

    all_records = await postgresql_agent.fetch_all_from_url()
    
    print(f"\n📊 Total versions extracted: {len(all_records)}")
    
    # Print all versions
    print("\n📋 All PostgreSQL Versions:")
    print("="*80)
    for idx, record in enumerate(all_records, 1):
        version = record.get("version", "N/A")
        release_date = record.get("release_date", "N/A")
        eol_date = record.get("eol_date", "N/A")
        latest = record.get("latest", "N/A")
        supported = record.get("supported", False)
        support_icon = "✅" if supported else "❌"
        
        print(f"\n{idx:2d}. PostgreSQL {version:4s} {support_icon}")
        print(f"    Latest:       {latest}")
        print(f"    Released:     {release_date}")
        print(f"    EOL:          {eol_date}")
        print(f"    Supported:    {supported}")
    
    # Assert we extracted some versions
    assert len(all_records) > 0, "Should have extracted at least some PostgreSQL versions"
    
    # Check that we have the expected fields
    if all_records:
        sample = all_records[0]
        required_fields = ["software_name", "version", "release_date", "eol_date", "source_url", "agent"]
        for field in required_fields:
            assert field in sample, f"Missing required field: {field}"
    
    print(f"\n✅ Successfully extracted {len(all_records)} PostgreSQL versions")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scrape_postgresql_versioning_page(postgresql_agent):
    """Test direct scraping of PostgreSQL versioning page."""
    import requests
    from bs4 import BeautifulSoup
    
    print("\n" + "="*80)
    print("Testing Direct PostgreSQL Page Scraping")
    print("="*80)
    
    url = postgresql_agent.eol_urls["postgresql"]["url"]
    print(f"\n📄 Processing: {url}")
    
    try:
        response = requests.get(url, headers=postgresql_agent.headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        print(f"   ✅ Found {len(tables)} table(s)")
        
        if tables:
            table = tables[0]
            rows = table.find_all('tr')
            print(f"   ✅ Found {len(rows) - 1} version rows (excluding header)")
            
            # Print header
            if rows:
                header_row = rows[0]
                headers = header_row.find_all(['th', 'td'])
                print(f"\n   Table Headers: {[h.get_text(strip=True) for h in headers]}")
            
            # Print first 5 data rows
            print(f"\n   First 5 versions:")
            for idx, row in enumerate(rows[1:6], 1):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 5:
                    print(f"   {idx}. {[c.get_text(strip=True) for c in cells]}")
        
        assert len(tables) > 0, "Should have found at least one table"
        print(f"\n✅ Page structure validated successfully")
        
    except Exception as e:
        pytest.fail(f"Failed to scrape PostgreSQL page: {e}")


if __name__ == "__main__":
    """Run tests directly for quick validation."""
    print("\n" + "="*80)
    print("Running PostgreSQL Agent Tests")
    print("="*80)
    
    agent = PostgreSQLEOLAgent()
    
    # Test configuration
    print("\n1. Testing URL Configuration...")
    test_postgresql_urls_configuration(agent)
    
    # Test relevance
    print("\n2. Testing Relevance Check...")
    test_postgresql_agent_relevance(agent)
    
    # Test async operations
    print("\n3. Testing EOL Data Retrieval...")
    asyncio.run(test_multiple_products(agent))
    
    # Test bulk extraction
    print("\n4. Testing Bulk Extraction...")
    asyncio.run(test_fetch_all_from_url(agent))
    
    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80)
