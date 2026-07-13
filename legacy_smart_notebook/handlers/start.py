from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp
)
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.crud import upsert_user

router = Router(name="start")

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user = message.from_user
    if not user:
        return

    # Upsert user record in the database
    await upsert_user(
        session=session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )

    # Configure persistent bottom-left Menu Button pointing to the WebApp
    try:
        await message.bot.set_chat_menu_button(
            chat_id=message.chat.id,
            menu_button=MenuButtonWebApp(
                text="📓 Блокнот",
                web_app=WebAppInfo(url=settings.webapp_url)
            )
        )
    except Exception as e:
        # Non-critical issue if setting menu button fails (e.g. mock bot during tests)
        pass

    # Personal browser link (with user_id for non-Telegram access)
    personal_link = f"{settings.webapp_url}/?user_id={user.id}"

    welcome_text = (
        f"👋 <b>Привет, {user.first_name or 'пользователь'}!</b>\n\n"
        "Я — <b>Умный голосовой блокнот</b> с веб-интерфейсом.\n\n"
        "Отправьте мне <b>голосовое сообщение</b> (или обычный текст), и я:\n"
        "1. 🎙️ Распознаю речь в текст (OpenAI Whisper)\n"
        "2. 🧠 Выделю суть и структурирую мысли (LLM)\n"
        "3. 📁 Автоматически присвою категорию\n"
        "4. 📝 Соберу задачи в маркированный список\n"
        "5. 💾 Сохраню всё в базу данных\n\n"
        "Вы можете просматривать, искать и управлять заметками прямо в интерактивном <b>веб-приложении</b> по кнопке ниже!\n\n"
        f"🔗 <b>Ваша личная ссылка для браузера:</b>\n"
        f"<code>{personal_link}</code>"
    )

    # Two buttons: open as Telegram Mini App + open in browser
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📓 Открыть в Telegram",
                    web_app=WebAppInfo(url=settings.webapp_url)
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Открыть в браузере",
                    url=personal_link
                )
            ]
        ]
    )
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.message(Command("mylink"))
async def cmd_mylink(message: Message):
    """Sends personal webapp link when user sends /mylink."""
    user = message.from_user
    if not user:
        return
    personal_link = f"{settings.webapp_url}/?user_id={user.id}"
    await message.answer(
        f"🔗 <b>Ваша личная ссылка на блокнот:</b>\n\n"
        f"<code>{personal_link}</code>\n\n"
        "Откройте её в браузере чтобы увидеть все ваши заметки.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🌐 Открыть в браузере", url=personal_link)
            ]]
        )
    )

