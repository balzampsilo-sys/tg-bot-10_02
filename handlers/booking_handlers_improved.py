"""
Улучшенные обработчики бронирования с:
- Полной валидацией callback_data (КРИТИЧНО)
- Отображением услуг во всех интерфейсах (ВЫСОКИЙ ПРИОРИТЕТ)
- Защитой от устаревших кнопок

Используйте этот файл вместо booking_handlers.py после тестирования.
"""

import logging
from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import (
    CANCELLATION_HOURS,
    DAY_NAMES,
    MAX_BOOKINGS_PER_USER,
)
from database.queries import Database
from database.repositories.service_repository import ServiceRepository
from keyboards.user_keyboards import MAIN_MENU
from services.booking_service import BookingService
from services.notification_service import NotificationService
from utils.callback_validator import (
    validate_booking_action,
    create_safe_callback,
    CallbackValidator
)
from utils.helpers import now_local

router = Router()


# === УТИЛИТЫ ===

async def get_service_with_validation(service_id: int) -> Optional[object]:
    """
    Получить услугу с проверкой доступности.
    
    Returns:
        Service объект или None если недоступна
    """
    service = await ServiceRepository.get_service_by_id(service_id)
    
    if not service or not service.is_active:
        return None
    
    return service


async def format_booking_info(booking_id: int, user_id: int) -> Optional[dict]:
    """
    Получить полную информацию о бронировании с услугой.
    
    Returns:
        dict с полной информацией или None
    """
    booking = await Database.get_booking_by_id(booking_id, user_id)
    
    if not booking:
        return None
    
    date_str, time_str, username = booking
    service_id = await Database.get_booking_service_id(booking_id)
    
    service = None
    if service_id:
        service = await get_service_with_validation(service_id)
    
    return {
        'booking_id': booking_id,
        'date': date_str,
        'time': time_str,
        'username': username,
        'service_id': service_id,
        'service': service
    }


# === ОБРАБОТЧИКИ ===

@router.message(F.text == "📋 Мои записи")
async def my_bookings_improved(message: Message):
    """
    Список записей пользователя с услугами.
    
    ВЫСОКИЙ ПРИОРИТЕТ: Отображение услуг.
    """
    user_id = message.from_user.id
    
    # Получаем записи с услугами
    bookings = await Database.get_user_bookings(user_id)
    
    if not bookings:
        await message.answer(
            "💭 У вас нет активных записей\n\n"
            "📅 Чтобы записаться, нажмите '📅 Записаться'",
            reply_markup=MAIN_MENU
        )
        return
    
    text = "📋 ВАШИ АКТИВНЫЕ ЗАПИСИ:\n\n"
    keyboard = []
    now = now_local()
    
    for i, booking_row in enumerate(bookings, 1):
        # Новый формат: (booking_id, date, time, service_name)
        if len(booking_row) == 4:
            booking_id, date_str, time_str, service_name = booking_row
        else:
            # Обратная совместимость
            booking_id, date_str, time_str = booking_row[:3]
            service_name = "Основная услуга"
        
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        booking_dt = datetime.strptime(
            f"{date_str} {time_str}", 
            "%Y-%m-%d %H:%M"
        )
        
        days_left = (booking_dt.date() - now.date()).days
        day_name = DAY_NAMES[date_obj.weekday()]
        
        # ✅ ВЫСОКИЙ ПРИОРИТЕТ: Отображение услуги
        text += f"{i}. 📍 {service_name}\n"
        text += f"   📅 {date_obj.strftime('%d.%m')} ({day_name}) 🕒 {time_str}"
        
        if days_left == 0:
            text += " — сегодня!\n"
        elif days_left == 1:
            text += " — завтра\n"
        else:
            text += f" — через {days_left} дн.\n"
        
        text += "\n"
        
        # ✅ КРИТИЧНО: Используем безопасные callback
        keyboard.append([
            InlineKeyboardButton(
                text=f"❌ Отменить #{i}",
                callback_data=create_safe_callback('cancel', booking_id)
            ),
            InlineKeyboardButton(
                text=f"🔄 Перенести #{i}",
                callback_data=create_safe_callback('reschedule', booking_id)
            ),
        ])
    
    text += f"\nℹ️ Максимум записей: {MAX_BOOKINGS_PER_USER}\n"
    text += f"⚠️ Отмена возможна за {CANCELLATION_HOURS}ч до встречи"
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("v2:cancel:"))
async def cancel_booking_improved(callback: CallbackQuery, state: FSMContext):
    """
    Отмена записи с полной валидацией.
    
    КРИТИЧНО: Валидация callback_data и проверка актуальности.
    """
    await state.clear()
    
    # ✅ КРИТИЧНО: Валидация
    valid, data, error = await validate_booking_action(
        callback.data,
        callback.from_user.id
    )
    
    if not valid:
        await callback.answer(error, show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    
    booking_id = data['booking_id']
    date_str = data['date']
    time_str = data['time']
    
    # Получаем полную информацию с услугой
    booking_info = await format_booking_info(booking_id, callback.from_user.id)
    
    if not booking_info:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    service = booking_info.get('service')
    service_name = service.name if service else "Основная услуга"
    
    # Создаем клавиатуру подтверждения
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=create_safe_callback('cancel_confirm', booking_id)
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Нет, оставить",
                callback_data="v2:cancel_decline"
            )
        ]
    ])
    
    # ✅ ВЫСОКИЙ ПРИОРИТЕТ: Отображаем услугу
    await callback.message.edit_text(
        "⚠️ ПОДТВЕРЖДЕНИЕ ОТМЕНЫ\n\n"
        f"📍 Услуга: {service_name}\n"
        f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {time_str}\n\n"
        "Точно отменить эту запись?",
        reply_markup=confirm_kb
    )


