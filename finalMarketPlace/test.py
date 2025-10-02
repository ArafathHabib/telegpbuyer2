"""
Test script to verify basic setup
Run this before starting the server
"""
import sys
import os

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    try:
        import config
        print("✓ config.py imported")
        
        import database
        print("✓ database.py imported")
        
        import auth
        print("✓ auth.py imported")
        
        from fastapi import FastAPI
        print("✓ FastAPI available")
        
        from telethon import TelegramClient
        print("✓ Telethon available")
        
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_database():
    """Test database initialization"""
    print("\nTesting database...")
    try:
        from database import init_database
        init_database()
        print("✓ Database schema created")
        
        # Test database operations
        from database import create_user, get_user_by_id
        import time
        
        user_id = create_user("testuser", "testpass", "@testuser", "0x123", int(time.time()))
        if user_id:
            print(f"✓ Test user created (ID: {user_id})")
            
            user = get_user_by_id(user_id)
            if user:
                print(f"✓ User retrieved: {user['username']}")
                return True
        
        return False
    except Exception as e:
        print(f"✗ Database error: {e}")
        return False

def test_config():
    """Test configuration"""
    print("\nTesting configuration...")
    try:
        import config
        
        print(f"✓ Database path: {config.DB_PATH}")
        print(f"✓ Server: {config.WEB_HOST}:{config.WEB_PORT}")
        print(f"✓ Admin tokens configured: {len(config.ADMIN_TOKENS)}")
        print(f"✓ Max groups per receiver: {config.MAX_GROUPS_PER_RECEIVER}")
        
        return True
    except Exception as e:
        print(f"✗ Config error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("SETUP VERIFICATION TEST")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Database", test_database),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} test crashed: {e}")
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    print("=" * 60)
    if all_passed:
        print("✓ All tests passed! Ready to proceed.")
    else:
        print("✗ Some tests failed. Fix issues before continuing.")
    
    return all_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)