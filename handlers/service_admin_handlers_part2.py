"""Обработчики управления услугами - Часть 2"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.queries import Database
from database.repositories.service_repository import ServiceRepository
from keyboards.admin_keyboards import ADMIN_MENU
from utils.helpers import is_admin
from utils.states import AdminStates

router = Router()


# === РЕДАКТИРОВАНИЕ УСЛУГ ===

@router.callback_query(F.data == "service_list_edit")
async def service_list_for_edit(callback: CallbackQuery):
    """Список услуг для редактирования"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    services = await ServiceRepository.get_all_services()

    if not services:
        await callback.answer("❌ Нет услуг для редактирования", show_alert=True)
        return

    keyboard = []
    for service in services:
        status = "✅" if service.is_active else "🚫"
        text = f"{status} {service.name} ({service.duration_minutes}м)"
        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"service_edit:{service.id}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_services")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "✏️ Выберите услугу для редактирования:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_edit:"))
async def service_edit_menu(callback: CallbackQuery):
    """Меню редактирования услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        service_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    service = await ServiceRepository.get_service_by_id(service_id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    status = "✅ Активна" if service.is_active else "🚫 Неактивна"
    toggle_text = "🚫 Отключить" if service.is_active else "✅ Включить"

    text = (
        f"✏️ РЕДАКТИРОВАНИЕ УСЛУГИ\n\n"
        f"📝 Название: {service.name}\n"
        f"💬 Описание: {service.description or 'не указано'}\n"
        f"⏱️ Длительность: {service.duration_minutes} мин\n"
        f"💰 Цена: {service.price}\n"
        f"🎨 Цвет: {service.color or '#4A90E2'}\n"
        f"📊 Порядок: {service.display_order}\n"
        f"📦 Статус: {status}\n\n"
        "Выберите действие:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                text="✏️ Изменить название",
                callback_data=f"service_field:{service_id}:name"
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Изменить описание",
                callback_data=f"service_field:{service_id}:description"
            )
        ],
        [
            InlineKeyboardButton(
                text="⏱️ Изменить длительность",
                callback_data=f"service_field:{service_id}:duration"
            )
        ],
        [
            InlineKeyboardButton(
                text="💰 Изменить цену",
                callback_data=f"service_field:{service_id}:price"
            )
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=f"service_toggle:{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🗑️ Удалить услугу",
                callback_data=f"service_delete_confirm:{service_id}"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="service_list_edit")
        ],
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("service_field:"))
async def service_edit_field_start(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования поля"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        _, service_id, field = callback.data.split(":", 2)
        service_id = int(service_id)
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    service = await ServiceRepository.get_service_by_id(service_id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    await state.update_data(edit_service_id=service_id, edit_field=field)
    await state.set_state(AdminStates.service_edit_value)

    field_names = {
        "name": "название",
        "description": "описание",
        "duration": "длительность (в минутах)",
        "price": "цену",
    }

    current_values = {
        "name": service.name,
        "description": service.description or 'не указано',
        "duration": service.duration_minutes,
        "price": service.price,
    }

    await callback.message.edit_text(
        f"✏️ Изменение поля: {field_names.get(field, field)}\n\n"
        f"Текущее значение: {current_values.get(field)}\n\n"
        f"Введите новое значение для {field_names.get(field, field)}:\n\n"
        "Для отмены: /cancel"
    )
    await callback.answer()


@router.message(AdminStates.service_edit_value)
async def service_edit_field_save(message: Message, state: FSMContext):
    """Сохранение измененного поля"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Редактирование отменено", reply_markup=ADMIN_MENU)
        return

    data = await state.get_data()
    service_id = data.get("edit_service_id")
    field = data.get("edit_field")

    # Валидация в зависимости от поля
    if field == "duration":
        try:
            value = int(message.text)
            if value < 15 or value > 480:
                await message.answer(
                    "❌ Длительность должна быть от 15 до 480 минут\n\n"
                    "Введите корректное значение:"
                )
                return
        except ValueError:
            await message.answer(
                "❌ Неверный формат. Введите число:"
            )
            return
    else:
        value = message.text

    # Обновляем поле
    success = await ServiceRepository.update_service_field(
        service_id=service_id,
        field=field,
        value=value
    )

    await state.clear()

    if success:
        await message.answer(
            f"✅ Поле успешно обновлено!\n\n"
            f"Новое значение: {value}",
            reply_markup=ADMIN_MENU
        )
        logging.info(f"Admin {message.from_user.id} updated service {service_id}, field {field}")
    else:
        await message.answer(
            "❌ Ошибка при обновлении",
            reply_markup=ADMIN_MENU
        )


