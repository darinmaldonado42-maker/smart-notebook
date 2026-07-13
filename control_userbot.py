import os
import time
import struct
import math
import wave
import tempfile
import asyncio
import logging
from dotenv import load_dotenv
from pyrogram import Client, filters
from pytgcalls import GroupCallFactory

# Import our executor module
import executor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load Telegram API credentials with fallback
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    logger.info("Credentials not found in .env, using official Telegram Android client fallback keys.")
    API_ID = 6
    API_HASH = "eb06d4abfb4902cd8d1c480b002e203d"
else:
    API_ID = int(API_ID)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

if not OPENAI_API_KEY:
    logger.error("WARNING: OPENAI_API_KEY is not set in .env! Audio commands will fail to transcribe.")

# Initialize Pyrogram User Client
app = Client("control_userbot", api_id=API_ID, api_hash=API_HASH)

# Initialize PyTgCalls Factory
factory = GroupCallFactory(app)

# Global variables
current_chat_id = None

# Calculate Root-Mean-Square (RMS) to measure volume of PCM audio
def get_rms(pcm_bytes: bytes) -> float:
    count = len(pcm_bytes) / 2  # 16-bit PCM is 2 bytes per sample
    if count == 0:
        return 0
    format_str = f"<{int(count)}h"
    try:
        shorts = struct.unpack(format_str, pcm_bytes)
    except Exception:
        return 0
    sum_squares = sum(s * s for s in shorts)
    return math.sqrt(sum_squares / count)

# Audio buffer and Voice Activity Detection (VAD) logic
class AudioRecorder:
    def __init__(self):
        self.buffer = bytearray()
        self.is_recording = False
        self.silence_start_time = None
        self.last_voice_time = time.time()
        self.voice_threshold = 700  # Calibration volume threshold (adjust based on mic)
        
    def add_audio(self, pcm_bytes: bytes):
        rms = get_rms(pcm_bytes)
        current_time = time.time()
        
        # Audio chunks are processed in WebRTC threads
        if rms > self.voice_threshold:
            if not self.is_recording:
                logger.info("🎙️ Voice detected, starting buffer recording...")
                self.is_recording = True
                self.buffer.clear()
            self.buffer.extend(pcm_bytes)
            self.last_voice_time = current_time
            self.silence_start_time = None
        else:
            if self.is_recording:
                self.buffer.extend(pcm_bytes)
                if self.silence_start_time is None:
                    self.silence_start_time = current_time
                elif current_time - self.silence_start_time > 1.5:
                    # Silence detected for more than 1.5 seconds, save and process
                    logger.info("🤫 Silence detected. Processing voice command...")
                    self.is_recording = False
                    self.silence_start_time = None
                    
                    # Safely schedule async processing on Pyrogram client's loop
                    pcm_data = bytes(self.buffer)
                    self.buffer.clear()
                    asyncio.run_coroutine_threadsafe(
                        process_and_execute_audio(pcm_data),
                        app.loop
                    )

recorder = AudioRecorder()

# PyTgCalls raw audio callback
def on_recorded_data(group_call, pcm_bytes, length):
    recorder.add_audio(pcm_bytes)

# Get raw group call instance
group_call = factory.get_raw_group_call(
    on_recorded_data=on_recorded_data
)

