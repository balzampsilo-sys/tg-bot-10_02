"""Configuration"""

import os
import sys
from pathlib import Path

import pytz
from dotenv import load_dotenv

load_dotenv()

# === BOT ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit("❌ BOT_TOKEN not found in .env")

# === ADMIN ===
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip()]

if not ADMIN_IDS:
    sys.exit("❌ ADMIN_IDS not found in .env")

# ✅ Rate limit для добавления админов
MAX_ADMIN_ADDITIONS_PER_HOUR = int(os.getenv("MAX_ADMIN_ADDITIONS_PER_HOUR", "3"))

# === BOOKINGS ===
MAX_BOOKINGS_PER_USER = int(os.getenv("MAX_BOOKINGS_PER_USER", "3"))
CANCELLATION_HOURS = int(os.getenv("CANCELLATION_HOURS", "24"))

# === REMINDERS ===
REMINDER_HOURS_BEFORE_1H = int(os.getenv("REMINDER_HOURS_BEFORE_1H", "1"))
REMINDER_HOURS_BEFORE_2H = int(os.getenv("REMINDER_HOURS_BEFORE_2H", "2"))
REMINDER_HOURS_BEFORE_24H = int(os.getenv("REMINDER_HOURS_BEFORE_24H", "24"))

# === FEEDBACK ===
FEEDBACK_HOURS_AFTER = int(os.getenv("FEEDBACK_HOURS_AFTER", "2"))

# === SERVICE INFO ===
SERVICE_LOCATION = os.getenv("SERVICE_LOCATION", "Москва, ул. Примерная, 1")

# === WORK SCHEDULE ===
WORK_HOURS_START = int(os.getenv("WORK_HOURS_START", "9"))
WORK_HOURS_END = int(os.getenv("WORK_HOURS_END", "18"))

# === DATABASE ===
DATABASE_PATH = os.getenv("DATABASE_PATH", "bookings.db")

# === DATABASE RETRY LOGIC ✅ NEW ===
DB_MAX_RETRIES = int(os.getenv("DB_MAX_RETRIES", "3"))
DB_RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "0.5"))  # seconds
DB_RETRY_BACKOFF = float(os.getenv("DB_RETRY_BACKOFF", "2.0"))  # multiplier

# === BACKUP ===
BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "True").lower() in ("true", "1", "yes")
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

# === BROADCAST ===
BROADCAST_DELAY = float(os.getenv("BROADCAST_DELAY", "0.05"))

# === CALENDAR ===
CALENDAR_MAX_MONTHS_AHEAD = int(os.getenv("CALENDAR_MAX_MONTHS_AHEAD", "3"))

# === TIMEZONE ✅ FIXED: Use pytz for proper DST handling ===
TIMEZONE = pytz.timezone('Europe/Moscow')  # Properly handles DST transitions

# === DAY NAMES ===
DAY_NAMES = [
    "Пн",  # Monday
    "Вт",  # Tuesday
    "Ср",  # Wednesday
    "Чт",  # Thursday
    "Пт",  # Friday
    "Сб",  # Saturday
    "Вс",  # Sunday
]

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

# === CALLBACK VALIDATION ===
CALLBACK_VERSION = "v3"
CALLBACK_MESSAGE_TTL_HOURS = 48

# === ERROR CODES ===
ERROR_NO_SERVICES = "NO_SERVICES"
ERROR_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
ERROR_LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
ERROR_SLOT_TAKEN = "SLOT_TAKEN"

# === ADMIN ROLES ===
ROLE_SUPER_ADMIN = "super_admin"
ROLE_MODERATOR = "moderator"

ADMIN_ROLES = [ROLE_SUPER_ADMIN, ROLE_MODERATOR]

ROLE_PERMISSIONS = {
    ROLE_SUPER_ADMIN: {
        "manage_admins": True,
        "view_audit_log": True,
        "manage_bookings": True,
        "manage_slots": True,
        "edit_services": True,
        "export_data": True,
    },
    ROLE_MODERATOR: {
        "manage_admins": False,
        "view_audit_log": False,
        "manage_bookings": True,
        "manage_slots": True,
        "edit_services": True,
        "export_data": False,
    },
}
