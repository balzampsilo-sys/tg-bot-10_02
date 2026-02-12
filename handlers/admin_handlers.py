"""Обработчики для администратора"""

import asyncio
import csv
import io
import logging
from collections import defaultdict
from datetime import timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import BROADCAST_DELAY, DAY_NAMES
from database.queries import Database
from keyboards.admin_keyboards import ADMIN_MENU
from keyboards.user_keyboards import MAIN_MENU
from services.analytics_service import AnalyticsService
from utils.helpers import is_admin, now_local
from utils.states import AdminStates

router = Router()


@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Вход в админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    await message.answer("🔐 АДМИН-ПАНЕЛЬ\n\nВыберите действие:", reply_markup=ADMIN_MENU)


@router.message(F.text == "🔙 Выход из админки")
async def exit_admin(message: Message):
    """Выход из админ-панели"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    await message.answer("👋 Вы вышли из админ-панели", reply_markup=MAIN_MENU)


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    """Глобальная отмена любого действия"""
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()

    # Возвращаем в соответствующее меню в зависимости от прав
    if is_admin(message.from_user.id):
        await message.answer("❌ Действие отменено", reply_markup=ADMIN_MENU)
    else:
        await message.answer("❌ Действие отменено", reply_markup=MAIN_MENU)


@router.message(F.text == "📊 Dashboard")
async def dashboard(message: Message):
    """Дашборд"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    stats = await AnalyticsService.get_dashboard_stats()

    await message.answer(
        "📊 ДАШБОРД\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📅 Активных записей: {stats['active_bookings']}\n"
        f"❌ Всего отмен: {stats['total_cancelled']}\n"
        f"⭐ Средний рейтинг: {stats['avg_rating']:.1f}/5",
        reply_markup=ADMIN_MENU,
    )


@router.message(F.text == "💡 Рекомендации")
async def recommendations(message: Message):
    """AI-рекомендации"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    recs = await AnalyticsService.get_recommendations()

    if not recs:
        await message.answer("✅ Всё отлично! Рекомендаций нет.", reply_markup=ADMIN_MENU)
        return

    text = "💡 РЕКОМЕНДАЦИИ:\n\n"
    for rec in recs:
        text += f"{rec['icon']} {rec['title']}\n{rec['text']}\n\n"

    await message.answer(text, reply_markup=ADMIN_MENU)


@router.message(F.text == "📅 Расписание")
async def schedule_view(message: Message):
    """Просмотр расписания на неделю"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    today = now_local()
    start_date = today.strftime("%Y-%m-%d")

    # ✅ ОБНОВЛЕНО: Используем новый метод Database API с услугами
    schedule = await Database.get_week_schedule(start_date, days=7)

    # Группируем по датам
    schedule_by_date = defaultdict(list)
    # ✅ ИСПРАВЛЕНО: SQL возвращает 6 колонок (date, time, username, service_name, duration, price)
    for date_str, time_str, username, service_name, duration, price in schedule:
        schedule_by_date[date_str].append((time_str, username, service_name))

    text = "📅 РАСПИСАНИЕ НА НЕДЕЛЮ\n\n"

    for day_offset in range(7):
        current_date = today + timedelta(days=day_offset)
        date_str = current_date.strftime("%Y-%m-%d")
        bookings = schedule_by_date.get(date_str, [])

        if bookings:
            day_name = DAY_NAMES[current_date.weekday()]
            text += f"📆 {current_date.strftime('%d.%m')} ({day_name})\n"
            for time_str, username, service_name in bookings:
                # ✅ ДОБАВЛЕНО: отображение услуги
                text += f"  🕒 {time_str} - @{username} ({service_name})\n"
            text += "\n"

    if len(text.split("\n")) == 3:  # только заголовок
        text += "📭 Нет записей на ближайшую неделю"

    await message.answer(text, reply_markup=ADMIN_MENU)


