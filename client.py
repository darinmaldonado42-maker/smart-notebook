import sys
import subprocess
import os

def main():
    print("=" * 60)
    print("🌍 ПРОЕКТ УСПЕШНО ПЕРЕСОЗДАН В 'НЕБЕСНЫЙ ГЕОДЕЗИСТ' 🌍")
    print("=" * 60)
    print("Бот для геолокации по кружкам с небом теперь запускается через bot.py.")
    print("Автоматически запускаю bot.py на вашем ПК...\n")
    
    bot_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.py")
    try:
        # Run bot.py and stream output to console
        process = subprocess.Popen([sys.executable, bot_script])
        process.wait()
    except KeyboardInterrupt:
        print("\nБот остановлен.")
    except Exception as e:
        print(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()
