"""Tests for Oracle EOL Agent PDF parsing."""

import pytest
import asyncio
from agents.oracle_agent import OracleEOLAgent


@pytest.fixture
def oracle_agent():
    """Create an Oracle agent instance for testing."""
    return OracleEOLAgent()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oracle_database_19c(oracle_agent):
    """Test Oracle Database 19c EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Oracle Database", "19c")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "Oracle Database"
    assert "19" in data.get("version", "")
    assert data.get("confidence", 0) > 0
    print(f"\n✅ Oracle Database 19c: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oracle_database_21c(oracle_agent):
    """Test Oracle Database 21c EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Oracle Database", "21c")
    
    assert result is not None
    assert result.get("success") is True
    
    data = result.get("data", {})
    assert data.get("software_name") == "Oracle Database"
    assert "21" in data.get("version", "")
    print(f"\n✅ Oracle Database 21c: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oracle_database_23ai(oracle_agent):
    """Test Oracle Database 23ai EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Oracle Database", "23ai")
    
    assert result is not None
    print(f"\n✅ Oracle Database 23ai: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mysql_8_0(oracle_agent):
    """Test MySQL 8.0 EOL data retrieval."""
    result = await oracle_agent.get_eol_data("MySQL", "8.0")
    
    assert result is not None
    print(f"\n✅ MySQL 8.0: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_java_17(oracle_agent):
    """Test Java 17 EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Java", "17")
    
    assert result is not None
    print(f"\n✅ Java 17: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_java_11(oracle_agent):
    """Test Java 11 EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Java", "11")
    
    assert result is not None
    print(f"\n✅ Java 11: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_weblogic_server(oracle_agent):
    """Test WebLogic Server EOL data retrieval."""
    result = await oracle_agent.get_eol_data("WebLogic Server", "14.1")
    
    assert result is not None
    print(f"\n✅ WebLogic Server: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_essbase(oracle_agent):
    """Test Essbase EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Essbase", "21")
    
    assert result is not None
    print(f"\n✅ Essbase: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_oracle_linux(oracle_agent):
    """Test Oracle Linux EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Oracle Linux", "8")
    
    assert result is not None
    print(f"\n✅ Oracle Linux: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_solaris(oracle_agent):
    """Test Solaris EOL data retrieval."""
    result = await oracle_agent.get_eol_data("Solaris", "11")
    
    assert result is not None
    print(f"\n✅ Solaris: {result}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_products(oracle_agent):
    """Test multiple Oracle products in sequence."""
    products = [
        ("Oracle Database", "19c"),
        ("Oracle Database", "21c"),
        ("MySQL", "8.0"),
        ("Java", "17"),
        ("WebLogic Server", "14.1"),
        ("Essbase", "21"),
    ]
    
    print("\n" + "="*80)
    print("Testing Multiple Oracle Products")
    print("="*80)
    
    for software_name, version in products:
        result = await oracle_agent.get_eol_data(software_name, version)
        
        success_icon = "✅" if result.get("success") else "❌"
        data = result.get("data") or {}
        eol_date = data.get("eol_date", "N/A") if data else "N/A"
        support_date = data.get("support_end_date", "N/A") if data else "N/A"
        
        # Get pdf_source from the cycle/additional data
        pdf_source = "Unknown"
        if result.get("success") and data:
            # Check in data for pdf_source or similar fields
            pdf_source = data.get("pdf_source", "Technology PDF")
        
        print(f"\n{success_icon} {software_name} {version}")
        print(f"   EOL Date: {eol_date}")
        print(f"   Support End: {support_date}")
        print(f"   Source: {pdf_source}")
        
        if not result.get("success"):
            error_msg = result.get("error", {}).get("software_name", "Unknown error")
            print(f"   Error: {error_msg}")


@pytest.mark.integration
def test_oracle_urls_configuration(oracle_agent):
    """Test that Oracle URLs are properly configured."""
    assert oracle_agent.eol_urls is not None
    assert len(oracle_agent.eol_urls) > 0
    
    print("\n" + "="*80)
    print("Oracle PDF Sources Configuration")
    print("="*80)
    
    for key, data in sorted(oracle_agent.eol_urls.items(), key=lambda x: x[1].get("priority", 999)):
        print(f"\n{data.get('priority')}. {data.get('description')}")
        print(f"   URL: {data.get('url')}")
        print(f"   Active: {data.get('active', True)}")


@pytest.mark.integration
def test_oracle_agent_relevance(oracle_agent):
    """Test the is_relevant method for various software names."""
    test_cases = [
        ("Oracle Database", True),
        ("MySQL", True),
        ("Java", True),
        ("JDK", True),
        ("VirtualBox", True),
        ("Solaris", True),
        ("Ubuntu", False),
        ("Windows Server", False),
        ("Python", False),
    ]
    
    print("\n" + "="*80)
    print("Testing Oracle Agent Relevance")
    print("="*80)
    
    for software_name, expected in test_cases:
        result = oracle_agent.is_relevant(software_name)
        icon = "✅" if result == expected else "❌"
        print(f"{icon} {software_name}: {result} (expected: {expected})")
        assert result == expected, f"Expected {expected} for {software_name}, got {result}"


@pytest.mark.integration
def test_get_oracle_url(oracle_agent):
    """Test URL retrieval for Oracle products."""
    url = oracle_agent._get_oracle_url("Oracle Database")
    
    assert url is not None
    assert "oracle.com" in url
    print(f"\n✅ Oracle URL: {url}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_all_from_url(oracle_agent):
    """Test parallel extraction of all software from Oracle PDFs using fetch_all_from_url."""
    import time
    
    print("\n" + "="*80)
    print("Testing Parallel Extraction from All Oracle PDFs")
    print("="*80)
    
    start_time = time.time()
    
    # Use the agent's parallel bulk extraction method
    all_software = await oracle_agent.fetch_all_from_url()
    
    elapsed = time.time() - start_time
    
    print(f"\n✅ Parallel extraction completed in {elapsed:.2f} seconds")
    print(f"📊 Total software entries extracted: {len(all_software)}")
    
    # Verify we got results
    assert len(all_software) > 0, "Should extract at least some software"
    
    # Show sample entries
    print("\n📋 Sample entries (first 20):")
    for idx, entry in enumerate(all_software[:20], 1):
        software = entry.get('software_name', 'N/A')
        version = entry.get('version', 'N/A')
        eol = entry.get('eol_date', 'N/A')
        pdf_source = entry.get('pdf_source', 'N/A')
        print(f"{idx:2d}. {software[:40]:40s} {version[:10]:10s} | EOL: {eol[:10]:10s} | {pdf_source[:25]:25s}")
    
    if len(all_software) > 20:
        print(f"    ... and {len(all_software) - 20} more entries")
    
    # Group by PDF source
    by_source = {}
    for entry in all_software:
        source = entry.get('pdf_source', 'Unknown')
        by_source[source] = by_source.get(source, 0) + 1
    
    print("\n📁 Entries by PDF source:")
    for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"   {source:60s}: {count:5d} entries")
    
    # Performance note
    num_pdfs = len([url for url in oracle_agent.eol_urls.values() if url.get('active', True)])
    print(f"\n⚡ Processed {num_pdfs} PDFs in parallel: {elapsed:.2f}s")
    print(f"   Average: ~{elapsed/num_pdfs:.2f}s per PDF (with parallelization)")
    
    print("\n" + "="*80)
    print(f"✅ Successfully extracted {len(all_software)} entries from {num_pdfs} PDFs")
    print("="*80)


if __name__ == "__main__":
    """Run tests directly for quick validation."""
    print("\n" + "="*80)
    print("Running Oracle Agent Tests")
    print("="*80)
    
    agent = OracleEOLAgent()
    
    # Test configuration
    print("\n1. Testing URL Configuration...")
    test_oracle_urls_configuration(agent)
    
    # Test relevance
    print("\n2. Testing Relevance Check...")
    test_oracle_agent_relevance(agent)
    
    # Test async operations
    print("\n3. Testing EOL Data Retrieval...")
    asyncio.run(test_multiple_products(agent))
    
    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80)
