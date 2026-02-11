"""Обработчики для управления администраторами"""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import ADMIN_IDS, ROLE_MODERATOR, ROLE_SUPER_ADMIN
from database.queries import Database
from database.repositories.audit_repository import AuditRepository
from keyboards.admin_keyboards import ADMIN_MENU
from utils.helpers import is_admin
from utils.permissions import get_admin_role_display, has_permission
from utils.rate_limiter import AdminRateLimiter
from utils.states import AdminStates

router = Router()


@router.message(F.text == "👥 Администраторы")
async def admin_management_menu(message: Message):
    """Меню управления администраторами"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    # Проверка разрешения
    if not await has_permission(message.from_user.id, "manage_admins"):
        await message.answer(
            "❌ Недостаточно прав\n\n"
            "🛡️ Только для Super Admin"
        )
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Список админов", callback_data="list_admins"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить админа", callback_data="add_admin_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ Удалить админа", callback_data="remove_admin_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Изменить роль", callback_data="change_role_start"
                )
            ],
        ]
    )

    admin_count = await Database.get_admin_count()
    total_admins = len(ADMIN_IDS) + admin_count

    await message.answer(
        f"👥 УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ\n\n"
        f"🔑 Статические (.env): {len(ADMIN_IDS)}\n"
        f"💾 Динамические (БД): {admin_count}\n"
        f"👥 Всего: {total_admins}\n\n"
        "Выберите действие:",
        reply_markup=kb,
    )


@router.callback_query(F.data == "list_admins")
async def list_admins(callback: CallbackQuery):
    """Список всех администраторов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    text = "📋 СПИСОК АДМИНИСТРАТОРОВ\n\n"

    # Статические админы из .env (всегда super_admin)
    text += "👑 Статические (.env) - Super Admin:\n"
    for admin_id in ADMIN_IDS:
        user_link = f"<a href='tg://user?id={admin_id}'>{admin_id}</a>"
        text += f"  • {user_link} 👑\n"
    text += "\n"

    # Динамические админы из БД
    db_admins = await Database.get_all_admins()

    if db_admins:
        # Группируем по ролям
        super_admins = [a for a in db_admins if a[4] == ROLE_SUPER_ADMIN]
        moderators = [a for a in db_admins if a[4] == ROLE_MODERATOR]

        if super_admins:
            text += "👑 Динамические - Super Admin:\n"
            for user_id, username, added_by, added_at, role in super_admins:
                user_link = f"<a href='tg://user?id={user_id}'>{user_id}</a>"
                username_display = f"@{username}" if username else "нет username"
                text += f"  • {user_link} ({username_display}) 👑\n"
            text += "\n"

        if moderators:
            text += "🛡️ Динамические - Moderator:\n"
            for user_id, username, added_by, added_at, role in moderators:
                user_link = f"<a href='tg://user?id={user_id}'>{user_id}</a>"
                username_display = f"@{username}" if username else "нет username"
                text += f"  • {user_link} ({username_display}) 🛡️\n"
            text += "\n"
    else:
        text += "💾 Динамические: нет\n\n"

    text += "ℹ️ Статические админы нельзя удалить или изменить"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Назад", callback_data="back_to_admin_menu"
                )
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "add_admin_start")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    """Начало добавления админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    # ✅ Проверка rate limit
    can_add, count, minutes = await AdminRateLimiter.can_add_admin(callback.from_user.id)

    if not can_add:
        await callback.answer(
            f"❌ ЛИМИТ ДОСТИГНУТ\n\n"
            f"Вы добавили {count} админов за последний час.\n"
            f"Максимум: 3 админа/час\n\n"
            f"⏰ Попробуйте через: {minutes} мин",
            show_alert=True,
        )
        return

    await state.set_state(AdminStates.awaiting_new_admin_id)

    await callback.message.edit_text(
        "➕ ДОБАВЛЕНИЕ АДМИНИСТРАТОРА\n\n"
        "Введите Telegram ID пользователя:\n\n"
        "💡 Как узнать ID:\n"
        "1. Попросить пользователя написать @userinfobot\n"
        "2. Использовать @getmyid_bot\n\n"
        "🛡️ По умолчанию: Moderator\n"
        "Роль можно изменить потом через 👑 Изменить роль\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_new_admin_id)
async def add_admin_process(message: Message, state: FSMContext):
    """Обработка добавления админа"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Добавление отменено", reply_markup=ADMIN_MENU)
        return

    # Валидация user_id
    try:
        new_admin_id = int(message.text)
        if new_admin_id <= 0:
            raise ValueError("ID must be positive")
    except ValueError:
        await message.answer(
            "❌ Неверный формат ID\n\n"
            "ID должен быть положительным числом.\n"
            "Пример: 123456789\n\n"
            "Введите корректный ID:"
        )
        return

    # Проверка что не уже админ
    if new_admin_id in ADMIN_IDS:
        await state.clear()
        await message.answer(
            "⚠️ Этот пользователь уже статический админ (.env)",
            reply_markup=ADMIN_MENU,
        )
        return

    is_already_admin = await Database.is_admin_in_db(new_admin_id)
    if is_already_admin:
        await state.clear()
        await message.answer(
            "⚠️ Этот пользователь уже админ", reply_markup=ADMIN_MENU
        )
        return

    # Получаем username с fallback
    username = None
    try:
        chat = await message.bot.get_chat(new_admin_id)
        username = chat.username
        logging.info(f"Successfully got username for {new_admin_id}: {username}")
    except Exception as e:
        logging.warning(f"Failed to get username for {new_admin_id}: {e}")
        
        # Просим ввести username вручную
        await state.update_data(pending_admin_id=new_admin_id)
        await state.set_state(AdminStates.awaiting_admin_username)
        
        await message.answer(
            "⚠️ Не удалось автоматически получить username\n\n"
            "📝 Введите username пользователя вручную:\n"
            "Пример: @username или username\n\n"
            "Если username нет - отправьте: none\n"
            "Для отмены: /cancel"
        )
        return

    # Добавляем в БД с ролью moderator по умолчанию
    await _finalize_admin_addition(
        message, state, new_admin_id, username, role=ROLE_MODERATOR
    )


