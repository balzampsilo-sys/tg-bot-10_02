"""Improved BookingRepository with transactions and proper error handling

Key improvements:
1. ACID transactions for critical operations
2. Comprehensive error handling
3. Input validation with Pydantic
4. Race condition prevention
5. Proper connection management
"""

import calendar
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiosqlite
from pydantic import ValidationError as PydanticValidationError

from config import (
    CANCELLATION_HOURS,
    DATABASE_PATH,
    MAX_BOOKINGS_PER_USER,
    TIMEZONE,
    WORK_HOURS_END,
    WORK_HOURS_START,
)
from database.base_repository import BaseRepository
from utils.error_handler import (
    DatabaseError,
    ValidationError,
    async_retry_on_error,
    handle_database_error,
    safe_operation,
)
from utils.helpers import now_local
from validation.schemas import (
    BookingCancelInput,
    BookingCreateInput,
    SlotBlockInput,
    TimeSlotInput,
)

logger = logging.getLogger(__name__)


class BookingRepositoryV2(BaseRepository):
    """Enhanced repository for managing bookings with transactions"""

    @staticmethod
    @async_retry_on_error(
        max_attempts=3, delay=0.5, exceptions=(aiosqlite.OperationalError,)
    )
    async def is_slot_free(date_str: str, time_str: str) -> bool:
        """Check if slot is free (atomic check)

        Args:
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format

        Returns:
            True if slot is free and not blocked

        Raises:
            ValidationError: If inputs are invalid
            DatabaseError: On database errors
        """
        try:
            # Validate inputs
            from datetime import datetime as dt

            date = dt.strptime(date_str, "%Y-%m-%d").date()
            time = dt.strptime(time_str, "%H:%M").time()
            TimeSlotInput(date=date, time=time)  # Validates

        except (ValueError, PydanticValidationError) as e:
            raise ValidationError(f"Invalid slot format: {e}") from e

        try:
            async with safe_operation("check_slot_free", date=date_str, time=time_str):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    # Single query with UNION for atomicity
                    async with db.execute(
                        """
                        SELECT 1 FROM (
                            SELECT 1 FROM bookings WHERE date=? AND time=?
                            UNION ALL
                            SELECT 1 FROM blocked_slots WHERE date=? AND time=?
                        ) LIMIT 1
                        """,
                        (date_str, time_str, date_str, time_str),
                    ) as cursor:
                        exists = await cursor.fetchone() is not None
                        return not exists

        except aiosqlite.Error as e:
            context = {"date": date_str, "time": time_str}
            await handle_database_error(e, context)
            raise DatabaseError(f"Failed to check slot: {e}") from e

    @staticmethod
    @async_retry_on_error(max_attempts=3, delay=0.5)
    async def create_booking_atomic(
        user_id: int,
        username: Optional[str],
        date_str: str,
        time_str: str,
        service_id: int = 1,
        duration_minutes: int = 60,
    ) -> Tuple[bool, Optional[str]]:
        """Create booking with ACID transaction (prevents race conditions)

        Args:
            user_id: Telegram user ID
            username: Telegram username
            date_str: Date in YYYY-MM-DD
            time_str: Time in HH:MM
            service_id: Service ID
            duration_minutes: Duration in minutes

        Returns:
            Tuple[success: bool, error_message: Optional[str]]

        Raises:
            ValidationError: If inputs are invalid
            DatabaseError: On critical database errors
        """
        # Validate inputs
        try:
            from datetime import datetime as dt

            date = dt.strptime(date_str, "%Y-%m-%d").date()
            time = dt.strptime(time_str, "%H:%M").time()

            booking_input = BookingCreateInput(
                user_id=user_id,
                username=username,
                date=date,
                time=time,
                service_id=service_id,
                duration_minutes=duration_minutes,
            )
        except PydanticValidationError as e:
            logger.warning(f"Booking validation failed: {e}")
            return False, f"Invalid input: {e.errors()[0]['msg']}"

        try:
            async with safe_operation(
                "create_booking",
                user_id=user_id,
                date=date_str,
                time=time_str,
            ):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    # BEGIN IMMEDIATE - locks database immediately
                    await db.execute("BEGIN IMMEDIATE")

                    try:
                        # 1. Check if slot is free (within transaction)
                        async with db.execute(
                            """
                            SELECT 1 FROM (
                                SELECT 1 FROM bookings WHERE date=? AND time=?
                                UNION ALL
                                SELECT 1 FROM blocked_slots WHERE date=? AND time=?
                            ) LIMIT 1
                            """,
                            (date_str, time_str, date_str, time_str),
                        ) as cursor:
                            if await cursor.fetchone():
                                await db.rollback()
                                return False, "Slot is already taken"

                        # 2. Check user booking limit
                        async with db.execute(
                            """SELECT COUNT(*) FROM bookings
                               WHERE user_id=? AND date >= date('now')""",
                            (user_id,),
                        ) as cursor:
                            count = (await cursor.fetchone())[0]
                            if count >= MAX_BOOKINGS_PER_USER:
                                await db.rollback()
                                return (
                                    False,
                                    f"Booking limit reached ({MAX_BOOKINGS_PER_USER})",
                                )

                        # 3. Create booking
                        await db.execute(
                            """
                            INSERT INTO bookings
                            (date, time, user_id, username, created_at, service_id, duration_minutes)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                date_str,
                                time_str,
                                user_id,
                                username,
                                now_local().isoformat(),
                                service_id,
                                duration_minutes,
                            ),
                        )

                        # COMMIT transaction
                        await db.commit()

                        logger.info(
                            f"Booking created: user={user_id}, slot={date_str} {time_str}"
                        )
                        return True, None

                    except aiosqlite.IntegrityError as e:
                        await db.rollback()
                        # Slot was taken between check and insert (rare)
                        logger.warning(f"Race condition detected: {e}")
                        return False, "Slot was just taken by another user"

                    except Exception as e:
                        await db.rollback()
                        raise

        except aiosqlite.Error as e:
            context = {
                "user_id": user_id,
                "date": date_str,
                "time": time_str,
            }
            can_retry = await handle_database_error(e, context)
            if can_retry:
                raise DatabaseError(f"Database error (retryable): {e}") from e
            else:
                return False, "Database error. Please try again later."

    @staticmethod
    @async_retry_on_error(max_attempts=3, delay=0.5)
    async def cancel_booking_atomic(
        booking_id: int, user_id: int, reason: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Cancel booking with transaction

        Args:
            booking_id: Booking ID
            user_id: User ID (for verification)
            reason: Cancellation reason

        Returns:
            Tuple[success: bool, error_message: Optional[str]]

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        try:
            cancel_input = BookingCancelInput(
                booking_id=booking_id, user_id=user_id, reason=reason
            )
        except PydanticValidationError as e:
            return False, f"Invalid input: {e.errors()[0]['msg']}"

        try:
            async with safe_operation(
                "cancel_booking", booking_id=booking_id, user_id=user_id
            ):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute("BEGIN IMMEDIATE")

                    try:
                        # 1. Get booking details
                        async with db.execute(
                            "SELECT date, time FROM bookings WHERE id=? AND user_id=?",
                            (booking_id, user_id),
                        ) as cursor:
                            booking = await cursor.fetchone()

                        if not booking:
                            await db.rollback()
                            return False, "Booking not found"

                        date_str, time_str = booking

                        # 2. Check cancellation policy
                        booking_dt_naive = datetime.strptime(
                            f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
                        )
                        booking_dt = TIMEZONE.localize(booking_dt_naive)
                        hours_until = (booking_dt - now_local()).total_seconds() / 3600

                        if hours_until < CANCELLATION_HOURS:
                            await db.rollback()
                            return (
                                False,
                                f"Can only cancel {CANCELLATION_HOURS}h before booking",
                            )

                        # 3. Delete booking
                        await db.execute(
                            "DELETE FROM bookings WHERE id=? AND user_id=?",
                            (booking_id, user_id),
                        )

                        await db.commit()

                        logger.info(
                            f"Booking cancelled: id={booking_id}, user={user_id}, "
                            f"reason={reason or 'none'}"
                        )
                        return True, None

                    except Exception as e:
                        await db.rollback()
                        raise

        except aiosqlite.Error as e:
            context = {"booking_id": booking_id, "user_id": user_id}
            await handle_database_error(e, context)
            return False, "Database error. Please try again."

    @staticmethod
    @async_retry_on_error(max_attempts=3, delay=0.5)
    async def block_slot_atomic(
        date_str: str, time_str: str, admin_id: int, reason: Optional[str] = None
    ) -> Tuple[bool, List[Dict], Optional[str]]:
        """Block slot with atomic transaction (cancels existing bookings)

        Args:
            date_str: Date in YYYY-MM-DD
            time_str: Time in HH:MM
            admin_id: Admin user ID
            reason: Block reason

        Returns:
            Tuple[
                success: bool,
                cancelled_users: List[Dict],
                error_message: Optional[str]
            ]

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        try:
            from datetime import datetime as dt

            date = dt.strptime(date_str, "%Y-%m-%d").date()
            time = dt.strptime(time_str, "%H:%M").time()

            block_input = SlotBlockInput(
                date=date, time=time, admin_id=admin_id, reason=reason
            )
        except PydanticValidationError as e:
            return False, [], f"Invalid input: {e.errors()[0]['msg']}"

        try:
            async with safe_operation(
                "block_slot", date=date_str, time=time_str, admin=admin_id
            ):
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute("BEGIN IMMEDIATE")

                    try:
                        # 1. Get existing bookings
                        async with db.execute(
                            "SELECT user_id, username FROM bookings WHERE date=? AND time=?",
                            (date_str, time_str),
                        ) as cursor:
                            existing_bookings = await cursor.fetchall()

                        cancelled_users = []
                        for user_id, username in existing_bookings:
                            cancelled_users.append(
                                {
                                    "user_id": user_id,
                                    "username": username or f"ID{user_id}",
                                    "date": date_str,
                                    "time": time_str,
                                    "reason": reason,
                                }
                            )

                        # 2. Delete existing bookings
                        if cancelled_users:
                            await db.execute(
                                "DELETE FROM bookings WHERE date=? AND time=?",
                                (date_str, time_str),
                            )

                        # 3. Create block
                        await db.execute(
                            """
                            INSERT INTO blocked_slots
                            (date, time, reason, blocked_by, blocked_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (date_str, time_str, reason, admin_id, now_local().isoformat()),
                        )

                        await db.commit()

                        logger.info(
                            f"Slot blocked: {date_str} {time_str} by admin {admin_id}, "
                            f"cancelled {len(cancelled_users)} bookings"
                        )
                        return True, cancelled_users, None

                    except aiosqlite.IntegrityError as e:
                        await db.rollback()
                        logger.warning(f"Slot already blocked: {e}")
                        return False, [], "Slot is already blocked"

                    except Exception as e:
                        await db.rollback()
                        raise

        except aiosqlite.Error as e:
            context = {"date": date_str, "time": time_str, "admin_id": admin_id}
            await handle_database_error(e, context)
            return False, [], "Database error. Please try again."

    # === KEEP ALL OTHER METHODS FROM ORIGINAL (they're already good) ===
    # Just add retry decorators where needed

    @staticmethod
    @async_retry_on_error(max_attempts=3, delay=0.5)
    async def get_occupied_slots_for_day(date_str: str) -> List[Tuple[str, int]]:
        """Get occupied slots with retry (unchanged from original)"""
        # ... (keep original implementation)
        occupied = []
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    """SELECT b.time, COALESCE(s.duration_minutes, 60) as duration
                    FROM bookings b
                    LEFT JOIN services s ON b.service_id = s.id
                    WHERE b.date = ?""",
                    (date_str,),
                ) as cursor:
                    bookings = await cursor.fetchall()
                    if bookings:
                        occupied.extend((time, duration) for time, duration in bookings)

                async with db.execute(
                    "SELECT time FROM blocked_slots WHERE date = ?", (date_str,)
                ) as cursor:
                    blocked = await cursor.fetchall()
                    if blocked:
                        occupied.extend((time, 60) for (time,) in blocked)

        except Exception as e:
            logger.error(f"Error getting occupied slots for {date_str}: {e}")

        return occupied

    @staticmethod
    @async_retry_on_error(max_attempts=2, delay=1.0)
    async def get_user_bookings(user_id: int) -> List[Tuple]:
        """Get user bookings with retry"""
        # ... (keep original implementation with retry)
        try:
            now = now_local()

            bookings = await BookingRepositoryV2._execute_query(
                """SELECT
                    b.id, b.date, b.time, b.username, b.created_at,
                    b.service_id,
                    COALESCE(s.name, 'Основная услуга') as service_name,
                    COALESCE(s.duration_minutes, 60) as duration_minutes,
                    COALESCE(s.price, '—') as price
                FROM bookings b
                LEFT JOIN services s ON b.service_id = s.id
                WHERE b.user_id = ?
                ORDER BY b.date, b.time""",
                (user_id,),
                fetch_all=True,
            )

            if not bookings:
                return []

            future_bookings = []
            for booking in bookings:
                booking_id, date_str, time_str = booking[0], booking[1], booking[2]
                booking_dt_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                booking_dt = TIMEZONE.localize(booking_dt_naive)
                if booking_dt >= now:
                    future_bookings.append(booking)

            return future_bookings
        except Exception as e:
            logger.error(f"Error getting bookings for user {user_id}: {e}")
            return []
