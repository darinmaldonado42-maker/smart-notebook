import os
import subprocess
import webbrowser
import tempfile
import logging
from PIL import ImageGrab
import pyautogui

logger = logging.getLogger(__name__)

# Configure PyAutoGUI safety features
pyautogui.FAILSAFE = False

def take_screenshot() -> str:
    """Takes a screenshot of the primary screen and returns the file path."""
    try:
        # Create a temp file path
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        # Capture screen using Pillow
        screenshot = ImageGrab.grab()
        screenshot.save(path)
        logger.info(f"Screenshot taken and saved to {path}")
        return path
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}", exc_info=True)
        return ""

def open_browser(url: str = "") -> str:
    """Opens default web browser, optionally navigating to a specific URL."""
    try:
        target_url = url if url else "https://www.google.com"
        webbrowser.open(target_url)
        return f"Открыл браузер на странице: {target_url}"
    except Exception as e:
        logger.error(f"Error opening browser: {e}", exc_info=True)
        return f"Ошибка при открытии браузера: {e}"

def open_app(app_query: str) -> str:
    """Launches local Windows applications based on query keywords."""
    query = app_query.lower()
    
    app_map = {
        "калькулятор": "calc.exe",
        "блокнот": "notepad.exe",
        "проводник": "explorer.exe",
        "паинт": "mspaint.exe",
        "paint": "mspaint.exe",
        "диспетчер задач": "taskmgr.exe"
    }
    
    executable = None
    for name, exe in app_map.items():
        if name in query:
            executable = exe
            break
            
    if not executable:
        # Fallback: attempt to execute query directly as system command if it ends with .exe
        if query.endswith(".exe"):
            executable = query
        else:
            return f"Не удалось сопоставить приложение '{app_query}' с поддерживаемым списком."
            
    try:
        subprocess.Popen(executable, shell=True)
        return f"Запустил приложение: {executable}"
    except Exception as e:
        logger.error(f"Error launching app {executable}: {e}", exc_info=True)
        return f"Ошибка при запуске {executable}: {e}"

def minimize_all() -> str:
    """Minimizes all open windows to show desktop."""
    try:
        pyautogui.hotkey('win', 'd')
        return "Свернул все окна (показал рабочий стол)."
    except Exception as e:
        logger.error(f"Error minimizing windows: {e}", exc_info=True)
        return f"Ошибка: {e}"

def adjust_volume(action: str, amount: int = 10) -> str:
    """Adjusts Windows system volume using PyAutoGUI hotkeys."""
    try:
        action = action.lower()
        if action == "up":
            press_count = max(1, amount // 2)
            for _ in range(press_count):
                pyautogui.press('volumeup')
            return f"Прибавил громкость (нажатий: {press_count})."
        elif action == "down":
            press_count = max(1, amount // 2)
            for _ in range(press_count):
                pyautogui.press('volumedown')
            return f"Убавил громкость (нажатий: {press_count})."
        elif action in ["mute", "toggle"]:
            pyautogui.press('volumemute')
            return "Переключил беззвучный режим."
        else:
            return f"Неизвестное действие с громкостью: {action}"
    except Exception as e:
        logger.error(f"Error adjusting volume: {e}", exc_info=True)
        return f"Ошибка: {e}"

def shutdown_pc(delay: int = 10) -> str:
    """Initiates Windows system shutdown."""
    try:
        os.system(f"shutdown /s /t {delay}")
        return f"Компьютер выключится через {delay} секунд."
    except Exception as e:
        logger.error(f"Error executing shutdown: {e}", exc_info=True)
        return f"Ошибка при выключении ПК: {e}"

def restart_pc(delay: int = 10) -> str:
    """Initiates Windows system restart."""
    try:
        os.system(f"shutdown /r /t {delay}")
        return f"Компьютер перезагрузится через {delay} секунд."
    except Exception as e:
        logger.error(f"Error executing restart: {e}", exc_info=True)
        return f"Ошибка при перезагрузке ПК: {e}"

def execute_command_dict(cmd_data: dict) -> tuple[str, str]:
    """
    Decodes the structured JSON command and calls the corresponding executor function.
    Returns a tuple (status_text, filepath_to_send)
    """
    command = cmd_data.get("command", "").lower()
    args = cmd_data.get("args", {})
    
    if command == "screenshot":
        path = take_screenshot()
        if path:
            return "Скриншот экрана готов!", path
        else:
            return "Не удалось сделать скриншот.", ""
            
    elif command == "open_browser":
        url = args.get("url", "")
        res = open_browser(url)
        return res, ""
        
    elif command == "open_app":
        app_name = args.get("app_name", "")
        res = open_app(app_name)
        return res, ""
        
    elif command == "minimize_all":
        res = minimize_all()
        return res, ""
        
    elif command == "adjust_volume":
        action = args.get("action", "up")
        amount = args.get("amount", 10)
        res = adjust_volume(action, amount)
        return res, ""
        
    elif command == "shutdown":
        delay = args.get("delay", 10)
        res = shutdown_pc(delay)
        return res, ""
        
    elif command == "restart":
        delay = args.get("delay", 10)
        res = restart_pc(delay)
        return res, ""
        
    return f"Команда '{command}' не распознана или не поддерживается.", ""
