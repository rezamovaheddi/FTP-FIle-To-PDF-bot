#!/usr/bin/env python3
"""
Test client for File-to-PDF Converter backend
"""

import requests
import os
from pathlib import Path

BACKEND_URL = "http://localhost:8000"
TEST_USER_ID = "test_user_123"

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def create_test_file():
    """Create a test text file"""
    test_content = """Test PDF Conversion
===================

This is a test file for the File-to-PDF Converter.

Features:
- Converts text files to PDF
- Stores conversion history in database
- User-friendly Telegram bot interface

Lines 1-5 complete.
This is line 6.
This is line 7.
This is line 8.
This is line 9.
This is line 10.
"""
    
    filename = "test_file.txt"
    with open(filename, 'w') as f:
        f.write(test_content)
    
    print(f"Created test file: {filename}")
    return filename

def test_health():
    """Test health endpoint"""
    print_section("1. Testing Health Endpoint")
    
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            print("✓ Health check passed")
            return True
        else:
            print("✗ Health check failed")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to backend")
        print(f"  Make sure backend is running: python backend.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_convert():
    """Test file conversion"""
    print_section("2. Testing File Conversion Endpoint")
    
    # Create test file
    test_file = create_test_file()
    
    try:
        with open(test_file, 'rb') as f:
            files = {'file': ('test_file.txt', f)}
            data = {'user_id': TEST_USER_ID}
            
            print("Sending request to /convert endpoint...")
            response = requests.post(
                f"{BACKEND_URL}/convert",
                files=files,
                data=data,
                timeout=10
            )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 200:
            result = response.json()
            pdf_path = result.get('pdf_file')
            print(f"✓ Conversion successful")
            print(f"  PDF path: {pdf_path}")
            return pdf_path
        else:
            print(f"✗ Conversion failed with status {response.status_code}")
            return None
    
    except Exception as e:
        print(f"✗ Error during conversion: {e}")
        return None
    
    finally:
        # Clean up test file
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"Cleaned up test file")

def test_get_last(user_id):
    """Test getting last conversions"""
    print_section("3. Testing Get Last Conversions Endpoint")
    
    try:
        print(f"Fetching last conversions for user: {user_id}")
        response = requests.get(
            f"{BACKEND_URL}/last/{user_id}",
            timeout=5
        )
        
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Response: {data}")
        
        if response.status_code == 200:
            conversions = data.get('conversions', [])
            print(f"✓ Retrieved {len(conversions)} conversions")
            for i, conv in enumerate(conversions, 1):
                print(f"  {i}. {conv['original_file']}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_pdf(pdf_path):
    """Test PDF retrieval"""
    print_section("4. Testing PDF Retrieval Endpoint")
    
    if not pdf_path:
        print("✗ No PDF path provided (conversion might have failed)")
        return False
    
    try:
        print(f"Requesting PDF: {pdf_path}")
        response = requests.get(
            f"{BACKEND_URL}/pdf",
            params={"file_path": pdf_path},
            timeout=5
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Content Type: {response.headers.get('content-type')}")
        print(f"Content Length: {len(response.content)} bytes")
        
        if response.status_code == 200:
            # Save the retrieved PDF
            output_path = "retrieved_test.pdf"
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✓ PDF retrieved successfully")
            print(f"  Saved to: {output_path}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_statistics():
    """Test statistics endpoint"""
    print_section("5. Testing Statistics Endpoint")
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/stats",
            timeout=5
        )
        
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Response: {data}")
        
        if response.status_code == 200:
            print("✓ Statistics retrieved successfully")
            print(f"  Total conversions: {data.get('total_conversions', 0)}")
            print(f"  Unique users: {data.get('unique_users', 0)}")
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Run all tests"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║        File-to-PDF Converter - Backend Test Suite         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    results = []
    
    # Test health
    if not test_health():
        print("\n✗ Backend is not running!")
        print("Start it with: python backend.py")
        return 1
    
    results.append(("Health Check", True))
    
    # Test conversion
    pdf_path = test_convert()
    results.append(("File Conversion", pdf_path is not None))
    
    # Test get last
    results.append(("Get Last Conversions", test_get_last(TEST_USER_ID)))
    
    # Test PDF retrieval
    if pdf_path:
        results.append(("PDF Retrieval", test_get_pdf(pdf_path)))
    
    # Test statistics
    results.append(("Statistics", test_statistics()))
    
    # Summary
    print_section("Test Summary")
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:.<40} {status}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n✓ All tests passed! Backend is working correctly.")
        return 0
    else:
        print("\n✗ Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())