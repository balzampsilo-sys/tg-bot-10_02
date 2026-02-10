"""Обработчики управления услугами для админ-панели"""

import logging
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.repositories.service_repository import ServiceRepository
from keyboards.admin_keyboards import ADMIN_MENU
from utils.helpers import is_admin
from utils.states import AdminStates

router = Router()

# === ГЛАВНОЕ МЕНЮ УСЛУГ ===

@router.message(F.text == "⚙️ Управление услугами")
async def service_management_menu(message: Message, state: FSMContext):
    """Главное меню управления услугами"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    await state.clear()
    await show_services_list(message)


async def show_services_list(message: Message, edit: bool = False):
    """Отобразить список услуг"""
    services = await ServiceRepository.get_all_services(active_only=False)
    
    text = "⚙️ УПРАВЛЕНИЕ УСЛУГАМИ\n\n"
    
    if not services:
        text += "💭 Услуг пока нет"
    else:
        text += f"📋 Всего услуг: {len(services)}\n\n"
        
        for service in services:
            status = "✅" if service.is_active else "❌"
            color_emoji = service.color or "⚪"
            text += (
                f"{color_emoji} {status} {service.name}\n"
                f"   🕒 {service.duration_minutes} мин | 💰 {service.price}\n"
            )
            if service.description:
                desc = service.description[:40] + "..." if len(service.description) > 40 else service.description
                text += f"   💬 {desc}\n"
            text += "\n"
    
    # Кнопки управления
    keyboard = []
    
    if services:
        for service in services:
            status_icon = "✅" if service.is_active else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} {service.name[:25]}",
                    callback_data=f"service_view:{service.id}"
                )
            ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="➕ Создать услугу",
            callback_data="service_create"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 Вернуться",
            callback_data="service_back"
        )
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    if edit and isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


# === ПРОСМОТР УСЛУГИ ===

@router.callback_query(F.data.startswith("service_view:"))
async def service_view(callback: CallbackQuery):
    """Просмотр деталей услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    service_id = int(callback.data.split(":")[1])
    service = await ServiceRepository.get_service_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return
    
    status = "✅ Активна" if service.is_active else "❌ Неактивна"
    color_emoji = service.color or "⚪"
    
    text = (
        f"{color_emoji} УСЛУГА\n\n"
        f"🏷 Название: {service.name}\n"
        f"💬 Описание: {service.description or 'нет'}\n"
        f"🕒 Длительность: {service.duration_minutes} мин\n"
        f"💰 Стоимость: {service.price}\n"
        f"🎨 Цвет: {service.color or 'по умолчанию'}\n"
        f"📊 Порядок: {service.display_order}\n"
        f"🟢 Статус: {status}\n"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="✏️ Редактировать",
                callback_data=f"service_edit:{service_id}"
            ),
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=f"service_delete:{service_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="✅ Активировать" if not service.is_active else "❌ Деактивировать",
                callback_data=f"service_toggle:{service_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬆️ Вверх",
                callback_data=f"service_move_up:{service_id}"
            ),
            InlineKeyboardButton(
                text="⬇️ Вниз",
                callback_data=f"service_move_down:{service_id}"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔙 К списку",
                callback_data="service_list"
            )
        ],
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# === СОЗДАНИЕ УСЛУГИ ===

