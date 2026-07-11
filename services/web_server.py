import hmac
import hashlib
import json
import logging
from urllib.parse import parse_qsl
from aiohttp import web
from sqlalchemy import select

from config import settings
from database import async_session
from database.models import Note
from database.crud import delete_note

logger = logging.getLogger(__name__)

def validate_init_data(init_data: str, token: str) -> dict | None:
    """
    Validates Telegram Web App initData using HMAC-SHA256 signature verification.
    Returns the user data dict if authentic, otherwise None.
    """
    try:
        parsed_data = dict(parse_qsl(init_data))
        if "hash" not in parsed_data:
            return None
        
        received_hash = parsed_data.pop("hash")
        
        # Build check string by sorting keys alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # Calculate key: HMAC-SHA256("WebAppData", token)
        secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        
        # Calculate hash: HMAC-SHA256(secret_key, data_check_string)
        local_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if local_hash == received_hash:
            # Authentic data. Parse user JSON
            user_json = parsed_data.get("user", "{}")
            return json.loads(user_json)
    except Exception as e:
        logger.error(f"Error validating initData: {e}")
    return None

def get_authenticated_user(request: web.Request) -> dict | None:
    """
    Retrieves user from Authorization header.
    Allows query parameter fallback for browser link access.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("tma "):
        user_id = request.query.get("user_id")
        if user_id:
            try:
                return {"id": int(user_id), "first_name": "Пользователь"}
            except ValueError:
                pass
        return None
    
    init_data = auth_header[4:] # Strip "tma "
    return validate_init_data(init_data, settings.bot_token)


# Handler actions
async def serve_index(request: web.Request):
    return web.FileResponse("webapp/index.html", headers={"Cache-Control": "no-cache"})

async def serve_css(request: web.Request):
    return web.FileResponse("webapp/style.css", headers={"Cache-Control": "no-cache"})

async def serve_js(request: web.Request):
    return web.FileResponse("webapp/app.js", headers={"Cache-Control": "no-cache"})

async def serve_api_config(request: web.Request):
    """Serves a dynamic api_config.js with the current API base URL (empty = same origin)."""
    content = "window.API_BASE = '';\n"
    return web.Response(
        text=content,
        content_type="application/javascript",
        headers={"Cache-Control": "no-cache"}
    )

async def get_notes(request: web.Request):
    """API endpoint: GET /api/notes"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    user_id = user["id"]
    
    try:
        async with request.app["db_session"]() as session:
            stmt = select(Note).where(Note.user_id == user_id).order_by(Note.created_at.desc())
            result = await session.execute(stmt)
            notes = result.scalars().all()
            
            notes_data = []
            for note in notes:
                # Dynamically convert legacy string tasks array to objects array
                formatted_tasks = []
                if note.tasks:
                    for t in note.tasks:
                        if isinstance(t, str):
                            formatted_tasks.append({"text": t, "completed": False})
                        elif isinstance(t, dict):
                            formatted_tasks.append({
                                "text": t.get("text", ""),
                                "completed": t.get("completed", False)
                            })
                
                notes_data.append({
                    "id": note.id,
                    "title": note.title,
                    "original_text": note.original_text,
                    "summary": note.summary,
                    "category": note.category,
                    "tasks": formatted_tasks,
                    "reminder_at": note.reminder_at.isoformat() if note.reminder_at else None,
                    "reminder_sent": note.reminder_sent,
                    "created_at": note.created_at.isoformat()
                })
            
            return web.json_response({"notes": notes_data})
    except Exception as e:
        logger.error(f"Error fetching notes for WebApp: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)

async def remove_note(request: web.Request):
    """API endpoint: DELETE /api/notes/{id}"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
        
    user_id = user["id"]
    try:
        note_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "Invalid note ID"}, status=400)

    try:
        async with request.app["db_session"]() as session:
            success = await delete_note(session, user_id=user_id, note_id=note_id)
            if success:
                return web.json_response({"status": "success"})
            else:
                return web.json_response({"error": "Note not found"}, status=404)
    except Exception as e:
        logger.error(f"Error deleting note {note_id} for WebApp: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


async def create_note_api(request: web.Request):
    """API endpoint: POST /api/notes"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    user_id = user["id"]
    try:
        data = await request.json()
        title = data.get("title", "")
        summary = data.get("summary", "")
        category = data.get("category", "Повседневное")
        tasks = data.get("tasks", [])
        original_text = data.get("original_text", "Создано вручную")
        
        reminder_at = None
        reminder_at_raw = data.get("reminder_at")
        if reminder_at_raw:
            from datetime import datetime
            reminder_at = datetime.fromisoformat(reminder_at_raw.replace("Z", "+00:00"))
            
        async with request.app["db_session"]() as session:
            from database.crud import create_note
            note = await create_note(
                session=session,
                user_id=user_id,
                title=title,
                original_text=original_text,
                summary=summary,
                category=category,
                tasks=tasks,
                reminder_at=reminder_at
            )
            return web.json_response({
                "id": note.id,
                "title": note.title,
                "original_text": note.original_text,
                "summary": note.summary,
                "category": note.category,
                "tasks": note.tasks,
                "reminder_at": note.reminder_at.isoformat() if note.reminder_at else None,
                "created_at": note.created_at.isoformat()
            })
    except Exception as e:
        logger.error(f"Error creating note manually: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


async def update_note_api(request: web.Request):
    """API endpoint: PUT /api/notes/{id}"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
        
    user_id = user["id"]
    try:
        note_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "Invalid note ID"}, status=400)
        
    try:
        data = await request.json()
        title = data.get("title")
        summary = data.get("summary")
        category = data.get("category")
        tasks = data.get("tasks")
        original_text = data.get("original_text")
        
        reminder_at_passed = "reminder_at" in data
        reminder_at = None
        if reminder_at_passed:
            reminder_at_raw = data.get("reminder_at")
            if reminder_at_raw:
                from datetime import datetime
                reminder_at = datetime.fromisoformat(reminder_at_raw.replace("Z", "+00:00"))
                
        async with request.app["db_session"]() as session:
            from database.crud import update_note
            # Build arguments dynamically to avoid overwriting with None
            kwargs = {}
            if title is not None: kwargs["title"] = title
            if category is not None: kwargs["category"] = category
            if summary is not None: kwargs["summary"] = summary
            if tasks is not None: kwargs["tasks"] = tasks
            if original_text is not None: kwargs["original_text"] = original_text
            if reminder_at_passed: kwargs["reminder_at"] = reminder_at
            
            note = await update_note(
                session=session,
                user_id=user_id,
                note_id=note_id,
                **kwargs
            )
            if not note:
                return web.json_response({"error": "Note not found"}, status=404)
                
            return web.json_response({
                "id": note.id,
                "title": note.title,
                "original_text": note.original_text,
                "summary": note.summary,
                "category": note.category,
                "tasks": note.tasks,
                "reminder_at": note.reminder_at.isoformat() if note.reminder_at else None,
                "created_at": note.created_at.isoformat()
            })
    except Exception as e:
        logger.error(f"Error updating note {note_id}: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


async def get_avatar(request: web.Request):
    """Proxy avatar from Telegram Bot API securely."""
    user_id_str = request.query.get("user_id")
    if not user_id_str:
        return web.Response(status=400, text="Missing user_id", headers={"Access-Control-Allow-Origin": "*"})
    try:
        user_id = int(user_id_str)
    except ValueError:
        return web.Response(status=400, text="Invalid user_id", headers={"Access-Control-Allow-Origin": "*"})
        
    bot = request.app.get("bot")
    if not bot:
        return web.Response(status=500, text="Bot not initialized", headers={"Access-Control-Allow-Origin": "*"})
        
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos and photos.photos:
            file_id = photos.photos[0][0].file_id
            file_info = await bot.get_file(file_id)
            
            # Download file bytes
            from io import BytesIO
            dest = BytesIO()
            await bot.download(file_info, destination=dest)
            dest.seek(0)
            
            return web.Response(
                body=dest.read(),
                content_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*"
                }
            )
    except Exception as e:
        logger.error(f"Error serving avatar for user {user_id}: {e}")
        
    return web.Response(status=404, text="Avatar not found", headers={"Access-Control-Allow-Origin": "*"})


async def get_categories(request: web.Request):
    """GET /api/categories"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    user_id = user["id"]
    
    try:
        async with request.app["db_session"]() as session:
            from database.crud import get_user_categories
            categories = await get_user_categories(session, user_id)
            data = [{"id": c.id, "name": c.name, "color": c.color, "icon": c.icon} for c in categories]
            return web.json_response({"categories": data})
    except Exception as e:
        logger.error(f"Error getting categories for user {user_id}: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


async def create_category_api(request: web.Request):
    """POST /api/categories"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    user_id = user["id"]
    
    try:
        req_data = await request.json()
        name = req_data.get("name")
        color = req_data.get("color")
        icon = req_data.get("icon", "tag") # default to tag
        if not name or not color:
            return web.json_response({"error": "Missing name or color"}, status=400)
            
        async with request.app["db_session"]() as session:
            from database.crud import create_user_category
            cat = await create_user_category(session, user_id, name, color, icon)
            return web.json_response({"id": cat.id, "name": cat.name, "color": cat.color, "icon": cat.icon})
    except Exception as e:
        logger.error(f"Error creating category for user {user_id}: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


async def remove_category_api(request: web.Request):
    """DELETE /api/categories/{id}"""
    user = get_authenticated_user(request)
    if not user:
        return web.json_response({"error": "Unauthorized"}, status=401)
    user_id = user["id"]
    
    try:
        cat_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "Invalid category ID"}, status=400)
        
    try:
        async with request.app["db_session"]() as session:
            from database.crud import delete_user_category
            success = await delete_user_category(session, user_id, cat_id)
            if success:
                return web.json_response({"status": "success"})
            else:
                return web.json_response({"error": "Category not found"}, status=404)
    except Exception as e:
        logger.error(f"Error deleting category {cat_id} for user {user_id}: {e}", exc_info=True)
        return web.json_response({"error": "Internal Server Error"}, status=500)


def create_webapp(bot) -> web.Application:
    """Configures and returns the web server Application instance."""
    
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        """Allow cross-origin requests from any domain (needed when frontend is on Timeweb)."""
        if request.method == "OPTIONS":
            return web.Response(headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Bypass-Tunnel-Reminder",
            })
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Bypass-Tunnel-Reminder"
        return response

    app = web.Application(middlewares=[cors_middleware])
    app["db_session"] = async_session
    app["bot"] = bot
    
    # Routes
    app.router.add_get("/", serve_index)
    app.router.add_get("/style.css", serve_css)
    app.router.add_get("/app.js", serve_js)
    app.router.add_get("/api_config.js", serve_api_config)
    
    app.router.add_route("OPTIONS", "/api/notes", lambda r: web.Response())
    app.router.add_route("OPTIONS", "/api/notes/{id}", lambda r: web.Response())
    app.router.add_route("OPTIONS", "/api/categories", lambda r: web.Response())
    app.router.add_route("OPTIONS", "/api/categories/{id}", lambda r: web.Response())
    app.router.add_route("OPTIONS", "/api/avatar", lambda r: web.Response())
    
    app.router.add_get("/api/notes", get_notes)
    app.router.add_post("/api/notes", create_note_api)
    app.router.add_put("/api/notes/{id}", update_note_api)
    app.router.add_delete("/api/notes/{id}", remove_note)
    
    app.router.add_get("/api/categories", get_categories)
    app.router.add_post("/api/categories", create_category_api)
    app.router.add_delete("/api/categories/{id}", remove_category_api)
    app.router.add_get("/api/avatar", get_avatar)
    
    return app
