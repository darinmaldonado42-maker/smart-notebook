from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import delete_note, get_note_by_id

router = Router(name="callbacks")

@router.callback_query(F.data.startswith("delete_note:"))
async def handle_delete_note(callback: CallbackQuery, session: AsyncSession):
    note_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    success = await delete_note(session, user_id=user_id, note_id=note_id)
    if success:
        await callback.answer("Заметка удалена")
        if callback.message:
            await callback.message.edit_text("❌ <b>Заметка успешно удалена.</b>", parse_mode="HTML")
    else:
        await callback.answer("Ошибка: заметка не найдена или уже удалена.", show_alert=True)

@router.callback_query(F.data.startswith("share_note:"))
async def handle_share_note(callback: CallbackQuery, session: AsyncSession):
    note_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    note = await get_note_by_id(session, user_id=user_id, note_id=note_id)
    if not note:
        await callback.answer("Ошибка: заметка не найдена.", show_alert=True)
        return

    # Build shareable formatted output
    tasks_text = "\n".join(f"• {task}" for task in note.tasks) if note.tasks else "Задачи отсутствуют."
    
    share_text = (
        f"📅 <b>Дата:</b> {note.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"📂 <b>Категория:</b> #{note.category}\n\n"
        f"🎯 <b>Главное:</b>\n{note.summary}\n\n"
        f"📝 <b>Задачи:</b>\n{tasks_text}\n\n"
        f"🎙️ <b>Оригинальный текст:</b>\n<i>{note.original_text}</i>"
    )
    
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"📋 <b>Скопируйте и перешлите это сообщение:</b>\n\n{share_text}",
            parse_mode="HTML"
        )
