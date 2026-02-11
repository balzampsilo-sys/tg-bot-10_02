"""Migration: Add admin roles and audit log"""

import asyncio
import logging

import aiosqlite

from config import DATABASE_PATH


async def migrate():
    """Добавляем роли админов и audit log"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 1. Добавляем роль в таблицу admins
        try:
            await db.execute(
                "ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'moderator'"
            )
            logging.info("✅ Added 'role' column to admins table")
        except Exception as e:
            logging.warning(f"⚠️ Column 'role' already exists: {e}")

        # 2. Создаем таблицу audit_log
        await db.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id TEXT,
                details TEXT,
                timestamp TEXT NOT NULL
            )"""
        )
        logging.info("✅ Created audit_log table")

        # 3. Индексы для audit_log
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_admin ON audit_log(admin_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)"
        )
        logging.info("✅ Created audit_log indexes")

        await db.commit()
        logging.info("✅✅✅ Migration 002 completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate())
    print("✅ Migration complete! Run: python database/migrations/002_add_admin_roles_and_audit.py")
