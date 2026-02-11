"""Migration 001: Add duration_minutes column to bookings table

This migration adds the missing duration_minutes column that is referenced
in booking_service.py but was not created in the initial schema.

Run this migration manually or via migration tool:
    python -m database.migrations.001_add_duration_minutes
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import aiosqlite
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


async def check_column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Check if column exists in table"""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    await cursor.close()
    return any(col[1] == column for col in columns)


async def migrate_up():
    """Add duration_minutes column to bookings table"""
    logger.info("Starting migration 001: add duration_minutes")
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if column already exists
        if await check_column_exists(db, "bookings", "duration_minutes"):
            logger.info("✅ Column 'duration_minutes' already exists, skipping migration")
            return True
        
        try:
            # Add column with default value
            await db.execute(
                "ALTER TABLE bookings ADD COLUMN duration_minutes INTEGER DEFAULT 60"
            )
            await db.commit()
            logger.info("✅ Migration 001 completed: duration_minutes column added")
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration 001 failed: {e}")
            await db.rollback()
            return False


async def migrate_down():
    """Remove duration_minutes column (SQLite doesn't support DROP COLUMN easily)"""
    logger.warning("⚠️ Rollback not supported for SQLite ALTER TABLE ADD COLUMN")
    logger.warning("To rollback, restore from backup or recreate table")
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🔄 Running migration 001: add duration_minutes")
    success = asyncio.run(migrate_up())
    
    if success:
        print("✅ Migration completed successfully")
        sys.exit(0)
    else:
        print("❌ Migration failed")
        sys.exit(1)
