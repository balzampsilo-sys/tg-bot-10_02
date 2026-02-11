"""Универсальный редактор для различных полей в БД

Priority 4 (Низкий): Универсальный редактор полей
"""

import logging
from typing import Dict, List, Optional

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup

import aiosqlite

from config import DATABASE_PATH
from keyboards.admin_keyboards import ADMIN_MENU
from utils.helpers import is_admin_async  # ✅ FIX: Используем async версию


router = Router()


class FieldEditStates(StatesGroup):
    """Состояния для редактирования полей"""
    selecting_field_type = State()
    selecting_record = State()
    entering_new_value = State()


# Конфигурация редактируемых полей
EDITABLE_FIELDS_CONFIG = {
    "services": {
        "table": "services",
        "id_field": "id",
        "fields": {
            "name": {"display": "Название", "type": "text", "max_length": 100},
            "description": {"display": "Описание", "type": "text", "max_length": 500},
            "duration_minutes": {"display": "Длительность (мин)", "type": "int", "min": 15, "max": 480},
            "price": {"display": "Цена", "type": "text", "max_length": 50},
        },
        "display_name": "Услуги",
        "list_format": "{name} ({duration_minutes}м, {price})"
    },
    "blocked_slots": {
        "table": "blocked_slots",
        "id_field": "id",
        "fields": {
            "reason": {"display": "Причина блокировки", "type": "text", "max_length": 200},
        },
        "display_name": "Причины блокировок",
        "list_format": "{date} {time}: {reason}"
    },
    "admins": {
        "table": "admins",
        "id_field": "user_id",
        "fields": {
            "username": {"display": "Username", "type": "text", "max_length": 50},
        },
        "display_name": "Администраторы",
        "list_format": "@{username} (ID: {user_id})"
    }
}


