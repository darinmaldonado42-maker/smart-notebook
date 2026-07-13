import os
import sys
import time
import subprocess
import webbrowser
import tempfile
import logging
from PIL import ImageGrab
import pyautogui
import pygetwindow as gw

logger = logging.getLogger(__name__)

# Disable PyAutoGUI fail-safe
pyautogui.FAILSAFE = False

def get_yandex_browser_path() -> str:
    """Finds the installation path of Yandex Browser on Windows."""
    try:
        username = os.getlogin()
        user_path = f"C:\\Users\\{username}\\AppData\\Local\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(user_path):
            return user_path
        prog_path_x86 = "C:\\Program Files (x86)\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(prog_path_x86):
            return prog_path_x86
        prog_path = "C:\\Program Files\\Yandex\\YandexBrowser\\Application\\browser.exe"
        if os.path.exists(prog_path):
            return prog_path
    except Exception as e:
        logger.error(f"Error searching Yandex Browser path: {e}")
    return ""

def open_url(url: str, target_screen: str = "main") -> str:
    """Opens a URL using Yandex Browser (if available) or system default browser."""
    yandex_path = get_yandex_browser_path()
    if yandex_path:
        try:
            subprocess.Popen([yandex_path, url])
            # Move the browser window after opening
            if target_screen != "main":
                time.sleep(1.0)
                move_window_to_screen("yandex", target_screen)
            return f"Открыл в Яндекс.Браузере: {url} (экран: {target_screen})"
        except Exception as e:
            logger.error(f"Failed to launch Yandex Browser: {e}", exc_info=True)
            
    try:
        webbrowser.open(url)
        return f"Открыл в браузере по умолчанию: {url}"
    except Exception as e:
        logger.error(f"Failed to open URL: {e}", exc_info=True)
        return f"Ошибка при открытии ссылки: {e}"

def get_screen_coordinates(target_screen: str) -> tuple[int, int]:
    """Returns starting (x, y) coordinates for target monitor."""
    try:
        main_width, main_height = pyautogui.size()
        if target_screen in ["second", "2"]:
            # Default second monitor is to the right of the main monitor
            return main_width, 0
    except Exception:
        pass
    return 0, 0

def move_window_to_screen(window_title_keyword: str, target_screen: str) -> str:
    """Finds an open window containing the keyword and moves it to the target screen."""
    keyword = window_title_keyword.lower()
    try:
        # Give a small delay for window to render/register in OS
        time.sleep(0.5)
        windows = gw.getAllWindows()
        target_win = None
        
        # Search for matching window title
        for w in windows:
            if w.title and keyword in w.title.lower():
                target_win = w
                break
                
        if target_win:
            if target_win.isMinimized:
                target_win.restore()
                
            x_offset, y_offset = get_screen_coordinates(target_screen)
            # Move to target screen coordinates
            target_win.moveTo(x_offset + 100, y_offset + 100)
            target_win.maximize()
            # Bring window to focus
            try:
                target_win.activate()
            except Exception:
                pass # Win32 can restrict foreground activations from background processes
            return f"Переместил окно '{target_win.title}' на экран {target_screen}."
        else:
            return f"Окно с ключевым словом '{window_title_keyword}' не найдено для перемещения."
    except Exception as e:
        logger.error(f"Error moving window {window_title_keyword}: {e}", exc_info=True)
        return f"Не удалось переместить окно: {e}"

def take_screenshot() -> str:
    """Takes a screenshot of all connected monitors (dual screen support) and saves it."""
    try:
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        screenshot = ImageGrab.grab(all_screens=True)
        screenshot.save(path)
        return path
    except Exception as e:
        logger.error(f"Error taking screenshot: {e}", exc_info=True)
        return ""

def open_youtube(query: str = "", mode: str = "search", target_screen: str = "main") -> str:
    """Opens YouTube search results or a specific channel page."""
    query = query.strip()
    if not query:
        return open_url("https://www.youtube.com", target_screen)
        
    if mode == "channel":
        channel = query.lstrip("@")
        url = f"https://www.youtube.com/@{channel}"
        return open_url(url, target_screen)
    else:
        import urllib.parse
        safe_query = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={safe_query}"
        return open_url(url, target_screen)

def open_yandex_music(query: str = "", target_screen: str = "main") -> str:
    """Opens Yandex Music search or home page."""
    query = query.strip()
    if not query:
        return open_url("https://music.yandex.ru", target_screen)
        
    import urllib.parse
    safe_query = urllib.parse.quote(query)
    url = f"https://music.yandex.ru/search?text={safe_query}"
    return open_url(url, target_screen)

