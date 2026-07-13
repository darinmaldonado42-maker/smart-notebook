import os
import subprocess
import webbrowser
import tempfile
import logging
from PIL import ImageGrab
import pyautogui

logger = logging.getLogger(__name__)

# Disable PyAutoGUI fail-safe to prevent termination during corner coordinates
pyautogui.FAILSAFE = False

def get_yandex_browser_path() -> str:
    """Finds the installation path of Yandex Browser on Windows."""
    try:
        # 1. Check user AppData (common install location for Yandex Browser)
        username = os.getlogin()
        user_path = f"C:\\Users\\{username}\\AppData\\Local\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(user_path):
            return user_path
            
        # 2. Check standard Program Files (x86)
        prog_path_x86 = "C:\\Program Files (x86)\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(prog_path_x86):
            return prog_path_x86
            
        # 3. Check standard Program Files
        prog_path = "C:\\Program Files\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(prog_path):
            return prog_path
    except Exception as e:
        logger.error(f"Error searching Yandex Browser path: {e}")
        
    return ""

def open_url(url: str) -> str:
    """Opens a URL using Yandex Browser (if available) or the system default browser."""
    yandex_path = get_yandex_browser_path()
    if yandex_path:
        try:
            subprocess.Popen([yandex_path, url])
            return f"Открыл в Яндекс.Браузере: {url}"
        except Exception as e:
            logger.error(f"Failed to launch Yandex Browser: {e}", exc_info=True)
            
    # Fallback to default browser
    try:
        webbrowser.open(url)
        return f"Открыл в браузере по умолчанию: {url}"
    except Exception as e:
        logger.error(f"Failed to open URL: {e}", exc_info=True)
        return f"Ошибка при открытии ссылки: {e}"

def take_screenshot() -> str:
    """Takes a screenshot of all connected monitors (dual screen support) and saves it."""
    try:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        
        # Grab all screens (multi-monitor setup support)
        screenshot = ImageGrab.grab(all_screens=True)
        screenshot.save(path)
        logger.info(f"Multi-screen screenshot saved to {path}")
        return path
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}", exc_info=True)
        return ""

def open_youtube(query: str = "", mode: str = "search") -> str:
    """Opens YouTube. Mode can be 'search' or 'channel'."""
    query = query.strip()
    if not query:
        return open_url("https://www.youtube.com")
        
    if mode == "channel":
        # Clean channel name (remove @ if present)
        channel = query.lstrip("@")
        url = f"https://www.youtube.com/@{channel}"
        return open_url(url)
    else:
        # Search query
        url = f"https://www.youtube.com/results?search_query={subprocess.RawConfigParser.optionxform(None, query) if False else query}"
        # We format URL safely
        import urllib.parse
        safe_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={safe_query}"
        return open_url(url)

def open_yandex_music(query: str = "") -> str:
    """Opens Yandex Music. Searches for track/artist if query is provided."""
    query = query.strip()
    if not query:
        return open_url("https://music.yandex.ru")
        
    import urllib.parse
    safe_query = urllib.parse.quote(query)
    url = f"https://music.yandex.ru/search?text={safe_query}"
    return open_url(url)

