"""Server contract tests for T7 / Ticket #8:
FreeInkUI Interactive Controls Widget Region & On-Demand Radio Burst.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.state.panel_store import Element
from app.touch_spec import build_frame_spec

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


def _validator() -> Draft202012Validator:
    spec = json.loads((_SCHEMA_DIR / "frame-spec.schema.json").read_text())
    atlas = json.loads((_SCHEMA_DIR / "atlas.schema.json").read_text())
    reg = Registry().with_resources([("atlas.schema.json", Resource.from_contents(atlas))])
    return Draft202012Validator(spec, registry=reg)


def test_frame_spec_emits_control_group_widget() -> None:
    els = [
        Element(
            id="controls1",
            kind="control_group",
            x=50,
            y=100,
            w=500,
            h=400,
            options={
                "controls": [
                    {
                        "id": "tab_view",
                        "type": "tabs",
                        "network": False,
                        "options": ["Daily", "Weekly", "Monthly"],
                        "value": 0,
                    },
                    {
                        "id": "light_sw",
                        "type": "switch",
                        "network": True,
                        "label": "Desk Light",
                        "state": "on",
                        "value_key": "ha:light.desk",
                    },
                    {
                        "id": "bright_sl",
                        "type": "slider",
                        "network": True,
                        "min": 0,
                        "max": 100,
                        "step": 5,
                        "value": 75,
                        "value_key": "ha:light.desk:brightness",
                    },
                    {
                        "id": "fan_step",
                        "type": "stepper",
                        "network": True,
                        "min": 0,
                        "max": 5,
                        "step": 1,
                        "value": 2,
                        "value_key": "ha:fan.speed",
                    },
                    {
                        "id": "action_btn",
                        "type": "button",
                        "network": True,
                        "label": "Goodnight",
                        "action": "webhook:https://example.com/goodnight",
                    },
                ]
            },
        ),
    ]

    doc = build_frame_spec(els)
    assert "widgets" in doc
    assert len(doc["widgets"]) == 1
    w = doc["widgets"][0]
    assert w["id"] == "controls1"
    assert w["kind"] == "control_group"
    assert w["rect"] == {"x": 50, "y": 100, "w": 500, "h": 400}

    # Validate against JSON schema
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(e.path))
    assert not errors, errors[0].message if errors else ""

    controls = w.get("options", {}).get("controls", [])
    assert len(controls) == 5
    assert controls[0]["network"] is False
    assert controls[0]["type"] == "tabs"
    assert controls[1]["network"] is True
    assert controls[1]["type"] == "switch"
    assert controls[2]["type"] == "slider"
    assert controls[3]["type"] == "stepper"
    assert controls[4]["type"] == "button"
