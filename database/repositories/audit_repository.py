"""Repository for audit logging"""

import logging
from typing import List, Optional, Tuple

import aiosqlite

from config import DATABASE_PATH
from database.base_repository import BaseRepository
from utils.helpers import now_local


class AuditRepository(BaseRepository):
    """Репозиторий для audit log"""

    @staticmethod
    async def log_action(
        admin_id: int,
        action: str,
        target_id: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """
        Записать действие в audit log.

        Args:
            admin_id: ID администратора
            action: Действие (add_admin, remove_admin, block_slot, etc.)
            target_id: ID цели (например, user_id или booking_id)
            details: Дополнительные детали

        Returns:
            True если успешно
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    "INSERT INTO audit_log (admin_id, action, target_id, details, timestamp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        admin_id,
                        action,
                        str(target_id) if target_id else None,
                        details,
                        now_local().isoformat(),
                    ),
                )
                await db.commit()
                logging.info(
                    f"Audit: admin={admin_id} action={action} target={target_id}"
                )
                return True
        except Exception as e:
            logging.error(f"Error logging audit action: {e}")
            return False

    @staticmethod
    async def get_logs(
        admin_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tuple[int, int, str, str, str, str]]:
        """
        Получить записи audit log.

        Args:
            admin_id: Фильтр по admin_id
            action: Фильтр по action
            limit: Максимум записей
            offset: Смещение для пагинации

        Returns:
            List[Tuple[id, admin_id, action, target_id, details, timestamp]]
        """
        try:
            query = "SELECT id, admin_id, action, target_id, details, timestamp FROM audit_log"
            params = []
            conditions = []

            if admin_id is not None:
                conditions.append("admin_id=?")
                params.append(admin_id)

            if action:
                conditions.append("action=?")
                params.append(action)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(query, params) as cursor:
                    return await cursor.fetchall() or []
        except Exception as e:
            logging.error(f"Error getting audit logs: {e}")
            return []

    @staticmethod
    async def get_logs_count(
        admin_id: Optional[int] = None, action: Optional[str] = None
    ) -> int:
        """
        Подсчитать количество записей.

        Args:
            admin_id: Фильтр по admin_id
            action: Фильтр по action

        Returns:
            Количество записей
        """
        try:
            query = "SELECT COUNT(*) FROM audit_log"
            params = []
            conditions = []

            if admin_id is not None:
                conditions.append("admin_id=?")
                params.append(admin_id)

            if action:
                conditions.append("action=?")
                params.append(action)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(query, params) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logging.error(f"Error counting audit logs: {e}")
            return 0

    @staticmethod
    async def export_to_csv(filepath: str) -> bool:
        """
        Экспортировать audit log в CSV.

        Args:
            filepath: Путь к CSV файлу

        Returns:
            True если успешно
        """
        try:
            import csv

            logs = await AuditRepository.get_logs(limit=100000)

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["ID", "Admin ID", "Action", "Target ID", "Details", "Timestamp"]
                )
                writer.writerows(logs)

            logging.info(f"Audit log exported to {filepath}")
            return True
        except Exception as e:
            logging.error(f"Error exporting audit log: {e}")
            return False
