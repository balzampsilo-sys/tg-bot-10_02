"""Главный файл приложения"""

import asyncio
import logging
import os
import sqlite3
import sys

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    BACKUP_DIR,
    BACKUP_ENABLED,
    BACKUP_INTERVAL_HOURS,
    BACKUP_RETENTION_DAYS,
    BOT_TOKEN,
    DATABASE_PATH,
    RATE_LIMIT_CALLBACK,
    RATE_LIMIT_MESSAGE,
    REDIS_DB,
    REDIS_ENABLED,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    SENTRY_DSN,
    SENTRY_ENABLED,
    SENTRY_ENVIRONMENT,
    SENTRY_TRACES_SAMPLE_RATE,
)
from database.migrations.migration_manager import MigrationManager
from database.migrations.versions.v004_add_services import AddServicesBackwardCompatible
from database.migrations.versions.v006_add_booking_history import AddBookingHistory
from database.queries import Database
from handlers import (
    admin_handlers,
    admin_management_handlers,
    audit_handlers,
    booking_handlers,
    mass_edit_handlers,
    service_management_handlers,
    universal_editor,
    user_handlers,
)
from middlewares.message_cleanup import MessageCleanupMiddleware
from middlewares.rate_limit import RateLimitMiddleware
from services.booking_service import BookingService
from services.notification_service import NotificationService
from services.reminder_service import ReminderService
from utils.backup_service import BackupService
from utils.retry import async_retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)

# Инициализация Sentry
if SENTRY_ENABLED and SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        
        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            integrations=[sentry_logging],
            release=f"booking-bot@1.0.0",
            attach_stacktrace=True,
            send_default_pii=False,
        )
        
        logger.info(f"Sentry initialized: {SENTRY_ENVIRONMENT} environment")
    except ImportError:
        logger.warning("Sentry SDK not installed. Install with: pip install sentry-sdk")
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")


def check_and_restore_database():
    """
    Проверяет целостность БД и восстанавливает из бэкапа при необходимости.
    Вызывается ДО инициализации БД.
    """
    db_exists = os.path.exists(DATABASE_PATH)
    db_corrupted = False

    if db_exists:
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()

            if result[0] != "ok":
                db_corrupted = True
                logger.error(f"Database corrupted: {result[0]}")
            else:
                logger.info("Database integrity check passed")
                return
        except sqlite3.Error as e:
            db_corrupted = True
            logger.error(f"Database error: {e}", exc_info=True)

    if not db_exists or db_corrupted:
        if not BACKUP_ENABLED:
            if not db_exists:
                logger.info("Database doesn't exist, will be created")
            else:
                logger.warning("Database corrupted but backup is disabled")
            return

        backup_service = BackupService(
            db_path=DATABASE_PATH, backup_dir=BACKUP_DIR, retention_days=BACKUP_RETENTION_DAYS
        )

        backups = backup_service.list_backups()

        if not backups:
            if not db_exists:
                logger.info("No database and no backups, will create new DB")
            else:
                logger.warning("Database corrupted but no backups available")
            return

        latest_backup = backups[0]
        backup_path = f"{BACKUP_DIR}/{latest_backup['filename']}"

        status = "повреждена" if db_corrupted else "отсутствует"
        logger.warning(f"Database {status}, restoring from backup: {latest_backup['filename']}")

        success = backup_service.restore_backup(backup_path)

        if success:
            logger.info(f"Database restored from backup ({latest_backup['created_at']})")
        else:
            logger.error("Failed to restore database from backup")


async def init_database():
    """Инициализация БД с миграциями"""
    await Database.init_db()

    manager = MigrationManager(DATABASE_PATH)
    manager.register(AddServicesBackwardCompatible)
    manager.register(AddBookingHistory)  # P0: История изменений записей
    await manager.migrate()

    logger.info("Database initialized with migrations")


