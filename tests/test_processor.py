from src.processor import MessageProcessor, extract_price, normalize_text


def test_extract_price_thousands_decimal():
    assert extract_price("R$ 1.299,99") == 1299.99


def test_extract_price_no_space():
    assert extract_price("R$800") == 800.0


def test_extract_price_picks_smallest_when_multiple():
    assert extract_price("de R$ 2.000 por R$ 1.500") == 1500.0


def test_extract_price_no_price_returns_none():
    assert extract_price("sem preço aqui") is None


def test_extract_price_without_currency_symbol_returns_none():
    assert extract_price("de 49,90") is None


def test_extract_price_with_decimal_only():
    assert extract_price("R$ 800,00") == 800.0


def test_normalize_text_lowercases():
    assert normalize_text("MONITOR GAMER 4K!!") == "monitor gamer 4k!!"


def test_normalize_text_collapses_spaces():
    assert normalize_text("  espaços   extras  ") == "espaços extras"


def test_process_message_returns_tuple():
    processor = MessageProcessor()
    normalized, price = processor.process_message("MONITOR R$ 1.299,99")
    assert normalized == "monitor r$ 1.299,99"
    assert price == 1299.99
