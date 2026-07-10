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

    async def structure_text(self, raw_text: str) -> dict:
        """
        Uses configured LLM model to analyze and structure user's raw thoughts into JSON.
        Returns a dict with: 'category', 'summary', 'tasks', and 'raw_clean_text'.
        """
        system_prompt = (
            "Ты ассистент-структуризатор. Пользователь наговаривает поток мыслей.\n"
            "Твоя задача:\n"
            "1. Сгенерировать короткий и емкий заголовок для заметки (2-5 слов в именительном падеже, например: 'Поход в гости к маме', 'Идея мобильной игры', 'Подготовка к экзамену').\n"
            "2. Убрать мусор и слова-паразиты, выделить главную мысль (summary).\n"
            "3. Вытащить конкретные задачи в маркированный список (tasks).\n"
            "4. Присвоить одну из категорий: 'Идея', 'Задача', 'Учеба', 'Повседневное'.\n\n"
            "Верни ответ строго в формате JSON:\n"
            "{\n"
            "  \"title\": string,\n"
            "  \"category\": string,\n"
            "  \"summary\": string,\n"
            "  \"tasks\": list of strings,\n"
            "  \"raw_clean_text\": string\n"
            "}"
        )
        
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
            required_keys = ["title", "category", "summary", "tasks", "raw_clean_text"]
            for key in required_keys:
                if key not in data:
                    data[key] = "" if key != "tasks" else []
            
            return data
        except Exception as e:
            logger.error(f"Failed to structure text via OpenAI GPT API: {e}", exc_info=True)
            raise RuntimeError("Ошибка при обработке текста ИИ-моделью") from e

# Export a single instance for application-wide use
openai_service = OpenAIService()
