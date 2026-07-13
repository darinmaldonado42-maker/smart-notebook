import os
import sys
import time
import json
import base64
import logging
import asyncio
import threading
import queue
import tempfile
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
from dotenv import load_dotenv
import speech_recognition as sr
import openai
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart

# Import the local executor
import executor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load credentials from .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

if not BOT_TOKEN:
    logger.error("BOT_TOKEN is not configured in .env file!")
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not configured in .env file!")

# Initialize OpenAI client
openai_client = openai.AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

# Initialize Telegram Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Thread-safe queue for Tkinter GUI updates
gui_queue = queue.Queue()

# Global event loop reference for scheduling async tasks from other threads
global_loop = None

# Auto-startup configuration helper
def get_startup_shortcut_path() -> str:
    startup_dir = os.path.join(
        os.getenv("APPDATA"),
        "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    return os.path.join(startup_dir, "PCControlClient.bat")

def set_startup_state(enable: bool):
    bat_path = get_startup_shortcut_path()
    if enable:
        try:
            python_exe = sys.executable
            script_path = os.path.abspath(__file__)
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(f'@echo off\ncd /d "{os.path.dirname(script_path)}"\nstart "" "{python_exe}" "{script_path}"\n')
            logger.info("Startup bat file created.")
        except Exception as e:
            logger.error(f"Failed to enable startup: {e}")
    else:
        try:
            if os.path.exists(bat_path):
                os.remove(bat_path)
                logger.info("Startup bat file removed.")
        except Exception as e:
            logger.error(f"Failed to disable startup: {e}")

def is_startup_enabled() -> bool:
    return os.path.exists(get_startup_shortcut_path())

# Helper to get currently open visible windows
def get_open_windows_list() -> list[str]:
    titles = []
    try:
        for w in gw.getAllWindows():
            if w.title and w.width > 120 and w.height > 120:
                titles.append(w.title)
    except Exception:
        pass
    return list(set(titles))

# GPT Parser (translates text into structured JSON commands)
async def parse_commands_gpt(text: str):
    open_wins = get_open_windows_list()
    windows_context = "\n".join([f"- {title}" for title in open_wins]) if open_wins else "Нет запущенных окон."

    prompt = (
        "Ты — ИИ-ассистент для управления домашним Windows ПК. Твоя задача — разобрать текстовый запрос пользователя "
        "и вернуть строго список JSON-команд для выполнения на компьютере.\n\n"
        "Доступные типы команд:\n"
        "1. Скриншот: {\"command\": \"screenshot\"}\n"
        "2. Поиск в YouTube: {\"command\": \"youtube\", \"args\": {\"query\": \"запрос\", \"mode\": \"search|play\", \"target_screen\": \"main|second\"}}\n"
        "   - mode: search (показать результаты) или play (запустить первое видео)\n"
        "3. Яндекс.Музыка: {\"command\": \"yandex_music\", \"args\": {\"query\": \"песня или исполнитель\", \"target_screen\": \"main|second\"}}\n"
        "4. Управление медиа: {\"command\": \"media_key\", \"args\": {\"key\": \"space|next|prev|volume_up|volume_down|mute|scroll_down|scroll_up|f11|close_tab|new_tab\"}}\n"
        "5. Запуск Python скрипта: {\"command\": \"run_custom_script\", \"args\": {\"script_code\": \"код на python\"}}\n"
        "6. Запуск приложений: {\"command\": \"open_app\", \"args\": {\"app_name\": \"калькулятор|блокнот|проводник|паинт|vs code|steam|telegram|discord|браузер\", \"target_screen\": \"main|second\"}}\n"
        "7. Громкость: {\"command\": \"adjust_volume\", \"args\": {\"action\": \"up|down|mute\", \"amount\": число_громкости_по_умолчанию_10}}\n"
        "8. Переместить окно: {\"command\": \"move_window\", \"args\": {\"keyword\": \"ключевое слово из названия окна\", \"target_screen\": \"main|second\"}}\n"
        "   - ВАЖНО: чтобы переместить окно, сопоставь запрос пользователя со списком ТЕКУЩИЕ ОТКРЫТЫЕ ОКНА ниже, выбери наиболее подходящее окно и укажи его краткое уникальное название как keyword!\n"
        "9. Список всех окон: {\"command\": \"list_windows\"} (вызывай, если просят показать открытые окна или процессы)\n\n"
        "КРИТИЧЕСКИЕ ПРАВИЛА ВЫБОРА КОМАНДЫ:\n"
        "- Если пользователь просит запустить 'Мою волну' или 'включить музыку' (имея в виду Мою волну Яндекс.Музыки) — ты ОБЯЗАН использовать команду 'run_custom_script' с кликом, а НЕ 'yandex_music'!\n"
        "- Если пользователь просит открыть 'первое видео' или 'видео в рекомендациях' на YouTube — ты ОБЯЗАН использовать команду 'run_custom_script' с кликом, а НЕ 'youtube'!\n\n"
        "10. ДИНАМИЧЕСКИЙ СКРИПТ (САМОАДАПТАЦИЯ И КЛИКИ НА ЭКРАНЕ):\n"
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
        "     time.sleep(1.5)\n"
        "     try:\n"
        "         win = [w for w in gw.getAllWindows() if any(k in w.title.lower() for k in ['yandex', 'яндекс', 'chrome', 'youtube', 'music', 'opera', 'edge', 'firefox', 'браузер'])][0]\n"
        "         win.activate()\n"
        "         time.sleep(0.5)\n"
        "     except:\n"
        "         pass\n"
        "     # 2. Кликаем точно в центр баннера 'Моя волна' (x=725, y=360)\n"
        "     pyautogui.click(725, 360)\n"
        "   - Пример для 'открой первое видео' (на главной YouTube):\n"
        "     Код: \n"
        "     import time, pyautogui\n"
        "     import pygetwindow as gw\n"
        "     try:\n"
        "         win = [w for w in gw.getAllWindows() if any(k in w.title.lower() for k in ['yandex', 'яндекс', 'chrome', 'youtube', 'music', 'opera', 'edge', 'firefox', 'браузер'])][0]\n"
        "         win.activate()\n"
        "         time.sleep(0.5)\n"
        "     except:\n"
        "         pass\n"
        "     # Кликаем на область первого видео в сетке рекомендаций (x=280, y=350)\n"
        "     pyautogui.click(280, 350)\n"
        "   - Любые другие действия — переводи в готовый скрипт python с фокусом окна и кликами.\n"
        "11. Выключение/Перезагрузка: {\"command\": \"shutdown\" или \"restart\", \"args\": {\"delay\": секунды_по_умолчанию_10}}\n\n"
        "ТЕКУЩИЕ ОТКРЫТЫЕ ОКНА НА ПК ПОЛЬЗОВАТЕЛЯ:\n"
        f"{windows_context}\n\n"
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

# Transcribe voice note using OpenAI Whisper
async def transcribe_voice(file_path: str) -> str:
    try:
        with open(file_path, "rb") as audio_file:
            transcript = await openai_client.audio.transcriptions.create(
                model=OPENAI_WHISPER_MODEL,
                file=audio_file,
                language="ru"
            )
            return transcript.text
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}", exc_info=True)
        return ""

# Pipeline to execute query commands locally on PC
async def execute_query_locally(query_text: str, telegram_message: types.Message = None):
    # Parse commands using GPT
    commands = await parse_commands_gpt(query_text)
    logger.info(f"Resolved commands for '{query_text}': {commands}")
    
    if not commands:
        if telegram_message:
            await telegram_message.reply("❓ Команды не распознаны.")
        return
        
    if telegram_message:
        await telegram_message.reply(f"⚡ <b>Выполняю {len(commands)} задач...</b>", parse_mode="HTML")
        
    # Execute each command
    for i, cmd in enumerate(commands):
        cmd_name = cmd.get("command", "")
        if cmd_name == "unknown":
            if telegram_message:
                await telegram_message.reply(f"❓ Шаг {i+1}: Команда не распознана.")
            continue
            
        gui_queue.put({"type": "log", "val": f"Выполняю: {cmd_name}"})
        
        # Run command via executor
        loop = asyncio.get_event_loop()
        status, file_path = await loop.run_in_executor(None, executor.execute_command_dict, cmd)
        
        if telegram_message:
            await telegram_message.reply(f"✅ <b>Шаг {i+1}/{len(commands)} ({cmd_name}):</b> {status}", parse_mode="HTML")
            
            # Send screenshot back to Telegram if generated
            if file_path and os.path.exists(file_path):
                try:
                    with open(file_path, "rb") as img_file:
                        screenshot_bytes = img_file.read()
                    os.remove(file_path)
                    
                    buffered_img = types.BufferedInputFile(screenshot_bytes, filename="screenshot.png")
                    await telegram_message.reply_document(buffered_img)
                except Exception as ex:
                    logger.error(f"Error handling screenshot: {ex}")
        else:
            # Local trigger (clean up screenshot silently if generated)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                    
        gui_queue.put({"type": "log", "val": f"Успешно выполнено: {cmd_name}"})

# Telegram Event Handlers (running locally!)
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply(
        f"👋 <b>Привет! Я твой локальный Пончик-помощник.</b>\n\n"
        f"Присылай мне <b>голосовые сообщения</b> или пиши <b>текстом</b>!\n\n"
        f"<b>Примеры команд:</b>\n"
        f"• <code>скриншот</code> — снимок экрана ПК\n"
        f"• <code>открой ютуб [запрос] на втором экране</code>\n"
        f"• <code>включи мою волну</code> — в Яндекс.Музыке\n"
        f"• <code>плей / пауза</code>, <code>тише / громче</code>\n",
        parse_mode="HTML"
    )

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
        gui_queue.put({"type": "log", "val": f"📱 Telegram-голос: \"{transcript}\""})
        await execute_query_locally(transcript, message)
    except Exception as e:
        logger.error(f"Error handling voice: {e}", exc_info=True)
        await message.reply(f"❌ Ошибка: {e}")
    finally:
        if ogg_path and os.path.exists(ogg_path):
            try:
                os.remove(ogg_path)
            except Exception:
                pass

@dp.message(F.text)
async def handle_text(message: types.Message):
    query = message.text.strip()
    if query.startswith("/"):
        return
    gui_queue.put({"type": "log", "val": f"📱 Telegram-текст: \"{query}\""})
    await execute_query_locally(query, message)

# Local Speech Listener (Wake Word: "Пончик")
def local_voice_listener():
    recognizer = sr.Recognizer()
    try:
        microphone = sr.Microphone()
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
    except Exception as mic_err:
        logger.error(f"Failed to initialize microphone: {mic_err}")
        gui_queue.put({"type": "log", "val": "🎙️ Ошибка: Микрофон не обнаружен. Пончик оффлайн."})
        return

    logger.info("Local voice listener started. Waiting for wake word 'Пончик'...")
    gui_queue.put({"type": "log", "val": "🎙️ Ассистент Пончик активен. Жду команду..."})
    
    while True:
        try:
            with microphone as source:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=8)
                
            text = recognizer.recognize_google(audio, language="ru-RU").lower().strip()
            logger.info(f"Local speech heard: '{text}'")
            
            # Check for wake word "пончик" or "ponchik"
            if "пончик" in text or "ponchik" in text:
                command_text = text.replace("пончик", "").replace("ponchik", "").strip()
                if command_text:
                    gui_queue.put({"type": "log", "val": f"🎙️ Пончик услышал: \"{command_text}\""})
                    
                    # Schedule execution on the main loop
                    if global_loop and global_loop.is_running():
                        asyncio.run_coroutine_threadsafe(execute_query_locally(command_text), global_loop)
                        
        except sr.UnknownValueError:
            pass
        except Exception as e:
            logger.error(f"Error in speech listener loop: {e}")
            time.sleep(2)

