#!/usr/bin/env python3
"""
Test script to demonstrate intelligent routing between local LLM and OpenAI API
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from test_local import is_personal_query

def test_routing_logic():
    """Test the personal query detection logic"""
    test_queries = [
        # Personal queries (should route to local LLM)
        ("What is my wife's name?", True),
        ("Tell me about my family", True),
        ("Remember my birthday", True),
        ("What's my phone number?", True),
        ("Do you know me personally?", True),
        ("What's my job?", True),
        ("Tell me about myself", True),
        
        # General queries (should route to OpenAI)
        ("What is the capital of France?", False),
        ("How does photosynthesis work?", False),
        ("Write a poem about nature", False),
        ("What's the weather like?", False),
        ("Explain quantum physics", False),
        ("What's 2+2?", False),
        ("Tell me about the phone specs", False),
    ]
    
    print("🧪 Testing Personal Query Detection")
    print("=" * 50)
    
    correct = 0
    total = len(test_queries)
    
    for query, expected_personal in test_queries:
        is_personal = is_personal_query(query)
        route = "Local LLM" if is_personal else "OpenAI"
        expected_route = "Local LLM" if expected_personal else "OpenAI"
        status = "✅" if is_personal == expected_personal else "❌"
        
        print(f"{status} '{query}'")
        print(f"   → {route} (Expected: {expected_route})")
        
        if is_personal == expected_personal:
            correct += 1
        print()
    
    accuracy = (correct / total) * 100
    print(f"🎯 Accuracy: {correct}/{total} ({accuracy:.1f}%)")

if __name__ == "__main__":
    test_routing_logic()