"""Централизованная валидация callback данных с проверкой актуальности"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from config import TIMEZONE, CALLBACK_VERSION, CALLBACK_MESSAGE_TTL_HOURS
from database.queries import Database
from database.repositories.service_repository import ServiceRepository


@dataclass
class ValidationResult:
    """Результат валидации callback"""
    is_valid: bool
    error_message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    should_clear_state: bool = False
    should_disable_buttons: bool = False


class CallbackValidator:
    """Централизованный валидатор для callback данных"""
    
    # Текущая версия callback (из config)
    CURRENT_VERSION = CALLBACK_VERSION
    
    # Время жизни callback сообщений (часы)
    MESSAGE_TTL_HOURS = CALLBACK_MESSAGE_TTL_HOURS
    
    @classmethod
    async def validate_callback(
        cls,
        callback: CallbackQuery,
        state: FSMContext,
        expected_parts: int = None,
        check_version: bool = True
    ) -> ValidationResult:
        """
        Комплексная валидация callback данных
        
        Args:
            callback: CallbackQuery объект
            state: FSMContext для проверки состояния
            expected_parts: Ожидаемое количество частей в callback_data
            check_version: Проверять ли версию callback
            
        Returns:
            ValidationResult с результатом валидации
        """
        
        # 1. Проверка версии callback (если включена)
        if check_version and ":" in callback.data:
            parts = callback.data.split(":")
            version = parts[0]
            
            if version.startswith("v") and version != cls.CURRENT_VERSION:
                return ValidationResult(
                    is_valid=False,
                    error_message="⚠️ Устаревшая кнопка\n\nИспользуйте /start для новой записи",
                    should_disable_buttons=True,
                    should_clear_state=True
                )
        
        # 2. Проверка возраста сообщения
        message_age = datetime.now(TIMEZONE) - callback.message.date
        if message_age.total_seconds() / 3600 > cls.MESSAGE_TTL_HOURS:
            return ValidationResult(
                is_valid=False,
                error_message=f"⚠️ Сообщение устарело (старше {cls.MESSAGE_TTL_HOURS}ч)\n\nНачните заново с /start",
                should_disable_buttons=True,
                should_clear_state=True
            )
        
        # 3. Проверка структуры данных
        if expected_parts:
            actual_parts = len(callback.data.split(":"))
            if actual_parts != expected_parts:
                logging.warning(
                    f"Invalid callback structure: expected {expected_parts} parts, "
                    f"got {actual_parts} in '{callback.data}'"
                )
                return ValidationResult(
                    is_valid=False,
                    error_message="❌ Ошибка данных кнопки",
                    should_clear_state=True
                )
        
        return ValidationResult(is_valid=True)
    
    @classmethod
    async def validate_booking_callback(
        cls,
        callback: CallbackQuery,
        state: FSMContext,
        booking_id: int
    ) -> ValidationResult:
        """
        Валидация callback связанного с бронированием
        
        Проверяет:
        - Существование бронирования
        - Принадлежность пользователю
        - Актуальность временных данных
        """
        
        # Базовая валидация
        base_result = await cls.validate_callback(callback, state)
        if not base_result.is_valid:
            return base_result
        
        # Проверка существования бронирования
        booking = await Database.get_booking_by_id(booking_id, callback.from_user.id)
        
        if not booking:
            return ValidationResult(
                is_valid=False,
                error_message="❌ Запись не найдена или была удалена",
                should_disable_buttons=True,
                should_clear_state=True
            )
        
        date_str, time_str, username = booking
        
        # Проверка что запись не в прошлом
        from utils.helpers import now_local
        booking_datetime = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        booking_datetime = TIMEZONE.localize(booking_datetime)
        
        if booking_datetime < now_local():
            return ValidationResult(
                is_valid=False,
                error_message="❌ Эта запись уже прошла",
                should_disable_buttons=True,
                should_clear_state=True
            )
        
        return ValidationResult(
            is_valid=True,
            data={
                "booking_id": booking_id,
                "date": date_str,
                "time": time_str,
                "username": username
            }
        )
    
    @classmethod
    async def validate_service_callback(
        cls,
        callback: CallbackQuery,
        state: FSMContext,
        service_id: int
    ) -> ValidationResult:
        """
        Валидация callback связанного с услугой
        
        Проверяет:
        - Существование услуги
        - Активность услуги
        """
        
        # Базовая валидация
        base_result = await cls.validate_callback(callback, state)
        if not base_result.is_valid:
            return base_result
        
        # Проверка существования услуги
        service = await ServiceRepository.get_service_by_id(service_id)
        
        if not service:
            return ValidationResult(
                is_valid=False,
                error_message="❌ Услуга не найдена",
                should_clear_state=True
            )
        
        if not service.is_active:
            return ValidationResult(
                is_valid=False,
                error_message="❌ Выбранная услуга больше недоступна\n\nВыберите другую",
                should_clear_state=True
            )
        
        return ValidationResult(
            is_valid=True,
            data={
                "service": service,
                "service_id": service_id
            }
        )
    
    @classmethod
    async def validate_slot_callback(
        cls,
        callback: CallbackQuery,
        state: FSMContext,
        date_str: str,
        time_str: str
    ) -> ValidationResult:
        """
        Валидация callback связанного со слотом времени
        
        Проверяет:
        - Формат даты/времени
        - Дата не в прошлом
        - Слот свободен
        - Слот не заблокирован
        """
        
        # Базовая валидация
        base_result = await cls.validate_callback(callback, state)
        if not base_result.is_valid:
            return base_result
        
        # Валидация формата даты
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            time_obj = datetime.strptime(time_str, "%H:%M")
        except ValueError:
            return ValidationResult(
                is_valid=False,
                error_message="❌ Неверный формат даты/времени",
                should_clear_state=True
            )
        
        # Проверка что дата не в прошлом
        from utils.helpers import now_local
        slot_datetime = datetime.combine(date_obj.date(), time_obj.time())
        slot_datetime = TIMEZONE.localize(slot_datetime)
        
        if slot_datetime < now_local():
            return ValidationResult(
                is_valid=False,
                error_message="❌ Выбрано прошедшее время\n\nВыберите актуальную дату",
                should_clear_state=True
            )
        
        # Проверка что слот свободен
        is_free = await Database.is_slot_free(date_str, time_str)
        
        if not is_free:
            return ValidationResult(
                is_valid=False,
                error_message="❌ Этот слот уже занят\n\nВыберите другое время",
                should_disable_buttons=False  # Не отключаем - пользователь может выбрать другой
            )
        
        return ValidationResult(
            is_valid=True,
            data={
                "date": date_str,
                "time": time_str,
                "datetime": slot_datetime
            }
        )
    
    @classmethod
    async def handle_validation_error(
        cls,
        callback: CallbackQuery,
        state: FSMContext,
        result: ValidationResult
    ):
        """
        Обработка ошибки валидации
        
        - Показывает сообщение пользователю
        - Отключает кнопки если нужно
        - Очищает состояние если нужно
        """
        
        # Показываем сообщение об ошибке
        await callback.answer(result.error_message or "❌ Ошибка", show_alert=True)
        
        # Отключаем кнопки если требуется
        if result.should_disable_buttons:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as e:
                logging.debug(f"Could not disable buttons: {e}")
        
        # Очищаем состояние если требуется
        if result.should_clear_state:
            await state.clear()
            
        logging.info(
            f"Validation failed for user {callback.from_user.id}: "
            f"callback='{callback.data}', error='{result.error_message}'"
        )


# Утилита для быстрого парсинга callback_data
def parse_callback_parts(callback_data: str, expected_parts: int = None) -> Optional[list]:
    """
    Безопасный парсинг callback_data
    
    Args:
        callback_data: Строка callback данных
        expected_parts: Ожидаемое количество частей
        
    Returns:
        Список частей или None если структура неверна
    """
    if not callback_data:
        return None
    
    parts = callback_data.split(":")
    
    if expected_parts and len(parts) != expected_parts:
        return None
    
    return parts