# Telegram Polling worker thread
async def telegram_polling_loop():
    global global_loop
    global_loop = asyncio.get_event_loop()
    
    try:
        # Fetch Bot info to show username in GUI
        bot_info = await bot.get_me()
        gui_queue.put({"type": "bot_info", "username": bot_info.username})
        gui_queue.put({"type": "status", "val": "connected"})
        logger.info(f"Telegram Bot @{bot_info.username} started polling locally.")
        
        # Start Telegram polling
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Telegram polling failed: {e}")
        gui_queue.put({"type": "status", "val": "error", "err": str(e)})

def start_telegram_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(telegram_polling_loop())

# Tkinter Graphical Interface
class PCControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Локальный помощник Пончик")
        self.root.geometry("480x420")
        self.root.minsize(450, 380)
        
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status Label
        self.status_label = ttk.Label(
            self.main_frame,
            text="Статус: Запуск Telegram...",
            font=("Arial", 12, "bold"),
            foreground="orange"
        )
        self.status_label.pack(anchor=tk.W, pady=5)
        
        # Bot Username Label
        self.bot_label = ttk.Label(
            self.main_frame,
            text="Бот в Telegram: загрузка...",
            font=("Arial", 10)
        )
        self.bot_label.pack(anchor=tk.W, pady=2)
        
        # Logs Text box
        ttk.Label(self.main_frame, text="Лог событий:", font=("Arial", 10)).pack(anchor=tk.W, pady=(10, 2))
        self.log_area = tk.Text(self.main_frame, height=10, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Checkbox for Startup
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        self.startup_check = ttk.Checkbutton(
            self.main_frame,
            text="Запускать автоматически при старте Windows",
            variable=self.startup_var,
            command=self.toggle_startup
        )
        self.startup_check.pack(anchor=tk.W, pady=5)
        
        # Local Command Entry frame
        self.cmd_frame = ttk.Frame(self.main_frame)
        self.cmd_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        self.cmd_entry = ttk.Entry(self.cmd_frame, font=("Arial", 10))
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.cmd_entry.insert(0, "Введите команду здесь...")
        self.cmd_entry.bind("<FocusIn>", self.clear_placeholder)
        self.cmd_entry.bind("<FocusOut>", self.add_placeholder)
        self.cmd_entry.bind("<Return>", self.send_local_command)
        
        self.send_btn = ttk.Button(self.cmd_frame, text="Отправить", command=self.send_local_command)
        self.send_btn.pack(side=tk.RIGHT)
        
        # Start queue checker
        self.root.after(100, self.update_gui_from_queue)
        self.log("Клиент инициализирован.")
        
    def log(self, text: str):
        self.log_area.config(state=tk.NORMAL)
        t = time.strftime("[%H:%M:%S] ") + text + "\n"
        self.log_area.insert(tk.END, t)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        
    def clear_placeholder(self, event):
        if self.cmd_entry.get() == "Введите команду здесь...":
            self.cmd_entry.delete(0, tk.END)
            
    def add_placeholder(self, event):
        if not self.cmd_entry.get():
            self.cmd_entry.insert(0, "Введите команду здесь...")
            
    def send_local_command(self, event=None):
        text = self.cmd_entry.get().strip()
        if not text or text == "Введите команду здесь...":
            return
            
        self.log(f"💻 Ввод команды: \"{text}\"")
        self.cmd_entry.delete(0, tk.END)
        
        if global_loop and global_loop.is_running():
            asyncio.run_coroutine_threadsafe(execute_query_locally(text), global_loop)
        else:
            self.log("⚠️ Ошибка: Асинхронный цикл не запущен.")
            
    def toggle_startup(self):
        state = self.startup_var.get()
        set_startup_state(state)
        if state:
            self.log("Автозапуск включен. Приложение добавлено в автозагрузку.")
        else:
            self.log("Автозапуск выключен. Приложение удалено из автозагрузки.")
            
    def update_gui_from_queue(self):
        try:
            while True:
                msg = gui_queue.get_nowait()
                msg_type = msg.get("type")
                
                if msg_type == "status":
                    val = msg.get("val")
                    if val == "connected":
                        self.status_label.config(text="🟢 Статус: Активен (Пончик)", foreground="green")
                        self.log("Telegram Bot успешно запущен локально.")
                    elif val == "error":
                        err = msg.get("err", "")
                        self.status_label.config(text="🔴 Статус: Ошибка Telegram", foreground="red")
                        self.log(f"Критическая ошибка Telegram: {err}")
                        
                elif msg_type == "bot_info":
                    username = msg.get("username", "")
                    self.bot_label.config(text=f"Бот в Telegram: @{username}")
                    
                elif msg_type == "log":
                    self.log(msg.get("val", ""))
                    
        except queue.Empty:
            pass
        self.root.after(100, self.update_gui_from_queue)

if __name__ == "__main__":
    if not BOT_TOKEN or not OPENAI_API_KEY:
        root_temp = tk.Tk()
        root_temp.withdraw()
        messagebox.showerror(
            "Ошибка конфигурации",
            "В файле .env отсутствуют BOT_TOKEN или OPENAI_API_KEY!\n\n"
            "Пожалуйста, пропишите эти ключи и перезапустите приложение."
        )
        sys.exit(1)
        
    # Start Telegram polling thread locally
    t_telegram = threading.Thread(target=start_telegram_thread, daemon=True)
    t_telegram.start()
    
    # Start Local Voice Listener thread
    t_voice = threading.Thread(target=local_voice_listener, daemon=True)
    t_voice.start()
    
    # Start GUI main loop
    root = tk.Tk()
    app_gui = PCControlGUI(root)
    root.mainloop()