@router.message(F.text == "👥 Клиенты")
async def clients_list(message: Message):
    """Список активных клиентов"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    # Используем новые методы Database API
    top_clients = await Database.get_top_clients(limit=10)
    total_users = await Database.get_total_users_count()

    text = "👥 КЛИЕНТЫ\n\n"
    text += f"Всего пользователей: {total_users}\n\n"

    if top_clients:
        text += "🏆 ТОП-10 по записям:\n\n"
        for i, (user_id, total) in enumerate(top_clients, 1):
            # ✅ ДОБАВЛЕНО: кликабельная ссылка на пользователя
            user_link = f"[{user_id}](tg://user?id={user_id})"
            text += f"{i}. {user_link}: {total} записей\n"
    else:
        text += "Пока нет записей"

    # ✅ ДОБАВЛЕНО: Markdown parse_mode
    await message.answer(text, reply_markup=ADMIN_MENU, parse_mode="Markdown")


@router.message(F.text == "⚡ Массовые операции")
async def mass_operations(message: Message):
    """Меню массовых операций"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="🗑 Очистить старые записи", callback_data="admin_cleanup")],
            [
                InlineKeyboardButton(
                    text="🔒 Заблокировать слоты", callback_data="admin_block_slots"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")],
        ]
    )

    await message.answer(
        "⚡ МАССОВЫЕ ОПЕРАЦИИ\n\n" "⚠️ Будьте осторожны!\n" "Выберите действие:",
        reply_markup=kb,
    )


@router.message(F.text == "📊 Экспорт данных")
async def export_data(message: Message):
    """Экспорт данных в CSV"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ Нет доступа")
        return

    # Получаем все записи через Database API
    today = now_local()
    start_date = (today - timedelta(days=365)).strftime("%Y-%m-%d")  # За последний год
    bookings_data = await Database.get_week_schedule(start_date, days=730)  # 2 года

    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    # ✅ ДОБАВЛЕНО: колонки Услуга, Длительность, Цена
    writer.writerow(["Дата", "Время", "Username", "Услуга", "Длительность (мин)", "Цена"])

    for date_str, time_str, username, service_name, duration, price in bookings_data:
        writer.writerow([date_str, time_str, username, service_name, duration, price])

    # Отправляем файл
    csv_data = output.getvalue().encode("utf-8-sig")  # BOM для Excel
    file = BufferedInputFile(csv_data, filename="bookings_export.csv")

    await message.answer_document(
        file,
        caption=f"📊 Экспорт записей\n\nВсего записей: {len(bookings_data)}",
        reply_markup=ADMIN_MENU,
    )


# === ОБРАБОТЧИКИ МАССОВЫХ ОПЕРАЦИЙ ===


@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Начало рассылки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.awaiting_broadcast_message)

    await callback.message.edit_text(
        "📢 РАССЫЛКА\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям.\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_broadcast_message)
async def broadcast_execute(message: Message, state: FSMContext):
    """Выполнение рассылки с rate limiting (SECURE)"""
    # CRITICAL SECURITY FIX: проверка админа в FSM-обработчике
    if not is_admin(message.from_user.id):
        await state.clear()
        await message.answer("❌ Нет доступа")
        logging.warning(
            f"🚨 SECURITY: Unauthorized broadcast attempt from user_id={message.from_user.id} "
            f"username=@{message.from_user.username}"
        )
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена", reply_markup=ADMIN_MENU)
        return

    broadcast_text = message.text

    # Используем новый метод Database API
    user_ids = await Database.get_all_users()

    await message.answer(f"📤 Начинаю рассылку {len(user_ids)} пользователям...")

    success_count = 0
    fail_count = 0

    # Используем константу из config
    for user_id in user_ids:
        try:
            await message.bot.send_message(user_id, broadcast_text)
            await asyncio.sleep(BROADCAST_DELAY)
            success_count += 1
        except Exception as e:
            logging.error(f"Broadcast failed for user_id={user_id}: {e}")
            fail_count += 1

    await state.clear()
    await message.answer(
        "✅ Рассылка завершена!\n\n" f"Успешно: {success_count}\n" f"Ошибок: {fail_count}",
        reply_markup=ADMIN_MENU,
    )

    logging.info(f"Broadcast completed by admin. Success: {success_count}, Failed: {fail_count}")


@router.callback_query(F.data == "admin_cleanup")
async def cleanup_old_bookings(callback: CallbackQuery):
    """Очистка старых записей"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    today_str = now_local().strftime("%Y-%m-%d")

    deleted_count = await Database.cleanup_old_bookings(today_str)

    await callback.message.edit_text(
        "✅ Очистка завершена\n\n" f"Удалено старых записей: {deleted_count}"
    )
    await callback.answer(f"Удалено: {deleted_count}")

    logging.info(f"Admin cleanup: deleted {deleted_count} old bookings")


