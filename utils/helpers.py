"""Вспомогательные функции"""

from datetime import datetime

from config import DAY_NAMES, TIMEZONE


def now_local() -> datetime:
    """Текущее время в московской таймзоне"""
    return datetime.now(TIMEZONE)


def format_date(date_obj: datetime) -> str:
    """Форматирование даты для отображения"""
    day_name = DAY_NAMES[date_obj.weekday()]
    return f"{date_obj.strftime('%d.%m.%Y')} ({day_name})"


def create_ascii_chart(data: list, width: int = 7) -> str:
    """Создать ASCII-график для дашборда"""
    if not data or max(data) == 0:
        return "▁▁▁▁▁▁▁"

    max_val = max(data)
    bars = []
    bar_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

    for val in data:
        height = int((val / max_val) * 7)
        bars.append(bar_chars[min(height, 7)])

    return "".join(bars)


def is_static_admin(user_id: int) -> bool:
    """
    Проверка статических админов из .env

    Проверяет только ADMIN_IDS из .env

    Args:
        user_id: Telegram user ID

    Returns:
        True если админ в .env, False если нет
    """
    from config import ADMIN_IDS

    return user_id in ADMIN_IDS


async def is_admin(user_id: int) -> bool:
    """
    Проверка прав администратора.

    Проверяет:
    1. Статические админы из .env (ADMIN_IDS)
    2. Динамические админы из БД (admins)

    Args:
        user_id: Telegram user ID

    Returns:
        True если админ, False если нет
    """
    from config import ADMIN_IDS
    from database.queries import Database

    # Проверяем статических админов из .env
    if user_id in ADMIN_IDS:
        return True

    # Проверяем динамических админов из БД
    return await Database.is_admin_in_db(user_id)
