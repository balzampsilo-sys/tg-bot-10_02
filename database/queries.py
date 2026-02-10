# Добавить в конец файла метод для получения service_id из бронирования

    @staticmethod
    async def get_booking_service_id(booking_id: int) -> int | None:
        """Получить service_id из бронирования
        
        Args:
            booking_id: ID бронирования
            
        Returns:
            service_id или None если не найдено
        """
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                async with db.execute(
                    "SELECT service_id FROM bookings WHERE id=?",
                    (booking_id,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logging.error(f"Error getting booking service_id: {e}")
            return None
