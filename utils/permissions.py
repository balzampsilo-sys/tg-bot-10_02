"""Permission checks for admin roles"""

import logging
from typing import Optional

from config import ADMIN_IDS, ROLE_PERMISSIONS, ROLE_SUPER_ADMIN
from database.repositories.admin_repository import AdminRepository


async def has_permission(user_id: int, permission: str) -> bool:
    """
    Проверить есть ли у админа разрешение.

    Args:
        user_id: Telegram user ID
        permission: Название разрешения (manage_admins, view_audit_log, etc.)

    Returns:
        True если есть разрешение
    """
    # Статические админы (.env) = super_admin
    if user_id in ADMIN_IDS:
        return ROLE_PERMISSIONS[ROLE_SUPER_ADMIN].get(permission, False)

    # Получаем роль из БД
    role = await AdminRepository.get_admin_role(user_id)

    if not role:
        return False

    return ROLE_PERMISSIONS.get(role, {}).get(permission, False)


async def get_admin_role_display(user_id: int) -> str:
    """
    Получить отображение роли админа.

    Args:
        user_id: Telegram user ID

    Returns:
        Бейдж роли (👑 или 🛡️)
    """
    if user_id in ADMIN_IDS:
        return "👑 Super"

    role = await AdminRepository.get_admin_role(user_id)

    if role == ROLE_SUPER_ADMIN:
        return "👑 Super"
    elif role == "moderator":
        return "🛡️ Mod"
    else:
        return "🛡️"
