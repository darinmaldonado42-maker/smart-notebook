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
                notes_data.append({
                    "id": note.id,
                    "title": note.title,
                    "original_text": note.original_text,
                    "summary": note.summary,
                    "category": note.category,
                    "tasks": note.tasks,
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


def create_webapp() -> web.Application:
    """Configures and returns the web server Application instance."""
    
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        """Allow cross-origin requests from any domain (needed when frontend is on Timeweb)."""
        if request.method == "OPTIONS":
            return web.Response(headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Bypass-Tunnel-Reminder",
            })
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Bypass-Tunnel-Reminder"
        return response

    app = web.Application(middlewares=[cors_middleware])
    app["db_session"] = async_session
    
    # Routes
    app.router.add_get("/", serve_index)
    app.router.add_get("/style.css", serve_css)
    app.router.add_get("/app.js", serve_js)
    app.router.add_get("/api_config.js", serve_api_config)
    app.router.add_route("OPTIONS", "/api/notes", lambda r: web.Response())
    app.router.add_route("OPTIONS", "/api/notes/{id}", lambda r: web.Response())
    
    app.router.add_get("/api/notes", get_notes)
    app.router.add_delete("/api/notes/{id}", remove_note)
    
    return app
