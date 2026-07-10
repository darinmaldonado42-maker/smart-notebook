from typing import Any, Callable, Dict, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from redis.asyncio import Redis

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, voice_limit: float = 5.0, text_limit: float = 1.0):
        super().__init__()
        self.redis = redis
        self.voice_limit = voice_limit
        self.text_limit = text_limit

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Rate limit only applies to user messages
        if not isinstance(event, Message) or not event.from_user:
            return await handler(event, data)

        user_id = event.from_user.id
        
        # Identify message type and apply appropriate limit
        is_voice = bool(event.voice or event.audio or event.video_note)
        limit = self.voice_limit if is_voice else self.text_limit
        action_type = "voice" if is_voice else "text"

        redis_key = f"throttle:{action_type}:{user_id}"

        # Query Redis for rate limit key
        is_throttled = await self.redis.get(redis_key)
        if is_throttled:
            if is_voice:
                await event.answer(
                    f"⚠️ Пожалуйста, отправляйте голосовые сообщения не чаще, чем раз в {int(self.voice_limit)} секунд."
                )
            else:
                await event.answer("⚠️ Вы отправляете сообщения слишком быстро!")
            return  # Stop processing further handlers

        # Set rate limit lock with TTL in milliseconds (px)
        await self.redis.set(redis_key, "1", px=int(limit * 1000))

        return await handler(event, data)
