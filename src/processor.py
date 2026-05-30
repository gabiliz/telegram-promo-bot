import re
import unicodedata
from typing import Optional

PRICE_PATTERN = re.compile(
    r"R\$\s*"
    r"(\d{1,3}(?:\.\d{3})+(?:,\d{2})?"  # com separador de milhar: 1.564 / 1.564,00 / 12.000,00
    r"|\d{1,6}(?:,\d{2})?)",  # sem separador: 1564 / 800 / 49,90 (até 999999)
    re.IGNORECASE,
)

# Cupom entre backticks é um delimitador explícito — aceita qualquer token.
_COUPON_BACKTICK_PATTERN = re.compile(r"`([A-Za-z0-9]{3,20})`")
# Cupom após palavra-chave: exige que o token pareça um código (tem dígito ou
# letra maiúscula) para evitar capturar palavras comuns como "aqui".
_COUPON_KEYWORD_PATTERN = re.compile(
    r"(?:cupom|c[oó]digo|code|coupon|promo|desconto)[:\s]+([A-Za-z0-9]{3,20})",
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


def _looks_like_code(token: str) -> bool:
    return any(ch.isdigit() for ch in token) or any(ch.isupper() for ch in token)


def extract_coupon(text: str) -> Optional[str]:
    backtick = _COUPON_BACKTICK_PATTERN.search(text)
    if backtick:
        return backtick.group(1).upper()
    keyword = _COUPON_KEYWORD_PATTERN.search(text)
    if keyword and _looks_like_code(keyword.group(1)):
        return keyword.group(1).upper()
    return None


def normalize_text(text: str) -> str:
    cleaned = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )
    cleaned = cleaned.replace("\n", " ").replace("\t", " ")
    cleaned = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned.lower()


class MessageProcessor:
    def process_message(
        self, raw_text: str
    ) -> tuple[str, Optional[float], Optional[str]]:
        normalized = normalize_text(raw_text)
        price = extract_price(raw_text)
        coupon = extract_coupon(raw_text)
        return normalized, price, coupon
