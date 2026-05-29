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
        matched_keywords=["monitor"],
        message_link="",
    )
    await repo.log_sent_notification(promo)
