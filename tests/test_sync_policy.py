"""Contract tests for Companion Server sync_policy configuration and delivery (#5 / T4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from app.device_service import device_config_doc
from app.main import REPO_ROOT, create_app
from app.state.deck_model import Deck, DeckPage
from devices.esp32_client.device import validate_config


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    a = create_app(
        testing=False,
        data_root=tmp_path,
        plugins_dir=REPO_ROOT / "plugins",
        renderers_dir=REPO_ROOT / "renderers",
        devices_dir=REPO_ROOT / "devices",
    )
    a.config["TESTING"] = True
    return a


def _register_e1003(app: Flask, client) -> str:
    client.post("/setup", data={"password": "abcdefgh", "password_confirm": "abcdefgh"})
    code = app.config["PAIRING_STORE"].issue(note="test").code
    resp = client.post(
        "/api/v1/device/register",
        headers={"X-Pairing-Code": code, "Content-Type": "application/json"},
        data=json.dumps(
            {
                "device_id": "e1003",
                "kind": "seeed_reterminal_e1003",
                "panel_w": 1872,
                "panel_h": 1404,
            }
        ),
    )
    assert resp.status_code == 201
    return resp.get_json()["device_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_default_sync_policy_in_device_config_and_status(app: Flask) -> None:
    client = app.test_client()
    token = _register_e1003(app, client)

    device = app.config["DEVICE_REGISTRY"].get("e1003")
    assert device is not None
    cfg = device_config_doc(app.config["SETTINGS_STORE"], device)
    assert cfg["sync_policy"] == {
        "scheduled_sync_local_hhmm": "06:00",
        "passive_refresh_s": 0,
    }

    resp = client.post(
        "/api/v1/device/e1003/status",
        headers=_auth(token),
        data=json.dumps({"battery_pct": 85, "rssi": -55}),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sync_policy"] == {
        "scheduled_sync_local_hhmm": "06:00",
        "passive_refresh_s": 0,
    }
    assert body["config"]["sync_policy"] == {
        "scheduled_sync_local_hhmm": "06:00",
        "passive_refresh_s": 0,
    }


def test_custom_sync_policy_persists_and_delivers_in_status_and_bundle(app: Flask) -> None:
    client = app.test_client()
    token = _register_e1003(app, client)

    store = app.config["SETTINGS_STORE"]
    device = app.config["DEVICE_REGISTRY"].get("e1003")
    assert device is not None

    store.update_for_namespace(
        "devices",
        "e1003",
        {
            "sleep_interval_s": 3600,
            "scheduled_sync_local_hhmm": "07:30",
            "passive_refresh_s": 900,
        },
        [{"name": "sleep_interval_s"}, {"name": "scheduled_sync_local_hhmm"}, {"name": "passive_refresh_s"}],
    )

    resp = client.post(
        "/api/v1/device/e1003/status",
        headers=_auth(token),
        data=json.dumps({"battery_pct": 90}),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sync_policy"] == {
        "scheduled_sync_local_hhmm": "07:30",
        "passive_refresh_s": 900,
    }
    assert body["config"]["scheduled_sync_local_hhmm"] == "07:30"
    assert body["config"]["passive_refresh_s"] == 900

    # Also verify /bundle includes sync_policy
    deck = Deck(
        id="d1",
        name="Deck",
        device_ids=["e1003"],
        entry_page_id="home",
        pages=[DeckPage(page_id="home")],
    )
    app.config["DECK_STORE"].upsert(deck)
    digest = "a" * 16
    (app.config["RENDERS_DIR"] / f"{digest}.bin").write_bytes(b"\x00" * 64)
    app.config["PUSH_MANAGER"]._deck_renders.setdefault("e1003", {})["home"] = {
        "digest": digest,
        "ext": "bin",
        "filename": f"{digest}.bin",
        "composition_digest": "c" * 16,
        "timestamp": 1000.0,
    }

    b_resp = client.get("/api/v1/device/e1003/bundle", headers=_auth(token))
    assert b_resp.status_code == 200
    b_body = b_resp.get_json()
    assert b_body["sync_policy"] == {
        "scheduled_sync_local_hhmm": "07:30",
        "passive_refresh_s": 900,
    }


def test_validate_config_sync_policy_fields() -> None:
    ok, err = validate_config(
        {
            "sleep_interval_s": 60,
            "scheduled_sync_local_hhmm": "06:00",
            "passive_refresh_s": 0,
        }
    )
    assert ok is True
    assert err is None

    ok, err = validate_config(
        {
            "sleep_interval_s": 60,
            "scheduled_sync_local_hhmm": "25:00",
        }
    )
    assert ok is False
    assert err is not None

    ok, err = validate_config(
        {
            "sleep_interval_s": 60,
            "passive_refresh_s": -5,
        }
    )
    assert ok is False
    assert err is not None
