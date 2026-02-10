#!/usr/bin/env python3
"""Миграция: Добавление колонки service_id в таблицу bookings

Эта миграция добавляет поддержку множественных услуг.
service_id будет ссылаться на ID услуги из таблицы services.

Выполнить: python database/migrations/add_service_id_to_bookings.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import aiosqlite
from config import DATABASE_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def migrate():
    """Добавить service_id в bookings"""
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Проверяем, существует ли уже колонка
        async with db.execute("PRAGMA table_info(bookings)") as cursor:
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if "service_id" in column_names:
                logging.info("✅ Колонка service_id уже существует в bookings")
                return True
        
        logging.info("🔄 Добавляем колонку service_id в таблицу bookings...")
        
        try:
            # Добавляем колонку service_id
            await db.execute(
                "ALTER TABLE bookings ADD COLUMN service_id INTEGER DEFAULT 1"
            )
            
            # Создаем индекс для service_id
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_service
                ON bookings(service_id)"""
            )
            
            await db.commit()
            
            logging.info("✅ Миграция успешно выполнена!")
            logging.info("   - Добавлена колонка service_id (DEFAULT 1)")
            logging.info("   - Создан индекс idx_bookings_service")
            
            # Проверяем результат
            async with db.execute("PRAGMA table_info(bookings)") as cursor:
                columns = await cursor.fetchall()
                logging.info(f"\n📋 Текущая схема таблицы bookings:")
                for col in columns:
                    logging.info(f"   {col[1]} ({col[2]})")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка миграции: {e}")
            await db.rollback()
            return False


async def rollback():
    """Откатить миграцию (удалить service_id)"""
    
    logging.warning("⚠️ ОТКАТ МИГРАЦИИ: Удаление service_id из bookings")
    logging.warning("   Это удалит связь всех бронирований с услугами!")
    
    response = input("Продолжить? (yes/no): ")
    if response.lower() != "yes":
        logging.info("Откат отменен")
        return False
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            # SQLite не поддерживает DROP COLUMN напрямую
            # Нужно пересоздать таблицу
            logging.info("🔄 Пересоздаем таблицу без service_id...")
            
            # Создаем временную таблицу без service_id
            await db.execute(
                """CREATE TABLE bookings_backup AS 
                SELECT id, date, time, user_id, username, created_at 
                FROM bookings"""
            )
            
            # Удаляем старую таблицу
            await db.execute("DROP TABLE bookings")
            
            # Переименовываем backup в bookings
            await db.execute("ALTER TABLE bookings_backup RENAME TO bookings")
            
            # Восстанавливаем индексы
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_date
                ON bookings(date, time)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_user
                ON bookings(user_id)"""
            )
            
            await db.commit()
            
            logging.info("✅ Откат выполнен успешно")
            return True
            
        except Exception as e:
            logging.error(f"❌ Ошибка отката: {e}")
            await db.rollback()
            return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        success = asyncio.run(rollback())
    else:
        success = asyncio.run(migrate())
    
    sys.exit(0 if success else 1)
