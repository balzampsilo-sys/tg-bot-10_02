"""Rate limiter for admin actions"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple  # ✅ ADDED: Optional

from config import MAX_ADMIN_ADDITIONS_PER_HOUR, ROLE_SUPER_ADMIN
from database.repositories.admin_repository import AdminRepository


class AdminRateLimiter:
    """
    Rate limiter для добавления админов.

    Ограничение: MAX_ADMIN_ADDITIONS_PER_HOUR добавлений в час.
    Super_admin освобожден от лимита.
    """

    # {admin_id: [timestamps]}
    _additions: Dict[int, List[datetime]] = {}

    @classmethod
    def _cleanup_old_timestamps(cls, admin_id: int):
        """Удалить timestamps старше 1 часа"""
        if admin_id not in cls._additions:
            return

        cutoff = datetime.now() - timedelta(hours=1)
        cls._additions[admin_id] = [
            ts for ts in cls._additions[admin_id] if ts > cutoff
        ]

        # Удаляем пустые списки
        if not cls._additions[admin_id]:
            del cls._additions[admin_id]

    @classmethod
    async def can_add_admin(cls, admin_id: int) -> Tuple[bool, int, int]:
        """
        Проверить можно ли добавить админа.

        Args:
            admin_id: ID администратора

        Returns:
            Tuple[can_add: bool, current_count: int, minutes_until_reset: int]
        """
        # Super_admin не ограничен
        role = await AdminRepository.get_admin_role(admin_id)
        if role == ROLE_SUPER_ADMIN:
            return True, 0, 0

        # Очищаем старые timestamps
        cls._cleanup_old_timestamps(admin_id)

        # Проверяем лимит
        current_count = len(cls._additions.get(admin_id, []))

        if current_count >= MAX_ADMIN_ADDITIONS_PER_HOUR:
            # Вычисляем когда сбросится лимит
            oldest_ts = min(cls._additions[admin_id])
            reset_time = oldest_ts + timedelta(hours=1)
            minutes_left = int((reset_time - datetime.now()).total_seconds() / 60)
            return False, current_count, max(1, minutes_left)

        return True, current_count, 0

    @classmethod
    def record_addition(cls, admin_id: int):
        """
        Записать добавление админа.

        Args:
            admin_id: ID администратора
        """
        if admin_id not in cls._additions:
            cls._additions[admin_id] = []

        cls._additions[admin_id].append(datetime.now())
        logging.info(
            f"Rate limiter: admin {admin_id} added admin "
            f"({len(cls._additions[admin_id])}/{MAX_ADMIN_ADDITIONS_PER_HOUR})"
        )

    @classmethod
    def reset(cls, admin_id: Optional[int] = None):
        """
        Сбросить rate limiter.

        Args:
            admin_id: ID админа или None для сброса всех
        """
        if admin_id is None:
            cls._additions.clear()
            logging.info("Rate limiter reset (all)")
        elif admin_id in cls._additions:
            del cls._additions[admin_id]
            logging.info(f"Rate limiter reset for admin {admin_id}")
