"""
Middleware для автоматической деактивации устаревших кнопок.

СРЕДНИЙ ПРИОРИТЕТ: Защита от старых сообщений с кнопками.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from utils.callback_validator import CallbackValidator
from utils.helpers import now_local


class CallbackSecurityMiddleware(BaseMiddleware):
    """
    Middleware для безопасности callback запросов.
    
    Функционал:
    - Автоматическое удаление кнопок из старых сообщений
    - Проверка версий callback_data
    - Rate limiting для callback запросов
    - Логирование подозрительной активности
    """
    
    def __init__(
        self,
        max_message_age_hours: int = 24,
        enable_version_check: bool = True,
        enable_rate_limit: bool = True,
        rate_limit_window: int = 60,  # секунд
        max_callbacks_per_window: int = 30
    ):
        """
        Args:
            max_message_age_hours: Максимальный возраст сообщений с кнопками
            enable_version_check: Включить проверку версий
            enable_rate_limit: Включить rate limiting
            rate_limit_window: Окно для rate limit (сек)
            max_callbacks_per_window: Макс количество callback в окне
        """
        super().__init__()
        self.max_message_age_hours = max_message_age_hours
        self.enable_version_check = enable_version_check
        self.enable_rate_limit = enable_rate_limit
        self.rate_limit_window = rate_limit_window
        self.max_callbacks_per_window = max_callbacks_per_window
        
        # Хранилище для rate limiting
        self.user_callbacks: Dict[int, list] = {}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Основной метод middleware"""
        
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)
        
        user_id = event.from_user.id
        callback_data = event.data
        message = event.message
        
        # === 1. ПРОВЕРКА ВОЗРАСТА СООБЩЕНИЯ ===
        if message and message.date:
            message_age = now_local() - message.date
            max_age = timedelta(hours=self.max_message_age_hours)
            
            if message_age > max_age:
                logging.info(
                    f"Blocking old callback from user {user_id}, "
                    f"message age: {message_age}"
                )
                
                try:
                    await message.edit_reply_markup(reply_markup=None)
                except Exception as e:
                    logging.debug(f"Failed to remove old keyboard: {e}")
                
                await event.answer(
                    "⚠️ Это сообщение устарело\n"
                    "Используйте /start для новой записи",
                    show_alert=True
                )
                return  # Блокируем дальнейшую обработку
        
        # === 2. ПРОВЕРКА ВЕРСИИ CALLBACK ===
        if self.enable_version_check and callback_data and ':' in callback_data:
            parsed = CallbackValidator.parse_versioned_callback(callback_data)
            
            if parsed is None:
                # Устаревшая версия
                logging.warning(
                    f"Outdated callback from user {user_id}: {callback_data}"
                )
                
                try:
                    await message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                
                await event.answer(
                    "⚠️ Устаревшая кнопка\n"
                    "Используйте меню для нового действия",
                    show_alert=True
                )
                return
        
        # === 3. RATE LIMITING ===
        if self.enable_rate_limit:
            now = datetime.now()
            
            # Инициализируем если пользователь новый
            if user_id not in self.user_callbacks:
                self.user_callbacks[user_id] = []
            
            # Удаляем старые записи
            cutoff_time = now - timedelta(seconds=self.rate_limit_window)
            self.user_callbacks[user_id] = [
                t for t in self.user_callbacks[user_id] 
                if t > cutoff_time
            ]
            
            # Проверяем лимит
            if len(self.user_callbacks[user_id]) >= self.max_callbacks_per_window:
                logging.warning(
                    f"Rate limit exceeded for user {user_id}: "
                    f"{len(self.user_callbacks[user_id])} callbacks in "
                    f"{self.rate_limit_window}s"
                )
                
                await event.answer(
                    "⚠️ Слишком много действий\n"
                    "Подождите немного",
                    show_alert=True
                )
                return
            
            # Добавляем текущее время
            self.user_callbacks[user_id].append(now)
        
        # === 4. ЛОГИРОВАНИЕ ПОДОЗРИТЕЛЬНОЙ АКТИВНОСТИ ===
        # Обнаружение множественных callback на одно сообщение
        if message:
            message_key = f"{user_id}:{message.message_id}"
            
            # Добавляем в данные для мониторинга
            data['_callback_metadata'] = {
                'user_id': user_id,
                'message_id': message.message_id,
                'callback_data': callback_data,
                'message_age': message_age.total_seconds() if message.date else 0,
                'timestamp': now
            }
        
        # === 5. ПРОДОЛЖАЕМ ОБРАБОТКУ ===
        try:
            return await handler(event, data)
        except Exception as e:
            logging.error(
                f"Error in callback handler for user {user_id}: {e}",
                exc_info=True
            )
            
            # Удаляем кнопки при ошибке
            try:
                if message:
                    await message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            
            await event.answer(
                "❌ Произошла ошибка\n"
                "Попробуйте снова",
                show_alert=True
            )
            raise


class MessageCleanupMiddleware(BaseMiddleware):
    """
    Middleware для автоматической очистки старых сообщений.
    
    Удаляет inline клавиатуры из сообщений старше определенного возраста.
    """
    
    def __init__(self, max_age_hours: int = 48):
        """
        Args:
            max_age_hours: Максимальный возраст сообщений с клавиатурами
        """
        super().__init__()
        self.max_age_hours = max_age_hours
        self.cleaned_messages = set()  # Кеш обработанных сообщений
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Обработка callback"""
        
        if not isinstance(event, CallbackQuery) or not event.message:
            return await handler(event, data)
        
        message = event.message
        message_id = message.message_id
        
        # Пропускаем уже обработанные
        if message_id in self.cleaned_messages:
            return await handler(event, data)
        
        # Проверяем возраст
        if message.date:
            message_age = now_local() - message.date
            max_age = timedelta(hours=self.max_age_hours)
            
            if message_age > max_age:
                try:
                    await message.edit_text(
                        f"{message.text or 'Сообщение'}\n\n"
                        "⚠️ Это сообщение устарело",
                        reply_markup=None
                    )
                    self.cleaned_messages.add(message_id)
                    logging.info(f"Cleaned old message {message_id}")
                except Exception as e:
                    logging.debug(f"Failed to clean message {message_id}: {e}")
        
        return await handler(event, data)


class CallbackIntegrityMiddleware(BaseMiddleware):
    """
    Middleware для проверки целостности FSM state.
    
    Предотвращает подмену данных в состоянии.
    """
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """Проверка целостности state"""
        
        if not isinstance(event, CallbackQuery):
            return await handler(event, data)
        
        # Получаем FSM state
        state = data.get('state')
        
        if state:
            state_data = await state.get_data()
            
            # Проверяем хеш если он есть
            expected_hash = state_data.get('_integrity_hash')
            
            if expected_hash:
                is_valid = await CallbackValidator.validate_state_integrity(
                    state_data,
                    expected_hash
                )
                
                if not is_valid:
                    logging.warning(
                        f"State integrity check failed for user "
                        f"{event.from_user.id}"
                    )
                    
                    await state.clear()
                    await event.answer(
                        "❌ Данные устарели\n"
                        "Начните заново",
                        show_alert=True
                    )
                    return
        
        return await handler(event, data)
