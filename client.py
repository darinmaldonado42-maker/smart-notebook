import os
import sys
import time
import json
import base64
import logging
import asyncio
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
import aiohttp
from dotenv import load_dotenv
import speech_recognition as sr

# Import the local executor
import executor

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()

# Load credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
SERVER_URL = os.getenv("WEBAPP_URL", "http://localhost:8080")

if not BOT_TOKEN:
    logger.warning("BOT_TOKEN is not configured in .env file!")

# Convert server URL to WebSocket URL (pointing to root path)
if SERVER_URL.startswith("https://"):
    WS_URL = SERVER_URL.replace("https://", "wss://") + "/"
elif SERVER_URL.startswith("http://"):
    WS_URL = SERVER_URL.replace("http://", "ws://") + "/"
else:
    WS_URL = f"ws://{SERVER_URL}/"

# Thread-safe queue for Tkinter GUI updates
gui_queue = queue.Queue()

# Global references for sending commands from local GUI/Voice threads to WebSocket
global_ws = None
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

# Local Speech Listener (Wake Word: "Джарвис")
def local_voice_listener():
    recognizer = sr.Recognizer()
    try:
        microphone = sr.Microphone()
        # Calibrate microphone for ambient noise
        with microphone as source:
            recognizer.adjust_for_ambient_noise(source, duration=1.0)
    except Exception as mic_err:
        logger.error(f"Failed to initialize microphone: {mic_err}")
        gui_queue.put({"type": "log", "val": "🎙️ Ошибка: Микрофон не обнаружен или занят. Джарвис оффлайн."})
        return

    logger.info("Local voice listener started. Waiting for wake word 'Джарвис'...")
    gui_queue.put({"type": "log", "val": "🎙️ Джарвис активен. Жду команду..."})
    
    while True:
        try:
            with microphone as source:
                # Listen for phrase (timeout None means wait indefinitely, phrase_time_limit sets max phrase duration)
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=8)
                
            # Transcribe audio using Google Speech API
            text = recognizer.recognize_google(audio, language="ru-RU").lower().strip()
            logger.info(f"Local speech heard: '{text}'")
            
            # Check if text contains the wake word "джарвис" or "jarvis"
            if "джарвис" in text or "jarvis" in text:
                # Extract command by stripping wake word
                command_text = text.replace("джарвис", "").replace("jarvis", "").strip()
                if command_text:
                    gui_queue.put({"type": "log", "val": f"🎙️ Джарвис услышал: \"{command_text}\""})
                    
                    # Send command thread-safely to WebSocket
                    if global_ws and global_loop and not global_ws.closed:
                        coro = global_ws.send_json({
                            "type": "local_voice_command",
                            "text": command_text
                        })
                        asyncio.run_coroutine_threadsafe(coro, global_loop)
                    else:
                        gui_queue.put({"type": "log", "val": "⚠️ Джарвис: Не могу отправить команду (нет сети с сервером)"})
                        
        except sr.UnknownValueError:
            # Unintelligible speech
            pass
        except Exception as e:
            logger.error(f"Error in speech listener loop: {e}")
            time.sleep(2)

# Client Websockets logic running in asyncio background thread
async def websocket_client_loop():
    global global_ws, global_loop
    global_loop = asyncio.get_event_loop()
    
    while True:
        gui_queue.put({"type": "status", "val": "connecting"})
        logger.info(f"Connecting to WebSocket server at {WS_URL}...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL, timeout=15) as ws:
                    # Authenticate
                    await ws.send_json({
                        "type": "auth",
                        "secret": BOT_TOKEN
                    })
                    
                    auth_resp = await ws.receive_json()
                    if auth_resp.get("type") != "auth_ok":
                        logger.error("Authentication failed.")
                        gui_queue.put({"type": "status", "val": "auth_err"})
                        await ws.close()
                        await asyncio.sleep(10)
                        continue
                        
                    # Set global reference
                    global_ws = ws
                    gui_queue.put({"type": "status", "val": "connected"})
                    logger.info("WebSocket authenticated and connected successfully.")
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except Exception:
                                logger.warning("Received invalid JSON data.")
                                continue
                                
                            if data.get("type") == "execute":
                                req_id = data.get("request_id")
                                cmd = data.get("command", {})
                                cmd_name = cmd.get("command", "")
                                
                                logger.info(f"Executing remote command {cmd_name} for request {req_id}")
                                gui_queue.put({"type": "log", "val": f"Выполняю: {cmd_name}"})
                                
                                # Run command on PC
                                loop = asyncio.get_event_loop()
                                status, file_path = await loop.run_in_executor(None, executor.execute_command_dict, cmd)
                                
                                # Prepare screenshot if present
                                screenshot_b64 = None
                                if file_path and os.path.exists(file_path):
                                    try:
                                        with open(file_path, "rb") as img_file:
                                            screenshot_b64 = base64.b64encode(img_file.read()).decode("utf-8")
                                        os.remove(file_path)
                                    except Exception as ex:
                                        logger.error(f"Error reading/removing screenshot: {ex}")
                                        
                                # Send result back to server
                                await ws.send_json({
                                    "type": "result",
                                    "request_id": req_id,
                                    "status": status,
                                    "screenshot": screenshot_b64
                                })
                                logger.info(f"Sent command execution status back: {status}")
                                gui_queue.put({"type": "log", "val": f"Успешно выполнено: {cmd_name}"})
                                
        except Exception as e:
            logger.error(f"WebSocket client loop exception: {e}")
            global_ws = None
            gui_queue.put({"type": "status", "val": "disconnected", "err": str(e)})
            
        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)

