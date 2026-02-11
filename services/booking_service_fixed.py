"""Booking Service with race condition protection

Key improvements:
1. Proper IntegrityError handling for duplicate bookings
2. Atomic check-and-insert operations where possible
3. Transaction-based operations with proper rollback
4. Retry logic via db_retry decorator

Usage:
    Replace imports in handlers:
    from services.booking_service_fixed import BookingService
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import aiosqlite
import pytz

from config import (
    DATABASE_PATH,
    TIMEZONE,
    MAX_BOOKINGS_PER_USER,
    CANCELLATION_HOURS,
)
from database.db_retry import db_retry, DBRetry

logger = logging.getLogger(__name__)


class BookingService:
    """Service for managing bookings with race condition protection"""
    
    @staticmethod
    def get_current_time() -> datetime:
        """Get current time in configured timezone (Moscow)"""
        # Use UTC internally, then localize
        utc_now = datetime.now(pytz.UTC)
        return utc_now.astimezone(TIMEZONE)
    
    @staticmethod
    @db_retry(max_retries=3)
    async def create_booking(
        date: str,
        time: str,
        user_id: int,
        username: str,
        service_id: int = 1,
        duration_minutes: int = 60
    ) -> tuple[bool, str]:
        """Create booking with race condition protection
        
        Returns:
            (success: bool, message: str)
        """
        async with DBRetry(DATABASE_PATH) as db:
            try:
                # Use a transaction for atomicity
                await db.execute("BEGIN IMMEDIATE")
                
                # 1. Check user booking limit
                cursor = await db.execute(
                    """SELECT COUNT(*) FROM bookings 
                       WHERE user_id = ? AND date >= ?""",
                    (user_id, date)
                )
                count = (await cursor.fetchone())[0]
                await cursor.close()
                
                if count >= MAX_BOOKINGS_PER_USER:
                    await db.rollback()
                    return False, f"Превышен лимит: максимум {MAX_BOOKINGS_PER_USER} записей"
                
                # 2. Check if slot is already taken (race condition check)
                cursor = await db.execute(
                    """SELECT id FROM bookings 
                       WHERE date = ? AND time = ?""",
                    (date, time)
                )
                existing = await cursor.fetchone()
                await cursor.close()
                
                if existing:
                    await db.rollback()
                    return False, "Это время уже занято. Выберите другое."
                
                # 3. Create booking
                created_at = BookingService.get_current_time().isoformat()
                
                await db.execute(
                    """INSERT INTO bookings 
                       (date, time, user_id, username, created_at, service_id, duration_minutes)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (date, time, user_id, username, created_at, service_id, duration_minutes)
                )
                
                await db.commit()
                logger.info(f"✅ Booking created: {date} {time} by user {user_id}")
                return True, "Запись успешно создана!"
                
            except aiosqlite.IntegrityError as e:
                # UNIQUE constraint violation - slot was taken between check and insert
                await db.rollback()
                logger.warning(f"⚠️ Race condition detected: {e}")
                return False, "Это время только что заняли. Попробуйте другое."
                
            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Booking creation failed: {e}")
                return False, f"Ошибка при создании записи: {str(e)}"
    
    @staticmethod
    @db_retry(max_retries=3)
    async def cancel_booking(booking_id: int, user_id: int) -> tuple[bool, str]:
        """Cancel booking with cancellation window check"""
        async with DBRetry(DATABASE_PATH) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                
                # Get booking details
                cursor = await db.execute(
                    """SELECT date, time, user_id FROM bookings 
                       WHERE id = ?""",
                    (booking_id,)
                )
                booking = await cursor.fetchone()
                await cursor.close()
                
                if not booking:
                    await db.rollback()
                    return False, "Запись не найдена"
                
                date_str, time_str, booking_user_id = booking
                
                # Check ownership
                if booking_user_id != user_id:
                    await db.rollback()
                    return False, "У вас нет прав на отмену этой записи"
                
                # Check cancellation window
                try:
                    booking_datetime = datetime.strptime(
                        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                    )
                    # Make timezone-aware
                    booking_datetime = TIMEZONE.localize(booking_datetime)
                    
                    current_time = BookingService.get_current_time()
                    time_until_booking = booking_datetime - current_time
                    
                    if time_until_booking < timedelta(hours=CANCELLATION_HOURS):
                        await db.rollback()
                        return False, f"Отмена возможна не позднее {CANCELLATION_HOURS}ч до записи"
                        
                except Exception as e:
                    logger.error(f"❌ Date parsing error: {e}")
                    await db.rollback()
                    return False, "Ошибка обработки даты"
                
                # Delete booking
                await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
                await db.commit()
                
                logger.info(f"✅ Booking {booking_id} cancelled by user {user_id}")
                return True, "Запись успешно отменена"
                
            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Booking cancellation failed: {e}")
                return False, f"Ошибка при отмене: {str(e)}"
    
    @staticmethod
    @db_retry(max_retries=2)
    async def get_user_bookings(user_id: int) -> List[Dict[str, Any]]:
        """Get all future bookings for user"""
        async with DBRetry(DATABASE_PATH) as db:
            current_date = BookingService.get_current_time().strftime("%Y-%m-%d")
            
            cursor = await db.execute(
                """SELECT id, date, time, service_id, duration_minutes, created_at
                   FROM bookings 
                   WHERE user_id = ? AND date >= ?
                   ORDER BY date, time""",
                (user_id, current_date)
            )
            
            rows = await cursor.fetchall()
            await cursor.close()
            
            bookings = []
            for row in rows:
                bookings.append({
                    'id': row[0],
                    'date': row[1],
                    'time': row[2],
                    'service_id': row[3],
                    'duration_minutes': row[4] or 60,  # Default if NULL
                    'created_at': row[5]
                })
            
            return bookings
    
    @staticmethod
    @db_retry(max_retries=2)
    async def is_slot_available(date: str, time: str) -> bool:
        """Check if time slot is available"""
        async with DBRetry(DATABASE_PATH) as db:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM bookings 
                   WHERE date = ? AND time = ?""",
                (date, time)
            )
            count = (await cursor.fetchone())[0]
            await cursor.close()
            
            # Also check blocked_slots table
            cursor = await db.execute(
                """SELECT COUNT(*) FROM blocked_slots 
                   WHERE date = ? AND time = ?""",
                (date, time)
            )
            blocked_count = (await cursor.fetchone())[0]
            await cursor.close()
            
            return count == 0 and blocked_count == 0
