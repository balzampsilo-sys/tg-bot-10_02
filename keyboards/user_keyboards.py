"""Клавиатуры для пользователей"""

import calendar
from datetime import datetime, timedelta
from typing import List

from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import (
    CALENDAR_MAX_MONTHS_AHEAD,
    DAY_NAMES,
    DAY_NAMES_SHORT,
    MONTH_NAMES,
    TIMEZONE,
    WORK_HOURS_END,
    WORK_HOURS_START,
)
from database.models import Service
from database.queries import Database
from database.repositories.service_repository import ServiceRepository
from utils.helpers import now_local

# Главное меню
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Записаться")],
        [KeyboardButton(text="📋 Мои записи"), KeyboardButton(text="ℹ️ О сервисе")],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


def create_services_keyboard(services: List[Service]) -> InlineKeyboardMarkup:
    """Клавиатура выбора услуги
    
    Args:
        services: Список активных услуг
        
    Returns:
        InlineKeyboardMarkup с кнопками выбора услуг
    """
    keyboard = []
    
    for service in services:
        # Форматируем кнопку: Название (длительность, цена)
        button_text = f"{service.name} ({service.duration_minutes}мин, {service.price})"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_service:{service.id}"
            )
        ])
    
    # Кнопка отмены
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="cancel_booking_flow"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def create_month_calendar(year: int, month: int) -> InlineKeyboardMarkup:
    """Календарь с навигацией по месяцам (с блокировкой прошедших дат)"""
    keyboard = []
    today = now_local()
    
    # Навигация
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    # Ограничение навигации: не позволяем уйти в прошлое
    can_go_prev = (
        prev_year > today.year or 
        (prev_year == today.year and prev_month >= today.month)
    )
    
    # Ограничение: максимум N месяцев вперёд
    max_year = today.year
    max_month = today.month + CALENDAR_MAX_MONTHS_AHEAD
    if max_month > 12:
        max_year += max_month // 12
        max_month = max_month % 12
        if max_month == 0:
            max_month = 12
            max_year -= 1
    
    can_go_next = (
        next_year < max_year or 
        (next_year == max_year and next_month <= max_month)
    )

    # Кнопки навигации
    prev_button = (
        InlineKeyboardButton(
            text="◀️", callback_data=f"cal:{prev_year}-{prev_month:02d}"
        )
        if can_go_prev
        else InlineKeyboardButton(text=" ", callback_data="ignore")
    )
    
    next_button = (
        InlineKeyboardButton(
            text="▶️", callback_data=f"cal:{next_year}-{next_month:02d}"
        )
        if can_go_next
        else InlineKeyboardButton(text=" ", callback_data="ignore")
    )

    keyboard.append(
        [
            prev_button,
            InlineKeyboardButton(
                text=f"{MONTH_NAMES[month-1]} {year}", callback_data="ignore"
            ),
            next_button,
        ]
    )

    # Дни недели
    keyboard.append(
        [
            InlineKeyboardButton(text=day, callback_data="ignore")
            for day in DAY_NAMES_SHORT
        ]
    )

    # Получаем все статусы одним запросом (ОПТИМИЗАЦИЯ!)
    month_statuses = await Database.get_month_statuses(year, month)

    # Дни месяца
    cal = calendar.monthcalendar(year, month)
    today_date = today.date()

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                date = datetime(year, month, day).date()
                date_str = date.strftime("%Y-%m-%d")

                # ✅ УЛУЧШЕНО: Прошедшие даты некликабельны
                if date < today_date:
                    row.append(InlineKeyboardButton(text="⚫", callback_data="ignore"))
                else:
                    # Используем закэшированный статус
                    status = month_statuses.get(date_str, "🟢")
                    
                    # ✅ УЛУЧШЕНО: Полностью занятые дни некликабельны
                    if status == "🔴":
                        row.append(
                            InlineKeyboardButton(
                                text=f"{day}🔴", callback_data="ignore"
                            )
                        )
                    else:
                        row.append(
                            InlineKeyboardButton(
                                text=f"{day}{status}", callback_data=f"day:{date_str}"
                            )
                        )
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_booking_flow")]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def create_time_slots(
    date_str: str, state: FSMContext = None
) -> tuple[str, InlineKeyboardMarkup]:
    """Слоты времени с валидацией и улучшенным UX"""
    keyboard = []
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    now = now_local()
    is_today = date_obj.date() == now.date()

    # ✅ УЛУЧШЕНО: Проверка что дата не в прошлом
    if date_obj.date() < now.date():
        # Возвращаем сообщение об ошибке
        error_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К календарю", callback_data="back_calendar")]
        ])
        return (
            "❌ ОШИБКА\n\n"
            "Эта дата уже прошла.\n"
            "Выберите дату из календаря.",
            error_kb
        )

    # ✅ КРИТИЧНО: Получаем service_id из состояния
    data = await state.get_data() if state else {}
    service_id = data.get("service_id")
    is_rescheduling = data.get("reschedule_booking_id") is not None

    # Получаем услугу для определения длительности
    service = None
    duration_minutes = 60  # Default fallback
    
    if service_id:
        service = await ServiceRepository.get_service_by_id(service_id)
        if service:
            duration_minutes = service.duration_minutes

    # Оптимизация: получаем все занятые слоты одним запросом
    occupied_slots = await Database.get_occupied_slots_for_day(date_str)

    free_count = 0
    # ✅ ИСПРАВЛЕНО: Учитываем длительность услуги
    duration_hours = (duration_minutes + 59) // 60  # Округление вверх
    total_possible_slots = max(0, WORK_HOURS_END - WORK_HOURS_START - duration_hours + 1)

    for hour in range(WORK_HOURS_START, WORK_HOURS_END - duration_hours + 1):
        time_str = f"{hour:02d}:00"
        
        # ИСПРАВЛЕНО: Используем TIMEZONE.localize() вместо .replace()
        slot_datetime_naive = datetime.combine(
            date_obj.date(), datetime.strptime(time_str, "%H:%M").time()
        )
        slot_datetime = TIMEZONE.localize(slot_datetime_naive)

        # ✅ ИСПРАВЛЕНО: Пропускаем прошедшие слоты сегодня
        if is_today and slot_datetime <= now:
            continue

        # ✅ КРИТИЧЕСКИ ВАЖНО: Проверяем ВСЕ нужные слоты
        slots_needed = []
        for i in range(duration_hours):
            needed_hour = hour + i
            if needed_hour < WORK_HOURS_END:
                slots_needed.append(f"{needed_hour:02d}:00")
            else:
                # Слот выходит за рабочие часы
                break
        
        # Все нужные слоты должны быть свободны
        is_free = all(slot not in occupied_slots for slot in slots_needed) and len(slots_needed) == duration_hours

        if is_free:
            free_count += 1

        button_text = time_str if is_free else f"❌ {time_str}"

        if not keyboard or len(keyboard[-1]) == 3:
            keyboard.append([])

        if is_free:
            callback_data = (
                f"reschedule_time:{date_str}:{time_str}"
                if is_rescheduling
                else f"time:{date_str}:{time_str}"
            )
        else:
            callback_data = "ignore"

        keyboard[-1].append(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )

    # ✅ УЛУЧШЕНО: Если нет свободных слотов
    if free_count == 0:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="😞 Все слоты заняты", callback_data="ignore"
                )
            ]
        ]
        reason = "прошли или заняты" if is_today else "заняты"
        text = (
            f"❌ ВСЕ СЛОТЫ {reason.upper()}\n\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} ({DAY_NAMES[date_obj.weekday()]})\n\n"
            "Попробуйте выбрать другую дату."
        )
    else:
        # Формируем текст
        day_name = DAY_NAMES[date_obj.weekday()]
        
        # ✅ НОВОЕ: Показываем информацию об услуге
        service_info = ""
        if service:
            service_info = (
                f"📝 Услуга: {service.name}\n"
                f"⏱ Длительность: {service.duration_minutes} мин\n"
                f"💰 Цена: {service.price}\n\n"
            )
        
        text = (
            f"{service_info}"
            "📍 ШАГ 3 из 4: Выберите время\n\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} ({day_name})\n"
            f"🟢 Свободно: {free_count}/{total_possible_slots} слотов\n"
        )

        if free_count <= 3:
            text += "⚠️ Мало мест — записывайтесь скорее!\n"

        text += "\n✅ = свободно | ❌ = занято"

    keyboard.append(
        [InlineKeyboardButton(text="🔙 К календарю", callback_data="back_calendar")]
    )

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_onboarding_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для онбординга"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎓 Как это работает?", callback_data="onboarding_tour"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚀 Записаться сразу", callback_data="skip_onboarding"
                )
            ],
        ]
    )


def create_confirmation_keyboard(date_str: str, time_str: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения записи"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить запись",
                    callback_data=f"confirm:{date_str}:{time_str}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Изменить дату", callback_data="back_calendar"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Другое время", callback_data=f"day:{date_str}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись", callback_data="cancel_booking_flow"
                )
            ],
        ]
    )


def create_cancel_confirmation_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения отмены"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, отменить", callback_data=f"cancel_confirm:{booking_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, оставить", callback_data="cancel_decline"
                )
            ],
        ]
    )
