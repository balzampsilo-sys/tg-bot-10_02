"""ФSM состояния"""

from aiogram.fsm.state import State, StatesGroup


class RescheduleStates(StatesGroup):
    """Состояния для переноса записи"""

    selecting_date = State()
    selecting_time = State()
    confirming = State()


class AdminStates(StatesGroup):
    """Состояния для админ-панели"""

    awaiting_message = State()
    awaiting_booking_data = State()
    awaiting_broadcast_message = State()
    
    # Состояния для блокировки слотов
    awaiting_block_date = State()
    awaiting_block_time = State()
    awaiting_block_reason = State()
    
    # Состояния для управления услугами
    service_awaiting_name = State()
    service_awaiting_description = State()
    service_awaiting_duration = State()
    service_awaiting_price = State()
    service_awaiting_color = State()
    
    # Состояния для редактирования услуги
    service_edit_field = State()
    service_edit_value = State()
    
    # Состояния для управления администраторами
    awaiting_new_admin_id = State()
