"""
Централизованная валидация callback_data с проверкой актуальности.

КРИТИЧНО: Защита от устаревших кнопок и некорректных данных.
"""

import hashlib
import logging
from datetime import datetime
from typing import Optional, Tuple

from config import TIMEZONE
from database.queries import Database
from utils.helpers import now_local


class CallbackValidator:
    """Валидатор callback данных с проверкой актуальности"""
    
    # Версия callback протокола (увеличивается при breaking changes)
    CALLBACK_VERSION = "v2"
    
    @classmethod
    def create_versioned_callback(cls, action: str, *args) -> str:
        """
        Создать версионированный callback_data.
        
        Args:
            action: Действие (например, 'cancel', 'confirm')
            *args: Дополнительные параметры
            
        Returns:
            Строка вида "v2:action:arg1:arg2"
            
        Example:
            >>> CallbackValidator.create_versioned_callback('cancel', 123)
            'v2:cancel:123'
        """
        parts = [cls.CALLBACK_VERSION, action] + [str(arg) for arg in args]
        callback_data = ":".join(parts)
        
        # Telegram ограничивает callback_data до 64 байт
        if len(callback_data.encode('utf-8')) > 64:
            # Используем хеш для длинных данных
            data_hash = hashlib.md5(callback_data.encode()).hexdigest()[:8]
            return f"{cls.CALLBACK_VERSION}:{action}:hash:{data_hash}"
        
        return callback_data
    
    @classmethod
    def parse_versioned_callback(cls, callback_data: str) -> Optional[Tuple[str, ...]]:
        """
        Парсит версионированный callback с проверкой версии.
        
        Args:
            callback_data: Строка callback_data
            
        Returns:
            Tuple с (action, *args) или None если версия устарела
            
        Example:
            >>> CallbackValidator.parse_versioned_callback('v2:cancel:123')
            ('cancel', '123')
        """
        if not callback_data or ':' not in callback_data:
            logging.warning(f"Invalid callback format: {callback_data}")
            return None
        
        parts = callback_data.split(':')
        version = parts[0]
        
        # Проверка версии
        if version != cls.CALLBACK_VERSION:
            logging.warning(
                f"Outdated callback version: {version} (current: {cls.CALLBACK_VERSION})"
            )
            return None
        
        # Возвращаем action и аргументы
        return tuple(parts[1:])
    
    @classmethod
    async def validate_booking_callback(
        cls, 
        callback_data: str, 
        user_id: int
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Валидация callback для операций с бронированием.
        
        Args:
            callback_data: callback_data строка
            user_id: ID пользователя
            
        Returns:
            (is_valid, data_dict, error_message)
            
        Example:
            >>> await validate_booking_callback('v2:cancel:123', 12345)
            (True, {'action': 'cancel', 'booking_id': 123}, None)
        """
        # Парсинг версионированного callback
        parsed = cls.parse_versioned_callback(callback_data)
        
        if not parsed:
            return False, None, "⚠️ Устаревшая кнопка. Используйте /start"
        
        action = parsed[0]
        
        # Валидация в зависимости от действия
        if action in ('cancel', 'reschedule', 'cancel_confirm'):
            if len(parsed) < 2:
                return False, None, "❌ Неверный формат данных"
            
            try:
                booking_id = int(parsed[1])
            except (ValueError, IndexError):
                return False, None, "❌ Неверный ID записи"
            
            # КРИТИЧНО: Проверка существования бронирования
            booking = await Database.get_booking_by_id(booking_id, user_id)
            
            if not booking:
                return False, None, "❌ Запись не найдена или была удалена"
            
            date_str, time_str, username = booking
            
            # Проверка что запись не в прошлом
            try:
                booking_dt = datetime.strptime(
                    f"{date_str} {time_str}", 
                    "%Y-%m-%d %H:%M"
                ).replace(tzinfo=TIMEZONE)
                
                if booking_dt < now_local():
                    return False, None, "❌ Эта запись уже в прошлом"
            except ValueError:
                return False, None, "❌ Ошибка формата даты"
            
            # Для отмены - проверка временных ограничений
            if action in ('cancel', 'cancel_confirm'):
                can_cancel, hours_left = await Database.can_cancel_booking(
                    date_str, time_str
                )
                
                if not can_cancel:
                    from config import CANCELLATION_HOURS
                    return False, None, (
                        f"⚠️ До встречи осталось {hours_left:.1f}ч\n"
                        f"Отмена возможна за {CANCELLATION_HOURS}ч"
                    )
            
            return True, {
                'action': action,
                'booking_id': booking_id,
                'date': date_str,
                'time': time_str,
                'username': username
            }, None
        
        elif action == 'confirm':
            # confirm:date:time
            if len(parsed) < 3:
                return False, None, "❌ Неверный формат данных"
            
            date_str = parsed[1]
            time_str = parsed[2]
            
            # Проверка формата даты/времени
            try:
                booking_dt = datetime.strptime(
                    f"{date_str} {time_str}", 
                    "%Y-%m-%d %H:%M"
                ).replace(tzinfo=TIMEZONE)
            except ValueError:
                return False, None, "❌ Неверный формат даты/времени"
            
            # Проверка что время не в прошлом
            if booking_dt < now_local():
                return False, None, "❌ Нельзя выбрать прошедшее время"
            
            # КРИТИЧНО: Проверка что слот свободен
            is_free = await Database.is_slot_free(date_str, time_str)
            
            if not is_free:
                return False, None, "❌ Этот слот уже занят"
            
            return True, {
                'action': action,
                'date': date_str,
                'time': time_str
            }, None
        
        elif action == 'select_service':
            if len(parsed) < 2:
                return False, None, "❌ Неверный формат"
            
            try:
                service_id = int(parsed[1])
            except ValueError:
                return False, None, "❌ Неверный ID услуги"
            
            # Проверка существования и активности услуги
            from database.repositories.service_repository import ServiceRepository
            service = await ServiceRepository.get_service_by_id(service_id)
            
            if not service or not service.is_active:
                return False, None, "❌ Услуга недоступна"
            
            return True, {
                'action': action,
                'service_id': service_id,
                'service': service
            }, None
        
        # Другие действия (день, месяц, время) - базовая валидация
        return True, {'action': action, 'params': parsed[1:]}, None
    
    @classmethod
    async def validate_and_cleanup_old_message(
        cls,
        message,
        max_age_hours: int = 24
    ) -> bool:
        """
        Проверяет возраст сообщения и удаляет клавиатуру если устарело.
        
        Args:
            message: Message объект
            max_age_hours: Максимальный возраст в часах
            
        Returns:
            True если сообщение актуально, False если устарело
        """
        if not message or not message.date:
            return False
        
        message_age = now_local() - message.date
        max_age_seconds = max_age_hours * 3600
        
        if message_age.total_seconds() > max_age_seconds:
            try:
                await message.edit_reply_markup(reply_markup=None)
                logging.info(
                    f"Removed keyboard from old message (age: {message_age})"
                )
            except Exception as e:
                logging.warning(f"Failed to remove old keyboard: {e}")
            
            return False
        
        return True
    
    @classmethod
    def create_state_hash(cls, **kwargs) -> str:
        """
        Создает хеш для проверки целостности состояния.
        
        Используется для обнаружения подмены данных в FSM state.
        
        Example:
            >>> hash1 = CallbackValidator.create_state_hash(
            ...     booking_id=123, user_id=456
            ... )
            >>> # Позже проверяем
            >>> hash2 = CallbackValidator.create_state_hash(
            ...     booking_id=123, user_id=456
            ... )
            >>> hash1 == hash2
            True
        """
        # Сортируем ключи для стабильности
        sorted_items = sorted(kwargs.items())
        data_string = ":".join(f"{k}={v}" for k, v in sorted_items)
        return hashlib.sha256(data_string.encode()).hexdigest()[:16]
    
    @classmethod
    async def validate_state_integrity(
        cls,
        state_data: dict,
        expected_hash: Optional[str] = None
    ) -> bool:
        """
        Проверяет целостность данных FSM state.
        
        Args:
            state_data: Данные из FSM
            expected_hash: Ожидаемый хеш (если None - создает новый)
            
        Returns:
            True если данные не изменены
        """
        if not state_data:
            return False
        
        # Исключаем системные поля
        filtered_data = {
            k: v for k, v in state_data.items() 
            if not k.startswith('_')
        }
        
        current_hash = cls.create_state_hash(**filtered_data)
        
        if expected_hash:
            return current_hash == expected_hash
        
        # Если expected_hash не передан, считаем что это первая проверка
        return True


# Утилиты для быстрого использования

async def validate_booking_action(callback_data: str, user_id: int):
    """
    Удобная обертка для валидации действий с бронированием.
    
    Usage в handlers:
        valid, data, error = await validate_booking_action(
            callback.data, 
            callback.from_user.id
        )
        if not valid:
            await callback.answer(error, show_alert=True)
            return
    """
    return await CallbackValidator.validate_booking_callback(
        callback_data, 
        user_id
    )


def create_safe_callback(action: str, *args) -> str:
    """
    Удобная обертка для создания безопасных callback.
    
    Usage в keyboards:
        InlineKeyboardButton(
            text="Отменить",
            callback_data=create_safe_callback('cancel', booking_id)
        )
    """
    return CallbackValidator.create_versioned_callback(action, *args)
