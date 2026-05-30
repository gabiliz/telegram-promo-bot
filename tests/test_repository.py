import pytest

from src.models import Promotion
from src.repository import KeywordRepository


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    repository = KeywordRepository(db_path)
    await repository.initialize()
    return repository


async def test_add_keyword_idempotent(repo):
    a = await repo.add_keyword("monitor", 1500.0)
    b = await repo.add_keyword("monitor", 1500.0)
    assert a.id == b.id
    keywords = await repo.get_all_keywords()
    assert len(keywords) == 1


async def test_is_already_seen_lifecycle(repo):
    assert not await repo.is_already_seen(10, 20)
    await repo.mark_as_seen(10, 20)
    assert await repo.is_already_seen(10, 20)


async def test_get_all_keywords_returns_typed(repo):
    await repo.add_keyword("monitor", 1500.0)
    await repo.add_keyword("notebook", None)
    keywords = await repo.get_all_keywords()
    assert {k.term for k in keywords} == {"monitor", "notebook"}
    assert all(isinstance(k.term, str) for k in keywords)


async def test_remove_keyword_returns_false_for_missing(repo):
    assert await repo.remove_keyword("inexistente") is False


async def test_remove_keyword_returns_true_for_existing(repo):
    await repo.add_keyword("monitor", None)
    assert await repo.remove_keyword("monitor") is True


async def test_update_keyword_price(repo):
    await repo.add_keyword("monitor", None)
    assert await repo.update_keyword_price("monitor", 1200.0) is True
    keywords = await repo.get_all_keywords()
    assert keywords[0].max_price == 1200.0


async def test_log_sent_notification(repo):
    promo = Promotion(
        message_id=1,
        group_id=2,
        group_name="g",
        group_username=None,
        raw_text="r",
        normalized_text="n",
        extracted_price=10.0,
        coupon="PROMO10",
        matched_keywords=["monitor"],
        message_link="",
    )
    await repo.log_sent_notification(promo)


async def test_monitored_group_lifecycle(repo):
    assert await repo.add_monitored_group("promosbr", "Promos BR") is True
    assert await repo.add_monitored_group("promosbr") is False  # idempotente
    groups = await repo.get_monitored_groups()
    assert groups == [{"identifier": "promosbr", "label": "Promos BR"}]
    assert await repo.remove_monitored_group("promosbr") is True
    assert await repo.remove_monitored_group("promosbr") is False
    assert await repo.get_monitored_groups() == []


async def test_quiet_hours_set_get_disable(repo):
    from datetime import time

    assert await repo.get_quiet_hours() is None
    await repo.set_quiet_hours(time(23, 0), time(7, 30))
    quiet = await repo.get_quiet_hours()
    assert quiet == (time(23, 0), time(7, 30))
    await repo.disable_quiet_hours()
    assert await repo.get_quiet_hours() is None


async def test_history_and_stats(repo):
    promo = Promotion(
        message_id=1,
        group_id=2,
        group_name="Fraguas84",
        group_username=None,
        raw_text="r",
        normalized_text="n",
        extracted_price=1564.0,
        coupon="GOLEADA",
        matched_keywords=["monitor"],
        message_link="https://t.me/g/1",
    )
    await repo.log_sent_notification(promo)
    await repo.mark_as_seen(1, 2)

    history = await repo.get_recent_notifications(5)
    assert len(history) == 1
    assert history[0]["group_name"] == "Fraguas84"
    assert history[0]["price"] == 1564.0
    assert history[0]["coupon"] == "GOLEADA"

    stats = await repo.get_stats()
    assert stats["total_notified"] == 1
    assert stats["total_processed"] == 1
    assert stats["top_keywords"] == [("monitor", 1)]
    assert stats["top_groups"] == [("Fraguas84", 1)]
