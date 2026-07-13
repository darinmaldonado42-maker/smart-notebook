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

def find_app_shortcut(app_name: str) -> str:
    """Recursively searches Start Menu and Desktop folders for a matching app shortcut (.lnk or .exe)."""
    app_name_lower = app_name.lower().strip()
    
    # Common Windows folders containing app shortcuts/executables
    username = os.getlogin()
    search_dirs = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        f"C:\\Users\\{username}\\AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs",
        r"C:\Users\Public\Desktop",
        f"C:\\Users\\{username}\\Desktop",
        f"C:\\Users\\{username}\\AppData\\Local\\Programs"
    ]
    
    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.lower().endswith((".lnk", ".exe")):
                    name_without_ext = os.path.splitext(file)[0].lower()
                    if app_name_lower == name_without_ext or app_name_lower in name_without_ext:
                        return os.path.join(root, file)
    return ""

def open_app(app_query: str, target_screen: str = "main") -> str:
    """Launches local Windows applications and optionally moves them to target screen."""
    query = app_query.lower().strip()
    
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
    
    # 1. Match hardcoded mapping
    for name, exe in app_map.items():
        if name in query:
            executable = exe
            keyword = name
            break
            
    # 2. Search for Windows Start Menu / Desktop shortcuts (.lnk or .exe)
    if not executable:
        shortcut_path = find_app_shortcut(app_query)
        if shortcut_path:
            executable = shortcut_path
            keyword = os.path.splitext(os.path.basename(shortcut_path))[0]
        elif query.endswith(".exe"):
            executable = query
            keyword = query.replace(".exe", "")
        else:
            # Fallback to direct execution attempt
            executable = app_query
            keyword = app_query
            
    try:
        if executable.endswith(".lnk"):
            os.startfile(executable)
            res_msg = f"Запустил ярлык: {os.path.basename(executable)}"
        else:
            subprocess.Popen(executable, shell=True)
            res_msg = f"Запустил приложение: {executable}"
            
        # Move window if target screen is not main
        if target_screen != "main" and keyword:
            time.sleep(2.0)  # Wait for program window to spawn
            move_window_to_screen(keyword, target_screen)
            return f"{res_msg} (переместил на экран: {target_screen})"
        return f"{res_msg} (экран: {target_screen})"
    except Exception as e:
        logger.error(f"Error launching application '{app_query}': {e}", exc_info=True)
        return f"Ошибка при запуске '{app_query}': {e}"

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

def play_my_wave(target_screen: str = "main") -> str:
    """Opens Yandex Music, waits 1.5s, focuses browser, and clicks banner dynamically based on window position."""
    try:
        # 1. Open Yandex Music
        open_url("https://music.yandex.ru/home", target_screen)
        time.sleep(1.5)
        
        # 2. Find and focus browser window
        win = None
        for w in gw.getAllWindows():
            if w.title and any(k in w.title.lower() for k in ['yandex', 'яндекс', 'chrome', 'youtube', 'music', 'opera', 'edge', 'firefox', 'браузер']):
                win = w
                break
                
        if win:
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.5)
            
            # Click exactly in the center of 'My Wave' banner relative to window left and top
            click_x = win.left + 725
            click_y = win.top + 360
            pyautogui.click(click_x, click_y)
            return "Запустил 'Мою волну' на Яндекс.Музыке (клик по баннеру)."
        else:
            return "Окно браузера не найдено для запуска воспроизведения."
    except Exception as e:
        logger.error(f"Failed to play My Wave: {e}", exc_info=True)
        return f"Не удалось включить Мою волну: {e}"

def play_first_youtube_video(target_screen: str = "main") -> str:
    """Opens YouTube, waits 2.0s, focuses browser, and clicks the first video relative to window position."""
    try:
        # 1. Open YouTube
        open_url("https://www.youtube.com", target_screen)
        time.sleep(2.0)
        
        # 2. Find and focus browser window
        win = None
        for w in gw.getAllWindows():
            if w.title and any(k in w.title.lower() for k in ['youtube', 'yandex', 'яндекс', 'chrome', 'opera', 'edge', 'firefox', 'браузер']):
                win = w
                break
                
        if win:
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.5)
            
            # Click first video relative to window left and top
            click_x = win.left + 280
            click_y = win.top + 350
            pyautogui.click(click_x, click_y)
            return "Открыл первое видео на YouTube."
        else:
            return "Окно YouTube не найдено."
    except Exception as e:
        logger.error(f"Failed to play first YouTube video: {e}", exc_info=True)
        return f"Не удалось открыть первое видео: {e}"

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
        
    elif command == "play_my_wave":
        res = play_my_wave(target_screen)
        return res, ""
        
    elif command == "play_first_youtube_video":
        res = play_first_youtube_video(target_screen)
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
        
    elif command == "list_windows":
        try:
            titles = []
            for w in gw.getAllWindows():
                if w.title and w.width > 100 and w.height > 100:
                    titles.append(w.title)
            unique_titles = list(set(titles))
            if not unique_titles:
                res = "Открытые окна не найдены."
            else:
                res = "Список открытых окон:\n" + "\n".join([f"- {t}" for t in unique_titles])
        except Exception as e:
            res = f"Ошибка получения списка окон: {e}"
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
