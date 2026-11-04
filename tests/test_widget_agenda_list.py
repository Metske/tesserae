"""Server contract tests for T6 / Ticket #7:
Scrollable Multi-Day Agenda List Widget Region.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bundle_sync import build_bundle
from app.state.deck_model import Deck, DeckPage
from app.state.panel_store import Element
from app.touch_spec import build_frame_spec


def test_frame_spec_emits_agenda_list_widget() -> None:
    els = [
        Element(
            id="agenda1",
            kind="agenda_list",
            x=60,
            y=120,
            w=800,
            h=1200,
        ),
    ]

    doc = build_frame_spec(els)
    assert "widgets" in doc
    assert len(doc["widgets"]) == 1
    w = doc["widgets"][0]
    assert w["id"] == "agenda1"
    assert w["kind"] == "agenda_list"
    assert w["rect"] == {"x": 60, "y": 120, "w": 800, "h": 1200}
    assert w["bindings"]["calendar"] == "calendar.upcoming"


def test_bundle_emits_calendar_upcoming_dataset(tmp_path: Path) -> None:
    deck = Deck(
        id="deck_agenda",
        name="Agenda Deck",
        pages=[DeckPage(page_id="p_agenda")],
    )

    class DummyPushMgr:
        def deck_render_for(self, device_id: str, page_id: str) -> dict[str, Any] | None:
            return {"digest": "1234567890abcdef", "filename": "agenda.bin"}

    renders_dir = tmp_path / "renders"
    renders_dir.mkdir()
    (renders_dir / "agenda.bin").write_bytes(b"\x00" * 100)

    bundle = build_bundle(
        deck,
        "dev1",
        push_mgr=DummyPushMgr(),
        renders_dir=renders_dir,
    )
    assert bundle is not None
    assert "datasets" in bundle
    assert "calendar" in bundle["datasets"]
    assert "upcoming" in bundle["datasets"]["calendar"]
    events = bundle["datasets"]["calendar"]["upcoming"]
    assert len(events) >= 5
    first = events[0]
    assert "id" in first
    assert "title" in first
    assert "start_epoch" in first
    assert "end_epoch" in first
    assert "time_str" in first