@router.callback_query(F.data == "admin_block_slots")
async def block_slots_menu(callback: CallbackQuery):
    """Меню блокировки слотов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔒 Заблокировать слот", callback_data="block_slot_start")],
            [
                InlineKeyboardButton(
                    text="🔓 Разблокировать слот", callback_data="unblock_slot_start"
                )
            ],
            [InlineKeyboardButton(text="📋 Список блокировок", callback_data="list_blocked_slots")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_cancel")],
        ]
    )

    await callback.message.edit_text(
        "🔒 БЛОКИРОВКА СЛОТОВ\n\n" "Выберите действие:", reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "block_slot_start")
async def block_slot_start(callback: CallbackQuery, state: FSMContext):
    """Начало блокировки слота"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminStates.awaiting_block_date)

    await callback.message.edit_text(
        "🔒 БЛОКИРОВКА СЛОТА\n\n"
        "Шаг 1: Введите дату в формате ГГГГ-ММ-ДД\n"
        "Например: 2026-02-15\n\n"
        "Для отмены отправьте /cancel"
    )
    await callback.answer()


@router.message(AdminStates.awaiting_block_date)
async def block_slot_date(message: Message, state: FSMContext):
    """Обработка даты для блокировки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Блокировка отменена", reply_markup=ADMIN_MENU)
        return

    # Валидация даты
    try:
        from datetime import datetime

        date_obj = datetime.strptime(message.text, "%Y-%m-%d")
        date_str = message.text

        # Проверка что дата не в прошлом
        if date_obj.date() < now_local().date():
            await message.answer(
                "❌ Нельзя блокировать прошедшие даты\n\n" "Введите корректную дату:"
            )
            return
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты\n\n" "Используйте формат ГГГГ-ММ-ДД\n" "Например: 2026-02-15"
        )
        return

    await state.update_data(block_date=date_str)
    await state.set_state(AdminStates.awaiting_block_time)

    await message.answer(
        f"✅ Дата: {date_str}\n\n"
        "Шаг 2: Введите время в формате ЧЧ:ММ\n"
        "Например: 14:00\n\n"
        "Или введите 'all' чтобы заблокировать весь день"
    )


@router.message(AdminStates.awaiting_block_time)
async def block_slot_time(message: Message, state: FSMContext):
    """Обработка времени для блокировки"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Блокировка отменена", reply_markup=ADMIN_MENU)
        return

    data = await state.get_data()
    date_str = data.get("block_date")

    # Блокировка всего дня
    if message.text.lower() == "all":
        await state.update_data(block_time="all")
        await state.set_state(AdminStates.awaiting_block_reason)

        await message.answer(
            f"📅 Дата: {date_str}\n"
            "🕒 Время: весь день\n\n"
            "Шаг 3: Введите причину блокировки\n"
            "(или отправьте '-' чтобы пропустить)"
        )
        return

    # Валидация времени
    try:
        from datetime import datetime

        from config import WORK_HOURS_END, WORK_HOURS_START

        time_obj = datetime.strptime(message.text, "%H:%M")
        hour = time_obj.hour

        if not (WORK_HOURS_START <= hour < WORK_HOURS_END):
            await message.answer(
                f"❌ Время должно быть в рабочих часах ({WORK_HOURS_START}:00 - {WORK_HOURS_END}:00)\n\n"
                "Введите корректное время:"
            )
            return

        time_str = message.text
    except ValueError:
        await message.answer(
            "❌ Неверный формат времени\n\n" "Используйте формат ЧЧ:ММ\n" "Например: 14:00"
        )
        return

    await state.update_data(block_time=time_str)
    await state.set_state(AdminStates.awaiting_block_reason)

    await message.answer(
        f"✅ Дата: {date_str}\n"
        f"✅ Время: {time_str}\n\n"
        "Шаг 3: Введите причину блокировки\n"
        "(или отправьте '-' чтобы пропустить)"
    )


