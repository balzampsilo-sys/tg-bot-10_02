# Database Migrations

## Overview

Migrations track and apply database schema changes in a controlled manner.

## Available Migrations

### 001_add_duration_minutes.py
**Status:** Required  
**Purpose:** Adds missing `duration_minutes` column to `bookings` table  
**Safe to run:** ✅ Yes (checks if column exists before adding)

**Run manually:**
```bash
python -m database.migrations.001_add_duration_minutes
```

## Migration Best Practices

1. **Always backup database before migrations**
   ```bash
   cp bookings.db bookings.db.backup
   ```

2. **Test on development copy first**

3. **Migrations should be idempotent** (safe to run multiple times)

4. **Never edit existing migrations** (create new ones)

## Creating New Migrations

1. Create file: `002_your_migration_name.py`
2. Implement `migrate_up()` and `migrate_down()`
3. Add checks for existing state
4. Test thoroughly

## Migration Template

```python
import asyncio
import logging
import aiosqlite
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

async def migrate_up():
    """Apply migration"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            # Your migration code here
            await db.commit()
            logger.info("✅ Migration completed")
            return True
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            await db.rollback()
            return False

async def migrate_down():
    """Rollback migration"""
    # Implementation
    pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate_up())
```
