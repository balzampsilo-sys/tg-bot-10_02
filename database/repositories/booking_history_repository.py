"""Репозиторий для работы с историей изменений бронирований

Priority: P0 (High)
Функции:
- Запись всех изменений бронирований
- Получение истории по booking_id
- Получение истории по user_id
- Очистка старых записей
"""

import logging
from datetime import datetime
from typing import List, Optional

import aiosqlite

from config import DATABASE_PATH
from database.base_repository import BaseRepository


class BookingHistoryRepository(BaseRepository):
    """Репозиторий для управления историей бронирований"""

    @staticmethod
    async def record_create(
        booking_id: int,
        user_id: int,
        date: str,
        time: str,
        service_id: int,
    ) -> bool:
        """Записать создание бронирования

        Args:
            booking_id: ID бронирования
            user_id: ID пользователя
            date: Дата записи
            time: Время записи
            service_id: ID услуги

        Returns:
            True если запись успешна
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO booking_history (
                        booking_id, action, changed_by, changed_by_type,
                        new_date, new_time, new_service_id, changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        booking_id,
                        "create",
                        user_id,
                        "user",
                        date,
                        time,
                        service_id,
                        datetime.now().isoformat(),
                    ),
                )
                await db.commit()

            logging.info(
                f"📝 Recorded booking create: booking_id={booking_id}, "
                f"user={user_id}, date={date}, time={time}"
            )
            return True

        except Exception as e:
            logging.error(f"❌ Failed to record booking create: {e}", exc_info=True)
            return False

    @staticmethod
    async def record_cancel(
        booking_id: int,
        user_id: int,
        changed_by_type: str,
        date: str,
        time: str,
        service_id: int,
        reason: Optional[str] = None,
    ) -> bool:
        """Записать отмену бронирования

        Args:
            booking_id: ID бронирования
            user_id: ID того, кто отменил
            changed_by_type: 'user' или 'admin'
            date: Дата записи
            time: Время записи
            service_id: ID услуги
            reason: Причина отмены

        Returns:
            True если запись успешна
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO booking_history (
                        booking_id, action, changed_by, changed_by_type,
                        old_date, old_time, old_service_id, reason, changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        booking_id,
                        "cancel",
                        user_id,
                        changed_by_type,
                        date,
                        time,
                        service_id,
                        reason,
                        datetime.now().isoformat(),
                    ),
                )
                await db.commit()

            logging.info(
                f"📝 Recorded booking cancel: booking_id={booking_id}, "
                f"by={changed_by_type}, reason={reason}"
            )
            return True

        except Exception as e:
            logging.error(f"❌ Failed to record booking cancel: {e}", exc_info=True)
            return False

    @staticmethod
    async def record_reschedule(
        booking_id: int,
        user_id: int,
        changed_by_type: str,
        old_date: str,
        old_time: str,
        new_date: str,
        new_time: str,
        old_service_id: Optional[int] = None,
        new_service_id: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        """Записать перенос бронирования

        Args:
            booking_id: ID бронирования
            user_id: ID того, кто изменил
            changed_by_type: 'user' или 'admin'
            old_date: Старая дата
            old_time: Старое время
            new_date: Новая дата
            new_time: Новое время
            old_service_id: Старая услуга (опционально)
            new_service_id: Новая услуга (опционально)
            reason: Причина переноса

        Returns:
            True если запись успешна
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO booking_history (
                        booking_id, action, changed_by, changed_by_type,
                        old_date, old_time, new_date, new_time,
                        old_service_id, new_service_id, reason, changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        booking_id,
                        "reschedule",
                        user_id,
                        changed_by_type,
                        old_date,
                        old_time,
                        new_date,
                        new_time,
                        old_service_id,
                        new_service_id,
                        reason,
                        datetime.now().isoformat(),
                    ),
                )
                await db.commit()

            logging.info(
                f"📝 Recorded booking reschedule: booking_id={booking_id}, "
                f"from {old_date} {old_time} to {new_date} {new_time}"
            )
            return True

        except Exception as e:
            logging.error(f"❌ Failed to record booking reschedule: {e}", exc_info=True)
            return False

    @staticmethod
    async def get_booking_history(booking_id: int) -> List[dict]:
        """Получить всю историю конкретного бронирования

        Args:
            booking_id: ID бронирования

        Returns:
            Список записей истории
        """
        try:
            rows = await BookingHistoryRepository._execute_query(
                """
                SELECT
                    id, action, changed_by, changed_by_type,
                    old_date, old_time, new_date, new_time,
                    old_service_id, new_service_id, reason, changed_at
                FROM booking_history
                WHERE booking_id = ?
                ORDER BY changed_at DESC
                """,
                (booking_id,),
                fetch_all=True,
            )

            if not rows:
                return []

            history = []
            for row in rows:
                history.append(
                    {
                        "id": row[0],
                        "action": row[1],
                        "changed_by": row[2],
                        "changed_by_type": row[3],
                        "old_date": row[4],
                        "old_time": row[5],
                        "new_date": row[6],
                        "new_time": row[7],
                        "old_service_id": row[8],
                        "new_service_id": row[9],
                        "reason": row[10],
                        "changed_at": row[11],
                    }
                )

            return history

        except Exception as e:
            logging.error(f"❌ Failed to get booking history: {e}", exc_info=True)
            return []

    @staticmethod
    async def get_user_history(user_id: int, limit: int = 50) -> List[dict]:
        """Получить историю изменений бронирований пользователя

        Args:
            user_id: ID пользователя
            limit: Максимальное количество записей

        Returns:
            Список записей истории
        """
        try:
            rows = await BookingHistoryRepository._execute_query(
                """
                SELECT
                    h.id, h.booking_id, h.action, h.changed_by_type,
                    h.old_date, h.old_time, h.new_date, h.new_time,
                    h.reason, h.changed_at
                FROM booking_history h
                WHERE h.changed_by = ?
                ORDER BY h.changed_at DESC
                LIMIT ?
                """,
                (user_id, limit),
                fetch_all=True,
            )

            if not rows:
                return []

            history = []
            for row in rows:
                history.append(
                    {
                        "id": row[0],
                        "booking_id": row[1],
                        "action": row[2],
                        "changed_by_type": row[3],
                        "old_date": row[4],
                        "old_time": row[5],
                        "new_date": row[6],
                        "new_time": row[7],
                        "reason": row[8],
                        "changed_at": row[9],
                    }
                )

            return history

        except Exception as e:
            logging.error(f"❌ Failed to get user history: {e}", exc_info=True)
            return []

    @staticmethod
    async def cleanup_old_history(before_date: str) -> int:
        """Удалить старые записи истории

        Args:
            before_date: Удалить записи до этой даты (ISO format)

        Returns:
            Количество удаленных записей
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    "DELETE FROM booking_history WHERE changed_at < ?",
                    (before_date,),
                )
                await db.commit()
                deleted_count = cursor.rowcount

            logging.info(f"🗑️ Cleaned up {deleted_count} old history records")
            return deleted_count

        except Exception as e:
            logging.error(f"❌ Failed to cleanup old history: {e}", exc_info=True)
            return 0

    @staticmethod
    async def get_statistics(days: int = 30) -> dict:
        """Получить статистику по действиям за период

        Args:
            days: Количество дней для анализа

        Returns:
            Словарь со статистикой
        """
        try:
            from datetime import timedelta

            since = (datetime.now() - timedelta(days=days)).isoformat()

            rows = await BookingHistoryRepository._execute_query(
                """
                SELECT
                    action,
                    COUNT(*) as count,
                    COUNT(DISTINCT changed_by) as unique_users
                FROM booking_history
                WHERE changed_at >= ?
                GROUP BY action
                """,
                (since,),
                fetch_all=True,
            )

            if not rows:
                return {"create": 0, "cancel": 0, "reschedule": 0}

            stats = {"create": 0, "cancel": 0, "reschedule": 0}
            for action, count, unique_users in rows:
                stats[action] = {"count": count, "unique_users": unique_users}

            return stats

        except Exception as e:
            logging.error(f"❌ Failed to get statistics: {e}", exc_info=True)
            return {"create": 0, "cancel": 0, "reschedule": 0}
