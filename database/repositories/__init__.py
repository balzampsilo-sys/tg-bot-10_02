"""Репозитории для работы с базой данных"""

from database.repositories.admin_repository import AdminRepository
from database.repositories.analytics_repository import (
    AnalyticsRepository,
    ClientStats,
)
from database.repositories.booking_repository import BookingRepository
from database.repositories.user_repository import UserRepository

__all__ = [
    "AdminRepository",
    "BookingRepository",
    "UserRepository",
    "AnalyticsRepository",
    "ClientStats",
]