def media_control(action: str) -> str:
    """Simulates keyboard media and browser controls."""
    action = action.lower()
    try:
        if action == "play_pause":
            pyautogui.press("playpause")
            pyautogui.press("space")
            return "Сымитировал Воспроизведение / Пауза"
        elif action == "next_track":
            pyautogui.press("nexttrack")
            return "Сымитировал Следующий трек"
        elif action == "prev_track":
            pyautogui.press("prevtrack")
            return "Сымитировал Предыдущий трек"
        elif action == "fullscreen":
            pyautogui.press("f")
            return "Сымитировал Режим во весь экран"
        elif action == "scroll_down":
            pyautogui.scroll(-600)
            return "Прокрутил страницу вниз"
        elif action == "scroll_up":
            pyautogui.scroll(600)
            return "Прокрутил страницу вверх"
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
            return f"Действие мультимедиа '{action}' не поддерживается."
    except Exception as e:
        logger.error(f"Media control failed: {e}", exc_info=True)
        return f"Ошибка мультимедиа: {e}"

def open_app(app_query: str, target_screen: str = "main") -> str:
    """Launches local Windows applications and optionally moves them to target screen."""
    query = app_query.lower()
    
    app_map = {
        "калькулятор": "calc.exe",
        "блокнот": "notepad.exe",
        "проводник": "explorer.exe",
        "паинт": "mspaint.exe",
        "paint": "mspaint.exe",
        "диспетчер задач": "taskmgr.exe",
        "vs code": "code",
        "code": "code"
    }
    
    executable = None
    keyword = None
    for name, exe in app_map.items():
        if name in query:
            executable = exe
            keyword = name
            break
            
    if not executable:
        if query.endswith(".exe"):
            executable = query
            keyword = query.replace(".exe", "")
        else:
            return f"Приложение '{app_query}' не найдено в списке поддерживаемых."
            
    try:
        subprocess.Popen(executable, shell=True)
        # Move window if target screen is not main
        if target_screen != "main" and keyword:
            time.sleep(1.5) # Wait for program GUI to spawn
            move_window_to_screen(keyword, target_screen)
        return f"Запустил приложение: {executable} (экран: {target_screen})"
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
            return f"Неизвестное действие с громкостью: {action}"
    except Exception as e:
        logger.error(f"Volume adjust failed: {e}", exc_info=True)
        return f"Ошибка при изменении громкости: {e}"

def run_custom_script(script_code: str) -> str:
    """Saves custom generated python script and executes it in the background."""
    logger.info("Executing custom generated script...")
    temp_path = ""
    try:
        fd, temp_path = tempfile.mkstemp(suffix=".py")
        os.close(fd)
        
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(script_code)
            
        # Run python script in subprocess
        res = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=15
        )
        output = f"Stdout:\n{res.stdout}\nStderr:\n{res.stderr}"
        logger.info(f"Custom script execution result: {output}")
        return f"Выполнил динамический скрипт. Результат:\n{output}"
    except Exception as e:
        logger.error("Failed executing custom script", exc_info=True)
        return f"Ошибка при выполнении динамического скрипта: {e}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

def shutdown_pc(delay: int = 10) -> str:
    try:
        os.system(f"shutdown /s /t {delay}")
        return f"Компьютер выключится через {delay} секунд."
    except Exception as e:
        return f"Ошибка: {e}"

def restart_pc(delay: int = 10) -> str:
    try:
        os.system(f"shutdown /r /t {delay}")
        return f"Компьютер перезагрузится через {delay} секунд."
    except Exception as e:
        return f"Ошибка: {e}"

def execute_command_dict(cmd_data: dict) -> tuple[str, str]:
    """Decodes JSON and executes the command on the Windows PC."""
    command = cmd_data.get("command", "").lower()
    args = cmd_data.get("args", {})
    target_screen = args.get("target_screen", "main")
    
    if command == "screenshot":
        path = take_screenshot()
        if path:
            return "Снимок экрана готов!", path
        else:
            return "Не удалось сделать снимок экрана.", ""
            
    elif command == "open_browser":
        url = args.get("url", "")
        res = open_url(url, target_screen)
        return res, ""
        
    elif command == "youtube":
        query = args.get("query", "")
        mode = args.get("mode", "search")
        res = open_youtube(query, mode, target_screen)
        return res, ""
        
    elif command == "yandex_music":
        query = args.get("query", "")
        res = open_yandex_music(query, target_screen)
        return res, ""
        
    elif command == "media_control":
        action = args.get("action", "")
        res = media_control(action)
        return res, ""
        
    elif command == "open_app":
        app_name = args.get("app_name", "")
        res = open_app(app_name, target_screen)
        return res, ""
        
    elif command == "adjust_volume":
        action = args.get("action", "up")
        amount = args.get("amount", 10)
        res = adjust_volume(action, amount)
        return res, ""
        
    elif command == "move_window":
        keyword = args.get("keyword", "")
        screen = args.get("target_screen", "main")
        res = move_window_to_screen(keyword, screen)
        return res, ""
        
    elif command == "run_custom_script":
        script_code = args.get("script_code", "")
        res = run_custom_script(script_code)
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