# Convert raw PCM bytes to WAV format
def save_pcm_to_wav(pcm_data: bytes, filepath: str):
    # standard pytgcalls PCM output: stereo, 16-bit PCM, 48000Hz
    with wave.open(filepath, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(48000)
        wav_file.writeframes(pcm_data)

# Transcribe WAV to text using Whisper
async def transcribe_audio_whisper(filepath: str) -> str:
    from openai import AsyncOpenAI
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

# Convert speech transcript to structured JSON command using GPT
async def parse_command_gpt(text: str) -> dict:
    from openai import AsyncOpenAI
    import json
    
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    
    prompt = (
        "Ты — транслятор голосовых команд для управления компьютером Windows.\n"
        "Проанализируй текст голосовой команды пользователя и верни строго JSON-объект.\n\n"
        "Доступные команды и их формат:\n"
        "1. Скриншот экрана:\n"
        "   - Текст: 'сделай скриншот', 'покажи экран', 'экран'\n"
        "   - JSON: {\"command\": \"screenshot\"}\n"
        "2. Открыть веб-браузер:\n"
        "   - Текст: 'открой гугл', 'открой яндекс', 'открой браузер', 'найди [запрос]'\n"
        "   - JSON: {\"command\": \"open_browser\", \"args\": {\"url\": \"ссылка или поисковый URL\"}}\n"
        "3. Запустить приложение:\n"
        "   - Текст: 'запусти калькулятор', 'открой блокнот', 'проводник', 'паинт'\n"
        "   - JSON: {\"command\": \"open_app\", \"args\": {\"app_name\": \"калькулятор|блокнот|проводник|паинт\"}}\n"
        "4. Свернуть все окна:\n"
        "   - Текст: 'сверни окна', 'сверни всё', 'рабочий стол'\n"
        "   - JSON: {\"command\": \"minimize_all\"}\n"
        "5. Управление громкостью:\n"
        "   - Текст: 'сделай погромче', 'тише', 'выключи звук', 'прибавь звук на 20'\n"
        "   - JSON: {\"command\": \"adjust_volume\", \"args\": {\"action\": \"up|down|mute\", \"amount\": число_от_2_до_100_по_умолчанию_10}}\n"
        "6. Выключить компьютер:\n"
        "   - Текст: 'выключи компьютер', 'выключи пк через минуту'\n"
        "   - JSON: {\"command\": \"shutdown\", \"args\": {\"delay\": секунды_по_умолчанию_10}}\n"
        "7. Перезагрузить компьютер:\n"
        "   - Текст: 'перезагрузи компьютер'\n"
        "   - JSON: {\"command\": \"restart\", \"args\": {\"delay\": секунды_по_умолчанию_10}}\n\n"
        "Если команда не подходит ни под один пункт, верни: {\"command\": \"unknown\"}\n\n"
        "Пример ответа:\n"
        "{\"command\": \"screenshot\"}\n\n"
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

# Main async processing loop
async def process_and_execute_audio(pcm_data: bytes):
    if not current_chat_id:
        logger.warning("No chat_id registered, cannot send feedback.")
        return
        
    temp_wav_path = ""
    try:
        # Create temp file
        fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        save_pcm_to_wav(pcm_data, temp_wav_path)
        logger.info(f"Audio file saved to {temp_wav_path}")
        
        # 1. Transcribe
        transcript = await transcribe_audio_whisper(temp_wav_path)
        logger.info(f"Transcription: {transcript}")
        if not transcript:
            await app.send_message(current_chat_id, "⚠️ Не удалось распознать голосовую команду.")
            return
            
        await app.send_message(current_chat_id, f"🎙️ <b>Услышал:</b> <i>\"{transcript}\"</i>", parse_mode="HTML")
        
        # 2. Parse command
        cmd_data = await parse_command_gpt(transcript)
        logger.info(f"Parsed command JSON: {cmd_data}")
        
        if cmd_data.get("command") == "unknown":
            await app.send_message(current_chat_id, "❓ Команда не распознана.")
            return
            
        # 3. Execute command
        status, file_to_send = executor.execute_command_dict(cmd_data)
        
        # Send confirmation
        await app.send_message(current_chat_id, f"⚙️ <b>Статус:</b> {status}", parse_mode="HTML")
        if file_to_send and os.path.exists(file_to_send):
            await app.send_document(current_chat_id, file_to_send)
            try:
                os.remove(file_to_send)
            except Exception as ex:
                logger.error(f"Error removing temp output file {file_to_send}: {ex}")
                
    except Exception as e:
        logger.error(f"Error processing audio command: {e}", exc_info=True)
        await app.send_message(current_chat_id, f"❌ Ошибка при выполнении команды: {e}")
    finally:
        if temp_wav_path and os.path.exists(temp_wav_path):
            try:
                os.remove(temp_wav_path)
            except Exception as ex:
                logger.error(f"Error removing temp wav {temp_wav_path}: {ex}")

# Pyrogram text handlers to join/leave voice calls
@app.on_message(filters.me & filters.command("join", prefixes="."))
async def join_call(client, message):
    global current_chat_id
    current_chat_id = message.chat.id
    
    try:
        await group_call.start(message.chat.id)
        await message.reply_text(
            "✅ <b>Подключился к голосовому чату!</b>\n"
            "Начните говорить в звонке, я слушаю ваши команды.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error joining voice call: {e}", exc_info=True)
        await message.reply_text(f"❌ Ошибка подключения к звонку: {e}")

@app.on_message(filters.me & filters.command("leave", prefixes="."))
async def leave_call(client, message):
    try:
        await group_call.stop()
        await message.reply_text("👋 <b>Отключился от голосового чата.</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error leaving voice call: {e}", exc_info=True)
        await message.reply_text(f"❌ Ошибка при выходе из звонка: {e}")

if __name__ == "__main__":
    logger.info("Starting PC Control Telegram Userbot...")
    app.run()
