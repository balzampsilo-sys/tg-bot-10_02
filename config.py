"""Конфигурация приложения"""

import os
import re

import pytz
from dotenv import load_dotenv

load_dotenv()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Админы (поддержка нескольких)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
if not ADMIN_IDS_STR:
    raise ValueError("ADMIN_IDS not found in .env file")

ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]

# Валидация токена бота
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in .env file")

# Проверка формата токена Telegram: 123456789:ABCdef_1234567890ABCdef
if not re.match(r'^\d{8,10}:[A-Za-z0-9_-]{35}$', BOT_TOKEN):
    raise ValueError(
        "Invalid BOT_TOKEN format. Expected format: 123456789:ABCdef_123..."
    )

if not ADMIN_IDS:
    raise ValueError("No valid admin IDs provided")

# База данных
DATABASE_PATH = "bookings.db"

# Настройки бронирования
MAX_BOOKINGS_PER_USER = 3
CANCELLATION_HOURS = 24
WORK_HOURS_START = 7   # ✅ ИЗМЕНЕНО: с 9 до 7
WORK_HOURS_END = 22    # ✅ ИЗМЕНЕНО: с 19 до 22

# ✅ DEPRECATED: Услуги теперь управляются через БД и админ-панель
# Оставлено для обратной совместимости в напоминаниях
SERVICE_LOCATION = "г. Москва, ул. Примерная, 1 / Онлайн"

# Временная зона (ИСПРАВЛЕНО: используем pytz для корректной обработки DST)
TIMEZONE = pytz.timezone("Europe/Moscow")

# === ✅ PRIORITY 1: ВЕРСИОНИРОВАНИЕ CALLBACK И ВАЛИДАЦИЯ ===
CALLBACK_VERSION = "v3"  # Увеличивать при breaking changes в callback_data
CALLBACK_MESSAGE_TTL_HOURS = 48  # Время жизни интерактивных сообщений (часы)

# Тайминги и задержки (в секундах)
ONBOARDING_DELAY_SHORT = 1.0  # Короткая задержка между сообщениями
ONBOARDING_DELAY_LONG = 1.0   # ✅ ИЗМЕНЕНО: с 4.0 до 1.0 секунды
BROADCAST_DELAY = 0.05        # Задержка между сообщениями в рассылке (50ms)
RATE_LIMIT_TIME = 1.0         # Время между действиями одного пользователя

# FSM таймауты (в секундах)
FSM_STATE_TTL = 600  # 10 минут - автоматический сброс состояния

# Ограничения навигации календаря
CALENDAR_MAX_MONTHS_AHEAD = 3  # Максимум месяцев вперёд для бронирования

# === КОНСТАНТЫ ВРЕМЕНИ (в часах) ===
REMINDER_HOURS_BEFORE_24H = 24  # Напоминание за 24 часа
REMINDER_HOURS_BEFORE_2H = 2    # Напоминание за 2 часа
REMINDER_HOURS_BEFORE_1H = 1    # Напоминание за 1 час
FEEDBACK_HOURS_AFTER = 2        # Запрос обратной связи через 2 часа после встречи

# === НАСТРОЙКИ РЕЗЕРВНОГО КОПИРОВАНИЯ ===
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "1"))  # ✅ ИЗМЕНЕНО: каждый 1 час
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))  # Хранить 30 дней
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")  # Директория для бэкапов

# === КОДЫ ОШИБОК БРОНИРОВАНИЯ ===
ERROR_NO_SERVICES = "no_services"              # Нет доступных услуг
ERROR_SERVICE_UNAVAILABLE = "service_not_available"  # Услуга недоступна
ERROR_LIMIT_EXCEEDED = "limit_exceeded"        # Превышен лимит записей
ERROR_SLOT_TAKEN = "slot_taken"                # Слот занят
ERROR_UNKNOWN = "unknown_error"                # Неизвестная ошибка
ERROR_SUCCESS = "success"                      # Успешно

# === ПАГИНАЦИЯ ===
DEFAULT_PAGE_SIZE = 20   # Размер страницы по умолчанию
MAX_PAGE_SIZE = 100      # Максимальный размер страницы

# Названия месяцев
MONTH_NAMES = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

# Названия дней недели
DAY_NAMES = [
    "понедельник",
    "вторник",
    "среду",
    "четверг",
    "пятницу",
    "субботу",
    "воскресенье",
]

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
