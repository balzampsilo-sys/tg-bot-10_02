"""Главный файл приложения"""

import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    BOT_TOKEN, 
    DATABASE_PATH,
    BACKUP_ENABLED,
    BACKUP_INTERVAL_HOURS,
    BACKUP_DIR,
    BACKUP_RETENTION_DAYS
)
from database.queries import Database
from database.migrations.migration_manager import MigrationManager
from database.migrations.versions.v004_add_services import AddServicesBackwardCompatible
from handlers import (
    admin_handlers,
    admin_management_handlers,
    audit_handlers,  # ✅ ADDED: Audit log handlers
    booking_handlers,
    mass_edit_handlers,
    service_management_handlers,
    user_handlers,
    universal_editor,
)
from middlewares.rate_limit import RateLimitMiddleware
from middlewares.message_cleanup import MessageCleanupMiddleware
from services.booking_service import BookingService
from services.notification_service import NotificationService
from utils.backup_service import BackupService
from utils.retry import async_retry

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def check_and_restore_database():
    """
    Проверяет целостность БД и восстанавливает из бэкапа при необходимости.
    Вызывается ДО инициализации БД.
    """
    db_exists = os.path.exists(DATABASE_PATH)
    db_corrupted = False
    
    # Проверяем целостность БД если она существует
    if db_exists:
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            
            if result[0] != "ok":
                db_corrupted = True
                logging.error(f"❌ Database corrupted: {result[0]}")
            else:
                logging.info("✅ Database integrity check passed")
                return  # БД в порядке
        except sqlite3.Error as e:
            db_corrupted = True
            logging.error(f"❌ Database error: {e}")
    
    # Если БД нет или она повреждена - пытаемся восстановить
    if not db_exists or db_corrupted:
        if not BACKUP_ENABLED:
            if not db_exists:
                logging.info("ℹ️ Database doesn't exist, will be created")
            else:
                logging.warning("⚠️ Database corrupted but backup is disabled")
            return
        
        backup_service = BackupService(
            db_path=DATABASE_PATH,
            backup_dir=BACKUP_DIR,
            retention_days=BACKUP_RETENTION_DAYS
        )
        
        backups = backup_service.list_backups()
        
        if not backups:
            if not db_exists:
                logging.info("ℹ️ No database and no backups, will create new DB")
            else:
                logging.warning("⚠️ Database corrupted but no backups available")
            return
        
        # Восстанавливаем из последнего бэкапа
        latest_backup = backups[0]
        backup_path = f"{BACKUP_DIR}/{latest_backup['filename']}"
        
        status = "повреждена" if db_corrupted else "отсутствует"
        logging.warning(
            f"🔄 Database {status}, restoring from backup: {latest_backup['filename']}"
        )
        
        success = backup_service.restore_backup(backup_path)
        
        if success:
            logging.info(
                f"✅ Database restored from backup ({latest_backup['created_at']})"
            )
        else:
            logging.error("❌ Failed to restore database from backup")


async def init_database():
    """Инициализация БД с миграциями"""
    # Сначала создаем базовую структуру (если еще не создана)
    await Database.init_db()
    
    # Затем применяем миграции
    manager = MigrationManager(DATABASE_PATH)
    
    # Регистрируем миграции
    manager.register(AddServicesBackwardCompatible)
    
    # Применяем миграции
    await manager.migrate()
    
    logging.info("✅ Database initialized with migrations")


def setup_backup_job(scheduler: AsyncIOScheduler, backup_service: BackupService):
    """
    Настройка периодического резервного копирования.
    """
    if not BACKUP_ENABLED:
        logging.info("⚠️ Backup disabled in config")
        return
    
    def backup_job():
        """Враппер для синхронного вызова"""
        backup_service.create_backup()
    
    # Добавляем задачу в планировщик
    scheduler.add_job(
        backup_job,
        'interval',
        hours=BACKUP_INTERVAL_HOURS,
        id='database_backup',
        replace_existing=True,
        max_instances=1
    )
    
    logging.info(
        f"💾 Backup scheduled: every {BACKUP_INTERVAL_HOURS}h, "
        f"retention: {BACKUP_RETENTION_DAYS} days"
    )


@async_retry(
    max_attempts=5,
    delay=2.0,
    backoff=2.0,
    exceptions=(TelegramNetworkError, TelegramRetryAfter, ConnectionError)
)
async def start_bot():
    """Запуск бота с retry логикой"""
    # ✅ ПРОВЕРКА И ВОССТАНОВЛЕНИЕ БД (ДО инициализации)
    check_and_restore_database()
    
    # Инициализация
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Настройка планировщика с одним исполнителем
    scheduler = AsyncIOScheduler(
        jobstores={},
        executors={
            'default': {'type': 'threadpool', 'max_workers': 1}
        },
        job_defaults={
            'coalesce': False,
            'max_instances': 1
        }
    )

    # Инициализация БД
    await init_database()

    # ✅ Сервис резервного копирования
    if BACKUP_ENABLED:
        backup_service = BackupService(
            db_path=DATABASE_PATH,
            backup_dir=BACKUP_DIR,
            retention_days=BACKUP_RETENTION_DAYS
        )
        # Создаём начальный бэкап при старте
        backup_service.create_backup()
        # Настраиваем периодическое копирование
        setup_backup_job(scheduler, backup_service)
        # Сохраняем в dispatcher для доступа из handlers
        dp["backup_service"] = backup_service

    # Сервисы
    booking_service = BookingService(scheduler, bot)
    notification_service = NotificationService(bot)

    # Регистрация сервисов для dependency injection
    dp["booking_service"] = booking_service
    dp["notification_service"] = notification_service

    # ✅ P3: MIDDLEWARE ДЛЯ АВТООЧИСТКИ СТАРЫХ СООБЩЕНИЙ (ДО rate limit!)
    dp.callback_query.middleware(MessageCleanupMiddleware(ttl_hours=48))
    
    # Rate limiting middleware
    dp.message.middleware(RateLimitMiddleware(rate_limit=0.5))  # 0.5 сек между сообщениями
    dp.callback_query.middleware(RateLimitMiddleware(rate_limit=0.3))  # 0.3 сек между callback

    # Регистрация роутеров (ВАЖЕН ПОРЯДОК!)
    dp.include_router(universal_editor.router)            # ✅ P4: Универсальный редактор
    dp.include_router(service_management_handlers.router)  # Управление услугами
    dp.include_router(admin_management_handlers.router)    # Управление админами
    dp.include_router(audit_handlers.router)              # ✅ ADDED: Audit log (/audit)
    dp.include_router(mass_edit_handlers.router)          # Массовое редактирование
    dp.include_router(admin_handlers.router)              # Админ
    dp.include_router(booking_handlers.router)            # Бронирования
    dp.include_router(user_handlers.router)               # Пользователи последним

    # Восстановление напоминаний
    await booking_service.restore_reminders()

    # Запуск планировщика
    scheduler.start()

    logging.info("🚀 Bot started with all features:")
    logging.info("   ✅ Priority 2: Services Display")
    logging.info("   ✅ Priority 3: MessageCleanup Middleware")
    logging.info("   ✅ Priority 4: Universal Field Editor")
    logging.info("   ✅ Low Priority: Admin Roles & Audit Log")
    logging.info("   ✅ Low Priority: Rate Limiting")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await bot.session.close()
        scheduler.shutdown()


async def main():
    """Главная функция с обработкой критических ошибок"""
    try:
        await start_bot()
    except Exception as e:
        logging.critical(f"Bot crashed with critical error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
