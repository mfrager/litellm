#!/usr/bin/env python3
"""
Simple test script to verify MySQL async connection using DATABASE_ASYNC_TEST environment variable.
"""

import os
import sys
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Load environment variables from the root .env file
load_dotenv('../../../.env')

# Also try loading from current directory and parent directories as fallback
load_dotenv()
load_dotenv('.env')
load_dotenv('../.env')
load_dotenv('../../.env')
load_dotenv('../../../.env')
sys.path.append('../..')

@pytest_asyncio.fixture(scope="session")
async def mysql_engine():
    """Create MySQL async engine and test connection."""
    # Get database URL from environment - must be MySQL, no fallback
    database_url = os.environ.get('DATABASE_ASYNC_TEST')
    
    if not database_url:
        raise ValueError("DATABASE_ASYNC_TEST environment variable is not set")
    
    if 'mysql' not in database_url:
        raise ValueError(f"DATABASE_ASYNC_TEST must be a MySQL URL, got: {database_url}")
    
    print(f"Connecting to MySQL: {database_url.replace(':password@', ':***@')}")
    
    # Create async database engine
    engine = create_async_engine(database_url, echo=False)
    
    yield engine
    
    # Cleanup
    await engine.dispose()

@pytest.mark.asyncio
async def test_mysql_connection(mysql_engine):
    """Test basic MySQL connection and query."""
    print("\n🧪 Testing MySQL Connection...")
    
    try:
        # Test basic connection with a simple query
        async with mysql_engine.begin() as conn:
            result = await conn.execute(text("SELECT 1 as test_value"))
            row = result.fetchone()
            assert row[0] == 1
            print("✅ Basic SELECT query successful")
            
            # Test database and version info
            result = await conn.execute(text("SELECT DATABASE() as current_db, VERSION() as mysql_version"))
            row = result.fetchone()
            current_db = row[0]
            mysql_version = row[1]
            
            print(f"✅ Connected to database: {current_db}")
            print(f"✅ MySQL version: {mysql_version}")
            
            # Verify it's actually MySQL (not SQLite or other)
            # Check for MySQL version format (numbers like 8.0.x, 9.x.x) or explicit mysql/mariadb
            is_mysql = ('mysql' in mysql_version.lower() or 
                       'mariadb' in mysql_version.lower() or
                       any(c.isdigit() for c in mysql_version))  # MySQL versions are numeric
            assert is_mysql, f"Expected MySQL/MariaDB but got version: {mysql_version}"
            print("✅ Confirmed MySQL/MariaDB connection")
            
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        raise
    
    print("🎉 All MySQL connection tests passed!")


if __name__ == "__main__":
    # Run the tests directly
    pytest.main([__file__, "-v", "-s"])
