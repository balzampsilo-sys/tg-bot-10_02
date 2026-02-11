"""Репозиторий для управления администраторами"""

import logging
from typing import List, Optional, Tuple

import aiosqlite

from config import DATABASE_PATH, ROLE_MODERATOR
from database.base_repository import BaseRepository
from utils.helpers import now_local


class AdminRepository(BaseRepository):
    """Репозиторий для управления администраторами"""

    @staticmethod
    async def get_all_admins() -> List[Tuple[int, str, str, str, str]]:
        """
        Получить всех администраторов.

        Returns:
            List[Tuple[user_id, username, added_by, added_at, role]]  # ✅ role added
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                # ✅ Добавлен role
                async with db.execute(
                    "SELECT user_id, username, added_by, added_at, "
                    "COALESCE(role, 'moderator') as role "
                    "FROM admins ORDER BY added_at"
                ) as cursor:
                    return await cursor.fetchall() or []
        except Exception as e:
            logging.error(f"Error getting all admins: {e}")
            return []

    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """
        Проверить, является ли пользователь администратором.

        Args:
            user_id: Telegram user ID

        Returns:
            True если админ, False если нет
        """
        return await AdminRepository._exists("admins", "user_id=?", (user_id,))

    @staticmethod
    async def add_admin(
        user_id: int,
        username: Optional[str] = None,
        added_by: Optional[int] = None,
        role: str = ROLE_MODERATOR,  # ✅ NEW: роль по умолчанию
    ) -> bool:
        """
        Добавить администратора.

        Args:
            user_id: Telegram user ID
            username: Username пользователя
            added_by: ID админа, который добавил
            role: Роль (super_admin, moderator)

        Returns:
            True если успешно, False если ошибка
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO admins (user_id, username, added_by, added_at, role) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, added_by, now_local().isoformat(), role),
                )
                await db.commit()
                logging.info(
                    f"Admin added: user_id={user_id}, role={role}, by={added_by}"
                )
                return True
        except Exception as e:
            logging.error(f"Error adding admin {user_id}: {e}")
            return False

    @staticmethod
    async def remove_admin(user_id: int) -> bool:
        """
        Удалить администратора.

        Args:
            user_id: Telegram user ID

        Returns:
            True если успешно, False если ошибка
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute(
                    "DELETE FROM admins WHERE user_id=?", (user_id,)
                )
                await db.commit()
                deleted = cursor.rowcount > 0

                if deleted:
                    logging.info(f"Admin removed: user_id={user_id}")
                else:
                    logging.warning(f"Admin not found: user_id={user_id}")

                return deleted
        except Exception as e:
            logging.error(f"Error removing admin {user_id}: {e}")
            return False

    @staticmethod
    async def get_admin_count() -> int:
        """
        Получить количество администраторов.

        Returns:
            Количество админов
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute("SELECT COUNT(*) FROM admins") as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logging.error(f"Error getting admin count: {e}")
            return 0

    @staticmethod
    async def get_admin_info(user_id: int) -> Optional[Tuple[str, int, str, str]]:
        """
        Получить информацию об админе.

        Args:
            user_id: Telegram user ID

        Returns:
            Tuple[username, added_by, added_at, role] или None
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT username, added_by, added_at, COALESCE(role, 'moderator') as role "
                    "FROM admins WHERE user_id=?",
                    (user_id,),
                ) as cursor:
                    return await cursor.fetchone()
        except Exception as e:
            logging.error(f"Error getting admin info for {user_id}: {e}")
            return None

    @staticmethod
    async def get_admin_role(user_id: int) -> Optional[str]:
        """
        ✅ NEW: Получить роль админа.

        Args:
            user_id: Telegram user ID

        Returns:
            Роль (super_admin, moderator) или None
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT COALESCE(role, 'moderator') FROM admins WHERE user_id=?",
                    (user_id,),
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logging.error(f"Error getting admin role for {user_id}: {e}")
            return None

    @staticmethod
    async def update_admin_role(user_id: int, role: str) -> bool:
        """
        ✅ NEW: Обновить роль админа.

        Args:
            user_id: Telegram user ID
            role: Новая роль

        Returns:
            True если успешно
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    "UPDATE admins SET role=? WHERE user_id=?", (role, user_id)
                )
                await db.commit()
                logging.info(f"Admin role updated: user_id={user_id}, role={role}")
                return True
        except Exception as e:
            logging.error(f"Error updating admin role for {user_id}: {e}")
            return False