@router.callback_query(F.data == "service_create")
async def service_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания услуги"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.service_awaiting_name)
    
    await callback.message.edit_text(
        "➕ СОЗДАНИЕ УСЛУГИ\n\n"
        "Шаг 1/5: Введите название услуги\n\n"
        "Пример: Консультация, Тренировка, Массаж\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.service_awaiting_name)
async def service_create_name(message: Message, state: FSMContext):
    """Ввод названия"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=ADMIN_MENU)
        return
    
    name = message.text.strip()
    
    if len(name) < 3 or len(name) > 100:
        await message.answer(
            "❌ Название должно быть от 3 до 100 символов\n\n"
            "Попробуйте ещё раз:"
        )
        return
    
    await state.update_data(name=name)
    await state.set_state(AdminStates.service_awaiting_description)
    
    await message.answer(
        f"✅ Название: {name}\n\n"
        "Шаг 2/5: Введите описание услуги\n\n"
        "Пример: Индивидуальная консультация по здоровью\n\n"
        "Или отправьте '-' чтобы пропустить"
    )


@router.message(AdminStates.service_awaiting_description)
async def service_create_description(message: Message, state: FSMContext):
    """Ввод описания"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=ADMIN_MENU)
        return
    
    description = None if message.text == "-" else message.text.strip()
    
    if description and len(description) > 500:
        await message.answer(
            "❌ Описание слишком длинное (макс. 500 символов)\n\n"
            "Попробуйте ещё раз:"
        )
        return
    
    await state.update_data(description=description)
    await state.set_state(AdminStates.service_awaiting_duration)
    
    await message.answer(
        f"✅ Описание: {description or 'нет'}\n\n"
        "Шаг 3/5: Введите длительность в минутах\n\n"
        "Пример: 60, 90, 120\n\n"
        "Мин. 15 мин, макс. 480 мин (8 часов)"
    )


@router.message(AdminStates.service_awaiting_duration)
async def service_create_duration(message: Message, state: FSMContext):
    """Ввод длительности"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=ADMIN_MENU)
        return
    
    try:
        duration = int(message.text.strip())
        if not (15 <= duration <= 480):
            raise ValueError()
    except ValueError:
        await message.answer(
            "❌ Неверное значение\n\n"
            "Введите число от 15 до 480:"
        )
        return
    
    await state.update_data(duration_minutes=duration)
    await state.set_state(AdminStates.service_awaiting_price)
    
    await message.answer(
        f"✅ Длительность: {duration} мин\n\n"
        "Шаг 4/5: Введите стоимость\n\n"
        "Пример: 3000 ₽, 5500 ₽, Бесплатно\n\n"
        "Макс. 100 символов"
    )


@router.message(AdminStates.service_awaiting_price)
async def service_create_price(message: Message, state: FSMContext):
    """Ввод стоимости"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=ADMIN_MENU)
        return
    
    price = message.text.strip()
    
    if len(price) > 100:
        await message.answer(
            "❌ Стоимость слишком длинная (макс. 100 символов)\n\n"
            "Попробуйте ещё раз:"
        )
        return
    
    await state.update_data(price=price)
    await state.set_state(AdminStates.service_awaiting_color)
    
    await message.answer(
        f"✅ Стоимость: {price}\n\n"
        "Шаг 5/5: Выберите цвет emoji\n\n"
        "🔴 🟠 🟡 🔵 🟣 🟤 ⚪ ⚫\n\n"
        "Отправьте emoji или '-' чтобы пропустить"
    )


@router.message(AdminStates.service_awaiting_color)
async def service_create_color(message: Message, state: FSMContext):
    """Завершение создания"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Создание отменено", reply_markup=ADMIN_MENU)
        return
    
    color = None if message.text == "-" else message.text.strip()[:10]
    
    data = await state.get_data()
    
    # Создаем услугу
    service_id = await ServiceRepository.create_service(
        name=data["name"],
        description=data.get("description"),
        duration_minutes=data["duration_minutes"],
        price=data["price"],
        color=color,
        is_active=True
    )
    
    await state.clear()
    
    if service_id:
        await message.answer(
            f"✅ Услуга создана!\n\n"
            f"🏷 {data['name']}\n"
            f"🕒 {data['duration_minutes']} мин\n"
            f"💰 {data['price']}",
            reply_markup=ADMIN_MENU
        )
        logging.info(f"Admin {message.from_user.id} created service: {data['name']}")
    else:
        await message.answer(
            "❌ Ошибка создания услуги",
            reply_markup=ADMIN_MENU
        )


# === РЕДАКТИРОВАНИЕ / УДАЛЕНИЕ ===

@router.callback_query(F.data.startswith("service_edit:"))
async def service_edit_menu(callback: CallbackQuery):
    """Меню редактирования"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    service_id = int(callback.data.split(":")[1])
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="🏷 Название",
                callback_data=f"service_edit_field:{service_id}:name"
            ),
            InlineKeyboardButton(
                text="💬 Описание",
                callback_data=f"service_edit_field:{service_id}:description"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🕒 Длительность",
                callback_data=f"service_edit_field:{service_id}:duration"
            ),
            InlineKeyboardButton(
                text="💰 Стоимость",
                callback_data=f"service_edit_field:{service_id}:price"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🎨 Цвет",
                callback_data=f"service_edit_field:{service_id}:color"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=f"service_view:{service_id}"
            )
        ],
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "✏️ РЕДАКТИРОВАНИЕ\n\n"
        "Выберите поле для редактирования:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_delete:"))
async def service_delete_confirm(callback: CallbackQuery):
    """Подтверждение удаления"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    service_id = int(callback.data.split(":")[1])
    service = await ServiceRepository.get_service_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return
    
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
                callback_data=f"service_view:{service_id}"
            )
        ],
    ]
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"⚠️ ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ\n\n"
        f"Вы уверены, что хотите удалить услугу?\n\n"
        f"🏷 {service.name}\n"
        f"🕒 {service.duration_minutes} мин\n"
        f"💰 {service.price}\n\n"
        "⚠️ Это действие нельзя отменить!",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_delete_yes:"))
async def service_delete_execute(callback: CallbackQuery):
    """Выполнение удаления"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    service_id = int(callback.data.split(":")[1])
    success = await ServiceRepository.delete_service(service_id)
    
    if success:
        await callback.answer("✅ Услуга удалена")
        logging.info(f"Admin {callback.from_user.id} deleted service {service_id}")
        await show_services_list(callback, edit=True)
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data.startswith("service_toggle:"))
async def service_toggle_active(callback: CallbackQuery):
    """Переключение активности"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    service_id = int(callback.data.split(":")[1])
    service = await ServiceRepository.get_service_by_id(service_id)
    
    if not service:
        await callback.answer("❌ Услуга не найдена", show_alert=True)
        return
    
    new_status = not service.is_active
    success = await ServiceRepository.update_service(
        service_id=service_id,
        is_active=new_status
    )
    
    if success:
        status_text = "активирована" if new_status else "деактивирована"
        await callback.answer(f"✅ Услуга {status_text}")
        # Обновляем отображение
        await service_view(callback)
    else:
        await callback.answer("❌ Ошибка", show_alert=True)


# === НАВИГАЦИЯ ===

@router.callback_query(F.data == "service_list")
async def service_list_callback(callback: CallbackQuery):
    """Возврат к списку"""
    await show_services_list(callback, edit=True)


@router.callback_query(F.data == "service_back")
async def service_back(callback: CallbackQuery):
    """Выход из управления услугами"""
    await callback.message.delete()
    await callback.message.answer(
        "🔐 Админ-панель",
        reply_markup=ADMIN_MENU
    )
    await callback.answer()
