import json
import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        # Use custom base_url (like agentplatform.ru) if provided, otherwise fallback to default OpenAI URL
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )

    async def transcribe_audio(self, file_path: str) -> str:
        """
        Transcribes the audio file using the configured Whisper model.
        Returns the raw transcribed text.
        """
        try:
            with open(file_path, "rb") as audio_file:
                transcript = await self.client.audio.transcriptions.create(
                    model=settings.openai_whisper_model,
                    file=audio_file
                )
            return transcript.text
        except Exception as e:
            logger.error(f"Failed to transcribe audio via Whisper API: {e}", exc_info=True)
            raise RuntimeError("Ошибка при транскрибации аудио") from e

    async def structure_text(self, raw_text: str, categories: list[str] = None, recent_notes: list[dict] = None) -> dict:
        """
        Uses configured LLM model to analyze and structure user's raw thoughts into JSON.
        Compares with recent notes to merge/append tasks semantically, and matches user categories.
        """
        categories_str = ", ".join(f"'{c}'" for c in categories) if categories else "'Идея', 'Учеба', 'Повседневное'"
        
        notes_str = ""
        if recent_notes:
            notes_str = "\n".join(f"- ID: {n['id']}, Заголовок: '{n['title']}', Суть: '{n['summary']}'" for n in recent_notes)
        else:
            notes_str = "Нет существующих заметок."

        system_prompt = (
            "Ты ассистент-структуризатор. Пользователь наговаривает поток мыслей.\n"
            "Твоя задача:\n"
            "1. Сравнить новую мысль со списком существующих заметок пользователя. Если новая мысль логически/тематически продолжает или дополняет одну из существующих заметок, выбери её.\n"
            "2. Сгенерировать короткий и емкий заголовок для заметки (если создается новая заметка) или вернуть заголовок существующей (если дополняется существующая). Заголовок должен быть 2-5 слов в именительном падеже.\n"
            "3. Убрать мусор и слова-паразиты, выделить главную мысль (summary). Если мысль дополняет существующую заметку, сгенерируй обновленный summary, объединяющий старую суть и новую мысль.\n"
            "4. Вытащить новые конкретные задачи в маркированный список (tasks).\n"
            "5. Присвоить одну из доступных категорий: {categories_str}.\n\n"
            "Список существующих заметок пользователя:\n"
            "{notes_str}\n\n"
            "Верни ответ строго в формате JSON:\n"
            "{{\n"
            "  \"matched_note_id\": int or null,  // ID существующей заметки, если новая мысль логически дополняет её, иначе null\n"
            "  \"title\": string,                 // заголовок заметки\n"
            "  \"category\": string,              // категория заметки (выбери одну из: {categories_str})\n"
            "  \"summary\": string,               // суть (обновленный summary для существующей или новый summary для новой)\n"
            "  \"tasks\": list of strings,        // только НОВЫЕ задачи, извлеченные из сообщения, которые нужно добавить/создать\n"
            "  \"raw_clean_text\": string\n"
            "}}"
        ).format(categories_str=categories_str, notes_str=notes_str)
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_chat_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text}
                ],
                temperature=0.3
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Получен пустой ответ от OpenAI API")
                
            data = json.loads(content)
            # Validate required JSON keys
            required_keys = ["title", "category", "summary", "tasks", "raw_clean_text", "matched_note_id"]
            for key in required_keys:
                if key not in data:
                    if key == "tasks":
                        data[key] = []
                    elif key == "matched_note_id":
                        data[key] = None
                    else:
                        data[key] = ""
            
            return data
        except Exception as e:
            logger.error(f"Failed to structure text via OpenAI GPT API: {e}", exc_info=True)
            raise RuntimeError("Ошибка при обработке текста ИИ-моделью") from e

# Export a single instance for application-wide use
openai_service = OpenAIService()
