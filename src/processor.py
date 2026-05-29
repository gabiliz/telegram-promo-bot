import re
import unicodedata
from typing import Optional

PRICE_PATTERN = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)",
    re.IGNORECASE,
)

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _to_float(raw: str) -> Optional[float]:
    cleaned = raw.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_price(text: str) -> Optional[float]:
    matches = PRICE_PATTERN.findall(text)
    if not matches:
        return None
    values = [v for v in (_to_float(m) for m in matches) if v is not None]
    if not values:
        return None
    return min(values)


def normalize_text(text: str) -> str:
    cleaned = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )
    cleaned = cleaned.replace("\n", " ").replace("\t", " ")
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned.lower()


class MessageProcessor:
    def process_message(self, raw_text: str) -> tuple[str, Optional[float]]:
        normalized = normalize_text(raw_text)
        price = extract_price(raw_text)
        return normalized, price
