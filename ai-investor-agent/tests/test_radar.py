from app.llm_agents import run_signal_radar


def test_radar_returns_feed_without_external_services():
    feed = run_signal_radar(limit=3)
    assert feed.radar_summary
    assert isinstance(feed.signals, list)
    assert len(feed.signals) <= 3
    for signal in feed.signals:
        assert signal.id
        assert signal.symbol
        assert signal.confidence_pct >= 0
