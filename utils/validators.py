"""Утилиты валидации данных"""

import logging
from datetime import datetime
from typing import Optional, Tuple


def parse_callback_data(
    callback_data: str, 
    expected_parts: int,
    separator: str = ":"
) -> Optional[Tuple[str, ...]]:
    """Безопасный парсинг callback_data
    
    Args:
        callback_data: Строка callback данных
        expected_parts: Ожидаемое количество частей
        separator: Разделитель (по умолчанию ":")
    
    Returns:
        Tuple с частями или None при ошибке
        
    Example:
        >>> parse_callback_data("confirm:2026-02-10:10:00", 3)
        ('confirm', '2026-02-10', '10:00')
        
        >>> parse_callback_data("invalid", 3)
        None
    """
    try:
        parts = callback_data.split(separator, expected_parts - 1)
        if len(parts) != expected_parts:
            logging.warning(
                f"Invalid callback_data: expected {expected_parts} parts, "
                f"got {len(parts)} in '{callback_data}'"
            )
            return None
        return tuple(parts)
    except Exception as e:
        logging.error(f"Error parsing callback_data '{callback_data}': {e}")
        return None


def validate_date_format(date_str: str, format: str = "%Y-%m-%d") -> bool:
    """Проверка формата даты
    
    Args:
        date_str: Строка даты
        format: Формат даты (по умолчанию YYYY-MM-DD)
        
    Returns:
        True если формат корректен
        
    Example:
        >>> validate_date_format("2026-02-10")
        True
        
        >>> validate_date_format("10-02-2026")
        False
    """
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False


def validate_time_format(time_str: str, format: str = "%H:%M") -> bool:
    """Проверка формата времени
    
    Args:
        time_str: Строка времени
        format: Формат времени (по умолчанию HH:MM)
        
    Returns:
        True если формат корректен
        
    Example:
        >>> validate_time_format("14:30")
        True
        
        >>> validate_time_format("25:00")
        False
    """
    try:
        datetime.strptime(time_str, format)
        return True
    except ValueError:
        return False


def validate_booking_data(date_str: str, time_str: str) -> Tuple[bool, str]:
    """Комплексная валидация данных бронирования
    
    Args:
        date_str: Дата в формате YYYY-MM-DD
        time_str: Время в формате HH:MM
        
    Returns:
        Tuple (is_valid, error_message)
        
    Example:
        >>> validate_booking_data("2026-02-10", "14:30")
        (True, "")
        
        >>> validate_booking_data("invalid", "14:30")
        (False, "Неверный формат даты")
    """
    if not validate_date_format(date_str):
        return False, "Неверный формат даты"
    
    if not validate_time_format(time_str):
        return False, "Неверный формат времени"
    
    return True, ""


def validate_rating(rating: int) -> bool:
    """Проверка рейтинга
    
    Args:
        rating: Значение рейтинга
        
    Returns:
        True если рейтинг в диапазоне 1-5
        
    Example:
        >>> validate_rating(5)
        True
        
        >>> validate_rating(0)
        False
    """
    return 1 <= rating <= 5


def sanitize_user_input(text: str, max_length: int = 200) -> str:
    """Очистка пользовательского ввода
    
    Args:
        text: Текст для очистки
        max_length: Максимальная длина
        
    Returns:
        Очищенный текст
        
    Example:
        >>> sanitize_user_input("  Привет   мир  ")
        'Привет мир'
    """
    if not text:
        return ""
    
    # Удаляем лишние пробелы
    text = " ".join(text.split())
    
    # Обрезаем до максимальной длины
    if len(text) > max_length:
        text = text[:max_length]
    
    return text


def validate_id(value: str, name: str = "ID") -> Optional[int]:
    """Валидация и преобразование ID в integer
    
    Args:
        value: Строковое значение ID
        name: Название поля для логирования
        
    Returns:
        Integer ID или None при ошибке
        
    Example:
        >>> validate_id("123")
        123
        
        >>> validate_id("invalid")
        None
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        logging.warning(f"Invalid {name}: '{value}'")
        return None
