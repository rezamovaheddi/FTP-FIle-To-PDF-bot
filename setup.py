#!/usr/bin/env python3
"""
Setup and diagnostic script for File-to-PDF Converter
"""

import subprocess
import sys
import os
import requests
from pathlib import Path

def print_section(title):
    """Print a section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def run_command(cmd, description=""):
    """Run a shell command and return result"""
    if description:
        print(f"Running: {description}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_python_version():
    """Check Python version"""
    print_section("1. Python Version Check")
    version = sys.version
    print(f"Python version: {version}")
    
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 8:
        print("✓ Python version is compatible (3.8+)")
        return True
    else:
        print("✗ Python 3.8+ required")
        return False

def install_dependencies():
    """Install required packages"""
    print_section("2. Installing Dependencies")
    
    packages = [
        'python-telegram-bot==21.3',
        'fastapi==0.109.0',
        'uvicorn==0.27.0',
        'fpdf2==2.7.0',
        'requests==2.32.0',
        'Pillow==10.1.0'
    ]
    
    print("Installing packages...")
    success, stdout, stderr = run_command(
        f"{sys.executable} -m pip install {' '.join(packages)}",
        "pip install"
    )
    
    if success:
        print("✓ All dependencies installed successfully")
        return True
    else:
        print("✗ Failed to install dependencies")
        print(f"Error: {stderr}")
        return False

def verify_imports():
    """Verify all imports work"""
    print_section("3. Verifying Imports")
    
    packages = [
        ('telegram', 'python-telegram-bot'),
        ('fastapi', 'fastapi'),
        ('uvicorn', 'uvicorn'),
        ('fpdf', 'fpdf2'),
        ('requests', 'requests'),
        ('PIL', 'Pillow')
    ]
    
    all_ok = True
    for module_name, package_name in packages:
        try:
            __import__(module_name)
            print(f"✓ {package_name}")
        except ImportError:
            print(f"✗ {package_name} - NOT INSTALLED")
            all_ok = False
    
    return all_ok

def check_files():
    """Check if required files exist"""
    print_section("4. Checking Project Files")
    
    files = ['bot.py', 'backend.py', 'requirements.txt']
    all_ok = True
    
    for filename in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            print(f"✓ {filename} ({size} bytes)")
        else:
            print(f"✗ {filename} - NOT FOUND")
            all_ok = False
    
    return all_ok

def check_backend_running():
    """Check if backend is running"""
    print_section("5. Backend Connectivity Check")
    
    try:
        response = requests.get('http://localhost:8000/health', timeout=2)
        if response.status_code == 200:
            print("✓ Backend is running on localhost:8000")
            print(f"  Response: {response.json()}")
            return True
        else:
            print(f"✗ Backend returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to backend on localhost:8000")
        print("  Make sure to run: python backend.py")
        return False
    except Exception as e:
        print(f"✗ Error checking backend: {e}")
        return False

def create_directories():
    """Create required directories"""
    print_section("6. Creating Required Directories")
    
    dirs = ['uploads', 'pdfs']
    all_ok = True
    
    for dirname in dirs:
        try:
            Path(dirname).mkdir(exist_ok=True)
            print(f"✓ {dirname}/")
        except Exception as e:
            print(f"✗ Failed to create {dirname}/: {e}")
            all_ok = False
    
    return all_ok

def check_telegram_token():
    """Check if Telegram token is set"""
    print_section("7. Telegram Bot Configuration")
    
    with open('bot.py', 'r') as f:
        content = f.read()
        if 'YOUR_TELEGRAM_BOT_TOKEN' in content:
            print("⚠ Telegram bot token not configured")
            print("  Edit bot.py and replace YOUR_TELEGRAM_BOT_TOKEN with your actual token")
            print("  Get token from @BotFather on Telegram")
            return False
        else:
            print("✓ Telegram bot token appears to be configured")
            return True

def main():
    """Run all checks"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║     File-to-PDF Converter - Setup & Diagnostic Tool       ║")
    print("╚════════════════════════════════════════════════════════════╝")
    
    results = []
    
    # Run checks
    results.append(("Python Version", check_python_version()))
    results.append(("Dependencies", install_dependencies()))
    results.append(("Imports", verify_imports()))
    results.append(("Project Files", check_files()))
    results.append(("Directories", create_directories()))
    results.append(("Telegram Token", check_telegram_token()))
    
    # Backend check (optional, may not be running yet)
    try:
        check_backend_running()
    except:
        pass
    
    # Summary
    print_section("Setup Summary")
    
    critical_passed = all(v for k, v in results if k in [
        "Python Version", "Dependencies", "Imports", "Project Files"
    ])
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:.<40} {status}")
    
    print("\n" + "="*60)
    
    if critical_passed:
        print("\n✓ Setup verification PASSED!")
        print("\nNext steps:")
        print("1. Ensure YOUR_TELEGRAM_BOT_TOKEN is set in bot.py")
        print("2. Terminal 1: python backend.py")
        print("3. Terminal 2: python bot.py")
        print("4. Send /start to your bot on Telegram")
        print("5. Send a .txt file to test")
    else:
        print("\n✗ Setup verification FAILED!")
        print("Please fix the issues above and try again.")
        return 1
    
    print("\n" + "="*60 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())