import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from aiohttp import web

from config import settings
from database import init_db, engine, async_session
from middlewares import DbSessionMiddleware, ThrottlingMiddleware
from handlers import start_router, search_router, callbacks_router, message_router
from services import create_webapp

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    # 1. Initialize Redis client and FSM Storage
    logger.info("Connecting to Redis...")
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = RedisStorage(redis_client)

    # 2. Initialize Bot and Dispatcher
    logger.info("Initializing Bot instance...")
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=storage)

    # 3. Setup Middlewares
    logger.info("Registering middlewares...")
    
    # Outer middleware on messages handles rate-limiting early, before filters
    dp.message.outer_middleware(
        ThrottlingMiddleware(
            redis=redis_client,
            voice_limit=settings.voice_throttle_rate,
            text_limit=settings.text_throttle_rate
        )
    )

    # Inner middlewares inject database session for database transactions
    dp.message.middleware(DbSessionMiddleware(session_pool=async_session))
    dp.callback_query.middleware(DbSessionMiddleware(session_pool=async_session))

    # 4. Include routers (Command handlers, callbacks, and generic messages)
    dp.include_router(start_router)
    dp.include_router(search_router)
    dp.include_router(callbacks_router)
    dp.include_router(message_router)

    # 5. Database Schema Initialization (run-once)
    logger.info("Ensuring PostgreSQL database tables are created...")
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}", exc_info=True)
        return

    # 6. Initialize and start the aiohttp Web Application for Telegram WebApp
    logger.info("Initializing aiohttp web server for Telegram WebApp...")
    app = create_webapp()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.web_host, settings.web_port)
    await site.start()
    logger.info(f"Web server is active and listening on http://{settings.web_host}:{settings.web_port}")

    # 7. Start bot polling
    logger.info("Starting Telegram Bot polling loop...")
    try:
        # Delete webhook before starting polling to clear pending updates
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        # Graceful shutdown of open connections and server runner
        logger.info("Shutting down resources (Web server, Redis, PostgreSQL)...")
        await runner.cleanup()
        await bot.session.close()
        await redis_client.close()
        await engine.dispose()
        logger.info("Bot application successfully stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution interrupted.")
