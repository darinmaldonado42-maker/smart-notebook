import os
import logging
import tempfile
import asyncio
import json
import uuid
import base64
from dotenv import load_dotenv
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from openai import AsyncOpenAI

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env!")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = 8080

# Initialize Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Global WebSocket references
active_client_ws = None
pending_requests = {}  # request_id -> asyncio.Future

# Helper to process local voice commands from the client PC
async def handle_local_voice_command(ws, text):
    try:
        commands = await parse_commands_gpt(text)
        logger.info(f"Parsed local commands: {commands}")
        for cmd in commands:
            req_id = f"local-{uuid.uuid4()}"
            await ws.send_json({
                "type": "execute",
                "request_id": req_id,
                "command": cmd
            })
    except Exception as e:
        logger.error(f"Error handling local voice command: {e}")

# aiohttp WebSocket Handler
async def websocket_handler(request):
    global active_client_ws
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    logger.info("New incoming WebSocket connection attempt...")
    
    authenticated = False
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except Exception:
                    logger.warning("Received invalid JSON message from client.")
                    continue
                
                # Handle auth message
                if not authenticated:
                    if data.get("type") == "auth" and data.get("secret") == BOT_TOKEN:
                        authenticated = True
                        active_client_ws = ws
                        await ws.send_json({"type": "auth_ok"})
                        logger.info("PC client successfully authenticated.")
                    else:
                        logger.warning("Authentication failed. Closing connection.")
                        await ws.send_json({"type": "auth_failed", "reason": "Invalid secret"})
                        await ws.close()
                        break
                    continue
                
                # Handle execution results
                if data.get("type") == "result":
                    req_id = data.get("request_id")
                    logger.info(f"Received execution result for request {req_id}")
                    fut = pending_requests.get(req_id)
                    if fut and not fut.done():
                        fut.set_result(data)
                
                # Handle local voice commands triggered on the client PC
                elif data.get("type") == "local_voice_command":
                    text = data.get("text", "")
                    logger.info(f"Received local voice command from client: {text}")
                    asyncio.create_task(handle_local_voice_command(ws, text))
                        
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}", exc_info=True)
    finally:
        if active_client_ws == ws:
            active_client_ws = None
            logger.info("PC client disconnected.")
            
    return ws

# Transcribe voice file using Whisper API
async def transcribe_voice(filepath: str) -> str:
    try:
        openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        with open(filepath, "rb") as audio_file:
            response = await openai_client.audio.transcriptions.create(
                model=OPENAI_WHISPER_MODEL,
                file=audio_file
            )
            return response.text.strip()
    except Exception as e:
        logger.error(f"Error in Whisper transcription: {e}", exc_info=True)
        return ""

