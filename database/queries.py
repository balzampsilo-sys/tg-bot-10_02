"""Фасад для работы с базой данных через репозитории"""

import logging
from typing import Dict, List, Optional, Tuple

import aiosqlite

from config import DATABASE_PATH
from database.repositories import (
    AdminRepository,
    AnalyticsRepository,
    BookingRepository,
    ClientStats,
    UserRepository,
)
from database.repositories.calendar_repository import CalendarRepository
from database.repositories.settings_repository import SettingsRepository

# Реэкспортируем ClientStats для обратной совместимости
__all__ = ["Database", "ClientStats"]


class Database:
    """
    Фасад для работы с базой данных.
    Делегирует вызовы специализированным репозиториям.
    """

    # === ИНИЦИАЛИЗАЦИЯ ===

    @staticmethod
    async def init_db():
        """Инициализация БД с таблицами и индексами"""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Таблицы
            await db.execute(
                """CREATE TABLE IF NOT EXISTS bookings
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, time TEXT, user_id INTEGER, username TEXT,
                created_at TEXT, service_id INTEGER DEFAULT 1,
                duration_minutes INTEGER DEFAULT 60,
                UNIQUE(date, time))"""
            )

            await db.execute(
                """CREATE TABLE IF NOT EXISTS users
                (user_id INTEGER PRIMARY KEY, first_seen TEXT)"""
            )

            await db.execute(
                """CREATE TABLE IF NOT EXISTS analytics
                (user_id INTEGER, event TEXT, data TEXT, timestamp TEXT)"""
            )

            await db.execute(
                """CREATE TABLE IF NOT EXISTS feedback
                (user_id INTEGER, booking_id INTEGER, rating INTEGER, timestamp TEXT)"""
            )

            await db.execute(
                """CREATE TABLE IF NOT EXISTS blocked_slots
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                reason TEXT,
                blocked_by INTEGER NOT NULL,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, time))"""
            )

            await db.execute(
                """CREATE TABLE IF NOT EXISTS admin_sessions
                (user_id INTEGER PRIMARY KEY, message_id INTEGER, updated_at TEXT)"""
            )

            # Sprint 3: Таблица администраторов
            await db.execute(
                """CREATE TABLE IF NOT EXISTS admins
                (user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_at TEXT NOT NULL,
                role TEXT DEFAULT 'moderator')"""
            )

            # Low Priority: Audit log
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

            # P0: История изменений записей
            # ✅ ИСПРАВЛЕНО: Убраны CHECK constraints для совместимости
            await db.execute(
                """CREATE TABLE IF NOT EXISTS booking_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                changed_by INTEGER NOT NULL,
                changed_by_type TEXT NOT NULL,
                action TEXT NOT NULL,
                old_date TEXT,
                old_time TEXT,
                new_date TEXT,
                new_time TEXT,
                old_service_id INTEGER,
                new_service_id INTEGER,
                reason TEXT,
                changed_at TIMESTAMP NOT NULL
            )"""
            )

            # P2: Миграция - добавляем service_id если его еще нет
            try:
                async with db.execute("PRAGMA table_info(bookings)") as cursor:
                    columns = await cursor.fetchall()
                    column_names = [col[1] for col in columns]

                    if "service_id" not in column_names:
                        logging.info("🔄 Добавляем service_id в существующую таблицу bookings...")
                        await db.execute(
                            "ALTER TABLE bookings ADD COLUMN service_id INTEGER DEFAULT 1"
                        )
                        logging.info("✅ service_id добавлен")

                    if "duration_minutes" not in column_names:
                        logging.info(
                            "🔄 Добавляем duration_minutes в существующую таблицу bookings..."
                        )
                        await db.execute(
                            "ALTER TABLE bookings ADD COLUMN duration_minutes INTEGER DEFAULT 60"
                        )
                        logging.info("✅ duration_minutes добавлен")
            except Exception as e:
                logging.warning(f"⚠️ Не удалось добавить колонки: {e}")

            # Low Priority: Добавляем role если его нет
            try:
                async with db.execute("PRAGMA table_info(admins)") as cursor:
                    columns = await cursor.fetchall()
                    column_names = [col[1] for col in columns]

                    if "role" not in column_names:
                        logging.info("🔄 Добавляем role в существующую таблицу admins...")
                        await db.execute(
                            "ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'moderator'"
                        )
                        logging.info("✅ role добавлен")
            except Exception as e:
                logging.warning(f"⚠️ Не удалось добавить role: {e}")

            # Индексы для производительности
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_date
                ON bookings(date, time)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_user
                ON bookings(user_id)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_service
                ON bookings(service_id)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_analytics_user
                ON analytics(user_id, event)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_blocked_date
                ON blocked_slots(date, time)"""
            )
            await db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_user_active_bookings
                ON bookings(user_id, date, time)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_analytics_timestamp
                ON analytics(timestamp)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_feedback_timestamp
                ON feedback(timestamp)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_feedback_user
                ON feedback(user_id)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_bookings_date_time
                ON bookings(date, time)"""
            )
            await db.execute(
                """CREATE INDEX IF NOT EXISTS idx_admins_added
                ON admins(added_at)"""
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_admin ON audit_log(admin_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)"
            )

            # P0: Индексы для booking_history
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_booking_history_booking ON booking_history(booking_id)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_booking_history_changed_by ON booking_history(changed_by)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_booking_history_timestamp ON booking_history(changed_at)"
            )

            await db.commit()
            logging.info("Database initialized with indexes and race condition protection")

        # Инициализация дополнительных таблиц
        await SettingsRepository.init_settings_table()
        await CalendarRepository.init_calendar_tables()
        logging.info("✅ All database tables initialized")

    # === БРОНИРОВАНИЯ (делегирование в BookingRepository) ===

    @staticmethod
    async def is_slot_free(date_str: str, time_str: str) -> bool:
        return await BookingRepository.is_slot_free(date_str, time_str)

    @staticmethod
    async def get_occupied_slots_for_day(date_str: str) -> List[Tuple[str, int]]:
        """Получить занятые слоты с длительностью

        Returns:
            List[Tuple[time_str, duration_minutes]]
        """
        return await BookingRepository.get_occupied_slots_for_day(date_str)

    @staticmethod
    async def get_month_statuses(year: int, month: int) -> Dict[str, str]:
        return await BookingRepository.get_month_statuses(year, month)

    @staticmethod
    async def get_user_bookings(user_id: int) -> List[Tuple]:
        return await BookingRepository.get_user_bookings(user_id)

    @staticmethod
    async def can_user_book(user_id: int) -> Tuple[bool, int]:
        return await BookingRepository.can_user_book(user_id)

    @staticmethod
    async def can_cancel_booking(date_str: str, time_str: str) -> Tuple[bool, float]:
        return await BookingRepository.can_cancel_booking(date_str, time_str)

    @staticmethod
    async def get_booking_by_id(booking_id: int, user_id: int) -> Optional[Tuple[str, str, str]]:
        return await BookingRepository.get_booking_by_id(booking_id, user_id)

    @staticmethod
    async def get_booking_service_id(booking_id: int) -> Optional[int]:
        """Получить service_id из бронирования

        Args:
            booking_id: ID бронирования

        Returns:
            service_id или None если не найдено
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT service_id FROM bookings WHERE id=?", (booking_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logging.error(f"Error getting booking service_id: {e}")
            return None

    @staticmethod
    async def delete_booking(booking_id: int, user_id: int) -> bool:
        return await BookingRepository.delete_booking(booking_id, user_id)

    @staticmethod
    async def cleanup_old_bookings(before_date: str) -> int:
        return await BookingRepository.cleanup_old_bookings(before_date)

    @staticmethod
    async def get_week_schedule(start_date: str, days: int = 7) -> List[Tuple]:
        return await BookingRepository.get_week_schedule(start_date, days)

    @staticmethod
    async def block_slot(date_str: str, time_str: str, admin_id: int, reason: str = None) -> bool:
        return await BookingRepository.block_slot(date_str, time_str, admin_id, reason)

    @staticmethod
    async def block_slot_with_notification(
        date_str: str, time_str: str, admin_id: int, reason: str = None
    ) -> Tuple[bool, List[Dict]]:
        """
        Заблокировать слот с уведомлением пользователей.

        Если слот занят - удаляет бронь и возвращает данные для уведомления.

        Args:
            date_str: Дата в формате YYYY-MM-DD
            time_str: Время в формате HH:MM
            admin_id: ID администратора
            reason: Причина блокировки

        Returns:
            Tuple[success: bool, cancelled_users: List[Dict]]
            cancelled_users = [{
                'user_id': int,
                'username': str,
                'date': str,
                'time': str,
                'reason': str
            }]
        """
        return await BookingRepository.block_slot_with_notification(
            date_str, time_str, admin_id, reason
        )

    @staticmethod
    async def unblock_slot(date_str: str, time_str: str) -> bool:
        return await BookingRepository.unblock_slot(date_str, time_str)

    @staticmethod
    async def is_slot_blocked(date_str: str, time_str: str) -> bool:
        """ДЕПРЕСИРОВАНО: Используйте is_slot_free() вместо этого"""
        result = await BookingRepository.is_slot_free(date_str, time_str)
        return not result

    @staticmethod
    async def get_blocked_slots(date_str: str = None) -> List[Tuple]:
        return await BookingRepository.get_blocked_slots(date_str)

    @staticmethod
    async def get_day_status(date_str: str) -> str:
        """Статус загрузки дня (🟢🟡🔴)"""
        occupied = await BookingRepository.get_occupied_slots_for_day(date_str)
        from config import WORK_HOURS_END, WORK_HOURS_START

        total_slots = WORK_HOURS_END - WORK_HOURS_START
        total_occupied = len(occupied)

        if total_occupied == 0:
            return "🟢"
        elif total_occupied < total_slots:
            return "🟡"
        else:
            return "🔴"

    # === ПОЛЬЗОВАТЕЛИ (делегирование в UserRepository) ===

    @staticmethod
    async def is_new_user(user_id: int) -> bool:
        return await UserRepository.is_new_user(user_id)

    @staticmethod
    async def get_all_users() -> List[int]:
        return await UserRepository.get_all_users()

    @staticmethod
    async def get_total_users_count() -> int:
        return await UserRepository.get_total_users_count()

    @staticmethod
    async def get_favorite_slots(user_id: int) -> Tuple[Optional[str], Optional[int]]:
        return await UserRepository.get_favorite_slots(user_id)

    # === АНАЛИТИКА И ОТЗЫВЫ (делегирование в AnalyticsRepository) ===

    @staticmethod
    async def log_event(user_id: int, event: str, data: str = ""):
        await AnalyticsRepository.log_event(user_id, event, data)

    @staticmethod
    async def get_client_stats(user_id: int) -> ClientStats:
        return await AnalyticsRepository.get_client_stats(user_id)

    @staticmethod
    async def save_feedback(user_id: int, booking_id: int, rating: int) -> bool:
        return await AnalyticsRepository.save_feedback(user_id, booking_id, rating)

    @staticmethod
    async def get_top_clients(limit: int = 10) -> List[Tuple]:
        return await AnalyticsRepository.get_top_clients(limit)

    # === АДМИНИСТРАТОРЫ (делегирование в AdminRepository) ===

    @staticmethod
    async def get_all_admins() -> List[Tuple[int, str, str, str, str]]:
        """Получить всех администраторов

        Returns:
            List[Tuple[user_id, username, added_by, added_at, role]]
        """
        return await AdminRepository.get_all_admins()

    @staticmethod
    async def is_admin_in_db(user_id: int) -> bool:
        """Проверить админа в БД"""
        return await AdminRepository.is_admin(user_id)

    @staticmethod
    async def add_admin(
        user_id: int,
        username: Optional[str] = None,
        added_by: Optional[int] = None,
        role: str = "moderator",
    ) -> bool:
        """Добавить администратора"""
        return await AdminRepository.add_admin(user_id, username, added_by, role)

    @staticmethod
    async def remove_admin(user_id: int) -> bool:
        """Удалить администратора"""
        return await AdminRepository.remove_admin(user_id)

    @staticmethod
    async def get_admin_count() -> int:
        """Количество админов"""
        return await AdminRepository.get_admin_count()

    @staticmethod
    async def get_admin_role(user_id: int) -> Optional[str]:
        """Получить роль админа"""
        return await AdminRepository.get_admin_role(user_id)

    @staticmethod
    async def update_admin_role(user_id: int, role: str) -> bool:
        """Обновить роль админа"""
        return await AdminRepository.update_admin_role(user_id, role)
