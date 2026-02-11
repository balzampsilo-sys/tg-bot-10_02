"""Database retry decorator with exponential backoff

Provides automatic retry logic for database operations to handle:
- Transient connection errors
- Database locked errors (SQLite)
- Network timeouts

Usage:
    @db_retry(max_retries=3)
    async def my_db_operation():
        async with aiosqlite.connect(DATABASE_PATH) as db:
            ...
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, Any

import aiosqlite

from config import DB_MAX_RETRIES, DB_RETRY_DELAY, DB_RETRY_BACKOFF

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Exceptions that should trigger retry
RETRYABLE_ERRORS = (
    aiosqlite.OperationalError,  # Database locked, unable to open
    aiosqlite.DatabaseError,      # Database disk image malformed (rare)
    ConnectionError,              # Network errors
    TimeoutError,                 # Operation timeout
)


def db_retry(
    max_retries: int = DB_MAX_RETRIES,
    base_delay: float = DB_RETRY_DELAY,
    backoff: float = DB_RETRY_BACKOFF,
    retryable_errors: tuple = RETRYABLE_ERRORS
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry database operations with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        retryable_errors: Tuple of exception types to retry on
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except retryable_errors as e:
                    last_exception = e
                    
                    if attempt >= max_retries:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries} retries: {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"⚠️ {func.__name__} attempt {attempt + 1}/{max_retries + 1} "
                        f"failed: {e}. Retrying in {delay:.2f}s..."
                    )
                    
                    await asyncio.sleep(delay)
                    delay *= backoff
                    
                except Exception as e:
                    # Non-retryable error, raise immediately
                    logger.error(f"❌ {func.__name__} failed with non-retryable error: {e}")
                    raise
            
            # Should never reach here, but for type safety
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


# Convenience wrapper for common database operations
class DBRetry:
    """Context manager for database operations with retry logic"""
    
    def __init__(self, db_path: str, **retry_kwargs):
        self.db_path = db_path
        self.retry_kwargs = retry_kwargs
        self.connection = None
    
    async def __aenter__(self) -> aiosqlite.Connection:
        @db_retry(**self.retry_kwargs)
        async def connect():
            return await aiosqlite.connect(self.db_path)
        
        self.connection = await connect()
        return self.connection
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            await self.connection.close()
        return False
