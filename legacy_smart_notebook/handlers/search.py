import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import search_notes, get_note_by_id

router = Router(name="search")

@router.message(Command("search"))
async def cmd_search(message: Message, session: AsyncSession):
    """Handles /search command. Extracts query, performs search, and prints matching records."""
    if not message.from_user:
        return

    # Extract search keyword
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        await message.answer(
            "⚠️ <b>Пожалуйста, укажите текст для поиска.</b>\n"
            "Пример: <code>/search проект</code>",
            parse_mode="HTML"
        )
        return

    query_text = args[1].strip()
    
    # Notify user we are searching
    loading_msg = await message.answer("🔍 <i>Поиск по базе данных...</i>", parse_mode="HTML")
    
    try:
        notes = await search_notes(session, user_id=message.from_user.id, query_text=query_text)
        
        if not notes:
            await loading_msg.edit_text(
                f"Ничего не найдено по запросу: <code>{query_text}</code>",
                parse_mode="HTML"
            )
            return

        response_lines = [f"🔍 <b>Найдено заметок: {len(notes)}</b>\n"]
        for idx, note in enumerate(notes, 1):
            date_str = note.created_at.strftime("%d.%m.%Y")
            note_title = note.title or f"Заметка #{note.id}"
            response_lines.append(
                f"{idx}. <b>📌 {note_title}</b> [#{note.category}] ({date_str})\n"
                f"🎯 {note.summary[:90]}...\n"
                f"👉 Посмотреть: /note_{note.id}\n"
            )

        await loading_msg.edit_text(
            "\n".join(response_lines),
            parse_mode="HTML"
        )
    except Exception as e:
        await loading_msg.edit_text(
            "❌ Произошла ошибка при выполнении поиска. Попробуйте еще раз позже.",
            parse_mode="HTML"
        )


@router.message(F.text.regexp(r"^/note_(\d+)$"))
async def show_single_note(message: Message, session: AsyncSession):
    """Allows user to open a specific note via clicking a link (/note_id) generated in search."""
    if not message.from_user or not message.text:
        return

    match = re.match(r"^/note_(\d+)$", message.text)
    if not match:
        return
    
    note_id = int(match.group(1))
    user_id = message.from_user.id

    try:
        note = await get_note_by_id(session, user_id=user_id, note_id=note_id)
        if not note:
            await message.answer("⚠️ Заметка не найдена или принадлежит другому пользователю.")
            return

        tasks_text = "\n".join(f"• {task}" for task in note.tasks) if note.tasks else "Задачи отсутствуют."
        note_title = note.title or "Без названия"
        
        text_content = (
            f"📌 <b>Название:</b> {note_title}\n"
            f"📅 <b>Дата:</b> {note.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📂 <b>Категория:</b> #{note.category}\n\n"
            f"🎯 <b>Главное:</b>\n{note.summary}\n\n"
            f"📝 <b>Задачи:</b>\n{tasks_text}\n\n"
            f"🎙️ <b>Оригинальный текст:</b>\n<i>{note.original_text}</i>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="📤 Поделиться", callback_data=f"share_note:{note.id}"),
                    InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_note:{note.id}")
                ]
            ]
        )

        await message.answer(text_content, reply_markup=keyboard, parse_mode="HTML")
    except Exception:
        await message.answer("❌ Произошла ошибка при открытии заметки.")
