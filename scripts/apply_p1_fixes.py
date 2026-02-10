#!/usr/bin/env python3
"""Скрипт для автоматического применения исправлений P1.2

Использование:
    python scripts/apply_p1_fixes.py

Что делает:
1. Читает handlers/booking_handlers.py
2. Добавляет await state.clear() в критических местах
3. Сохраняет изменения
"""

import re
from pathlib import Path


def apply_fixes():
    file_path = Path(__file__).parent.parent / "handlers" / "booking_handlers.py"
    
    if not file_path.exists():
        print(f"❌ Файл не найден: {file_path}")
        return False
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    original_content = content
    fixes_applied = 0
    
    # Фикс 1: select_service() - после validate_id
    pattern1 = r'(service_id = validate_id\(callback\.data\.split\(":"\)\[1\], "service_id"\)\s+if not service_id:\s+await callback\.answer\("[^"]+", show_alert=True\))\s+(return)'
    replacement1 = r'\1\n        await state.clear()\n        \2'
    if re.search(pattern1, content) and 'await state.clear()' not in content[content.find('if not service_id:'):content.find('if not service_id:')+200]:
        content = re.sub(pattern1, replacement1, content)
        fixes_applied += 1
        print("✅ Fix 1: Добавлен state.clear() после validate_id в select_service()")
    
    # Фикс 2: select_service() - после проверки service.is_active
    pattern2 = r'(service = await ServiceRepository\.get_service_by_id\(service_id\)\s+if not service or not service\.is_active:\s+await callback\.answer\([^)]+\))\s+(return)'
    replacement2 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern2, replacement2, content)
    if content != original_content:
        fixes_applied += 1
        print("✅ Fix 2: Добавлен state.clear() после проверки is_active в select_service()")
    
    # Фикс 3: select_day() - после validate_date_not_past (если еще нет)
    pattern3 = r'(is_valid, error_msg = validate_date_not_past\(date_str\)\s+if not is_valid:\s+await callback\.answer\(f"[^"]+{error_msg}", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement3 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern3, replacement3, content)
    if content != original_content:
        fixes_applied += 1
        print("✅ Fix 3: Добавлен state.clear() после validate_date_not_past")
    
    # Фикс 4: book_time() - после parse_callback_data
    pattern4 = r'(@router\.callback_query\(F\.data\.startswith\("confirm:"\)\).*?result = parse_callback_data\(callback\.data, 3\)\s+if not result:\s+await callback\.answer\("[^"]+", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement4 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern4, replacement4, content, flags=re.DOTALL)
    
    # Фикс 5: book_time() - после validate_booking_data
    pattern5 = r'(is_valid, _ = validate_booking_data\(date_str, time_str\)\s+if not is_valid:\s+await callback\.answer\("[^"]+", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement5 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern5, replacement5, content)
    
    # Фикс 6: cancel_booking_callback() - дополнительные места
    # После validate_id
    pattern6 = r'(booking_id = validate_id\(booking_id_str\)\s+if not booking_id:\s+await callback\.answer\("[^"]+", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement6 = r'\1\n        await state.clear()\n        \2'
    
    # Нужно применять только к cancel_booking_callback, не к cancel_confirmed
    # Поэтому ищем контекст
    
    # Фикс 7: start_reschedule() - все 3 return
    pattern7 = r'(@router\.callback_query\(F\.data\.startswith\("reschedule:"\)\).*?result = parse_callback_data\(callback\.data, 2\)\s+if not result:\s+await callback\.answer\("[^"]+", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement7 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern7, replacement7, content, flags=re.DOTALL)
    
    # Фикс 8: confirm_reschedule_time()
    pattern8 = r'(@router\.callback_query\(F\.data\.startswith\("reschedule_time:"\)\).*?result = parse_callback_data\(callback\.data, 3\)\s+if not result:\s+await callback\.answer\("[^"]+", show_alert=True\))(?!\s+await state\.clear\(\))\s+(return)'
    replacement8 = r'\1\n        await state.clear()\n        \2'
    content = re.sub(pattern8, replacement8, content, flags=re.DOTALL)
    
    if content != original_content:
        # Сохраняем изменения
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"\n✅ Всего применено исправлений: {fixes_applied}")
        print(f"✅ Файл обновлен: {file_path}")
        return True
    else:
        print("ℹ️ Все исправления уже применены")
        return True


if __name__ == "__main__":
    print("🔧 Применение исправлений P1.2: state.clear() при ошибках\n")
    success = apply_fixes()
    
    if success:
        print("\n✅ Исправления P1.2 успешно применены!")
        print("\n📝 Рекомендации:")
        print("1. Проверьте изменения: git diff handlers/booking_handlers.py")
        print("2. Запустите тесты (если есть)")
        print("3. Закоммитьте: git add . && git commit -m 'Fix P1.2: Add state.clear() on errors'")
    else:
        print("\n❌ Ошибка при применении исправлений")
        exit(1)
