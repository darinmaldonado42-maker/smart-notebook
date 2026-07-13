import os
import logging
import tempfile
import asyncio
import json
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from openai import AsyncOpenAI

# Import our executor module
import executor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load Telegram Bot credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in your .env file!")

# Load OpenAI credentials
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

if not OPENAI_API_KEY:
    logger.error("WARNING: OPENAI_API_KEY is not set in .env! Audio commands and translation will fail.")

# Initialize Aiogram Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Transcribe voice file to text using Whisper API
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

# Convert user request text into structured JSON command using GPT
async def parse_command_gpt(text: str) -> dict:
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    
    prompt = (
        "Ты — транслятор голосовых и текстовых команд для управления компьютером Windows.\n"
        "Проанализируй текст команды пользователя и верни строго JSON-объект.\n\n"
        "Доступные команды и их форматы:\n"
        "1. Скриншот экрана (захватывает оба монитора):\n"
        "   - Примеры: 'скриншот', 'покажи экран', 'экран', 'сделай скрин'\n"
        "   - JSON: {\"command\": \"screenshot\"}\n"
        "2. Открыть веб-ссылку / браузер:\n"
        "   - Примеры: 'открой яндекс', 'открой гугл', 'открой сайт [ссылка]'\n"
        "   - JSON: {\"command\": \"open_browser\", \"args\": {\"url\": \"ссылка\"}}\n"
        "3. Управление YouTube:\n"
        "   - Поиск видео: 'найди на ютубе как приготовить пиццу', 'поиск в ютубе [запрос]'\n"
        "     JSON: {\"command\": \"youtube\", \"args\": {\"query\": \"как приготовить пиццу\", \"mode\": \"search\"}}\n"
        "   - Переход на канал: 'открой канал влад бумага', 'канал @wylsacom на ютубе'\n"
        "     JSON: {\"command\": \"youtube\", \"args\": {\"query\": \"wylsacom\", \"mode\": \"channel\"}}\n"
        "   - Просто открыть YouTube: 'открой ютуб'\n"
        "     JSON: {\"command\": \"youtube\", \"args\": {\"query\": \"\", \"mode\": \"search\"}}\n"
        "4. Яндекс.Музыка в Яндекс.Браузере:\n"
        "   - Поиск/запуск трека: 'включи музыку queen', 'запусти яндекс музыку с песнями цоя'\n"
        "     JSON: {\"command\": \"yandex_music\", \"args\": {\"query\": \"queen\"}}\n"
        "   - Просто открыть Яндекс.Музыку: 'открой яндекс музыку'\n"
        "     JSON: {\"command\": \"yandex_music\", \"args\": {\"query\": \"\"}}\n"
        "5. Управление плеером и вкладками браузера (Media Controls):\n"
        "   - 'пауза', 'плей', 'продолжи', 'воспроизведение': {\"command\": \"media_control\", \"args\": {\"action\": \"play_pause\"}}\n"
        "   - 'следующий трек', 'включи следующее': {\"command\": \"media_control\", \"args\": {\"action\": \"next_track\"}}\n"
        "   - 'предыдущий трек': {\"command\": \"media_control\", \"args\": {\"action\": \"prev_track\"}}\n"
        "   - 'во весь экран', 'полный экран': {\"command\": \"media_control\", \"args\": {\"action\": \"fullscreen\"}}\n"
        "   - 'прокрути вниз', 'листай вниз': {\"command\": \"media_control\", \"args\": {\"action\": \"scroll_down\"}}\n"
        "   - 'прокрути вверх', 'листай вверх': {\"command\": \"media_control\", \"args\": {\"action\": \"scroll_up\"}}\n"
        "   - 'закрой вкладку', 'закрой страницу': {\"command\": \"media_control\", \"args\": {\"action\": \"close_tab\"}}\n"
        "   - 'новая вкладка': {\"command\": \"media_control\", \"args\": {\"action\": \"new_tab\"}}\n"
        "   - 'нажми ввод', 'нажми энтер': {\"command\": \"media_control\", \"args\": {\"action\": \"enter\"}}\n"
        "6. Запуск приложений Windows:\n"
        "   - Примеры: 'запусти калькулятор', 'открой блокнот', 'проводник', 'паинт', 'диспетчер задач'\n"
        "   - JSON: {\"command\": \"open_app\", \"args\": {\"app_name\": \"калькулятор|блокнот|проводник|паинт|диспетчер задач\"}}\n"
        "7. Громкость звука:\n"
        "   - Примеры: 'громче на 20', 'сделай тише', 'выключи звук'\n"
        "   - JSON: {\"command\": \"adjust_volume\", \"args\": {\"action\": \"up|down|mute\", \"amount\": число_от_2_до_100_по_умолчанию_10}}\n"
        "8. Выключение / Перезагрузка ПК:\n"
        "   - Примеры: 'выключи компьютер через 20 секунд', 'перезагрузи пк'\n"
        "   - JSON: {\"command\": \"shutdown\" или \"restart\", \"args\": {\"delay\": секунды_по_умолчанию_10}}\n\n"
        "Если команда не подходит ни под один пункт, верни: {\"command\": \"unknown\"}\n\n"
        "Верни ТОЛЬКО валидный JSON, без разметки ```json и лишних слов."
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
        return json.loads(content)
    except Exception as e:
        logger.error(f"Error parsing with GPT: {e}", exc_info=True)
        return {"command": "error", "error": str(e)}

# Command /start handler
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 <b>Привет! Я бот для удаленного управления твоим ПК.</b>\n\n"
        "Присылай мне <b>голосовые сообщения</b> или пиши <b>текстом</b>!\n\n"
        "<b>Доступный функционал:</b>\n"
        "📸 <code>скриншот</code> — снимок всех экранов компьютера\n"
        "📺 <code>открой ютуб [запрос]</code> / <code>канал [имя]</code> — поиск видео/каналов\n"
        "🎵 <code>включи [песню/автора]</code> — запуск трека в Яндекс.Музыке (в Яндекс.Браузере)\n"
        "⏯️ <code>плей/пауза</code>, <code>следующий трек</code>, <code>во весь экран</code>\n"
        "🖱️ <code>прокрути вниз</code> / <code>прокрути вверх</code>, <code>закрой вкладку</code>\n"
        "🖥️ <code>запусти калькулятор / блокнот / проводник</code>\n"
        "🔊 <code>сделай громче / тише</code>, <code>выключи звук</code>\n"
        "🔌 <code>выключи / перезагрузи компьютер</code>\n",
        parse_mode="HTML"
    )

