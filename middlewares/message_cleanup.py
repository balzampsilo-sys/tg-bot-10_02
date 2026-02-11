"""
Middleware для автоматической очистки старых интерактивных сообщений

Приоритет 3 (Средний): Автоматическая деактивация старых кнопок
"""

import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from config import CALLBACK_MESSAGE_TTL_HOURS, TIMEZONE


class MessageCleanupMiddleware(BaseMiddleware):
    """
    Автоматически деактивирует кнопки в старых сообщениях
    
    Проверяет возраст сообщения и отключает интерактивность
    если оно старше установленного TTL
    """
    
    def __init__(self, ttl_hours: int = CALLBACK_MESSAGE_TTL_HOURS):
        """
        Args:
            ttl_hours: Время жизни интерактивных сообщений в часах
        """
        self.ttl_hours = ttl_hours
        self.ttl_delta = timedelta(hours=ttl_hours)
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        """
        Проверяет возраст сообщения перед обработкой callback
        """
        
        # Пропускаем системные callback (ignore, error и т.д.)
        if event.data in ("ignore", "error"):
            return await handler(event, data)
        
        message_date = event.message.date
        now = datetime.now(message_date.tzinfo or TIMEZONE)
        
        message_age = now - message_date
        
        # Если сообщение старше TTL
        if message_age > self.ttl_delta:
            hours_old = int(message_age.total_seconds() / 3600)
            
            await event.answer(
                f"⚠️ Это сообщение устарело ({hours_old}ч)\n\n"
                "Используйте /start для новой записи",
                show_alert=True
            )
            
            # Пытаемся отключить кнопки
            try:
                await event.message.edit_reply_markup(reply_markup=None)
                
                # Добавляем пометку что сообщение устарело
                try:
                    current_text = event.message.text or event.message.caption
                    if current_text and not current_text.startswith("⚠️"):
                        new_text = f"⚠️ УСТАРЕЛО\n\n{current_text}"
                        await event.message.edit_text(
                            new_text[:4096],  # Telegram limit
                            reply_markup=None
                        )
                except Exception as e:
                    logging.debug(f"Could not update message text: {e}")
                    
            except Exception as e:
                logging.debug(f"Could not disable buttons in old message: {e}")
            
            # Очищаем состояние пользователя
            state = data.get("state")
            if state:
                await state.clear()
            
            logging.info(
                f"Blocked interaction with old message: "
                f"user={event.from_user.id}, age={hours_old}h, "
                f"callback={event.data}"
            )
            
            return  # НЕ вызываем handler
        
        # Сообщение актуально - продолжаем обработку
        return await handler(event, data)


class RateLimitedCleanupMiddleware(MessageCleanupMiddleware):
    """
    Расширенная версия с rate limiting
    
    Отслеживает частоту нажатий на старые кнопки
    и временно блокирует пользователей при злоупотреблении
    """
    
    def __init__(self, ttl_hours: int = CALLBACK_MESSAGE_TTL_HOURS, max_attempts: int = 5):
        """
        Args:
            ttl_hours: Время жизни сообщений
            max_attempts: Максимальное количество попыток за минуту
        """
        super().__init__(ttl_hours)
        self.max_attempts = max_attempts
        self.user_attempts: Dict[int, list] = {}
        self.block_duration = timedelta(minutes=5)
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        now = datetime.now(TIMEZONE)
        
        # Очищаем старые попытки (старше 1 минуты)
        if user_id in self.user_attempts:
            self.user_attempts[user_id] = [
                attempt_time for attempt_time in self.user_attempts[user_id]
                if now - attempt_time < timedelta(minutes=1)
            ]
        
        # Проверяем количество попыток
        attempts = self.user_attempts.get(user_id, [])
        
        if len(attempts) >= self.max_attempts:
            await event.answer(
                "⚠️ Слишком много действий\n\n"
                "Подождите немного",
                show_alert=True
            )
            logging.warning(
                f"Rate limit exceeded for user {user_id}: "
                f"{len(attempts)} attempts in 1 minute"
            )
            return
        
        # Вызываем базовую логику
        result = await super().__call__(handler, event, data)
        
        # Если сообщение было заблокировано - считаем попытку
        message_age = now - event.message.date
        if message_age > self.ttl_delta:
            if user_id not in self.user_attempts:
                self.user_attempts[user_id] = []
            self.user_attempts[user_id].append(now)
        
        return result


class SmartCleanupMiddleware(MessageCleanupMiddleware):
    """
    Умная версия с адаптивным TTL
    
    Разные типы сообщений могут иметь разный TTL:
    - Календари - короткий TTL (быстро устаревают)
    - Списки записей - средний TTL
    - Подтверждения - длинный TTL (могут думать)
    """
    
    def __init__(self):
        super().__init__()
        # Настраиваемые TTL для разных типов сообщений
        self.ttl_map = {
            'calendar': timedelta(hours=12),   # Календарь быстро устаревает
            'slots': timedelta(hours=6),       # Слоты еще быстрее
            'list': timedelta(hours=24),       # Списки живут дольше
            'confirm': timedelta(hours=48),    # Подтверждения долго
            'default': timedelta(hours=CALLBACK_MESSAGE_TTL_HOURS)
        }
    
    def _detect_message_type(self, callback_data: str, message_text: str = None) -> str:
        """Определяем тип сообщения по callback_data и тексту"""
        if callback_data.startswith(("cal:", "day:", "back_calendar")):
            return 'calendar'
        elif callback_data.startswith("time:"):
            return 'slots'
        elif callback_data.startswith("confirm:"):
            return 'confirm'
        elif message_text and "МОИ ЗАПИСИ" in message_text.upper():
            return 'list'
        return 'default'
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        # Пропускаем системные
        if event.data in ("ignore", "error"):
            return await handler(event, data)
        
        # Определяем тип сообщения
        message_type = self._detect_message_type(
            event.data,
            event.message.text or event.message.caption
        )
        
        # Используем специфичный TTL
        self.ttl_delta = self.ttl_map.get(message_type, self.ttl_map['default'])
        
        # Вызываем базовую логику
        return await super().__call__(handler, event, data)
