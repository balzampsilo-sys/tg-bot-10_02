"""Handlers для настроек системы"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.repositories.audit_repository import AuditRepository
from database.repositories.settings_repository import SettingsRepository
from keyboards.admin_keyboards import ADMIN_MENU
from utils.helpers import is_admin
from utils.permissions import has_permission
from utils.states import AdminStates

router = Router()


@router.message(F.text == "⚙️ Настройки")
async def settings_menu(message: Message):
    """Главное меню настроек"""
    if not await is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    # Получаем текущие рабочие часы
    start_hour, end_hour = await SettingsRepository.get_work_hours()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ Рабочие часы", callback_data="settings_work_hours"
                )
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="settings_close")],
        ]
    )

    await message.answer(
        f"⚙️ НАСТРОЙКИ СИСТЕМЫ\n\n"
        f"⏰ Рабочие часы: {start_hour:02d}:00 - {end_hour:02d}:00\n\n"
        "Выберите настройку:",
        reply_markup=kb,
    )


@router.callback_query(F.data == "settings_work_hours")
async def work_hours_menu(callback: CallbackQuery):
    """Меню настройки рабочих часов"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    # Проверяем разрешения
    if not await has_permission(callback.from_user.id, "manage_settings"):
        await callback.answer(
            "❌ Недостаточно прав\n\nТолько для Super Admin", show_alert=True
        )
        return

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔽 Изменить начало", callback_data="settings_change_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔼 Изменить конец", callback_data="settings_change_end"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back")],
        ]
    )

    await callback.message.edit_text(
        f"⏰ РАБОЧИЕ ЧАСЫ\n\n"
        f"🕒 Текущие: {start_hour:02d}:00 - {end_hour:02d}:00\n\n"
        f"ℹ️ Эти часы будут доступны для записи клиентам\n"
        f"⚠️ Изменения применяются немедленно\n\n"
        "Выберите действие:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "settings_change_start")
async def change_start_hour(callback: CallbackQuery, state: FSMContext):
    """Начало изменения начала рабочего дня"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_settings"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    await state.set_state(AdminStates.awaiting_work_hours_start)

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    await callback.message.edit_text(
        f"🔽 ИЗМЕНЕНИЕ НАЧАЛА РАБОЧЕГО ДНЯ\n\n"
        f"🕒 Текущее начало: {start_hour:02d}:00\n"
        f"🕒 Конец дня: {end_hour:02d}:00\n\n"
        "Введите новое начало рабочего дня (час 0-23):\n"
        "Пример: 8 (для 8:00)\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_work_hours_start)
async def process_start_hour(message: Message, state: FSMContext):
    """Обработка нового начала"""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Изменение отменено", reply_markup=ADMIN_MENU)
        return

    try:
        new_start = int(message.text.strip())
        if not (0 <= new_start <= 23):
            raise ValueError()
    except ValueError:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите число от 0 до 23\n"
            "Пример: 9"
        )
        return

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    if new_start >= end_hour:
        await message.answer(
            f"❌ Начало должно быть раньше конца\n\n"
            f"Конец дня: {end_hour:02d}:00\n"
            f"Введите час меньше {end_hour}"
        )
        return

    # Обновляем
    success = await SettingsRepository.update_work_hours(new_start, end_hour)

    await state.clear()

    if success:
        # Audit log
        await AuditRepository.log_action(
            admin_id=message.from_user.id,
            action="update_work_hours_start",
            details=f"from={start_hour} to={new_start}",
        )

        await message.answer(
            f"✅ НАЧАЛО РАБОЧЕГО ДНЯ ИЗМЕНЕНО!\n\n"
            f"🕒 Было: {start_hour:02d}:00\n"
            f"✅ Стало: {new_start:02d}:00\n\n"
            f"🕒 Рабочие часы: {new_start:02d}:00 - {end_hour:02d}:00\n\n"
            "ℹ️ Изменения применены немедленно",
            reply_markup=ADMIN_MENU,
        )
        logging.info(
            f"Admin {message.from_user.id} changed work hours start: {start_hour} -> {new_start}"
        )
    else:
        await message.answer("❌ Ошибка при сохранении", reply_markup=ADMIN_MENU)


@router.callback_query(F.data == "settings_change_end")
async def change_end_hour(callback: CallbackQuery, state: FSMContext):
    """Начало изменения конца рабочего дня"""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_settings"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    await state.set_state(AdminStates.awaiting_work_hours_end)

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    await callback.message.edit_text(
        f"🔼 ИЗМЕНЕНИЕ КОНЦА РАБОЧЕГО ДНЯ\n\n"
        f"🕒 Начало дня: {start_hour:02d}:00\n"
        f"🕒 Текущий конец: {end_hour:02d}:00\n\n"
        "Введите новый конец рабочего дня (час 1-24):\n"
        "Пример: 19 (для 19:00)\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_work_hours_end)
async def process_end_hour(message: Message, state: FSMContext):
    """Обработка нового конца"""
    if not await is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Изменение отменено", reply_markup=ADMIN_MENU)
        return

    try:
        new_end = int(message.text.strip())
        if not (1 <= new_end <= 24):
            raise ValueError()
    except ValueError:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введите число от 1 до 24\n"
            "Пример: 19"
        )
        return

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    if new_end <= start_hour:
        await message.answer(
            f"❌ Конец должен быть позже начала\n\n"
            f"Начало дня: {start_hour:02d}:00\n"
            f"Введите час больше {start_hour}"
        )
        return

    # Обновляем
    success = await SettingsRepository.update_work_hours(start_hour, new_end)

    await state.clear()

    if success:
        # Audit log
        await AuditRepository.log_action(
            admin_id=message.from_user.id,
            action="update_work_hours_end",
            details=f"from={end_hour} to={new_end}",
        )

        await message.answer(
            f"✅ КОНЕЦ РАБОЧЕГО ДНЯ ИЗМЕНЕН!\n\n"
            f"🕒 Было: {end_hour:02d}:00\n"
            f"✅ Стало: {new_end:02d}:00\n\n"
            f"🕒 Рабочие часы: {start_hour:02d}:00 - {new_end:02d}:00\n\n"
            "ℹ️ Изменения применены немедленно",
            reply_markup=ADMIN_MENU,
        )
        logging.info(
            f"Admin {message.from_user.id} changed work hours end: {end_hour} -> {new_end}"
        )
    else:
        await message.answer("❌ Ошибка при сохранении", reply_markup=ADMIN_MENU)


@router.callback_query(F.data == "settings_back")
async def settings_back(callback: CallbackQuery):
    """Возврат в главное меню настроек"""
    await callback.message.delete()

    start_hour, end_hour = await SettingsRepository.get_work_hours()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ Рабочие часы", callback_data="settings_work_hours"
                )
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="settings_close")],
        ]
    )

    await callback.message.answer(
        f"⚙️ НАСТРОЙКИ СИСТЕМЫ\n\n"
        f"⏰ Рабочие часы: {start_hour:02d}:00 - {end_hour:02d}:00\n\n"
        "Выберите настройку:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "settings_close")
async def settings_close(callback: CallbackQuery):
    """Закрытие меню настроек"""
    await callback.message.delete()
    await callback.answer("Закрыто")
