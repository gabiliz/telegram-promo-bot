from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Keyword:
    id: Optional[int]
    term: str
    max_price: Optional[float]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Promotion:
    message_id: int
    group_id: int
    group_name: str
    group_username: Optional[str]
    raw_text: str
    normalized_text: str
    extracted_price: Optional[float]
    matched_keywords: list[str]
    message_link: str
    detected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AppConfig:
    api_id: int
    api_hash: str
    bot_token: str
    owner_chat_id: int
    monitored_groups: list[str]
    default_max_price: float
    database_path: str
    session_name: str
