from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from database.models import User, Note, Category

async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None
) -> User:
    """Inserts a new user or updates their profile info if they already exist."""
    stmt = insert(User).values(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.telegram_id],
        set_={
            User.username: stmt.excluded.username,
            User.first_name: stmt.excluded.first_name,
            User.last_name: stmt.excluded.last_name
        }
    )
    # Returning the upserted user object
    stmt = stmt.returning(User)
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one()

from datetime import datetime

def ensure_task_objects(tasks):
    if not tasks:
        return []
    result = []
    for task in tasks:
        if isinstance(task, str):
            result.append({"text": task, "completed": False})
        elif isinstance(task, dict):
            # Ensure keys exist
            result.append({
                "text": task.get("text", ""),
                "completed": task.get("completed", False)
            })
    return result

async def create_note(
    session: AsyncSession,
    user_id: int,
    title: str,
    original_text: str,
    summary: str,
    category: str,
    tasks: list,
    reminder_at: datetime = None
) -> Note:
    """Creates a new note for a user."""
    note = Note(
        user_id=user_id,
        title=title,
        original_text=original_text,
        summary=summary,
        category=category,
        tasks=ensure_task_objects(tasks),
        reminder_at=reminder_at,
        reminder_sent=False
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note

async def get_note_by_id(session: AsyncSession, user_id: int, note_id: int) -> Note | None:
    """Retrieves a specific note belonging to a user."""
    stmt = select(Note).where(Note.id == note_id, Note.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def delete_note(session: AsyncSession, user_id: int, note_id: int) -> bool:
    """Deletes a specific note belonging to a user."""
    stmt = delete(Note).where(Note.id == note_id, Note.user_id == user_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0

async def search_notes(session: AsyncSession, user_id: int, query_text: str) -> list[Note]:
    """
    Performs full-text search on user notes using PostgreSQL to_tsvector and plainto_tsquery.
    Indexes Russian words using Russian language configuration.
    """
    stmt = (
        select(Note)
        .where(Note.user_id == user_id)
        .where(
            text(
                "to_tsvector('russian', coalesce(notes.title, '') || ' ' || coalesce(notes.original_text, '') || ' ' || coalesce(notes.summary, '')) @@ plainto_tsquery('russian', :query)"
            )
        )
        .params(query=query_text)
        .order_by(Note.created_at.desc())
    )
    result = await session.execute(stmt)
    notes = result.scalars().all()
    
    # Fallback to ILIKE if no matches are found, for better user experience on partial/substring matches
    if not notes:
        like_query = f"%{query_text}%"
        stmt_fallback = (
            select(Note)
            .where(Note.user_id == user_id)
            .where(
                (Note.title.ilike(like_query)) |
                (Note.original_text.ilike(like_query)) | 
                (Note.summary.ilike(like_query)) |
                (Note.category.ilike(like_query))
            )
            .order_by(Note.created_at.desc())
        )
        result_fallback = await session.execute(stmt_fallback)
        notes = result_fallback.scalars().all()
        
    return list(notes)

async def get_user_categories(session: AsyncSession, user_id: int) -> list[Category]:
    """Fetches user-defined categories. Seeds default ones if none exist."""
    stmt = select(Category).where(Category.user_id == user_id).order_by(Category.id.asc())
    result = await session.execute(stmt)
    categories = list(result.scalars().all())
    
    if not categories:
        # Seed default categories
        defaults = [
            ("Идея", "idea", "lightbulb"),
            ("Учеба", "study", "graduation-cap"),
            ("Повседневное", "daily", "house")
        ]
        categories = []
        for name, color, icon in defaults:
            cat = Category(user_id=user_id, name=name, color=color, icon=icon)
            session.add(cat)
            categories.append(cat)
        await session.commit()
        # Refresh to get IDs
        for cat in categories:
            await session.refresh(cat)
    return categories

async def create_user_category(
    session: AsyncSession,
    user_id: int,
    name: str,
    color: str,
    icon: str
) -> Category:
    """Creates a new custom category for a user."""
    cat = Category(user_id=user_id, name=name, color=color, icon=icon)
    session.add(cat)
    await session.commit()
    await session.refresh(cat)
    return cat

async def delete_user_category(
    session: AsyncSession,
    user_id: int,
    category_id: int
) -> bool:
    """Deletes a custom category for a user."""
    stmt = delete(Category).where(Category.id == category_id, Category.user_id == user_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0

async def update_note_append(
    session: AsyncSession,
    user_id: int,
    note_id: int,
    new_summary: str,
    append_tasks: list,
    append_raw_text: str,
    reminder_at: datetime = None
) -> Note | None:
    """Appends tasks, updates summary, and appends raw original text to an existing note."""
    note = await get_note_by_id(session, user_id, note_id)
    if not note:
        return None
        
    note.summary = new_summary
    
    # Format current tasks to objects to handle string legacy tasks
    current_tasks = ensure_task_objects(note.tasks)
    
    # Merge new append tasks avoiding duplicate text
    new_tasks = ensure_task_objects(append_tasks)
    for nt in new_tasks:
        if not any(t["text"].lower() == nt["text"].lower() for t in current_tasks):
            current_tasks.append(nt)
            
    note.tasks = current_tasks
    
    # Append to original text
    note.original_text = note.original_text + f"\n\n--- [Дополнение] ---\n" + append_raw_text
    
    # Reset/update reminder
    if reminder_at:
        note.reminder_at = reminder_at
        note.reminder_sent = False
        
    await session.commit()
    await session.refresh(note)
    return note


async def update_note(
    session: AsyncSession,
    user_id: int,
    note_id: int,
    title: str = None,
    category: str = None,
    summary: str = None,
    tasks: list = None,
    original_text: str = None,
    reminder_at: datetime = None
) -> Note | None:
    """Updates fields of an existing note."""
    note = await get_note_by_id(session, user_id, note_id)
    if not note:
        return None
        
    if title is not None:
        note.title = title
    if category is not None:
        note.category = category
    if summary is not None:
        note.summary = summary
    if tasks is not None:
        note.tasks = ensure_task_objects(tasks)
    if original_text is not None:
        note.original_text = original_text
        
    # Reset reminder status if updated
    if reminder_at is not None:
        note.reminder_at = reminder_at
        note.reminder_sent = False
    elif reminder_at is None and "reminder_at" in locals():
        # Specifically clearing reminder
        note.reminder_at = None
        note.reminder_sent = False
        
    await session.commit()
    await session.refresh(note)
    return note