@router.message(F.text == "✏️ Редактор полей")
async def field_editor_menu(message: Message, state: FSMContext):
    """Главное меню универсального редактора"""
    if not await is_admin_async(message.from_user.id):  # ✅ FIX: async проверка
        await message.answer("❌ Нет доступа")
        return
    
    await state.clear()
    
    keyboard = []
    for key, config in EDITABLE_FIELDS_CONFIG.items():
        keyboard.append([
            InlineKeyboardButton(
                text=f"✏️ {config['display_name']}",
                callback_data=f"editor_select_type:{key}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data="editor_close")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        "✏️ УНИВЕРСАЛЬНЫЙ РЕДАКТОР ПОЛЕЙ\n\n"
        "Выберите тип данных для редактирования:\n\n"
        "⚠️ Изменения применяются немедленно!",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("editor_select_type:"))
async def select_field_type(callback: CallbackQuery, state: FSMContext):
    """Выбор типа полей для редактирования"""
    if not await is_admin_async(callback.from_user.id):  # ✅ FIX
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    field_type = callback.data.split(":")[1]
    config = EDITABLE_FIELDS_CONFIG.get(field_type)
    
    if not config:
        await callback.answer("❌ Неизвестный тип", show_alert=True)
        return
    
    await state.update_data(field_type=field_type)
    
    # Получаем список записей
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Получаем все поля для отображения
            all_fields = [config['id_field']] + list(config['fields'].keys())
            query = f"SELECT {', '.join(all_fields)} FROM {config['table']} LIMIT 50"
            
            async with db.execute(query) as cursor:
                records = await cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description]
    except Exception as e:
        logging.error(f"Error fetching records: {e}")
        await callback.answer("❌ Ошибка БД", show_alert=True)
        return
    
    if not records:
        await callback.answer(
            f"💭 Нет записей в '{config['display_name']}'",
            show_alert=True
        )
        return
    
    # Создаём кнопки для выбора записи
    keyboard = []
    
    for record in records[:20]:  # Ограничение 20 записей
        record_dict = dict(zip(column_names, record))
        record_id = record_dict[config['id_field']]
        
        # Форматируем отображение
        try:
            display_text = config['list_format'].format(**record_dict)
        except KeyError:
            display_text = f"ID: {record_id}"
        
        # Ограничиваем длину
        if len(display_text) > 50:
            display_text = display_text[:47] + "..."
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"✏️ {display_text}",
                callback_data=f"editor_select_record:{field_type}:{record_id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="editor_back_to_menu")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"✏️ {config['display_name'].upper()}\n\n"
        f"📊 Найдено записей: {len(records)}\n"
        f"{'(показаны первые 20)' if len(records) > 20 else ''}\n\n"
        "Выберите запись для редактирования:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("editor_select_record:"))
async def select_record(callback: CallbackQuery, state: FSMContext):
    """Выбор записи - показываем доступные поля"""
    if not await is_admin_async(callback.from_user.id):  # ✅ FIX
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    field_type = parts[1]
    record_id = parts[2]
    
    config = EDITABLE_FIELDS_CONFIG[field_type]
    
    # Получаем текущие значения
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            all_fields = [config['id_field']] + list(config['fields'].keys())
            query = f"SELECT {', '.join(all_fields)} FROM {config['table']} WHERE {config['id_field']} = ?"
            
            async with db.execute(query, (record_id,)) as cursor:
                record = await cursor.fetchone()
                column_names = [desc[0] for desc in cursor.description]
    except Exception as e:
        logging.error(f"Error fetching record: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return
    
    if not record:
        await callback.answer("❌ Запись не найдена", show_alert=True)
        return
    
    record_dict = dict(zip(column_names, record))
    await state.update_data(field_type=field_type, record_id=record_id, record_data=record_dict)
    
    # Создаём кнопки для выбора поля
    keyboard = []
    
    for field_name, field_config in config['fields'].items():
        current_value = record_dict.get(field_name, "—")
        if current_value is None:
            current_value = "—"
        
        # Ограничиваем длину отображения
        value_display = str(current_value)
        if len(value_display) > 30:
            value_display = value_display[:27] + "..."
        
        button_text = f"{field_config['display']}: {value_display}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"editor_edit_field:{field_type}:{record_id}:{field_name}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="🔙 К списку",
            callback_data=f"editor_select_type:{field_type}"
        )
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Формируем текст с текущими значениями
    text = f"✏️ РЕДАКТИРОВАНИЕ: {config['display_name']}\n\n"
    
    try:
        display_info = config['list_format'].format(**record_dict)
        text += f"📝 {display_info}\n\n"
    except KeyError:
        text += f"📝 ID: {record_id}\n\n"
    
    text += "Выберите поле для изменения:"
    
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("editor_edit_field:"))
async def start_field_edit(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования поля"""
    if not await is_admin_async(callback.from_user.id):  # ✅ FIX
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    parts = callback.data.split(":")
    field_type = parts[1]
    record_id = parts[2]
    field_name = parts[3]
    
    config = EDITABLE_FIELDS_CONFIG[field_type]
    field_config = config['fields'][field_name]
    
    # Получаем текущее значение
    data = await state.get_data()
    record_data = data.get("record_data", {})
    current_value = record_data.get(field_name, "—")
    
    await state.update_data(
        editing_field=field_name,
        current_value=current_value
    )
    await state.set_state(FieldEditStates.entering_new_value)
    
    # Формируем инструкции на основе типа поля
    instructions = ""
    if field_config['type'] == 'text':
        instructions = f"Введите новый текст (макс. {field_config['max_length']} символов)"
    elif field_config['type'] == 'int':
        min_val = field_config.get('min', '')
        max_val = field_config.get('max', '')
        instructions = f"Введите число от {min_val} до {max_val}"
    
    await callback.message.edit_text(
        f"✏️ ИЗМЕНЕНИЕ ПОЛЯ\n\n"
        f"Поле: {field_config['display']}\n"
        f"Текущее значение: {current_value}\n\n"
        f"{instructions}\n\n"
        f"Или отправьте /cancel для отмены"
    )
    await callback.answer()


@router.message(FieldEditStates.entering_new_value)
async def apply_field_edit(message: Message, state: FSMContext):
    """Применение изменения поля"""
    if not await is_admin_async(message.from_user.id):  # ✅ FIX
        await state.clear()
        return
    
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=ADMIN_MENU)
        return
    
    new_value = message.text.strip()
    
    # Получаем контекст
    data = await state.get_data()
    field_type = data['field_type']
    record_id = data['record_id']
    field_name = data['editing_field']
    current_value = data['current_value']
    
    config = EDITABLE_FIELDS_CONFIG[field_type]
    field_config = config['fields'][field_name]
    
    # Валидация нового значения
    if field_config['type'] == 'text':
        if len(new_value) > field_config['max_length']:
            await message.answer(
                f"❌ Слишком длинный текст\n"
                f"Максимум: {field_config['max_length']} символов\n"
                f"У вас: {len(new_value)}\n\n"
                f"Попробуйте ещё раз:"
            )
            return
    
    elif field_config['type'] == 'int':
        try:
            new_value_int = int(new_value)
            if 'min' in field_config and new_value_int < field_config['min']:
                await message.answer(
                    f"❌ Значение слишком маленькое\n"
                    f"Минимум: {field_config['min']}\n\n"
                    f"Попробуйте ещё раз:"
                )
                return
            if 'max' in field_config and new_value_int > field_config['max']:
                await message.answer(
                    f"❌ Значение слишком большое\n"
                    f"Максимум: {field_config['max']}\n\n"
                    f"Попробуйте ещё раз:"
                )
                return
            new_value = new_value_int
        except ValueError:
            await message.answer(
                f"❌ Это должно быть число\n\n"
                f"Попробуйте ещё раз:"
            )
            return
    
    # Применяем изменение
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            query = f"UPDATE {config['table']} SET {field_name} = ? WHERE {config['id_field']} = ?"
            await db.execute(query, (new_value, record_id))
            await db.commit()
        
        await state.clear()
        
        await message.answer(
            f"✅ УСПЕШНО ИЗМЕНЕНО\n\n"
            f"Поле: {field_config['display']}\n"
            f"Было: {current_value}\n"
            f"Стало: {new_value}\n\n"
            f"ID записи: {record_id}",
            reply_markup=ADMIN_MENU
        )
        
        logging.info(
            f"Admin {message.from_user.id} edited {field_type}.{field_name} "
            f"for record {record_id}: '{current_value}' → '{new_value}'"
        )
    
    except Exception as e:
        logging.error(f"Error updating field: {e}")
        await message.answer(
            f"❌ ОШИБКА ПРИ СОХРАНЕНИИ\n\n"
            f"{str(e)}\n\n"
            f"Изменение не применено",
            reply_markup=ADMIN_MENU
        )
        await state.clear()


@router.callback_query(F.data == "editor_back_to_menu")
async def back_to_editor_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню редактора"""
    await state.clear()
    
    keyboard = []
    for key, config in EDITABLE_FIELDS_CONFIG.items():
        keyboard.append([
            InlineKeyboardButton(
                text=f"✏️ {config['display_name']}",
                callback_data=f"editor_select_type:{key}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data="editor_close")
    ])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "✏️ УНИВЕРСАЛЬНЫЙ РЕДАКТОР ПОЛЕЙ\n\n"
        "Выберите тип данных:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "editor_close")
async def close_editor(callback: CallbackQuery, state: FSMContext):
    """Закрытие редактора"""
    await state.clear()
    await callback.message.delete()
    await callback.answer("Редактор закрыт")