@router.message(AdminStates.awaiting_block_reason)
async def block_slot_reason(message: Message, state: FSMContext):
    """Обработка причины и финальная блокировка с уведомлениями"""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    date_str = data.get("block_date")
    time_str = data.get("block_time")
    reason = None if message.text == "-" else message.text

    admin_id = message.from_user.id
    bot = message.bot

    # Блокировка всего дня
    if time_str == "all":
        from config import WORK_HOURS_END, WORK_HOURS_START

        blocked_count = 0
        failed_count = 0
        all_cancelled_users = []

        for hour in range(WORK_HOURS_START, WORK_HOURS_END):
            slot_time = f"{hour:02d}:00"
            # ✅ ОБНОВЛЕНО: используем новый метод с уведомлениями
            success, cancelled_users = await Database.block_slot_with_notification(
                date_str, slot_time, admin_id, reason
            )
            if success:
                blocked_count += 1
                all_cancelled_users.extend(cancelled_users)
            else:
                failed_count += 1

        # Отправляем уведомления всем затронутым пользователям
        notifications_sent = 0
        for user_data in all_cancelled_users:
            try:
                notification_text = (
                    f"⚠️ ОТМЕНА ЗАПИСИ ПО РЕШЕНИЮ АДМИНИСТРАТОРА\n\n"
                    f"📅 Дата: {user_data['date']}\n"
                    f"🕒 Время: {user_data['time']}\n\n"
                    f"💬 Причина:\n{user_data['reason'] or 'Не указана'}\n\n"
                    f"Приносим извинения за неудобства.\n"
                    f"Для новой записи используйте /start"
                )
                await bot.send_message(user_data["user_id"], notification_text)
                notifications_sent += 1
                await asyncio.sleep(0.05)  # rate limiting
            except Exception as e:
                logging.error(f"Failed to notify user {user_data['user_id']}: {e}")

        await state.clear()
        await message.answer(
            f"✅ Блокировка завершена!\n\n"
            f"📅 Дата: {date_str}\n"
            f"🔒 Заблокировано: {blocked_count} слотов\n"
            f"❌ Уже были заняты: {failed_count} слотов\n"
            f"📧 Отменено записей: {len(all_cancelled_users)}\n"
            f"✉️ Уведомлений отправлено: {notifications_sent}",
            reply_markup=ADMIN_MENU,
        )

        logging.info(
            f"Admin {admin_id} blocked full day {date_str}, "
            f"cancelled {len(all_cancelled_users)} bookings"
        )
        return

    # ✅ ОБНОВЛЕНО: Блокировка одного слота с уведомлением
    success, cancelled_users = await Database.block_slot_with_notification(
        date_str, time_str, admin_id, reason
    )

    await state.clear()

    if success:
        # Отправляем уведомления
        notifications_sent = 0
        for user_data in cancelled_users:
            try:
                notification_text = (
                    f"⚠️ ОТМЕНА ЗАПИСИ ПО РЕШЕНИЮ АДМИНИСТРАТОРА\n\n"
                    f"📅 Дата: {user_data['date']}\n"
                    f"🕒 Время: {user_data['time']}\n\n"
                    f"💬 Причина:\n{user_data['reason'] or 'Не указана'}\n\n"
                    f"Приносим извинения за неудобства.\n"
                    f"Для новой записи используйте /start"
                )
                await bot.send_message(user_data["user_id"], notification_text)
                notifications_sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logging.error(f"Failed to notify user {user_data['user_id']}: {e}")

        response_text = (
            f"✅ Слот заблокирован!\n\n"
            f"📅 Дата: {date_str}\n"
            f"🕒 Время: {time_str}\n"
            f"💬 Причина: {reason or 'не указана'}"
        )

        if cancelled_users:
            response_text += (
                f"\n\n📧 Отменено записей: {len(cancelled_users)}\n"
                f"✉️ Уведомлений отправлено: {notifications_sent}\n\n"
                f"Затронутые пользователи:\n"
            )
            for user_data in cancelled_users:
                response_text += f"  • @{user_data['username']}\n"

        await message.answer(response_text, reply_markup=ADMIN_MENU)

        logging.info(
            f"Admin {admin_id} blocked slot {date_str} {time_str}, "
            f"cancelled {len(cancelled_users)} bookings"
        )
    else:
        await message.answer(
            f"❌ Слот уже заблокирован\n\n" f"📅 {date_str} {time_str}", reply_markup=ADMIN_MENU
        )


