from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.models import AppConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_api_id: int
    telegram_api_hash: str
    bot_token: str
    owner_chat_id: int
    monitored_groups: str
    default_max_price: float = 0.0
    database_path: str = "promo_bot.db"
    session_name: str = "promo_bot_session"

    @field_validator("telegram_api_hash")
    @classmethod
    def hash_must_be_32_chars(cls, v: str) -> str:
        if len(v) != 32:
            raise ValueError("TELEGRAM_API_HASH deve ter exatamente 32 caracteres")
        return v

    def to_app_config(self) -> AppConfig:
        groups = [g.strip() for g in self.monitored_groups.split(",") if g.strip()]
        return AppConfig(
            api_id=self.telegram_api_id,
            api_hash=self.telegram_api_hash,
            bot_token=self.bot_token,
            owner_chat_id=self.owner_chat_id,
            monitored_groups=groups,
            default_max_price=self.default_max_price,
            database_path=self.database_path,
            session_name=self.session_name,
        )


def load_config() -> AppConfig:
    return Settings().to_app_config()  # type: ignore[call-arg]
