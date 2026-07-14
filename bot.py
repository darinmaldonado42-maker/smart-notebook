import os
import sys
import time
import logging
import tempfile
import base64
import asyncio
import cv2
import openai
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o") # Use GPT-4o for high-accuracy vision analysis

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not configured in .env file!")
    sys.exit("Error: BOT_TOKEN is missing!")
if not OPENAI_API_KEY:
    logger.critical("OPENAI_API_KEY is not configured in .env file!")
    sys.exit("Error: OPENAI_API_KEY is missing!")

# Initialize OpenAI Client
openai_client = openai.AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

# Initialize Telegram Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Frame extraction helper using OpenCV
def extract_video_frames(video_path: str, num_frames: int = 3) -> list[str]:
    """Extracts a set of evenly distributed frames from a video file."""
    logger.info(f"Extracting {num_frames} frames from video: {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Failed to open video file: {video_path}")
        return []
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        logger.error("Video contains 0 frames.")
        cap.release()
        return []
        
    # Pick frame indices at 10%, 50%, and 90% of the video duration
    indices = [int(total_frames * ratio) for ratio in [0.1, 0.5, 0.9]]
    # Ensure they are within bounds
    indices = [max(0, min(idx, total_frames - 1)) for idx in indices]
    
    frame_paths = []
    for i, idx in enumerate(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            # Save frame to a temporary file
            fd, temp_img_path = tempfile.mkstemp(suffix=f"_frame_{i}.png")
            os.close(fd)
            cv2.imwrite(temp_img_path, frame)
            frame_paths.append(temp_img_path)
            logger.info(f"Extracted frame {i} (index {idx}) to: {temp_img_path}")
        else:
            logger.warning(f"Failed to read frame at index {idx}")
            
    cap.release()
    return frame_paths

# Vision OSINT analysis using GPT-4o
async def analyze_location_vision(frame_paths: list[str], timestamp_str: str) -> str:
    """Sends frames to GPT-4o Vision API for astronomical & geographical location analysis."""
    logger.info("Starting GPT-4o Vision Geolocation analysis...")
    
    # Base user instructions for the Geoguessr / OSINT task
    user_prompt = (
        f"Ты — профессиональный специалист по OSINT-разведке и эксперт Geoguessr.\n"
        f"Перед тобой {len(frame_paths)} кадров, вырезанных из кружка (видеосообщения) Telegram.\n"
        f"Видео было снято приблизительно: {timestamp_str} UTC.\n\n"
        f"Твоя задача — провести глубокий анализ изображений и определить координаты места съемки:\n"
        f"1. **Астрономический анализ (Небо):** Оцени положение солнца (азимут, угол высоты), цвет неба, тип облаков, интенсивность света, фазу луны или расположение звезд (если видно). Сопоставь это с датой/временем, чтобы сузить возможные широты/долготы.\n"
        f"2. **Географический анализ (Окружение):** Проанализируй рельеф местности (горы, равнины), тип почвы (песок, глина, чернозем), флору (виды деревьев, травы, кустов), архитектуру зданий (европейский стиль, советские панельки, азиатские постройки), дорожную разметку, знаки и номера машин (если есть).\n"
        f"3. **Культурный анализ:** Любые надписи, рекламные щиты, язык, направление движения (правостороннее/левостороннее).\n\n"
        f"Сделай аргументированный вывод и выдай финальный результат строго на русском языке.\n\n"
        f"Формат ответа должен быть оформлен в красивой разметке Markdown:\n\n"
        f"🌍 **Предполагаемые координаты:** [Широта, Долгота в формате DD.DDDD, DD.DDDD]\n"
        f"🗺️ **Ссылка на Google Карты:** [Открыть в Google Maps](https://www.google.com/maps/place/ШИРОТА,ДОЛГОТА)\n\n"
        f"🔍 **Подробный анализ визуальных ориентиров:**\n"
        f"- *Небо и Солнце:* [анализ положения солнца, времени суток и теней]\n"
        f"- *Природа и Рельеф:* [описание растительности и ландшафта]\n"
        f"- *Архитектура и Инфраструктура:* [описание построек, дорог и строений]\n"
        f"- *Ход рассуждения:* [пошаговый логический вывод, почему выбрана эта страна/город]"
    )
    
    content_list = [
        {
            "type": "text",
            "text": user_prompt
        }
    ]
    
    # Encode images to base64 and append to OpenAI messages payload
    for path in frame_paths:
        try:
            with open(path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode("utf-8")
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_data}"
                }
            })
        except Exception as img_err:
            logger.error(f"Error encoding image {path} to base64: {img_err}")
            
    try:
        response = await openai_client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": content_list
                }
            ],
            max_tokens=1500,
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI Vision API request failed: {e}", exc_info=True)
        return f"❌ Ошибка при отправке запроса в нейросеть: {e}"