@router.callback_query(F.data == "unblock_slot_start")
async def unblock_slot_menu(callback: CallbackQuery):
    """Меню разблокировки"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    blocked = await Database.get_blocked_slots()

    if not blocked:
        await callback.answer("✅ Нет заблокированных слотов", show_alert=True)
        return

    keyboard = []
    for date_str, time_str, reason in blocked[:20]:
        text = f"🔓 {date_str} {time_str}"
        if reason:
            text += f" ({reason[:20]}...)" if len(reason) > 20 else f" ({reason})"

        keyboard.append(
            [InlineKeyboardButton(text=text, callback_data=f"unblock:{date_str}:{time_str}")]
        )

    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_block_slots")])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.edit_text(
        f"🔓 РАЗБЛОКИРОВАТЬ СЛОТ\n\n"
        f"Найдено блокировок: {len(blocked)}\n"
        "Выберите слот для разблокировки:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("unblock:"))
async def unblock_slot_confirm(callback: CallbackQuery):
    """Разблокировка слота"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        _, date_str, time_str = callback.data.split(":", 2)
    except ValueError:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    success = await Database.unblock_slot(date_str, time_str)

    if success:
        await callback.answer(f"✅ Слот {date_str} {time_str} разблокирован")
        logging.info(f"Admin {callback.from_user.id} unblocked slot {date_str} {time_str}")

        await unblock_slot_menu(callback)
    else:
        await callback.answer("❌ Слот не найден", show_alert=True)


@router.callback_query(F.data == "list_blocked_slots")
async def list_blocked_slots(callback: CallbackQuery):
    """Список всех блокировок"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    blocked = await Database.get_blocked_slots()

    if not blocked:
        await callback.message.edit_text(
            "✅ Нет заблокированных слотов",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_block_slots")]
                ]
            ),
        )
        return

    text = f"📋 ЗАБЛОКИРОВАННЫЕ СЛОТЫ ({len(blocked)})\n\n"

    for date_str, time_str, reason in blocked[:50]:
        text += f"🔒 {date_str} {time_str}"
        if reason:
            text += f"\n   💬 {reason}\n"
        text += "\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_block_slots")]]
    )

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "admin_cancel")
async def admin_cancel_operation(callback: CallbackQuery):
    """Отмена админской операции"""
    await callback.message.delete()
    await callback.answer("Отменено")
