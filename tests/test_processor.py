from src.processor import (
    MessageProcessor,
    extract_coupon,
    extract_price,
    normalize_text,
)


def test_extract_price_thousands_decimal():
    assert extract_price("R$ 1.299,99") == 1299.99


def test_extract_price_no_separator_full_digits():
    assert extract_price("R$ 1564 no PIX") == 1564.0


def test_extract_price_thousands_separator_no_decimal():
    assert extract_price("R$ 1.564 no PIX") == 1564.0


def test_extract_price_no_separator_with_decimal():
    assert extract_price("R$ 1564,00") == 1564.0


def test_extract_price_thousands_separator_with_decimal():
    assert extract_price("R$ 1.564,00") == 1564.0


def test_extract_price_five_digits_thousands():
    assert extract_price("R$ 12.999,99") == 12999.99


def test_extract_price_multiple_from_por():
    assert extract_price("de R$ 2.000 por R$ 1.564") == 1564.0


def test_extract_price_multiple_picks_smallest_no_separator():
    assert extract_price("R$ 1564 ou R$ 800") == 800.0


def test_extract_price_cents_only():
    assert extract_price("R$ 0,99") == 0.99


def test_extract_price_six_digits():
    assert extract_price("R$ 999999") == 999999.0


def test_extract_price_number_without_currency_returns_none():
    assert extract_price("1564 reais") is None


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


def test_extract_coupon_backticks():
    assert extract_coupon("cupom: `GOLEADA`") == "GOLEADA"


def test_extract_coupon_keyword_prefix():
    assert extract_coupon("use o código PROMO10 para desconto") == "PROMO10"


def test_extract_coupon_lowercase_normalizes_to_upper():
    assert extract_coupon("cupom: save20") == "SAVE20"


def test_extract_coupon_none():
    assert extract_coupon("sem cupom aqui") is None


def test_process_message_returns_triple():
    processor = MessageProcessor()
    normalized, price, coupon = processor.process_message(
        "MONITOR R$ 1.299,99 cupom: `OFERTA`"
    )
    assert normalized == "monitor r$ 1.299,99 cupom: `oferta`"
    assert price == 1299.99
    assert coupon == "OFERTA"