@router.message(AdminStates.awaiting_admin_username)
async def add_admin_username(message: Message, state: FSMContext):
    """Обработка вручного ввода username"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Добавление отменено", reply_markup=ADMIN_MENU)
        return

    data = await state.get_data()
    new_admin_id = data.get("pending_admin_id")

    if not new_admin_id:
        await state.clear()
        await message.answer("❌ Ошибка: данные потеряны", reply_markup=ADMIN_MENU)
        return

    # Обработка username
    username_input = message.text.strip()
    
    if username_input.lower() == "none":
        username = None
    else:
        username = username_input.lstrip("@")
        
        # Валидация формата
        if not username.replace("_", "").isalnum() or len(username) < 3:
            await message.answer(
                "❌ Неверный формат username\n\n"
                "Username должен:\n"
                "- Состоять из букв, цифр и _\n"
                "- Быть минимум 3 символа\n\n"
                "Пример: @john_doe\n"
                "Попробуйте снова:"
            )
            return

    # Добавляем в БД
    await _finalize_admin_addition(
        message, state, new_admin_id, username, role=ROLE_MODERATOR
    )


async def _finalize_admin_addition(
    message: Message, 
    state: FSMContext, 
    new_admin_id: int, 
    username: str | None,
    role: str = ROLE_MODERATOR
):
    """Завершить добавление админа"""
    success = await Database.add_admin(
        user_id=new_admin_id,
        username=username,
        added_by=message.from_user.id,
        role=role,
    )

    await state.clear()

    if success:
        # ✅ Записываем в rate limiter
        AdminRateLimiter.record_addition(message.from_user.id)
        
        # ✅ Записываем в audit log
        await AuditRepository.log_action(
            admin_id=message.from_user.id,
            action="add_admin",
            target_id=str(new_admin_id),
            details=f"role={role}, username={username or 'none'}",
        )
        
        role_badge = "👑 Super" if role == ROLE_SUPER_ADMIN else "🛡️ Moderator"
        username_display = f"@{username}" if username else "нет username"
        
        await message.answer(
            f"✅ Администратор добавлен!\n\n"
            f"🆔 ID: {new_admin_id}\n"
            f"👤 Username: {username_display}\n"
            f"🔑 Роль: {role_badge}\n\n"
            f"ℹ️ Пользователь теперь может использовать /admin\n"
            f"👑 Роль можно изменить через меню",
            reply_markup=ADMIN_MENU,
        )

        # Уведомляем нового админа
        try:
            await message.bot.send_message(
                new_admin_id,
                f"🎉 Поздравляем!\n\n"
                f"Вы получили права администратора!\n"
                f"🔑 Роль: {role_badge}\n\n"
                f"Используйте /admin для доступа к панели",
            )
        except Exception as e:
            logging.warning(f"Failed to notify new admin {new_admin_id}: {e}")

        logging.info(
            f"Admin {message.from_user.id} added new admin {new_admin_id} ({username}) with role {role}"
        )
    else:
        await message.answer(
            "❌ Ошибка при добавлении админа", reply_markup=ADMIN_MENU
        )


# ✅ NEW: Изменение роли

@router.callback_query(F.data == "change_role_start")
async def change_role_menu(callback: CallbackQuery):
    """Меню изменения роли"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    db_admins = await Database.get_all_admins()

    if not db_admins:
        await callback.answer(
            "ℹ️ Нет динамических админов", show_alert=True
        )
        return

    keyboard = []
    for user_id, username, added_by, added_at, role in db_admins:
        role_badge = "👑" if role == ROLE_SUPER_ADMIN else "🛡️"
        display_text = f"{role_badge} {user_id}"
        if username:
            display_text += f" (@{username})"

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=display_text, callback_data=f"select_role_admin:{user_id}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_menu")]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "👑 ИЗМЕНЕНИЕ РОЛИ\n\n"
        f"Динамических админов: {len(db_admins)}\n\n"
        "⚠️ Статические админы (.env) всегда Super Admin\n\n"
        "Выберите админа:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("select_role_admin:"))
