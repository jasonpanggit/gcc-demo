#!/usr/bin/env python3
"""
Test the mock data endpoints
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint, name):
    """Test an API endpoint"""
    try:
        print(f"\n{'='*80}")
        print(f"Testing: {name}")
        print(f"URL: {BASE_URL}{endpoint}")
        print(f"{'='*80}")
        
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status: {response.status_code}")
            print(f"✅ Success: {data.get('success', 'N/A')}")
            print(f"✅ Count: {data.get('count', len(data.get('data', [])))}")
            
            if 'data' in data and data['data']:
                print(f"\nFirst item sample:")
                first_item = data['data'][0]
                for key, value in list(first_item.items())[:5]:
                    print(f"  - {key}: {value}")
            
            return True
        else:
            print(f"❌ Status: {response.status_code}")
            print(f"❌ Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("\n🧪 TESTING MOCK DATA ENDPOINTS")
    print("="*80)
    
    # Test endpoints
    tests = [
        ("/api/inventory", "Software Inventory"),
        ("/api/inventory/raw/os", "OS Inventory"),
        ("/health", "Health Check"),
    ]
    
    results = []
    for endpoint, name in tests:
        result = test_endpoint(endpoint, name)
        results.append((name, result))
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} | {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