def setup_backup_job(scheduler: AsyncIOScheduler, backup_service: BackupService):
    """Настройка периодического резервного копирования"""
    if not BACKUP_ENABLED:
        logger.info("Backup disabled in config")
        return

    def backup_job():
        """Wrapper для синхронного вызова"""
        try:
            backup_service.create_backup()
        except Exception as e:
            logger.error(f"Backup job failed: {e}", exc_info=True)

    scheduler.add_job(
        backup_job,
        "interval",
        hours=BACKUP_INTERVAL_HOURS,
        id="database_backup",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(
        f"Backup scheduled: every {BACKUP_INTERVAL_HOURS}h, retention: {BACKUP_RETENTION_DAYS} days"
    )


def setup_reminder_jobs(scheduler: AsyncIOScheduler, bot: Bot):
    """Настройка автоматических напоминаний о записях
    
    Priority: P0 (High)
    - Напоминание за 24 часа: ежедневно в 10:00
    - Напоминание за 1 час: каждый час
    """
    async def reminder_24h_job():
        """Отправка напоминаний за 24 часа"""
        try:
            success, total = await ReminderService.send_reminders_24h(bot)
            if total > 0:
                logger.info(f"⏰ Reminder 24h job completed: {success}/{total} sent")
        except Exception as e:
            logger.error(f"❌ Reminder 24h job failed: {e}", exc_info=True)
    
    async def reminder_1h_job():
        """Отправка напоминаний за 1 час"""
        try:
            success, total = await ReminderService.send_reminders_1h(bot)
            if total > 0:
                logger.info(f"🔔 Reminder 1h job completed: {success}/{total} sent")
        except Exception as e:
            logger.error(f"❌ Reminder 1h job failed: {e}", exc_info=True)
    
    # Напоминание за 24 часа - ежедневно в 10:00
    scheduler.add_job(
        reminder_24h_job,
        "cron",
        hour=10,
        minute=0,
        id="reminder_24h",
        replace_existing=True,
        max_instances=1,
    )
    
    # Напоминание за 1 час - каждый час
    scheduler.add_job(
        reminder_1h_job,
        "interval",
        hours=1,
        id="reminder_1h",
        replace_existing=True,
        max_instances=1,
    )
    
    logger.info("⏰ Reminder service activated:")
    logger.info("  - 24h reminders: daily at 10:00")
    logger.info("  - 1h reminders: every hour")


async def get_storage():
    """Создает FSM storage: Redis если доступен, иначе MemoryStorage"""
    if REDIS_ENABLED:
        try:
            import redis.asyncio as aioredis
            
            redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
            if REDIS_PASSWORD:
                redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
            
            redis_client = aioredis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            
            storage = RedisStorage(
                redis=redis_client,
                key_builder=DefaultKeyBuilder(with_destiny=True)
            )
            
            logger.info(f"Using RedisStorage: {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
            return storage
            
        except ImportError:
            logger.warning("Redis library not installed. Install with: pip install redis")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
    
    logger.info("Using MemoryStorage (FSM states will be lost on restart)")
    return MemoryStorage()


@async_retry(
    max_attempts=5,
    delay=2.0,
    backoff=2.0,
    exceptions=(TelegramNetworkError, TelegramRetryAfter, ConnectionError),
)
async def start_bot():
    """Запуск бота с retry логикой и централизованной обработкой ошибок"""
    check_and_restore_database()

    bot = Bot(token=BOT_TOKEN)
    storage = await get_storage()
    dp = Dispatcher(storage=storage)

    scheduler = AsyncIOScheduler(
        jobstores={},
        executors={"default": {"type": "threadpool", "max_workers": 1}},
        job_defaults={"coalesce": False, "max_instances": 1},
    )

    await init_database()

    if BACKUP_ENABLED:
        backup_service = BackupService(
            db_path=DATABASE_PATH, backup_dir=BACKUP_DIR, retention_days=BACKUP_RETENTION_DAYS
        )
        backup_service.create_backup()
        setup_backup_job(scheduler, backup_service)
        dp["backup_service"] = backup_service

    booking_service = BookingService(scheduler, bot)
    notification_service = NotificationService(bot)

    dp["booking_service"] = booking_service
    dp["notification_service"] = notification_service
    
    # P0: Настройка автоматических напоминаний
    setup_reminder_jobs(scheduler, bot)

    # Middlewares (порядок важен!)
    dp.callback_query.middleware(MessageCleanupMiddleware(ttl_hours=48))
    dp.message.middleware(RateLimitMiddleware(rate_limit=RATE_LIMIT_MESSAGE))
    dp.callback_query.middleware(RateLimitMiddleware(rate_limit=RATE_LIMIT_CALLBACK))

    # Централизованная обработка ошибок
    @dp.errors()
    async def error_handler(event: ErrorEvent):
        """Глобальный обработчик ошибок с Sentry интеграцией"""
        logger.error(
            f"Critical error in update {event.update.update_id}: {event.exception}",
            exc_info=event.exception,
        )
        
        # Отправка в Sentry
        if SENTRY_ENABLED:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(event.exception)
            except Exception as e:
                logger.error(f"Failed to send error to Sentry: {e}")
        
        return True

    # Регистрация роутеров (порядок важен!)
    dp.include_router(universal_editor.router)
    dp.include_router(service_management_handlers.router)
    dp.include_router(admin_management_handlers.router)
    dp.include_router(audit_handlers.router)
    dp.include_router(mass_edit_handlers.router)
    dp.include_router(admin_handlers.router)
    dp.include_router(booking_handlers.router)
    dp.include_router(user_handlers.router)

    await booking_service.restore_reminders()
    scheduler.start()

    logger.info("Bot started successfully")
    logger.info(
        "Features: Services, Audit Log, Universal Editor, Rate Limiting, "
        "Auto Cleanup, Reminders, Booking History"
    )
    
    if SENTRY_ENABLED:
        logger.info(f"Sentry monitoring active: {SENTRY_ENVIRONMENT}")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        logger.info("Shutting down bot...")
        
        if isinstance(storage, RedisStorage):
            await storage.close()
            logger.info("Redis connection closed")
        
        await bot.session.close()
        scheduler.shutdown(wait=False)
        logger.info("Bot stopped")


async def main():
    """Главная функция с обработкой критических ошибок"""
    try:
        await start_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Bot crashed with critical error: {e}", exc_info=True)
        
        # Отправка критичной ошибки в Sentry
        if SENTRY_ENABLED:
            try:
                import sentry_sdk
                sentry_sdk.capture_exception(e)
                sentry_sdk.flush(timeout=2.0)
            except Exception:
                pass
        
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
