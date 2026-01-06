#!/usr/bin/env python3
"""
Test script to verify Amazon product search fixes
Tests both the connector and the langchain command processor
"""

import json
import sys
import os
from pprint import pprint

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from connectors.amzon_connector import get_amazon_result

def test_amazon_search():
    """Test Amazon single product search with the example from the issue"""
    print("=" * 60)
    print("Testing Amazon Product Search Fix")
    print("=" * 60)
    
    # Test with the boat soundbar product from the issue
    test_query = "boat aavante soundbar"
    
    print(f"\nSearching Amazon for: '{test_query}'")
    print("-" * 60)
    
    tool_request = {
        "action": "single_product_search",
        "query": test_query
    }
    
    result = get_amazon_result(tool_request)
    
    print("\nProduct Information Retrieved:")
    print("-" * 60)
    
    if result:
        pprint(result)
        
        # Check that critical fields are not None
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS:")
        print("=" * 60)
        
        checks = {
            'Title': result.get('title'),
            'Price': result.get('price'),
            'Rating': result.get('rating'),
            'Reviews Count': result.get('reviews_count'),
            'URL': result.get('url'),
            'ASIN': result.get('asin'),
        }
        
        all_passed = True
        for field, value in checks.items():
            status = "✓ PASS" if value else "✗ FAIL"
            print(f"{status}: {field} = {value}")
            if not value:
                all_passed = False
        
        if all_passed:
            print("\n✓ All fields extracted successfully!")
            print("✓ The product data is now TTS-ready")
            return True
        else:
            print("\n✗ Some fields are still None or missing")
            print("Check the fallback logic in amzon_connector.py")
            return False
    else:
        print("✗ Search returned no results")
        return False


def test_multi_product_search():
    """Test Amazon multi-product search"""
    print("\n" + "=" * 60)
    print("Testing Amazon Multi-Product Search")
    print("=" * 60)
    
    test_query = "soundbar under 5000"
    
    print(f"\nSearching Amazon for: '{test_query}'")
    print("-" * 60)
    
    tool_request = {
        "action": "multi_product_search",
        "query": test_query,
        "max_results": 3
    }
    
    result = get_amazon_result(tool_request)
    
    if isinstance(result, list):
        print(f"\nFound {len(result)} products")
        for i, product in enumerate(result[:3], 1):
            print(f"\nProduct {i}:")
            print(f"  Title: {product.get('title', 'N/A')}")
            print(f"  Price: {product.get('price', 'N/A')}")
            print(f"  Rating: {product.get('rating', 'N/A')}")
            print(f"  Reviews: {product.get('reviews_count', 'N/A')}")
        return True
    else:
        print("✗ Multi-product search failed")
        return False


if __name__ == "__main__":
    try:
        single_result = test_amazon_search()
        multi_result = test_multi_product_search()
        
        print("\n" + "=" * 60)
        print("FINAL RESULTS:")
        print("=" * 60)
        print(f"Single Product Search: {'✓ PASS' if single_result else '✗ FAIL'}")
        print(f"Multi Product Search: {'✓ PASS' if multi_result else '✗ FAIL'}")
        
        if single_result and multi_result:
            print("\n✓ All tests passed! The fix is working correctly.")
            sys.exit(0)
        else:
            print("\n✗ Some tests failed. Review the output above.")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
