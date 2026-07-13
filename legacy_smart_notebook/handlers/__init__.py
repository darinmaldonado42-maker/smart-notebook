from handlers.start import router as start_router
from handlers.search import router as search_router
from handlers.callbacks import router as callbacks_router
from handlers.message import router as message_router

__all__ = [
    "start_router",
    "search_router",
    "callbacks_router",
    "message_router",
]
