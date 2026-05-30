import pytest

from src.filter_engine import FilterEngine
from src.repository import KeywordRepository


@pytest.fixture
async def repo(tmp_path):
    repository = KeywordRepository(str(tmp_path / "test.db"))
    await repository.initialize()
    return repository


async def test_already_seen_returns_false(repo):
    await repo.add_keyword("monitor", None)
    await repo.mark_as_seen(1, 100)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor barato", None, 1, 100)
    assert ok is False
    assert matched == []


async def test_keyword_without_price_matches_regardless(repo):
    await repo.add_keyword("monitor", None)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor 4k incrivel", 9999.0, 1, 100)
    assert ok is True
    assert matched == ["monitor"]


async def test_price_above_max_excludes(repo):
    await repo.add_keyword("monitor", 1500.0)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor por r$ 2000", 2000.0, 1, 100)
    assert ok is False
    assert matched == []


async def test_price_below_max_matches(repo):
    await repo.add_keyword("monitor", 1500.0)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor por r$ 1200", 1200.0, 1, 100)
    assert ok is True
    assert "monitor" in matched


async def test_no_price_in_message_but_keyword_has_max_excludes(repo):
    await repo.add_keyword("monitor", 1500.0)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor incrivel", None, 1, 100)
    assert ok is False
    assert matched == []


async def test_no_keyword_match(repo):
    await repo.add_keyword("notebook", None)
    engine = FilterEngine(repo, default_max_price=0.0)
    ok, matched = await engine.evaluate("monitor por r$ 1200", 1200.0, 1, 100)
    assert ok is False
    assert matched == []


async def test_quiet_hours_suppresses_notification(repo, monkeypatch):
    await repo.add_keyword("monitor", None)
    engine = FilterEngine(repo, default_max_price=0.0)

    async def _always_quiet() -> bool:
        return True

    monkeypatch.setattr(engine, "_is_quiet_time", _always_quiet)
    ok, matched = await engine.evaluate("monitor 4k", 100.0, 1, 100)
    assert ok is False
    assert matched == []
    # Não deve marcar como visto durante horário silencioso.
    assert not await repo.is_already_seen(1, 100)