def media_control(action: str) -> str:
    """Simulates keyboard media and browser controls."""
    action = action.lower()
    try:
        # Ensure focus is correct or click if needed (simulate user action)
        if action == "play_pause":
            # space is universal for YouTube/Yandex Music when focused, but we also try media key
            pyautogui.press("playpause")
            # If playpause doesn't work, space can work if page is focused
            pyautogui.press("space")
            return "Воспроизведение / Пауза"
            
        elif action == "next_track":
            pyautogui.press("nexttrack")
            return "Следующий трек"
            
        elif action == "prev_track":
            pyautogui.press("prevtrack")
            return "Предыдущий трек"
            
        elif action == "fullscreen":
            # Press 'f' (standard for YouTube fullscreen) and also F11 for browser fullscreen
            pyautogui.press("f")
            return "Режим во весь экран"
            
        elif action == "scroll_down":
            pyautogui.scroll(-600)
            return "Прокрутил вниз"
            
        elif action == "scroll_up":
            pyautogui.scroll(600)
            return "Прокрутил вверх"
            
        elif action == "close_tab":
            pyautogui.hotkey("ctrl", "w")
            return "Закрыл вкладку"
            
        elif action == "new_tab":
            pyautogui.hotkey("ctrl", "t")
            return "Открыл новую вкладку"
            
        elif action == "enter":
            pyautogui.press("enter")
            return "Нажал Enter"
            
        else:
            return f"Неподдерживаемое действие мультимедиа: {action}"
    except Exception as e:
        logger.error(f"Error during media control action {action}: {e}", exc_info=True)
        return f"Ошибка при управлении мультимедиа: {e}"

def open_app(app_query: str) -> str:
    """Launches standard Windows applications."""
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
        if query.endswith(".exe"):
            executable = query
        else:
            return f"Приложение '{app_query}' не найдено в списке поддерживаемых."
            
    try:
        subprocess.Popen(executable, shell=True)
        return f"Запустил приложение: {executable}"
    except Exception as e:
        logger.error(f"Error launching {executable}: {e}", exc_info=True)
        return f"Ошибка при запуске: {e}"

def adjust_volume(action: str, amount: int = 10) -> str:
    """Adjusts Windows system volume."""
    try:
        action = action.lower()
        if action == "up":
            press_count = max(1, amount // 2)
            for _ in range(press_count):
                pyautogui.press("volumeup")
            return f"Увеличил громкость на {amount}%."
        elif action == "down":
            press_count = max(1, amount // 2)
            for _ in range(press_count):
                pyautogui.press("volumedown")
            return f"Уменьшил громкость на {amount}%."
        elif action in ["mute", "toggle"]:
            pyautogui.press("volumemute")
            return "Переключил режим без звука."
        else:
            return f"Действие с громкостью не распознано: {action}"
    except Exception as e:
        logger.error(f"Volume adjustment failed: {e}", exc_info=True)
        return f"Ошибка при изменении громкости: {e}"

def shutdown_pc(delay: int = 10) -> str:
    """Shuts down the Windows PC."""
    try:
        os.system(f"shutdown /s /t {delay}")
        return f"Компьютер будет выключен через {delay} секунд."
    except Exception as e:
        logger.error(f"Shutdown execution failed: {e}", exc_info=True)
        return f"Ошибка при выключении: {e}"

def restart_pc(delay: int = 10) -> str:
    """Restarts the Windows PC."""
    try:
        os.system(f"shutdown /r /t {delay}")
        return f"Компьютер будет перезагружен через {delay} секунд."
    except Exception as e:
        logger.error(f"Restart execution failed: {e}", exc_info=True)
        return f"Ошибка при перезагрузке: {e}"

def execute_command_dict(cmd_data: dict) -> tuple[str, str]:
    """Decodes JSON and executes the command on the Windows PC."""
    command = cmd_data.get("command", "").lower()
    args = cmd_data.get("args", {})
    
    if command == "screenshot":
        path = take_screenshot()
        if path:
            return "Снимок экрана готов!", path
        else:
            return "Не удалось сделать снимок экрана.", ""
            
    elif command == "open_browser":
        url = args.get("url", "")
        res = open_url(url)
        return res, ""
        
    elif command == "youtube":
        query = args.get("query", "")
        mode = args.get("mode", "search")
        res = open_youtube(query, mode)
        return res, ""
        
    elif command == "yandex_music":
        query = args.get("query", "")
        res = open_yandex_music(query)
        return res, ""
        
    elif command == "media_control":
        action = args.get("action", "")
        res = media_control(action)
        return res, ""
        
    elif command == "open_app":
        app_name = args.get("app_name", "")
        res = open_app(app_name)
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
        
    return f"Команда '{command}' не поддерживается.", ""
