from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from database.models import User, Note

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

async def create_note(
    session: AsyncSession,
    user_id: int,
    title: str,
    original_text: str,
    summary: str,
    category: str,
    tasks: list[str]
) -> Note:
    """Creates a new note for a user."""
    note = Note(
        user_id=user_id,
        title=title,
        original_text=original_text,
        summary=summary,
        category=category,
        tasks=tasks
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