@router.callback_query(F.data.startswith("v2:cancel_confirm:"))
async def cancel_confirmed_improved(
    callback: CallbackQuery,
    booking_service: BookingService,
    notification_service: NotificationService,
):
    """
    Подтвержденная отмена с валидацией.
    """
    # ✅ КРИТИЧНО: Валидация
    valid, data, error = await validate_booking_action(
        callback.data,
        callback.from_user.id
    )
    
    if not valid:
        await callback.answer(error, show_alert=True)
        return
    
    booking_id = data['booking_id']
    date_str = data['date']
    time_str = data['time']
    
    # Получаем информацию об услуге
    booking_info = await format_booking_info(booking_id, callback.from_user.id)
    service_name = "Основная услуга"
    
    if booking_info and booking_info.get('service'):
        service_name = booking_info['service'].name
    
    # Отменяем
    success, _ = await booking_service.cancel_booking(
        date_str, time_str, callback.from_user.id
    )
    
    if success:
        await callback.message.edit_text(
            "✅ ЗАПИСЬ ОТМЕНЕНА\n\n"
            f"📍 Услуга: {service_name}\n"
            f"📅 Дата: {date_str}\n"
            f"🕒 Время: {time_str}\n\n"
            "📋 Вы можете записаться снова в любое время"
        )
        await callback.answer("✅ Отменено")
        
        try:
            await notification_service.notify_admin_cancellation(
                date_str, time_str, callback.from_user.id
            )
        except Exception as e:
            logging.error(f"Failed to notify admin: {e}")
    else:
        await callback.answer("❌ Ошибка отмены", show_alert=True)


@router.callback_query(F.data == "v2:cancel_decline")
async def cancel_decline_improved(callback: CallbackQuery):
    """Отклонение отмены"""
    await callback.message.edit_text(
        "👍 ЗАПИСЬ СОХРАНЕНА\n\n"
        "📋 Вы можете посмотреть её в 'Мои записи'"
    )
    await callback.answer("Запись сохранена")


# === CATCH-ALL ОБРАБОТЧИК ===

@router.callback_query()
async def catch_outdated_callbacks(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик для всех необработанных callback.
    
    КРИТИЧНО: Защита от устаревших кнопок.
    """
    # Игнорируем ignore кнопки
    if callback.data == "ignore":
        await callback.answer()
        return
    
    logging.warning(
        f"Unhandled callback: {callback.data} from user {callback.from_user.id}"
    )
    
    # Очищаем state
    await state.clear()
    
    # Удаляем клавиатуру
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    await callback.answer(
        "⚠️ Устаревшая кнопка\n"
        "Используйте меню для нового действия",
        show_alert=True
    )
    
    # Показываем главное меню
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=MAIN_MENU
    )