# Convert user request text into structured JSON list of commands using GPT
async def parse_commands_gpt(text: str) -> list[dict]:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    
    prompt = (
        "Ты — сверхразумный ИИ-транслятор голосовых и текстовых команд для управления Windows ПК.\n"
        "Пользователь может сказать ОДНУ или НЕСКОЛЬКО команд в одном предложении.\n"
        "Проанализируй запрос и верни строго JSON-список объектов (команд) в порядке их выполнения.\n\n"
        "Каждая команда может содержать параметр \"target_screen\": \"main\" (первый/основной монитор, по умолчанию) "
        "или \"second\" (второй монитор, если пользователь указал 'на втором экране', 'на второй монитор').\n\n"
        "Доступные команды и их параметры:\n"
        "1. Скриншот: {\"command\": \"screenshot\"}\n"
        "2. Открыть браузер: {\"command\": \"open_browser\", \"args\": {\"url\": \"ссылка\", \"target_screen\": \"main|second\"}}\n"
        "3. YouTube: {\"command\": \"youtube\", \"args\": {\"query\": \"поисковый запрос или пусто\", \"mode\": \"search|channel\", \"target_screen\": \"main|second\"}}\n"
        "4. Яндекс.Музыка: {\"command\": \"yandex_music\", \"args\": {\"query\": \"название трека/артиста или пусто\", \"target_screen\": \"main|second\"}}\n"
        "5. Клавиатура и Мультимедиа (Media Control):\n"
        "   {\"command\": \"media_control\", \"args\": {\"action\": \"play_pause|next_track|prev_track|fullscreen|scroll_down|scroll_up|close_tab|new_tab|enter\"}}\n"
        "6. Запуск приложений: {\"command\": \"open_app\", \"args\": {\"app_name\": \"калькулятор|блокнот|проводник|паинт|vs code\", \"target_screen\": \"main|second\"}}\n"
        "7. Громкость: {\"command\": \"adjust_volume\", \"args\": {\"action\": \"up|down|mute\", \"amount\": число_громкости_по_умолчанию_10}}\n"
        "8. Переместить окно: {\"command\": \"move_window\", \"args\": {\"keyword\": \"название приложения (например: yandex, code)\", \"target_screen\": \"main|second\"}}\n"
        "9. ДИНАМИЧЕСКИЙ СКРИПТ (САМОАДАПТАЦИЯ И КЛИКИ НА ЭКРАНЕ):\n"
        "   Если пользователь просит совершить действие на странице (кликнуть на видео, включить 'Мою волну', запустить воспроизведение):\n"
        "   Ты должен сгенерировать Python-скрипт с использованием `pyautogui`, `pygetwindow as gw` и `time`!\n"
        "   КРИТИЧЕСКИ ВАЖНО: на Windows первый клик по неактивному окну только переводит на него фокус. "
        "   Поэтому скрипт должен СНАЧАЛА найти окно браузера (например, содержащее в заголовке 'yandex', 'янд' или 'youtube'), "
        "   активировать его через `win.activate()`, подождать 0.5 секунд, и только потом кликать!\n"
        "   - Пример для 'включи мою волну' (Яндекс.Музыка):\n"
        "     Код: \n"
        "     import webbrowser, time, pyautogui\n"
        "     import pygetwindow as gw\n"
        "     # 1. Открываем или фокусируем браузер\n"
        "     webbrowser.open('https://music.yandex.ru/home')\n"
        "     time.sleep(2.5)\n"
        "     try:\n"
        "         win = [w for w in gw.getAllWindows() if 'yandex' in w.title.lower() or 'яндекс' in w.title.lower()][0]\n"
        "         win.activate()\n"
        "         time.sleep(0.5)\n"
        "     except:\n"
        "         pass\n"
        "     # 2. Кликаем на пункт 'Моя волна' в левом меню (x=100, y=260)\n"
        "     pyautogui.click(100, 260)\n"
        "     time.sleep(1.0)\n"
        "     # 3. Кликаем на желтую круглую кнопку воспроизведения внизу по центру (x=725, y=810)\n"
        "     pyautogui.click(725, 810)\n"
        "   - Пример для 'открой первое видео' (на главной YouTube):\n"
        "     Код: \n"
        "     import time, pyautogui\n"
        "     import pygetwindow as gw\n"
        "     try:\n"
        "         win = [w for w in gw.getAllWindows() if 'youtube' in w.title.lower() or 'yandex' in w.title.lower()][0]\n"
        "         win.activate()\n"
        "         time.sleep(0.5)\n"
        "     except:\n"
        "         pass\n"
        "     # Кликаем на область первого видео в сетке рекомендаций (x=280, y=350)\n"
        "     pyautogui.click(280, 350)\n"
        "   - Любые другие действия — переводи в готовый скрипт python с фокусом окна и кликами.\n"
        "10. Выключение/Перезагрузка: {\"command\": \"shutdown\" или \"restart\", \"args\": {\"delay\": секунды_по_умолчанию_10}}\n\n"
        "ПРИМЕР ВЫХОДНЫХ ДАННЫХ (для запроса: 'открой клип queen на втором экране, сделай громче на 20 и открой vs code'):\n"
        "[\n"
        "  {\"command\": \"youtube\", \"args\": {\"query\": \"queen\", \"mode\": \"search\", \"target_screen\": \"second\"}},\n"
        "  {\"command\": \"adjust_volume\", \"args\": {\"action\": \"up\", \"amount\": 20}},\n"
        "  {\"command\": \"open_app\", \"args\": {\"app_name\": \"vs code\", \"target_screen\": \"main\"}}\n"
        "]\n\n"
        "Верни ТОЛЬКО валидный JSON-список без разметки ```json и лишнего текста."
    )
    
    try:
        response = await openai_client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            temperature=0.0
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
        
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return [parsed]
        return []
    except Exception as e:
        logger.error(f"Error parsing with GPT: {e}", exc_info=True)
        return [{"command": "error", "error": str(e)}]

