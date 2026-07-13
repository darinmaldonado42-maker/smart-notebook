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

# Initialize Aiogram Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
        "9. ДИНАМИЧЕСКИЙ СКРИПТ (САМОАДАПТАЦИЯ):\n"
        "   Если пользователь просит написать код, сделать сложную последовательность кликов, нажать горячие клавиши, "
        "   создать текстовый файл или выполнить действия, которых нет в списке выше — сгенерируй готовый Python-скрипт на базе pyautogui/os/sys/time "
        "   и верни его в этой команде!\n"
        "   Формат: {\"command\": \"run_custom_script\", \"args\": {\"script_code\": \"код на python\"}}\n"
        "   Важно: пиши код надежно, импортируй нужные библиотеки, обрабатывай ошибки.\n"
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

# Command /start handler
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 <b>Привет! Я бот-автоматизатор для управления твоим ПК.</b>\n\n"
        "Я умею выполнять <b>несколько задач одновременно</b>, открывать окна на <b>первом или втором экране</b>, "
        "а также <b>самостоятельно писать и запускать скрипты</b> для решения нестандартных задач!\n\n"
        "🎙️ Присылай мне голосовые сообщения или пиши текстом.\n\n"
        "<b>Примеры сложных запросов:</b>\n"
        "• <i>\"Включи клип Цоя на втором экране и открой VS Code на основном\"</i>\n"
        "• <i>\"Сделай скриншот, убавь звук на 10 и открой блокнот\"</i>\n"
        "• <i>\"Напиши скрипт который создаст файл hello.txt на рабочем столе и запусти его\"</i>",
        parse_mode="HTML"
    )

# Common processor for text query
async def execute_query_pipeline(message: types.Message, query_text: str):
    # 1. Parse into command list
    commands = await parse_commands_gpt(query_text)
    logger.info(f"Resolved commands list: {commands}")
    
    if not commands:
        await message.reply("❓ Команды не распознаны.")
        return
        
    # 2. Iterate and execute commands
    for i, cmd in enumerate(commands):
        command_name = cmd.get("command", "")
        if command_name == "unknown":
            await message.reply(f"❓ Шаг {i+1}: Команда не распознана.")
            continue
            
        await message.reply(f"⚡ <b>Выполняю шаг {i+1}/{len(commands)}:</b> <code>{command_name}</code>", parse_mode="HTML")
        
        try:
            status, file_to_send = executor.execute_command_dict(cmd)
            
            # Send status feedback
            await message.reply(f"✅ <b>Результат шага {i+1}:</b> {status}", parse_mode="HTML")
            
            # Send document if generated (e.g. screenshot)
            if file_to_send and os.path.exists(file_to_send):
                await message.reply_document(types.FSInputFile(file_to_send))
                try:
                    os.remove(file_to_send)
                except Exception as ex:
                    logger.error(f"Error removing temp output file: {ex}")
        except Exception as e:
            logger.error(f"Step {i+1} execution failed: {e}")
            await message.reply(f"❌ Ошибка на шаге {i+1}: {e}")
            
    await message.reply("🏁 <b>Все задачи выполнены!</b>", parse_mode="HTML")

# Voice messages handler
@dp.message(F.voice)
async def handle_voice_message(message: types.Message):
    await message.reply("⏳ <i>Распознаю голосовую команду...</i>", parse_mode="HTML")
    ogg_path = ""
    try:
        voice = message.voice
        file_info = await bot.get_file(voice.file_id)
        
        fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        
        await bot.download_file(file_info.file_path, ogg_path)
        transcript = await transcribe_voice(ogg_path)
        
        if not transcript:
            await message.reply("⚠️ Не удалось распознать речь. Попробуйте еще раз.")
            return
            
        await message.reply(f"🎙️ <b>Услышал:</b> <i>\"{transcript}\"</i>", parse_mode="HTML")
        await execute_query_pipeline(message, transcript)
        
    except Exception as e:
        logger.error(f"Error in voice message handler: {e}", exc_info=True)
        await message.reply(f"❌ Системная ошибка: {e}")
    finally:
        if ogg_path and os.path.exists(ogg_path):
            try:
                os.remove(ogg_path)
            except Exception:
                pass

# Text messages handler
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    query = message.text.strip()
    if query.startswith("/"):
        return
    await execute_query_pipeline(message, query)

async def main():
    logger.info("Starting Telegram Advanced PC Control Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
