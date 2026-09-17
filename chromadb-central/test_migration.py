#!/usr/bin/env python3
"""
Test script for PostgreSQL migration functionality.
Run this locally to verify the migration setup before deploying.
"""
import os
import sys
import json
from pathlib import Path

# Add chromadb-central to path
sys.path.insert(0, str(Path(__file__).parent))

def test_postgres_connection():
    """Test PostgreSQL connection."""
    print("\n" + "=" * 60)
    print("TEST 1: PostgreSQL Connection")
    print("=" * 60)
    
    try:
        from api.postgres_db import get_postgres_connection, test_postgres_connection as pg_test
        
        result = pg_test()
        print(f"Connection Status: {result['status']}")
        print(f"Details: {result['details']}")
        print(json.dumps(result, indent=2))
        return result['status'] in ['ok', 'configured']
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def test_chromadb_projects():
    """Test ChromaDB project discovery."""
    print("\n" + "=" * 60)
    print("TEST 2: ChromaDB Projects Discovery")
    print("=" * 60)
    
    try:
        from api.migrate_to_postgres import list_chromadb_projects
        
        projects = list_chromadb_projects()
        if not projects:
            print("[WARNING] No ChromaDB projects found")
            return True
        
        print(f"Found {len(projects)} projects:")
        for project, collections in projects.items():
            print(f"  [PROJECT] {project}")
            for col in collections:
                print(f"     * {col}")
        return True
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def test_migration_status():
    """Test migration status retrieval."""
    print("\n" + "=" * 60)
    print("TEST 3: Migration Status")
    print("=" * 60)
    
    try:
        from api.migrate_to_postgres import get_migration_status
        
        status = get_migration_status()
        print(f"PostgreSQL Available: {status.get('postgres_available', False)}")
        print(f"Total Tables: {len(status.get('tables', []))}")
        print(f"Total Documents: {status.get('total_documents', 0)}")
        
        if status.get('tables'):
            print("\nTables:")
            for table in status['tables']:
                print(f"  - {table['name']}: {table['document_count']} docs, {table['vectors_indexed']} vectorized")
        
        print(json.dumps(status, indent=2))
        return True
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def test_table_creation():
    """Test creating a vector table."""
    print("\n" + "=" * 60)
    print("TEST 4: Table Creation")
    print("=" * 60)
    
    try:
        from api.migrate_to_postgres import create_vector_table
        
        # Try to create a test table
        success, msg = create_vector_table("test_project", "test_collection")
        if success:
            print(f"[OK] {msg}")
        else:
            print(f"[ERROR] {msg}")
        return success
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def test_routes_import():
    """Test that migration routes can be imported."""
    print("\n" + "=" * 60)
    print("TEST 5: Route Import")
    print("=" * 60)
    
    try:
        from api.routes import migration
        print("[OK] Migration routes imported successfully")
        print(f"Available endpoints:")
        print(f"  - GET  /migration/status")
        print(f"  - GET  /migration/projects")
        print(f"  - POST /migration/migrate-all")
        print(f"  - POST /migration/migrate/{{project}}/{{collection}}")
        print(f"  - GET  /migration/health")
        return True
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n[TEST] PostgreSQL Migration Test Suite")
    
    # Check if we have env vars
    if not os.getenv("POSTGRES_HOST") and not os.getenv("POSTGRES_DATABASE_URL"):
        print("\n[WARNING] No PostgreSQL configuration found")
        print("Set POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB environment variables")
    
    results = {
        "PostgreSQL Connection": test_postgres_connection(),
        "ChromaDB Discovery": test_chromadb_projects(),
        "Migration Status": test_migration_status(),
        "Table Creation": test_table_creation(),
        "Route Import": test_routes_import(),
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nPassed: {passed}/{total}\n")
    
    for test_name, result in results.items():
        status = "[OK]" if result else "[FAIL]"
        print(f"{status} {test_name}")
    
    return all(results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
