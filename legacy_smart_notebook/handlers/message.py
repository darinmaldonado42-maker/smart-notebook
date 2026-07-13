import os
import tempfile
import logging
import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import create_note, get_user_categories, update_note_append
from database.models import Note
from services.openai import openai_service

logger = logging.getLogger(__name__)
router = Router(name="message")

class LocationStates(StatesGroup):
    WaitingForCity = State()

async def process_and_save_note(session: AsyncSession, user_id: int, raw_text: str) -> tuple[Note, bool]:
    """
    Sends raw text along with recent notes and custom categories to LLM,
    then saves as a new note or appends to an existing note.
    Returns a tuple: (note, was_updated)
    """
    # 1. Fetch user categories
    categories = await get_user_categories(session, user_id)
    category_names = [c.name for c in categories]
    
    # 2. Fetch last 10 notes to check for semantic matching
    stmt = select(Note).where(Note.user_id == user_id).order_by(Note.created_at.desc()).limit(10)
    result = await session.execute(stmt)
    recent_notes_objs = result.scalars().all()
    recent_notes = [{"id": n.id, "title": n.title, "summary": n.summary} for n in recent_notes_objs]
    
    # 3. Structure text via OpenAI service
    structured = await openai_service.structure_text(raw_text, categories=category_names, recent_notes=recent_notes)
    
    matched_note_id = structured.get("matched_note_id")
    title = structured.get("title", "Без названия")
    category = structured.get("category", "Повседневное")
    summary = structured.get("summary", "Нет описания.")
    tasks = structured.get("tasks", [])
    is_outdoor = structured.get("is_outdoor", False)
    
    # Parse reminder date if present
    reminder_at = None
    reminder_at_raw = structured.get("reminder_at")
    if reminder_at_raw:
        try:
            from datetime import datetime
            reminder_at = datetime.fromisoformat(reminder_at_raw.replace("Z", "+00:00"))
        except Exception as ex:
            logger.error(f"Failed to parse reminder_at '{reminder_at_raw}': {ex}")
            
    note = None
    was_updated = False
    
    if matched_note_id:
        # Semantically matched: append to existing note
        note = await update_note_append(
            session=session,
            user_id=user_id,
            note_id=matched_note_id,
            new_summary=summary,
            append_tasks=tasks,
            append_raw_text=raw_text,
            reminder_at=reminder_at,
            is_outdoor=is_outdoor
        )
        if note:
            was_updated = True
            
    if not note:
        # Create a new note
        note = await create_note(
            session=session,
            user_id=user_id,
            title=title,
            original_text=raw_text,
            summary=summary,
            category=category,
            tasks=tasks,
            reminder_at=reminder_at,
            is_outdoor=is_outdoor
        )
        
    return note, was_updated

async def render_and_send_note(message: Message, note: Note, status_msg: Message, was_updated: bool = False):
    """Formats and edits status message with the saved note info and inline buttons."""
    tasks_text = "\n".join(f"• {task}" for task in note.tasks) if note.tasks else "Задачи отсутствуют."
    status_header = "обновлена" if was_updated else "сохранена"
    
    response_text = (
        f"✅ <b>Заметка успешно {status_header}!</b>\n\n"
        f"📌 <b>Название:</b> {note.title}\n"
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
    
    await status_msg.edit_text(response_text, reply_markup=keyboard, parse_mode="HTML")

@router.message(F.voice | F.audio)
async def handle_voice_message(message: Message, session: AsyncSession, bot: Bot):
    """Processes incoming voice or audio messages. Downloands, transcribes, and structures."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    voice = message.voice or message.audio
    
    # Ensure voice object is present (sanity check)
    if not voice:
        return

    # Check file size (Telegram bot limit for direct download is 20MB)
    if voice.file_size > 20 * 1024 * 1024:
        await message.answer("⚠️ Размер аудиофайла не должен превышать 20 МБ.")
        return

    status_msg = await message.answer("📥 <i>Скачиваю голосовое сообщение...</i>", parse_mode="HTML")
    
    temp_file_path = ""
    try:
        # Retrieve path from telegram server
        file_info = await bot.get_file(voice.file_id)
        
        # Detect extension
        suffix = ".ogg" if message.voice else os.path.splitext(file_info.file_path)[1] or ".mp3"
        
        # Create a secure temporary file
        fd, temp_file_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd) # Close handle, write bytes directly using bot client
        
        await bot.download_file(file_info.file_path, temp_file_path)
        
        # Transcribe
        await status_msg.edit_text("🎙️ <i>Распознаю речь (Whisper)...</i>", parse_mode="HTML")
        raw_text = await openai_service.transcribe_audio(temp_file_path)
        
        if not raw_text or not raw_text.strip():
            await status_msg.edit_text(
                "⚠️ Не удалось распознать слова в аудиосообщении. Попробуйте наговорить погромче и разборчивее."
            )
            return

    except Exception as e:
        logger.error(f"Error in transcription handler: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ Произошла ошибка при обработке аудио. Возможно, сервис временно перегружен. Попробуйте позже."
        )
        return
    finally:
        # Clean up temporary file immediately under any circumstances
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as err:
                logger.error(f"Error removing temp voice file {temp_file_path}: {err}")

    # Process and save transcript
    await status_msg.edit_text("🧠 <i>Выделяю суть и задачи (GPT-4o-mini)...</i>", parse_mode="HTML")
    try:
        note, was_updated = await process_and_save_note(session, user_id, raw_text)
        await render_and_send_note(message, note, status_msg, was_updated)
    except Exception as e:
        logger.error(f"Error in GPT or DB storage: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ К сожалению, сервис структурирования мыслей временно недоступен. Пожалуйста, отправьте заметку повторно."
        )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text_message(message: Message, session: AsyncSession):
    """Processes incoming text notes. Directly structures and saves them."""
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    raw_text = message.text

    status_msg = await message.answer("🧠 <i>Выделяю суть и задачи (GPT-4o-mini)...</i>", parse_mode="HTML")
    
    try:
        note, was_updated = await process_and_save_note(session, user_id, raw_text)
        await render_and_send_note(message, note, status_msg, was_updated)
    except Exception as e:
        logger.error(f"Error in structuring text or saving note: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ Не удалось обработать текст с помощью ИИ. Попробуйте отправить сообщение повторно."
        )