# Async thread launcher
def start_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(websocket_client_loop())

# Tkinter Graphical Interface Class
class PCControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("PC Control Client (Jarvis)")
        self.root.geometry("480x420")
        self.root.minsize(450, 380)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Frames
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status Label
        self.status_label = ttk.Label(
            self.main_frame,
            text="Статус: Запуск...",
            font=("Arial", 12, "bold"),
            foreground="orange"
        )
        self.status_label.pack(anchor=tk.W, pady=5)
        
        # Server IP Label
        self.server_label = ttk.Label(
            self.main_frame,
            text=f"Подключение к: {WS_URL}",
            font=("Arial", 9)
        )
        self.server_label.pack(anchor=tk.W, pady=2)
        
        # Logs Listbox
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
        self.log("Клиент запущен. Готов к работе.")
        
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
            
        self.log(f"💻 Отправляю команду: \"{text}\"")
        self.cmd_entry.delete(0, tk.END)
        
        if global_ws and global_loop and not global_ws.closed:
            coro = global_ws.send_json({
                "type": "local_voice_command",
                "text": text
            })
            asyncio.run_coroutine_threadsafe(coro, global_loop)
        else:
            self.log("⚠️ Ошибка: Нет соединения с облачным сервером.")
            
    def toggle_startup(self):
        state = self.startup_var.get()
        set_startup_state(state)
        if state:
            self.log("Автозапуск включен. Приложение добавлено в Windows Startup.")
        else:
            self.log("Автозапуск выключен. Приложение удалено из Windows Startup.")
            
    def update_gui_from_queue(self):
        try:
            while True:
                msg = gui_queue.get_nowait()
                msg_type = msg.get("type")
                
                if msg_type == "status":
                    val = msg.get("val")
                    if val == "connecting":
                        self.status_label.config(text="🔌 Статус: Подключение...", foreground="orange")
                    elif val == "connected":
                        self.status_label.config(text="🟢 Статус: Подключено к серверу", foreground="green")
                        self.log("Успешное подключение к облаку.")
                    elif val == "auth_err":
                        self.status_label.config(text="🔴 Статус: Ошибка авторизации (BOT_TOKEN)", foreground="red")
                        self.log("Критическая ошибка: неверный BOT_TOKEN!")
                    elif val == "disconnected":
                        err = msg.get("err", "")
                        self.status_label.config(text="🔴 Статус: Оффлайн", foreground="red")
                        self.log(f"Ошибка соединения: {err}. Повтор...")
                        
                elif msg_type == "log":
                    self.log(msg.get("val", ""))
                    
        except queue.Empty:
            pass
        self.root.after(100, self.update_gui_from_queue)

if __name__ == "__main__":
    if not BOT_TOKEN:
        root_temp = tk.Tk()
        root_temp.withdraw()
        messagebox.showerror(
            "Ошибка конфигурации",
            "В файле .env отсутствует BOT_TOKEN!\n\n"
            "Пожалуйста, пропишите BOT_TOKEN и перезапустите клиент."
        )
        sys.exit(1)
        
    # Start the async thread loop
    t_async = threading.Thread(target=start_async_loop, daemon=True)
    t_async.start()
    
    # Start the local voice listener thread
    t_voice = threading.Thread(target=local_voice_listener, daemon=True)
    t_voice.start()
    
    # Start the Tkinter App
    root = tk.Tk()
    app_gui = PCControlGUI(root)
    root.mainloop()
