"""Обработчики audit log"""

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.repositories.audit_repository import AuditRepository
from utils.helpers import is_admin
from utils.permissions import has_permission

router = Router()

PAGE_SIZE = 10


@router.message(F.text == "/audit")
async def audit_log_menu(message: Message):
    """Просмотр audit log (super_admin only)"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    # Проверка разрешения
    if not await has_permission(message.from_user.id, "view_audit_log"):
        await message.answer(
            "❌ Недостаточно прав\n\n"
            "Только для Super Admin"
        )
        return

    await show_audit_page(message, page=0)


async def show_audit_page(message: Message, page: int = 0):
    """Показать страницу audit log"""
    offset = page * PAGE_SIZE
    logs = await AuditRepository.get_logs(limit=PAGE_SIZE, offset=offset)
    total = await AuditRepository.get_logs_count()

    if not logs:
        await message.answer("📜 Audit log пуст")
        return

    text = "📜 AUDIT LOG\n\n"

    for log_id, admin_id, action, target_id, details, timestamp in logs:
        dt = datetime.fromisoformat(timestamp)
        text += f"🔹 {dt.strftime('%d.%m %H:%M')}\n"
        text += f"   Admin: {admin_id}\n"
        text += f"   Action: {action}\n"

        if target_id:
            text += f"   Target: {target_id}\n"

        if details:
            text += f"   Details: {details[:50]}\n"

        text += "\n"

    # Пагинация
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    text += f"📊 Page {page + 1}/{total_pages} | Total: {total}"

    keyboard = []

    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="⬅️ Prev", callback_data=f"audit_page:{page - 1}")
        )
    if (page + 1) < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="Next ➡️", callback_data=f"audit_page:{page + 1}")
        )

    if nav_buttons:
        keyboard.append(nav_buttons)

    # Экспорт
    keyboard.append(
        [InlineKeyboardButton(text="💾 Export CSV", callback_data="audit_export")]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    try:
        await message.edit_text(text, reply_markup=kb)
    except:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("audit_page:"))
async def audit_page_callback(callback: CallbackQuery):
    """Навигация по страницам"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "view_audit_log"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    await show_audit_page(callback.message, page)
    await callback.answer()


@router.callback_query(F.data == "audit_export")
async def audit_export_callback(callback: CallbackQuery):
    """Экспорт audit log в CSV"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    if not await has_permission(callback.from_user.id, "export_data"):
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    await callback.answer("⏳ Генерирую CSV...")

    from pathlib import Path

    filepath = Path("exports") / f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath.parent.mkdir(exist_ok=True)

    success = await AuditRepository.export_to_csv(str(filepath))

    if success:
        from aiogram.types import FSInputFile

        await callback.message.answer_document(
            FSInputFile(filepath), caption="💾 Audit Log Export"
        )
        filepath.unlink()  # Удаляем после отправки
    else:
        await callback.message.answer("❌ Ошибка экспорта")
