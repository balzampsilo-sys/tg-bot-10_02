"""Migration v005: Add FOREIGN KEY constraints

Эта миграция добавляет FOREIGN KEY constraints для:
1. bookings.service_id -> services.id
2. Включает PRAGMA foreign_keys = ON

Это предотвращает создание бронирований с несуществующими услугами.
"""

import logging
import sqlite3
from typing import Optional

import aiosqlite

from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class AddForeignKeys:
    """Migration для добавления FOREIGN KEY constraints"""

    version = 5
    description = "Add FOREIGN KEY constraints for data integrity"

    @staticmethod
    async def up() -> bool:
        """Применить миграцию

        ВАЖНО: SQLite требует пересоздания таблицы для добавления FK

        Returns:
            True если успешно, False иначе
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                # Включаем foreign keys
                await db.execute("PRAGMA foreign_keys = ON")

                # Проверяем есть ли уже FK constraints
                async with db.execute("PRAGMA foreign_key_list(bookings)") as cursor:
                    existing_fks = await cursor.fetchall()

                if existing_fks:
                    logger.info("✅ FOREIGN KEY constraints already exist, skipping")
                    return True

                logger.info("🔄 Adding FOREIGN KEY constraints to bookings table...")

                # SQLite не поддерживает ALTER TABLE ADD CONSTRAINT
                # Нужно пересоздать таблицу

                # 1. Создаем новую таблицу с FK
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS bookings_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        time TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        created_at TEXT NOT NULL,
                        service_id INTEGER NOT NULL DEFAULT 1,
                        duration_minutes INTEGER NOT NULL DEFAULT 60,
                        UNIQUE(date, time),
                        FOREIGN KEY (service_id) REFERENCES services(id)
                            ON DELETE RESTRICT
                            ON UPDATE CASCADE
                    )"""
                )

                # 2. Копируем данные
                await db.execute(
                    """INSERT INTO bookings_new 
                       (id, date, time, user_id, username, created_at, service_id, duration_minutes)
                       SELECT id, date, time, user_id, username, created_at, 
                              COALESCE(service_id, 1), COALESCE(duration_minutes, 60)
                       FROM bookings"""
                )

                # 3. Удаляем старую таблицу
                await db.execute("DROP TABLE bookings")

                # 4. Переименовываем новую
                await db.execute("ALTER TABLE bookings_new RENAME TO bookings")

                # 5. Восстанавливаем индексы
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date, time)"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_service ON bookings(service_id)"
                )
                await db.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS idx_user_active_bookings 
                       ON bookings(user_id, date, time)"""
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_date_time ON bookings(date, time)"
                )

                await db.commit()

                # Проверяем результат
                async with db.execute("PRAGMA foreign_key_list(bookings)") as cursor:
                    fks = await cursor.fetchall()

                if fks:
                    logger.info(f"✅ Successfully added {len(fks)} FOREIGN KEY constraint(s)")
                    return True
                else:
                    logger.error("❌ Failed to add FOREIGN KEY constraints")
                    return False

        except Exception as e:
            logger.error(f"❌ Migration v005 failed: {e}", exc_info=True)
            return False

    @staticmethod
    async def down() -> bool:
        """Откатить миграцию

        Returns:
            True если успешно, False иначе
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                logger.info("🔄 Removing FOREIGN KEY constraints...")

                # Создаем таблицу без FK
                await db.execute(
                    """CREATE TABLE IF NOT EXISTS bookings_old (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,
                        time TEXT,
                        user_id INTEGER,
                        username TEXT,
                        created_at TEXT,
                        service_id INTEGER DEFAULT 1,
                        duration_minutes INTEGER DEFAULT 60,
                        UNIQUE(date, time)
                    )"""
                )

                await db.execute(
                    """INSERT INTO bookings_old SELECT * FROM bookings"""
                )

                await db.execute("DROP TABLE bookings")
                await db.execute("ALTER TABLE bookings_old RENAME TO bookings")

                # Восстанавливаем индексы
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings(date, time)"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)"
                )

                await db.commit()

                logger.info("✅ FOREIGN KEY constraints removed")
                return True

        except Exception as e:
            logger.error(f"❌ Migration v005 rollback failed: {e}", exc_info=True)
            return False


if __name__ == "__main__":
    import asyncio

    async def test():
        print("🧪 Testing migration v005...")
        success = await AddForeignKeys.up()
        print(f"Result: {'✅ Success' if success else '❌ Failed'}")

    asyncio.run(test())