async def select_role_for_admin(callback: CallbackQuery):
    """Выбор новой роли для админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    try:
        target_user_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    # Нельзя изменить себя
    if target_user_id == callback.from_user.id:
        await callback.answer(
            "❌ Нельзя изменить свою роль", show_alert=True
        )
        return

    # Получаем текущую роль
    current_role = await Database.get_admin_role(target_user_id)

    keyboard = [
        [
            InlineKeyboardButton(
                text="👑 Super Admin",
                callback_data=f"confirm_role:{target_user_id}:{ROLE_SUPER_ADMIN}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🛡️ Moderator",
                callback_data=f"confirm_role:{target_user_id}:{ROLE_MODERATOR}",
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад", callback_data="change_role_start"
            )
        ],
    ]

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    current_badge = "👑 Super" if current_role == ROLE_SUPER_ADMIN else "🛡️ Moderator"

    await callback.message.edit_text(
        f"👑 ВЫБОР РОЛИ\n\n"
        f"🆔 Admin ID: {target_user_id}\n"
        f"🔑 Текущая роль: {current_badge}\n\n"
        f"👑 **Super Admin:**\n"
        f"  • Управление админами\n"
        f"  • Просмотр audit log\n"
        f"  • Экспорт данных\n"
        f"  • Все остальные функции\n\n"
        f"🛡️ **Moderator:**\n"
        f"  • Управление бронированиями\n"
        f"  • Блокировка слотов\n"
        f"  • Редактирование услуг\n"
        f"  • Без доступа к админам\n\n"
        f"Выберите новую роль:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_role:"))
async def confirm_role_change(callback: CallbackQuery):
    """Подтверждение изменения роли"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    try:
        _, target_user_id_str, new_role = callback.data.split(":")
        target_user_id = int(target_user_id_str)
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    # Обновляем роль
    success = await Database.update_admin_role(target_user_id, new_role)

    if success:
        # ✅ Записываем в audit log
        await AuditRepository.log_action(
            admin_id=callback.from_user.id,
            action="change_admin_role",
            target_id=str(target_user_id),
            details=f"new_role={new_role}",
        )

        role_badge = "👑 Super Admin" if new_role == ROLE_SUPER_ADMIN else "🛡️ Moderator"

        await callback.answer(f"✅ Роль изменена на {role_badge}")

        # Уведомляем админа
        try:
            await callback.bot.send_message(
                target_user_id,
                f"🔄 Ваша роль изменена\n\n"
                f"🔑 Новая роль: {role_badge}",
            )
        except Exception as e:
            logging.warning(f"Failed to notify admin {target_user_id}: {e}")

        logging.info(
            f"Admin {callback.from_user.id} changed role of {target_user_id} to {new_role}"
        )

        # Возвращаемся в меню
        await change_role_menu(callback)
    else:
        await callback.answer("❌ Ошибка изменения роли", show_alert=True)


