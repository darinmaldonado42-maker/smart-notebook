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
    # We will let the client run but show a warning if BOT_TOKEN is empty
    logger.warning("BOT_TOKEN is not configured in .env file!")

# Convert http/https server URL to WebSocket ws/wss URL
if SERVER_URL.startswith("https://"):
    WS_URL = SERVER_URL.replace("https://", "wss://") + "/ws"
elif SERVER_URL.startswith("http://"):
    WS_URL = SERVER_URL.replace("http://", "ws://") + "/ws"
else:
    WS_URL = f"ws://{SERVER_URL}/ws"

# Thread-safe queue for Tkinter GUI updates
gui_queue = queue.Queue()

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
            # Write a simple launcher batch file
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

# Client Websockets logic running in asyncio background thread
async def websocket_client_loop():
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
                        
                    gui_queue.put({"type": "status", "val": "connected"})
                    logger.info("WebSocket authenticated and connected successfully.")
                    
                    async for msg in ws:
                        if msg.type == web.WSMsgType.TEXT if 'web' in globals() else msg.type == aiohttp.WSMsgType.TEXT:
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
                                # Run CPU/IO bound executor in default executor thread to avoid blocking loop
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
        self.root.title("PC Control Client")
        self.root.geometry("450x350")
        self.root.minsize(400, 300)
        
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
        self.log_area = tk.Text(self.main_frame, height=8, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
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
        
        # Start queue checker
        self.root.after(100, self.update_gui_from_queue)
        self.log("Клиент запущен. Готов к работе.")
        
    def log(self, text: str):
        self.log_area.config(state=tk.NORMAL)
        t = time.strftime("[%H:%M:%S] ") + text + "\n"
        self.log_area.insert(tk.END, t)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)
        
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
                        self.log(f"Потеряно соединение с сервером. Повтор...")
                        
                elif msg_type == "log":
                    self.log(msg.get("val", ""))
                    
        except queue.Empty:
            pass
        self.root.after(100, self.update_gui_from_queue)

if __name__ == "__main__":
    # If BOT_TOKEN is missing, show an alert dialog first
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
    t = threading.Thread(target=start_async_loop, daemon=True)
    t.start()
    
    # Start the Tkinter App
    root = tk.Tk()
    app_gui = PCControlGUI(root)
    root.mainloop()
