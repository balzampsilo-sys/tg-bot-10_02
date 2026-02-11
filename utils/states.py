"""Состояния FSM"""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    """Состояния для администраторов"""
    # Управление админами
    awaiting_new_admin_id = State()
    awaiting_admin_username = State()
    
    # Рассылка
    awaiting_broadcast_message = State()
    
    # ✅ ADDED: Блокировка слотов
    awaiting_block_date = State()
    awaiting_block_time = State()
    awaiting_block_reason = State()


class FieldEditStates(StatesGroup):
    """Состояния для редактирования полей"""
    selecting_field_type = State()
    selecting_record = State()
    entering_new_value = State()
