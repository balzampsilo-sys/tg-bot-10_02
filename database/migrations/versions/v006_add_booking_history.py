"""Миграция v006: Добавление таблицы истории изменений записей

Priority: P0 (High)

Функционал:
- История всех изменений бронирований
- Кто сделал изменение (пользователь/админ)
- Старые и новые значения
- Причина изменения
- Индексы для быстрого поиска
"""

import logging
from datetime import datetime

import aiosqlite

from database.migrations.migration_manager import Migration


class AddBookingHistory(Migration):
    """Миграция: Добавление таблицы booking_history"""

    version = 6
    description = "Add booking_history table for audit trail"

    async def upgrade(self, db: aiosqlite.Connection) -> None:
        """Применить миграцию"""
        logging.info(f"[v{self.version}] Creating booking_history table...")

        # Создаем таблицу истории
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS booking_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                changed_by INTEGER NOT NULL,
                changed_by_type TEXT NOT NULL,
                old_date TEXT,
                old_time TEXT,
                new_date TEXT,
                new_time TEXT,
                old_service_id INTEGER,
                new_service_id INTEGER,
                reason TEXT,
                changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE
            )
            """
        )

        # Индексы для производительности
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_booking_history_booking
            ON booking_history(booking_id)
            """
        )

        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_booking_history_action
            ON booking_history(action)
            """
        )

        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_booking_history_changed_by
            ON booking_history(changed_by)
            """
        )

        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_booking_history_changed_at
            ON booking_history(changed_at)
            """
        )

        logging.info(f"[v{self.version}] ✅ booking_history table created with indexes")

    async def downgrade(self, db: aiosqlite.Connection) -> None:
        """Откат миграции"""
        logging.info(f"[v{self.version}] Dropping booking_history table...")

        # Удаляем индексы
        await db.execute("DROP INDEX IF EXISTS idx_booking_history_booking")
        await db.execute("DROP INDEX IF EXISTS idx_booking_history_action")
        await db.execute("DROP INDEX IF EXISTS idx_booking_history_changed_by")
        await db.execute("DROP INDEX IF EXISTS idx_booking_history_changed_at")

        # Удаляем таблицу
        await db.execute("DROP TABLE IF EXISTS booking_history")

        logging.info(f"[v{self.version}] ✅ booking_history table dropped")

    async def validate(self, db: aiosqlite.Connection) -> bool:
        """Проверить применение миграции"""
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='booking_history'"
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                logging.error(f"[v{self.version}] ❌ Validation failed: table not found")
                return False

        # Проверяем структуру
        async with db.execute("PRAGMA table_info(booking_history)") as cursor:
            columns = await cursor.fetchall()
            column_names = {col[1] for col in columns}

            required_columns = {
                "id",
                "booking_id",
                "action",
                "changed_by",
                "changed_by_type",
                "old_date",
                "old_time",
                "new_date",
                "new_time",
                "old_service_id",
                "new_service_id",
                "reason",
                "changed_at",
            }

            if not required_columns.issubset(column_names):
                missing = required_columns - column_names
                logging.error(
                    f"[v{self.version}] ❌ Validation failed: missing columns {missing}"
                )
                return False

        # Проверяем индексы
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='booking_history'"
        ) as cursor:
            indexes = await cursor.fetchall()
            index_names = {idx[0] for idx in indexes}

            required_indexes = {
                "idx_booking_history_booking",
                "idx_booking_history_action",
                "idx_booking_history_changed_by",
                "idx_booking_history_changed_at",
            }

            if not required_indexes.issubset(index_names):
                missing = required_indexes - index_names
                logging.warning(
                    f"[v{self.version}] ⚠️ Some indexes missing: {missing} (non-critical)"
                )

        logging.info(f"[v{self.version}] ✅ Validation passed")
        return True
