"""Сервис управления бронированием"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    DATABASE_PATH,
    FEEDBACK_HOURS_AFTER,
    MAX_BOOKINGS_PER_USER,
    REMINDER_HOURS_BEFORE_1H,
    REMINDER_HOURS_BEFORE_2H,
    REMINDER_HOURS_BEFORE_24H,
    TIMEZONE,
)
from database.queries import Database
from database.repositories.booking_history_repository import BookingHistoryRepository
from utils.helpers import now_local


class BookingService:
    """Сервис для работы с бронированием"""

    def __init__(self, scheduler: AsyncIOScheduler, bot):
        self.scheduler = scheduler
        self.bot = bot

    async def _get_default_service(self) -> Optional[Tuple[int, int]]:
        """Получить дефолтную активную услугу

        Returns:
            Tuple[service_id, duration] или None если услуг нет
        """
        from database.repositories.service_repository import ServiceRepository

        services = await ServiceRepository.get_all_services(active_only=True)

        if not services:
            logging.error("No active services available for booking")
            return None

        # Берем первую активную услугу по display_order
        default_service = services[0]
        logging.info(
            f"Using default service: {default_service.name} "
            f"(id={default_service.id}, duration={default_service.duration_minutes}min)"
        )

        return (default_service.id, default_service.duration_minutes)

    async def create_booking(
        self,
        date_str: str,
        time_str: str,
        user_id: int,
        username: str,
        service_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Создание записи с атомарной проверкой и поддержкой услуг

        Args:
            date_str: Дата в формате YYYY-MM-DD
            time_str: Время в формате HH:MM
            user_id: ID пользователя
            username: Имя пользователя
            service_id: ID услуги (опционально, для обратной совместимости)

        Returns:
            Tuple[bool, str]: (success, error_code)
            error_code может быть:
                - 'success' - успешно
                - 'no_services' - нет доступных услуг
                - 'service_not_available' - выбранная услуга недоступна
                - 'limit_exceeded' - превышен лимит записей
                - 'slot_taken' - слот занят
                - 'unknown_error' - неизвестная ошибка
        """
        # Если service_id не передан, используем дефолтную услугу
        if service_id is None:
            default = await self._get_default_service()
            if default is None:
                logging.error("Cannot create booking: no active services")
                return False, "no_services"

            service_id, duration = default
        else:
            # Проверяем что услуга существует и активна
            from database.repositories.service_repository import ServiceRepository

            service = await ServiceRepository.get_service_by_id(service_id)
            if not service:
                logging.warning(f"Service {service_id} not found")
                return False, "service_not_available"

            if not service.is_active:
                logging.warning(f"Service {service_id} is inactive")
                return False, "service_not_available"

            duration = service.duration_minutes

        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("BEGIN IMMEDIATE")

            try:
                # Проверяем лимит пользователя
                async with db.execute(
                    "SELECT COUNT(*) FROM bookings WHERE user_id=? AND date >= date('now')",
                    (user_id,),
                ) as cursor:
                    user_count = (await cursor.fetchone())[0]

                if user_count >= MAX_BOOKINGS_PER_USER:
                    await db.rollback()
                    logging.warning(f"User {user_id} exceeded booking limit")
                    return False, "limit_exceeded"

                # Проверяем пересечения с учетом длительности
                is_available = await self._check_slot_availability_in_transaction(
                    db, date_str, time_str, duration
                )

                if not is_available:
                    await db.rollback()
                    logging.info(f"Slot {date_str} {time_str} not available")
                    return False, "slot_taken"

                # Создаем запись (service_id гарантированно не NULL)
                cursor = await db.execute(
                    """INSERT INTO bookings (date, time, user_id, username, service_id, duration_minutes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        date_str,
                        time_str,
                        user_id,
                        username,
                        service_id,
                        duration,
                        now_local().isoformat(),
                    ),
                )
                booking_id = cursor.lastrowid

                await db.commit()

                # ✅ P0: Записываем в историю
                await BookingHistoryRepository.record_create(
                    booking_id=booking_id,
                    user_id=user_id,
                    date=date_str,
                    time=time_str,
                    service_id=service_id,
                )

                # Планируем напоминание (вне транзакции)
                await self._schedule_reminder(booking_id, date_str, time_str, user_id)
                await Database.log_event(
                    user_id, "booking_created", f"{date_str} {time_str} service_id={service_id}"
                )

                logging.info(
                    f"Booking created: {booking_id} for user {user_id}, "
                    f"service {service_id}, duration {duration}min"
                )
                return True, "success"

            except sqlite3.IntegrityError as e:
                await db.rollback()
                logging.warning(f"Integrity error creating booking: {e}")
                return False, "slot_taken"
            except Exception as e:
                await db.rollback()
                logging.error(f"Error in create_booking: {e}", exc_info=True)
                return False, "unknown_error"

    async def _check_slot_availability_in_transaction(
        self, db: aiosqlite.Connection, date_str: str, time_str: str, duration_minutes: int
    ) -> bool:
        """Проверка доступности с учетом пересечений (внутри транзакции)

        Args:
            db: Активное соединение с БД (внутри транзакции)
            date_str: Дата в формате YYYY-MM-DD
            time_str: Время в формате HH:MM
            duration_minutes: Длительность в минутах

        Returns:
            True если слот свободен, False если занят
        """
        # Парсим время начала
        start_time = datetime.strptime(time_str, "%H:%M")
        end_time = start_time + timedelta(minutes=duration_minutes)

        # Получаем все записи на этот день
        async with db.execute(
            "SELECT time, duration_minutes FROM bookings WHERE date=?", (date_str,)
        ) as cursor:
            existing = await cursor.fetchall()

        # Проверяем заблокированные слоты
        async with db.execute("SELECT time FROM blocked_slots WHERE date=?", (date_str,)) as cursor:
            blocked = await cursor.fetchall()

        # Проверяем пересечения с существующими записями
        for booking_time_str, booking_duration in existing:
            booking_start = datetime.strptime(booking_time_str, "%H:%M")
            booking_end = booking_start + timedelta(minutes=booking_duration or 60)

            # Интервалы пересекаются если:
            # start_time < booking_end AND end_time > booking_start
            if start_time < booking_end and end_time > booking_start:
                logging.debug(
                    f"Slot conflict: {time_str}-{end_time.strftime('%H:%M')} overlaps with "
                    f"{booking_time_str}-{booking_end.strftime('%H:%M')}"
                )
                return False

        # Проверяем заблокированные слоты
        for (blocked_time,) in blocked:
            if blocked_time == time_str:
                logging.debug(f"Slot {time_str} is blocked")
                return False

        return True

    async def reschedule_booking(
        self,
        booking_id: int,
        old_date_str: str,
        old_time_str: str,
        new_date_str: str,
        new_time_str: str,
        user_id: int,
        username: str,
    ) -> bool:
        """Перенос записи в одной транзакции

        Args:
            booking_id: ID записи для переноса
            old_date_str: Старая дата
            old_time_str: Старое время
            new_date_str: Новая дата
            new_time_str: Новое время
            user_id: ID пользователя
            username: Имя пользователя

        Returns:
            True если перенос успешен, False иначе
        """
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("BEGIN IMMEDIATE")

            try:
                # 1. Проверяем что старая запись существует
                async with db.execute(
                    "SELECT id, duration_minutes, service_id FROM bookings WHERE id=? AND user_id=?",
                    (booking_id, user_id),
                ) as cursor:
                    old_booking = await cursor.fetchone()

                if not old_booking:
                    await db.rollback()
                    logging.warning(f"Booking {booking_id} not found for user {user_id}")
                    return False

                duration = old_booking[1] or 60
                old_service_id = old_booking[2]

                # 2. Проверяем что новый слот свободен
                is_available = await self._check_slot_availability_in_transaction(
                    db, new_date_str, new_time_str, duration
                )

                if not is_available:
                    await db.rollback()
                    logging.info(f"Slot {new_date_str} {new_time_str} not available")
                    return False

                # 3. Обновляем запись (вместо удаления и создания)
                await db.execute(
                    """UPDATE bookings
                    SET date=?, time=?, created_at=?
                    WHERE id=?""",
                    (new_date_str, new_time_str, now_local().isoformat(), booking_id),
                )

                await db.commit()

                # ✅ P0: Записываем в историю
                await BookingHistoryRepository.record_reschedule(
                    booking_id=booking_id,
                    user_id=user_id,
                    changed_by_type="user",
                    old_date=old_date_str,
                    old_time=old_time_str,
                    new_date=new_date_str,
                    new_time=new_time_str,
                    old_service_id=old_service_id,
                    new_service_id=old_service_id,  # Услуга не меняется при переносе
                )

                # 4. Перепланируем напоминания (вне транзакции)
                self._remove_job_safe(f"reminder_{booking_id}")
                self._remove_job_safe(f"feedback_{booking_id}")

                await self._schedule_reminder(booking_id, new_date_str, new_time_str, user_id)

                await Database.log_event(
                    user_id,
                    "booking_rescheduled",
                    f"{old_date_str} {old_time_str} -> {new_date_str} {new_time_str}",
                )

                logging.info(f"Booking {booking_id} rescheduled successfully")
                return True

            except Exception as e:
                await db.rollback()
                logging.error(f"Error in reschedule_booking: {e}", exc_info=True)
                return False

    def _remove_job_safe(self, job_id: str) -> None:
        """Безопасное удаление задачи из scheduler

        Args:
            job_id: Идентификатор задачи
        """
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

    async def _schedule_reminder(
        self, booking_id: int, date_str: str, time_str: str, user_id: int
    ) -> None:
        """Планирование напоминаний

        Args:
            booking_id: ID записи
            date_str: Дата записи
            time_str: Время записи
            user_id: ID пользователя
        """
        try:
            booking_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            booking_datetime = TIMEZONE.localize(booking_datetime)
            now = now_local()
            time_until_booking = booking_datetime - now

            # Напоминание (используем константы)
            if time_until_booking > timedelta(hours=REMINDER_HOURS_BEFORE_24H):
                reminder_time = booking_datetime - timedelta(hours=REMINDER_HOURS_BEFORE_24H)
                self.scheduler.add_job(
                    self._send_reminder,
                    "date",
                    run_date=reminder_time,
                    args=[user_id, date_str, time_str],
                    id=f"reminder_{booking_id}",
                    replace_existing=True,
                )
            elif time_until_booking > timedelta(hours=REMINDER_HOURS_BEFORE_2H):
                reminder_time = booking_datetime - timedelta(hours=REMINDER_HOURS_BEFORE_2H)
                self.scheduler.add_job(
                    self._send_reminder,
                    "date",
                    run_date=reminder_time,
                    args=[user_id, date_str, time_str],
                    id=f"reminder_{booking_id}",
                    replace_existing=True,
                )
            elif time_until_booking > timedelta(hours=REMINDER_HOURS_BEFORE_1H):
                reminder_time = booking_datetime - timedelta(hours=REMINDER_HOURS_BEFORE_1H)
                self.scheduler.add_job(
                    self._send_reminder,
                    "date",
                    run_date=reminder_time,
                    args=[user_id, date_str, time_str],
                    id=f"reminder_{booking_id}",
                    replace_existing=True,
                )

            # Запрос обратной связи (используем константы)
            feedback_time = booking_datetime + timedelta(hours=FEEDBACK_HOURS_AFTER)
            self.scheduler.add_job(
                self._send_feedback_request,
                "date",
                run_date=feedback_time,
                args=[user_id, booking_id, date_str, time_str],
                id=f"feedback_{booking_id}",
                replace_existing=True,
            )
        except Exception as e:
            logging.error(f"Error scheduling reminder: {e}", exc_info=True)

    async def cancel_booking(
        self, date_str: str, time_str: str, user_id: int, admin_id: Optional[int] = None
    ) -> Tuple[bool, int]:
        """Отмена записи

        Args:
            date_str: Дата записи
            time_str: Время записи
            user_id: ID пользователя
            admin_id: ID админа (если отмена админом)

        Returns:
            Tuple[success, booking_id]
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT id, service_id FROM bookings WHERE date=? AND time=? AND user_id=?",
                    (date_str, time_str, user_id),
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        return False, 0

                    booking_id, service_id = result

                await db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
                await db.commit()

            # ✅ P0: Записываем в историю
            changed_by = admin_id if admin_id else user_id
            changed_by_type = "admin" if admin_id else "user"

            await BookingHistoryRepository.record_cancel(
                booking_id=booking_id,
                user_id=changed_by,
                changed_by_type=changed_by_type,
                date=date_str,
                time=time_str,
                service_id=service_id,
                reason="Cancelled by user" if not admin_id else "Cancelled by admin",
            )

            # Удаляем напоминания
            self._remove_job_safe(f"reminder_{booking_id}")
            self._remove_job_safe(f"feedback_{booking_id}")

            await Database.log_event(user_id, "booking_cancelled", f"{date_str} {time_str}")
            logging.info(
                f"Booking {booking_id} cancelled by {changed_by_type} (id={changed_by})"
            )
            return True, booking_id
        except Exception as e:
            logging.error(f"Error cancelling booking: {e}", exc_info=True)
            return False, 0

    async def restore_reminders(self, batch_size: int = 50) -> None:
        """Восстановить напоминания после рестарта с батчингом

        Args:
            batch_size: Размер батча для обработки (по умолчанию 50)
        """
        try:
            now = now_local()
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT id, date, time, user_id FROM bookings ORDER BY date, time"
                ) as cursor:
                    all_bookings = await cursor.fetchall()

            total_bookings = len(all_bookings)
            restored_count = 0
            processed_count = 0

            logging.info(f"Starting reminder restoration for {total_bookings} bookings...")

            # Обработка батчами
            for i in range(0, total_bookings, batch_size):
                batch = all_bookings[i : i + batch_size]

                for booking_id, date_str, time_str, user_id in batch:
                    try:
                        booking_datetime = datetime.strptime(
                            f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                        )
                        booking_datetime = TIMEZONE.localize(booking_datetime)

                        # Восстановить напоминание (используем константы)
                        reminder_time = booking_datetime - timedelta(
                            hours=REMINDER_HOURS_BEFORE_24H
                        )
                        if reminder_time > now:
                            self.scheduler.add_job(
                                self._send_reminder,
                                "date",
                                run_date=reminder_time,
                                args=[user_id, date_str, time_str],
                                id=f"reminder_{booking_id}",
                                replace_existing=True,
                            )
                            restored_count += 1

                        # Восстановить запрос обратной связи
                        feedback_time = booking_datetime + timedelta(hours=FEEDBACK_HOURS_AFTER)
                        if feedback_time > now:
                            self.scheduler.add_job(
                                self._send_feedback_request,
                                "date",
                                run_date=feedback_time,
                                args=[user_id, booking_id, date_str, time_str],
                                id=f"feedback_{booking_id}",
                                replace_existing=True,
                            )

                    except Exception as e:
                        logging.warning(
                            f"Failed to restore reminders for booking {booking_id}: {e}"
                        )
                    finally:
                        processed_count += 1

                # Логируем прогресс после каждого батча
                logging.info(
                    f"Reminder restoration progress: {processed_count}/{total_bookings} processed, "
                    f"{restored_count} restored"
                )

            logging.info(
                f"Reminder restoration completed: {restored_count} reminders restored from "
                f"{total_bookings} bookings"
            )
        except Exception as e:
            logging.error(f"Error restoring reminders: {e}", exc_info=True)

    async def _send_reminder(self, user_id: int, date_str: str, time_str: str) -> None:
        """Отправка напоминания

        Args:
            user_id: ID пользователя
            date_str: Дата записи
            time_str: Время записи
        """
        try:
            from config import DAY_NAMES, SERVICE_LOCATION

            date_obj = datetime.strptime(date_str, "%Y-%m-%d")

            await self.bot.send_message(
                user_id,
                "⏰ НАПОМИНАНИЕ!\n\n"
                "У вас запись ЗАВТРА:\n"
                f"📅 {date_obj.strftime('%d.%m.%Y')} ({DAY_NAMES[date_obj.weekday()]})\n"
                f"🕒 {time_str}\n"
                f"📍 {SERVICE_LOCATION}\n\n"
                "Если нужно отменить → '📋 Мои записи'",
            )
            await Database.log_event(user_id, "reminder_sent", f"{date_str} {time_str}")
        except Exception as e:
            logging.error(f"Error sending reminder: {e}", exc_info=True)

    async def _send_feedback_request(
        self, user_id: int, booking_id: int, date_str: str, time_str: str
    ) -> None:
        """Запрос обратной связи

        Args:
            user_id: ID пользователя
            booking_id: ID записи
            date_str: Дата записи
            time_str: Время записи
        """
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        feedback_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐⭐⭐⭐⭐", callback_data=f"feedback:{booking_id}:5"
                    ),
                    InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data=f"feedback:{booking_id}:4"),
                ],
                [
                    InlineKeyboardButton(text="⭐⭐⭐", callback_data=f"feedback:{booking_id}:3"),
                    InlineKeyboardButton(text="⭐⭐", callback_data=f"feedback:{booking_id}:2"),
                    InlineKeyboardButton(text="⭐", callback_data=f"feedback:{booking_id}:1"),
                ],
            ]
        )

        try:
            await self.bot.send_message(
                user_id,
                "💬 Как прошла встреча?\n\nОцените качество услуги:",
                reply_markup=feedback_kb,
            )
            await Database.log_event(user_id, "feedback_request_sent", f"{date_str} {time_str}")
        except Exception as e:
            logging.error(f"Error sending feedback request: {e}", exc_info=True)