# === ВКЛ/ОТКЛ УСЛУГИ ===

@router.callback_query(F.data.startswith("service_toggle:"))
async def service_toggle_active(callback: CallbackQuery):
    """Переключение активности услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        service_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    service = await ServiceRepository.get_service_by_id(service_id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    new_status = not service.is_active
    success = await ServiceRepository.update_service_field(
        service_id=service_id,
        field="is_active",
        value=1 if new_status else 0
    )

    if success:
        status_text = "Включена" if new_status else "Отключена"
        await callback.answer(f"✅ Услуга {status_text}")
        logging.info(f"Admin {callback.from_user.id} toggled service {service_id} to {new_status}")
        
        # Обновляем меню
        await service_edit_menu(callback)
    else:
        await callback.answer("❌ Ошибка при обновлении", show_alert=True)


# === УДАЛЕНИЕ УСЛУГИ ===

@router.callback_query(F.data.startswith("service_delete_confirm:"))
async def service_delete_confirm(callback: CallbackQuery):
    """Подтверждение удаления услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        service_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    service = await ServiceRepository.get_service_by_id(service_id)
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return

    # Проверяем наличие записей на эту услугу
    import aiosqlite
    from config import DATABASE_PATH
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM bookings WHERE service_id = ?",
            (service_id,)
        ) as cursor:
            (count,) = await cursor.fetchone()

    warning = ""
    if count > 0:
        warning = f"\n\n⚠️ ВНИМАНИЕ: На эту услугу есть {count} записей!"

    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Да, удалить",
                callback_data=f"service_delete_yes:{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"service_edit:{service_id}"
            )
        ],
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"🗑️ УДАЛЕНИЕ УСЛУГИ\n\n"
        f"📝 {service.name}\n"
        f"⏱️ {service.duration_minutes} мин\n"
        f"💰 {service.price}\n"
        f"{warning}\n\n"
        "Вы уверены?",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_delete_yes:"))
async def service_delete_execute(callback: CallbackQuery):
    """Выполнение удаления услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        service_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    success = await ServiceRepository.delete_service(service_id)

    if success:
        await callback.message.edit_text(
            "✅ УСЛУГА УДАЛЕНА\n\n"
            "Услуга больше не доступна для записи."
        )
        await callback.answer("✅ Удалено")
        logging.info(f"Admin {callback.from_user.id} deleted service {service_id}")
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


# === ИЗМЕНЕНИЕ ПОРЯДКА ===

@router.callback_query(F.data == "service_reorder")
async def service_reorder_menu(callback: CallbackQuery):
    """Меню изменения порядка услуг"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    services = await ServiceRepository.get_all_services()

    if not services:
        await callback.answer("❌ Нет услуг", show_alert=True)
        return

    text = "🔄 ПОРЯДОК УСЛУГ\n\n"
    text += "Текущий порядок:\n\n"

    keyboard = []
    for i, service in enumerate(services, 1):
        text += f"{i}. {service.name}\n"
        
        buttons_row = []
        
        # Кнопка вверх (если не первый)
        if i > 1:
            buttons_row.append(
                InlineKeyboardButton(
                    text="⬆️",
                    callback_data=f"service_move:{service.id}:up"
                )
            )
        
        buttons_row.append(
            InlineKeyboardButton(
                text=f"{i}. {service.name[:20]}",
                callback_data="service_reorder_noop"
            )
        )
        
        # Кнопка вниз (если не последний)
        if i < len(services):
            buttons_row.append(
                InlineKeyboardButton(
                    text="⬇️",
                    callback_data=f"service_move:{service.id}:down"
                )
            )
        
        keyboard.append(buttons_row)

    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_services")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("service_move:"))
async def service_move_execute(callback: CallbackQuery):
    """Перемещение услуги вверх/вниз"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        _, service_id, direction = callback.data.split(":", 2)
        service_id = int(service_id)
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    success = await ServiceRepository.reorder_service(service_id, direction)

    if success:
        await callback.answer("✅ Порядок изменен")
        # Обновляем меню
        await service_reorder_menu(callback)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "service_reorder_noop")
async def service_reorder_noop(callback: CallbackQuery):
    """Пустой колбэк для кнопок названий"""
    await callback.answer()