# Voice messages handler
@dp.message(F.voice)
async def handle_voice_message(message: types.Message):
    await message.reply("⏳ <i>Обрабатываю голосовую команду...</i>", parse_mode="HTML")
    
    ogg_path = ""
    try:
        voice = message.voice
        file_info = await bot.get_file(voice.file_id)
        
        # Create temp file
        fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        
        await bot.download_file(file_info.file_path, ogg_path)
        logger.info(f"Downloaded voice note to {ogg_path}")
        
        # 1. Transcribe
        transcript = await transcribe_voice(ogg_path)
        logger.info(f"Whisper transcript: {transcript}")
        
        if not transcript:
            await message.reply("⚠️ Не удалось распознать речь. Попробуй сказать громче или четче.")
            return
            
        await message.reply(f"🎙️ <b>Услышал:</b> <i>\"{transcript}\"</i>", parse_mode="HTML")
        
        # 2. Parse command
        cmd_data = await parse_command_gpt(transcript)
        logger.info(f"Parsed JSON command: {cmd_data}")
        
        if cmd_data.get("command") == "unknown":
            await message.reply("❓ Команда не распознана. Попробуйте сформулировать иначе.")
            return
            
        # 3. Execute command
        status, file_to_send = executor.execute_command_dict(cmd_data)
        
        # Send status and optional screenshot
        await message.reply(f"⚙️ <b>Результат:</b> {status}", parse_mode="HTML")
        if file_to_send and os.path.exists(file_to_send):
            await message.reply_document(types.FSInputFile(file_to_send))
            try:
                os.remove(file_to_send)
            except Exception as ex:
                logger.error(f"Error removing temp output file {file_to_send}: {ex}")
                
    except Exception as e:
        logger.error(f"Error handling voice message: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка при выполнении голосовой команды: {e}")
    finally:
        if ogg_path and os.path.exists(ogg_path):
            try:
                os.remove(ogg_path)
            except Exception as ex:
                logger.error(f"Error removing temp ogg file {ogg_path}: {ex}")

# Text messages handler
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    text_query = message.text.strip()
    
    # Ignore commands starting with slash (they are handled by CommandStart, etc.)
    if text_query.startswith("/"):
        return
        
    await message.reply("⏳ <i>Выполняю текстовую команду...</i>", parse_mode="HTML")
    
    try:
        # 1. Parse command
        cmd_data = await parse_command_gpt(text_query)
        logger.info(f"Parsed text command JSON: {cmd_data}")
        
        if cmd_data.get("command") == "unknown":
            await message.reply("❓ Команда не распознана. Попробуйте перефразировать.")
            return
            
        # 2. Execute command
        status, file_to_send = executor.execute_command_dict(cmd_data)
        
        # Send status and optional screenshot
        await message.reply(f"⚙️ <b>Результат:</b> {status}", parse_mode="HTML")
        if file_to_send and os.path.exists(file_to_send):
            await message.reply_document(types.FSInputFile(file_to_send))
            try:
                os.remove(file_to_send)
            except Exception as ex:
                logger.error(f"Error removing temp file {file_to_send}: {ex}")
                
    except Exception as e:
        logger.error(f"Error handling text command: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка при выполнении команды: {e}")

async def main():
    logger.info("Starting Telegram PC Control Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
