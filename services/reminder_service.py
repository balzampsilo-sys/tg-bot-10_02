"""Сервис напоминаний о записях

Priority: P0 (High)
Функции:
- Напоминание за 24 часа
- Напоминание за 1 час
- Автоматическая отмена неподтвержденных записей
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from aiogram import Bot

from database.repositories.booking_repository import BookingRepository
from database.repositories.service_repository import ServiceRepository
from utils.helpers import now_local


class ReminderService:
    """Сервис для отправки напоминаний о записях"""

    @staticmethod
    async def send_reminders_24h(bot: Bot) -> Tuple[int, int]:
        """Отправить напоминания за 24 часа до записи

        Args:
            bot: Экземпляр бота для отправки сообщений

        Returns:
            Tuple[success_count, total_count]
        """
        try:
            # Получаем записи на завтра
            tomorrow = now_local() + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%Y-%m-%d")

            bookings = await BookingRepository.get_bookings_for_date(tomorrow_str)

            if not bookings:
                logging.info("📭 Нет записей на завтра для напоминаний 24h")
                return 0, 0

            success_count = 0
            total_count = len(bookings)

            for booking in bookings:
                try:
                    # Получаем информацию об услуге
                    service = await ServiceRepository.get_service_by_id(booking["service_id"])
                    service_name = service.name if service else "Консультация"

                    # Форматируем сообщение
                    message = (
                        f"⏰ НАПОМИНАНИЕ О ЗАПИСИ\n\n"
                        f"📅 Завтра, {tomorrow.strftime('%d.%m.%Y')}\n"
                        f"🕒 Время: {booking['time']}\n"
                        f"📋 Услуга: {service_name}\n"
                        f"⏱ Длительность: {booking['duration_minutes']} минут\n\n"
                        f"💡 Отменить запись можно в разделе\n"
                        f'"📋 Мои записи" до 18:00 сегодня'
                    )

                    await bot.send_message(booking["user_id"], message)
                    success_count += 1

                    logging.info(
                        f"✅ Reminder 24h sent to user {booking['user_id']} "
                        f"for {tomorrow_str} {booking['time']}"
                    )

                except Exception as e:
                    logging.error(
                        f"❌ Failed to send 24h reminder to user {booking['user_id']}: {e}"
                    )

            logging.info(f"📊 Reminders 24h: sent {success_count}/{total_count}")
            return success_count, total_count

        except Exception as e:
            logging.error(f"❌ Error in send_reminders_24h: {e}")
            return 0, 0

    @staticmethod
    async def send_reminders_1h(bot: Bot) -> Tuple[int, int]:
        """Отправить напоминания за 1 час до записи

        Args:
            bot: Экземпляр бота для отправки сообщений

        Returns:
            Tuple[success_count, total_count]
        """
        try:
            # Получаем текущее время и +1 час
            now = now_local()
            one_hour_later = now + timedelta(hours=1)

            # Округляем до часа
            target_time = one_hour_later.replace(minute=0, second=0, microsecond=0)
            target_date = target_time.strftime("%Y-%m-%d")
            target_time_str = target_time.strftime("%H:%M")

            # Получаем все записи на сегодня
            bookings = await BookingRepository.get_bookings_for_date(target_date)

            if not bookings:
                return 0, 0

            # Фильтруем записи на ближайший час
            target_bookings = [
                b
                for b in bookings
                if b["time"] == target_time_str or b["time"] == target_time_str.replace(":00", "")
            ]

            if not target_bookings:
                return 0, 0

            success_count = 0
            total_count = len(target_bookings)

            for booking in target_bookings:
                try:
                    # Получаем информацию об услуге
                    service = await ServiceRepository.get_service_by_id(booking["service_id"])
                    service_name = service.name if service else "Консультация"

                    # Форматируем сообщение
                    message = (
                        f"🔔 СКОРО ВАША ЗАПИСЬ!\n\n"
                        f"📅 Сегодня, {target_time.strftime('%d.%m.%Y')}\n"
                        f"🕒 Время: {booking['time']}\n"
                        f"📋 Услуга: {service_name}\n\n"
                        f"⏰ Через 1 час\n"
                        f"Будем рады вас видеть!"
                    )

                    await bot.send_message(booking["user_id"], message)
                    success_count += 1

                    logging.info(
                        f"✅ Reminder 1h sent to user {booking['user_id']} "
                        f"for {target_date} {booking['time']}"
                    )

                except Exception as e:
                    logging.error(f"❌ Failed to send 1h reminder to user {booking['user_id']}: {e}")

            if success_count > 0:
                logging.info(f"📊 Reminders 1h: sent {success_count}/{total_count}")

            return success_count, total_count

        except Exception as e:
            logging.error(f"❌ Error in send_reminders_1h: {e}")
            return 0, 0

    @staticmethod
    async def get_upcoming_bookings_count(hours: int = 24) -> int:
        """Получить количество предстоящих записей

        Args:
            hours: Период в часах

        Returns:
            Количество записей
        """
        try:
            target = now_local() + timedelta(hours=hours)
            target_date = target.strftime("%Y-%m-%d")

            bookings = await BookingRepository.get_bookings_for_date(target_date)
            return len(bookings)

        except Exception as e:
            logging.error(f"❌ Error getting upcoming bookings count: {e}")
            return 0
