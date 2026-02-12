"""Состояния FSM"""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния для администраторов"""

    # Управление админами
    awaiting_new_admin_id = State()
    awaiting_admin_username = State()

    # Рассылка
    awaiting_broadcast_message = State()

    # Блокировка слотов (старый способ - текстовый)
    awaiting_block_date = State()
    awaiting_block_time = State()
    awaiting_block_reason = State()

    # Блокировка через календарь ✅ NEW
    awaiting_block_reason_calendar = State()  # После выбора времени через календарь

    # Управление услугами
    service_awaiting_name = State()
    service_awaiting_description = State()
    service_awaiting_duration = State()
    service_awaiting_price = State()
    service_edit_value = State()

    # Настройки системы ✅ NEW
    awaiting_work_hours_start = State()
    awaiting_work_hours_end = State()


class FieldEditStates(StatesGroup):
    """Состояния для редактирования полей"""

    selecting_field_type = State()
    selecting_record = State()
    entering_new_value = State()


class MassEditStates(StatesGroup):
    """Состояния для массового редактирования"""

    awaiting_date_for_time_edit = State()  # Дата для массового переноса
    awaiting_new_time = State()  # Новое время (сдвиг)
