"""Server contract tests for T5 / Ticket #6:
Hybrid /frame/spec widgets[]: Live Clock, Indoor Climate & Hourly Weather Strip.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.bundle_sync import build_bundle
from app.state.deck_model import Deck, DeckPage
from app.state.panel_store import Element
from app.touch_spec import (
    build_frame_spec,
    touch_layout_digest,
    wire_transform,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


def _validator() -> Draft202012Validator:
    spec = json.loads((_SCHEMA_DIR / "frame-spec.schema.json").read_text())
    atlas = json.loads((_SCHEMA_DIR / "atlas.schema.json").read_text())
    reg = Registry().with_resources([("atlas.schema.json", Resource.from_contents(atlas))])
    return Draft202012Validator(spec, registry=reg)


def test_frame_spec_emits_status_strip_widget() -> None:
    els = [
        Element(
            id="strip1",
            kind="status_strip",
            x=0,
            y=0,
            w=1872,
            h=60,
            options={
                "bindings": {
                    "clock": True,
                    "env": True,
                    "battery": True,
                    "weather": "forecast.hourly",
                }
            },
        ),
        Element(
            id="btn1",
            kind="button",
            x=40,
            y=200,
            w=180,
            h=80,
            label="Next",
            on_tap="page:2",
        ),
    ]

    doc = build_frame_spec(els)
    assert "widgets" in doc
    assert len(doc["widgets"]) == 1
    w = doc["widgets"][0]
    assert w["id"] == "strip1"
    assert w["kind"] == "status_strip"
    assert w["rect"] == {"x": 0, "y": 0, "w": 1872, "h": 60}
    assert w["bindings"]["clock"] is True
    assert w["bindings"]["weather"] == "forecast.hourly"

    # Must validate against schema
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, errors[0].message if errors else ""


def test_frame_spec_clamps_or_skips_invalid_widgets() -> None:
    els = [
        # negative coordinates
        Element(id="bad1", kind="status_strip", x=-10, y=0, w=100, h=50),
        # unknown kind
        Element(id="unknown1", kind="rect", x=10, y=10, w=100, h=50),
    ]
    doc = build_frame_spec(els)
    assert "widgets" not in doc or len(doc.get("widgets", [])) == 0


def test_bundle_emits_forecast_hourly_dataset(tmp_path: Path) -> None:
    deck = Deck(
        id="deck1",
        name="Test Deck",
        pages=[DeckPage(page_id="p1")],
    )

    class DummyPushMgr:
        def deck_render_for(self, device_id: str, page_id: str) -> dict[str, Any] | None:
            return {"digest": "0123456789abcdef", "filename": "test.bin"}

    renders_dir = tmp_path / "renders"
    renders_dir.mkdir()
    (renders_dir / "test.bin").write_bytes(b"\x00" * 100)

    bundle = build_bundle(
        deck,
        "dev1",
        push_mgr=DummyPushMgr(),
        renders_dir=renders_dir,
    )
    assert bundle is not None
    assert "datasets" in bundle
    assert "forecast" in bundle["datasets"]
    assert "hourly" in bundle["datasets"]["forecast"]
    hourly = bundle["datasets"]["forecast"]["hourly"]
    assert len(hourly) >= 12
    first = hourly[0]
    assert "epoch" in first
    assert "temp_c" in first
    assert "condition" in first
    assert "icon" in first