# Command handler: /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply(
        "🌍 <b>Привет! Я Небесный Геодезист — бот для OSINT-геолокации.</b>\n\n"
        "Отправь мне <b>видеосообщение (кружок)</b> или обычное <b>видео</b>, на котором видно небо и окружающую местность.\n\n"
        "Я нарежу кадры из видео, проанализирую положение солнца, тени, растительность и архитектуру с помощью нейросети "
        "и попробую найти точные координаты места съемки, а также вышлю ссылку на Google Карты!",
        parse_mode="HTML"
    )

# Command handler: /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "🕵️‍♂️ <b>Как пользоваться ботом:</b>\n\n"
        "1. Запиши или перешли кружок (видеосообщение), снятый на улице.\n"
        "2. Желательно, чтобы на видео было видно небо с солнцем, тени, деревья или здания на горизонте.\n"
        "3. Бот определит время съемки и проанализирует кадры, чтобы рассчитать геопозицию.\n\n"
        "<i>Примечание: точность анализа зависит от количества визуальных деталей на видео.</i>",
        parse_mode="HTML"
    )

# Core video note processing pipeline
async def process_video_and_respond(message: types.Message, file_id: str):
    status_msg = await message.reply("⏳ <i>Скачиваю видео и нарезаю кадры...</i>", parse_mode="HTML")
    video_path = ""
    extracted_frames = []
    
    try:
        # 1. Download video file
        file_info = await bot.get_file(file_id)
        fd, video_path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        
        await bot.download_file(file_info.file_path, video_path)
        
        # 2. Extract frames
        extracted_frames = extract_video_frames(video_path, num_frames=3)
        if not extracted_frames:
            await status_msg.edit_text("❌ Не удалось извлечь кадры из видео. Убедитесь, что видеофайл не поврежден.")
            return
            
        # Update progress
        await status_msg.edit_text("🔍 <i>Кадры извлечены. Нейросеть GPT-4o проводит OSINT-анализ неба и местности...</i>", parse_mode="HTML")
        
        # 3. Format message time context
        timestamp_str = message.date.strftime("%Y-%m-%d %H:%M:%S")
        
        # 4. Request location analysis
        report = await analyze_location_vision(extracted_frames, timestamp_str)
        
        # 5. Send report
        await status_msg.delete()
        await message.reply(report, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error processing video note: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Произошла ошибка во время анализа: {e}")
    finally:
        # Clean up temporary files
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except Exception:
                pass
        for path in extracted_frames:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

# Handle Telegram video notes
@dp.message(F.video_note)
async def handle_video_note(message: types.Message):
    logger.info("Received a video note message.")
    await process_video_and_respond(message, message.video_note.file_id)

# Handle standard Telegram videos
@dp.message(F.video)
async def handle_video(message: types.Message):
    logger.info("Received a standard video message.")
    await process_video_and_respond(message, message.video.file_id)

# Run the Bot locally using asyncio polling
async def main():
    logger.info("Starting OSINT Geoguessr bot polling loop...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
