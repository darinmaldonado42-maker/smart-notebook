import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices, field_validator

class Settings(BaseSettings):
    bot_token: str = Field(..., validation_alias="BOT_TOKEN")
    database_url: str = Field(..., validation_alias="DATABASE_URL")
    redis_url: str = Field(..., validation_alias="REDIS_URL")
    
    # OpenAI configurations
    openai_api_key: str = Field(..., validation_alias="OPENAI_KEY" if os.getenv("OPENAI_KEY") else "OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_chat_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_CHAT_MODEL")
    openai_whisper_model: str = Field(default="whisper-1", validation_alias="OPENAI_WHISPER_MODEL")

    # Throttling configurations (seconds)
    voice_throttle_rate: float = Field(default=5.0, validation_alias="VOICE_THROTTLE_RATE")
    text_throttle_rate: float = Field(default=1.0, validation_alias="TEXT_THROTTLE_RATE")

    # Web Server & WebApp configurations
    webapp_url: str = Field(default="http://localhost:8080", validation_alias="WEBAPP_URL")
    web_port: int = Field(default=8080, validation_alias=AliasChoices("PORT", "WEB_PORT"))
    web_host: str = Field(default="0.0.0.0", validation_alias="WEB_HOST")

    @field_validator("database_url", mode="before")
    @classmethod
    def convert_postgres_url(cls, v: str) -> str:
        if v and isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings singleton
settings = Settings()