@router.callback_query(F.data == "remove_admin_start")
async def remove_admin_menu(callback: CallbackQuery):
    """Меню удаления админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    db_admins = await Database.get_all_admins()

    if not db_admins:
        await callback.answer(
            "ℹ️ Нет динамических админов для удаления", show_alert=True
        )
        return

    keyboard = []
    for user_id, username, added_by, added_at, role in db_admins:
        role_badge = "👑" if role == ROLE_SUPER_ADMIN else "🛡️"
        display_text = f"➖ {role_badge} {user_id}"
        if username:
            display_text += f" (@{username})"

        keyboard.append(
            [
                InlineKeyboardButton(
                    text=display_text, callback_data=f"remove_admin:{user_id}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_menu")]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        "➖ УДАЛЕНИЕ АДМИНИСТРАТОРА\n\n"
        f"Динамических админов: {len(db_admins)}\n\n"
        "⚠️ Статические админы (.env) не могут быть удалены\n\n"
        "Выберите админа для удаления:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_admin:"))
async def remove_admin_confirm(callback: CallbackQuery):
    """Подтверждение удаления админа"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "manage_admins"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    try:
        admin_to_remove = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    # Нельзя удалить себя
    if admin_to_remove == callback.from_user.id:
        await callback.answer(
            "❌ Нельзя удалить себя", show_alert=True
        )
        return

    # Проверка последнего админа
    total_admins = len(ADMIN_IDS) + await Database.get_admin_count()
    if total_admins <= 1:
        await callback.answer(
            "❌ Нельзя удалить последнего админа", show_alert=True
        )
        return

    # Удаляем
    success = await Database.remove_admin(admin_to_remove)

    if success:
        # ✅ Записываем в audit log
        await AuditRepository.log_action(
            admin_id=callback.from_user.id,
            action="remove_admin",
            target_id=str(admin_to_remove),
            details="",
        )

        await callback.answer(f"✅ Админ {admin_to_remove} удалён")

        # Уведомляем удалённого админа
        try:
            await callback.bot.send_message(
                admin_to_remove,
                "⚠️ Ваши права администратора были отозваны",
            )
        except Exception as e:
            logging.warning(f"Failed to notify removed admin {admin_to_remove}: {e}")

        logging.info(
            f"Admin {callback.from_user.id} removed admin {admin_to_remove}"
        )

        # Обновляем меню
        await remove_admin_menu(callback)
    else:
        await callback.answer("❌ Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "back_to_admin_menu")
async def back_to_admin_menu(callback: CallbackQuery):
    """Возврат в меню управления админами"""
    await callback.message.delete()

    # Пересоздаём меню
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Список админов", callback_data="list_admins"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить админа", callback_data="add_admin_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➖ Удалить админа", callback_data="remove_admin_start"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Изменить роль", callback_data="change_role_start"
                )
            ],
        ]
    )

    admin_count = await Database.get_admin_count()
    total_admins = len(ADMIN_IDS) + admin_count

    await callback.message.answer(
        f"👥 УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ\n\n"
        f"🔑 Статические (.env): {len(ADMIN_IDS)}\n"
        f"💾 Динамические (БД): {admin_count}\n"
        f"👥 Всего: {total_admins}\n\n"
        "Выберите действие:",
        reply_markup=kb,
    )
    await callback.answer()