# Core Pipeline to execute query via WebSocket client
async def execute_query_pipeline(message: types.Message, query_text: str):
    global active_client_ws
    
    # 1. Check if PC client is connected
    if not active_client_ws:
        await message.reply("❌ <b>Ваш домашний ПК сейчас не в сети (оффлайн).</b>\nЗапустите client.py на компьютере.", parse_mode="HTML")
        return
        
    # 2. Parse commands
    commands = await parse_commands_gpt(query_text)
    logger.info(f"Resolved commands: {commands}")
    
    if not commands:
        await message.reply("❓ Команды не распознаны.")
        return
        
    await message.reply(f"⚡ <b>Отправляю {len(commands)} задач на выполнение...</b>", parse_mode="HTML")
    
    # 3. Create requests futures and send to client
    loop = asyncio.get_event_loop()
    
    for i, cmd in enumerate(commands):
        cmd_name = cmd.get("command", "")
        if cmd_name == "unknown":
            await message.reply(f"❓ Шаг {i+1}: Команда не распознана.")
            continue
            
        req_id = str(uuid.uuid4())
        fut = loop.create_future()
        pending_requests[req_id] = fut
        
        try:
            # Send command over websocket
            await active_client_ws.send_json({
                "type": "execute",
                "request_id": req_id,
                "command": cmd
            })
            
            # Wait for response (with 35 seconds timeout per command)
            response = await asyncio.wait_for(fut, timeout=35.0)
            
            status = response.get("status", "Выполнено")
            screenshot_b64 = response.get("screenshot")
            
            await message.reply(f"✅ <b>Шаг {i+1}/{len(commands)} ({cmd_name}):</b> {status}", parse_mode="HTML")
            
            # Send screenshot if present
            if screenshot_b64:
                screenshot_bytes = base64.b64decode(screenshot_b64)
                buffered_img = types.BufferedInputFile(screenshot_bytes, filename="screenshot.png")
                await message.reply_document(buffered_img)
                
        except asyncio.TimeoutError:
            await message.reply(f"❌ <b>Ошибка шага {i+1}:</b> Превышено время ожидания ответа от ПК.")
            break
        except Exception as e:
            logger.error(f"Error executing step {i+1}: {e}")
            await message.reply(f"❌ <b>Ошибка на шаге {i+1}:</b> {e}")
            break
        finally:
            pending_requests.pop(req_id, None)
            
    await message.reply("🏁 <b>Обработка конвейера задач завершена.</b>", parse_mode="HTML")

# Command /start handler
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    pc_status = "🟢 <b>В сети (онлайн)</b>" if active_client_ws else "🔴 <b>Не в сети (оффлайн)</b>"
    await message.reply(
        f"👋 <b>Привет! Я бот для управления твоим ПК.</b>\n"
        f"Статус домашнего компьютера: {pc_status}\n\n"
        f"Присылай мне <b>голосовые сообщения</b> или пиши <b>текстом</b>!\n\n"
        f"<b>Примеры команд:</b>\n"
        f"• <code>скриншот</code> — снимок экрана ПК\n"
        f"• <code>открой ютуб [запрос] на втором экране</code>\n"
        f"• <code>включи [песню]</code> — в Яндекс.Музыке\n"
        f"• <code>плей / пауза</code>, <code>следующий трек</code>, <code>тише / громче</code>\n"
        f"• <code>запусти блокнот / калькулятор</code>\n"
        f"• <code>перемести окно yandex на второй экран</code>\n",
        parse_mode="HTML"
    )

# Voice message handler
@dp.message(F.voice)
async def handle_voice(message: types.Message):
    await message.reply("⏳ <i>Распознаю голос...</i>", parse_mode="HTML")
    ogg_path = ""
    try:
        voice = message.voice
        file_info = await bot.get_file(voice.file_id)
        
        fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        
        await bot.download_file(file_info.file_path, ogg_path)
        transcript = await transcribe_voice(ogg_path)
        
        if not transcript:
            await message.reply("⚠️ Речь не распознана.")
            return
            
        await message.reply(f"🎙️ <b>Услышал:</b> <i>\"{transcript}\"</i>", parse_mode="HTML")
        await execute_query_pipeline(message, transcript)
    except Exception as e:
        logger.error(f"Error handling voice: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {e}")
    finally:
        if ogg_path and os.path.exists(ogg_path):
            try:
                os.remove(ogg_path)
            except Exception:
                pass

# Text message handler
@dp.message(F.text)
async def handle_text(message: types.Message):
    query = message.text.strip()
    if query.startswith("/"):
        return
    await execute_query_pipeline(message, query)

# Combined handler for root health check and WebSocket upgrades
async def root_handler(request):
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await websocket_handler(request)
    return web.Response(text="OK")

# Concurrent Web Server + Telegram Polling
async def main():
    # Setup aiohttp Server
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/ws', websocket_handler) # Keep /ws route as fallback
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host=WEB_HOST, port=WEB_PORT)
    await site.start()
    logger.info(f"WebSocket Cloud Server running on ws://{WEB_HOST}:{WEB_PORT}/ws")
    
    # Start Telegram Bot Polling
    logger.info("Starting Telegram polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
