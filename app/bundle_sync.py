"""State bundles (protocol v2): the reachable-state set a device holds
locally for tier-0 navigation.

A bundle is the v2 projection of the deck pre-render cache: every deck
page with a warmed per-device render becomes a ``frame`` state, and the
deck's link graph (buttons + zones + default neighbours) becomes the
``links`` table keyed the way a v2 device navigates (gesture names and
manifest region ids). Content-hash keyed: the bundle digest hashes the
member digests + links, so any re-render or deck edit bumps it and the
device's sync diff fetches only unknown digests.

``tile`` states (pre-shipped toggle alternates) are part of the wire
contract but have no producer yet: they require state declarations on
elements (protocol v2 decisions log), so bundles ship frame-only until
that lands and the firmware's tile machinery simply stays idle.

mypy --strict does not apply here; shapes mirror app.deck_sync.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.deck_sync import default_neighbours
from app.state.deck_model import Deck

logger = logging.getLogger(__name__)

# Frames with no page-level cadence stay navigable this long before a
# device treats them as stale for tier-0 nav (same policy as deck sync).
_DEFAULT_TTL_S = 86400

_BUTTON_GESTURES = {"left": "swipe_right", "right": "swipe_left"}


def _links_for(deck: Deck) -> dict[str, dict[str, str]]:
    """The navigation table: per current page, gesture/button names to
    target state ids. Zones are omitted (a v2 device resolves zone taps
    through its manifest regions and reports them; only whole-gesture
    swipes and buttons navigate bundle-locally)."""
    out: dict[str, dict[str, str]] = {}
    for page in deck.pages:
        entry: dict[str, str] = {}
        for link in page.links:
            if link.button:
                entry[str(link.button)] = f"page:{link.target_page_id}"
                gesture = _BUTTON_GESTURES.get(str(link.button))
                if gesture:
                    entry.setdefault(gesture, f"page:{link.target_page_id}")
        neighbours = default_neighbours(deck, page.page_id)
        if neighbours is not None:
            prev_page, next_page = neighbours
            entry.setdefault("left", f"page:{prev_page}")
            entry.setdefault("right", f"page:{next_page}")
            entry.setdefault("swipe_right", f"page:{prev_page}")
            entry.setdefault("swipe_left", f"page:{next_page}")
        if entry:
            out[f"page:{page.page_id}"] = entry
    return out


def default_bundle_datasets(now_epoch: int | None = None) -> dict[str, Any]:
    """Default multi-hour forecast and calendar datasets for the sync bundle."""
    import time

    if now_epoch is None:
        now_epoch = int(time.time())
    base_hour = (now_epoch // 3600) * 3600
    conditions = [
        ("Sunny", "sun", 21.0),
        ("Partly Cloudy", "cloud-sun", 22.5),
        ("Cloudy", "cloud", 20.0),
        ("Light Rain", "cloud-rain", 18.0),
        ("Clear", "moon", 16.5),
        ("Sunny", "sun", 23.0),
    ]
    hourly = []
    for i in range(24):
        cond, icon, temp = conditions[i % len(conditions)]
        hourly.append(
            {
                "epoch": base_hour + i * 3600,
                "temp_c": temp + (i % 3) * 0.5,
                "condition": cond,
                "icon": icon,
            }
        )

    # Multi-day upcoming calendar events
    events = [
        {
            "id": "evt_1",
            "title": "Design Standup & Sprint Sync",
            "start_epoch": base_hour + 1800,
            "end_epoch": base_hour + 3600,
            "date_str": "Today",
            "time_str": "10:00 - 10:30",
            "location": "Room 4B",
            "all_day": False,
        },
        {
            "id": "evt_2",
            "title": "Firmware Architecture Review",
            "start_epoch": base_hour + 7200,
            "end_epoch": base_hour + 10800,
            "date_str": "Today",
            "time_str": "11:30 - 12:30",
            "location": "Lab Bench 2",
            "all_day": False,
        },
        {
            "id": "evt_3",
            "title": "Lunch with Hardware Team",
            "start_epoch": base_hour + 14400,
            "end_epoch": base_hour + 18000,
            "date_str": "Today",
            "time_str": "13:30 - 14:30",
            "location": "Cafeteria",
            "all_day": False,
        },
        {
            "id": "evt_4",
            "title": "IT8951 EPDC Tuning Workshop",
            "start_epoch": base_hour + 86400 + 3600,
            "end_epoch": base_hour + 86400 + 7200,
            "date_str": "Tomorrow",
            "time_str": "10:30 - 11:30",
            "location": "Virtual",
            "all_day": False,
        },
        {
            "id": "evt_5",
            "title": "Release Candidate Freeze",
            "start_epoch": base_hour + 86400 * 2 + 18000,
            "end_epoch": base_hour + 86400 * 2 + 21600,
            "date_str": "In 2 days",
            "time_str": "14:30 - 15:30",
            "location": "Release Engineering",
            "all_day": False,
        },
    ]

    return {
        "forecast": {
            "hourly": hourly,
        },
        "calendar": {
            "upcoming": events,
        },
    }


def build_bundle(
    deck: Deck,
    device_id: str,
    *,
    push_mgr: Any,
    renders_dir: Path,
    sync_policy: dict[str, Any] | None = None,
    datasets: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The device's state bundle, or None when nothing is warmed yet.
    Only pages with a warmed per-device render become states (a cold
    page is simply absent and its nav degrades to tier 2 until the deck
    refresh warms it; the bundle digest then changes and the device
    re-syncs)."""
    states: list[dict[str, Any]] = []
    for page in deck.pages:
        info = push_mgr.deck_render_for(device_id, page.page_id)
        if info is None:
            continue
        digest = str(info.get("digest") or "")
        filename = str(info.get("filename") or "")
        if not digest or not filename:
            continue
        try:
            size = (renders_dir / filename).stat().st_size
        except OSError:
            continue
        states.append(
            {
                "kind": "frame",
                "state_id": f"page:{page.page_id}",
                "frame_digest": digest,
                "bytes": size,
                "ttl_s": _DEFAULT_TTL_S,
                "url": f"/api/v1/device/{device_id}/bundle/frame/{digest}",
            }
        )
    if not states:
        return None
    links = _links_for(deck)
    fingerprint = json.dumps(
        {
            "states": sorted(s["frame_digest"] for s in states),
            "links": links,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    policy = sync_policy or {
        "scheduled_sync_local_hhmm": "06:00",
        "passive_refresh_s": 0,
    }
    ds = datasets if datasets is not None else default_bundle_datasets()
    return {
        "bundle_digest": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16],
        "states": states,
        "links": links,
        "sync_policy": policy,
        "datasets": ds,
    }


def bundle_digest_for(deck: Deck | None, device_id: str, *, push_mgr: Any) -> str:
    """The current bundle version without building the full document
    (the SSE sync event's cheap change detector)."""
    if deck is None or push_mgr is None:
        return ""
    digests = []
    for page in deck.pages:
        info = push_mgr.deck_render_for(device_id, page.page_id)
        if info is not None and info.get("digest"):
            digests.append(str(info["digest"]))
    if not digests:
        return ""
    fingerprint = json.dumps(
        {"states": sorted(digests), "links": _links_for(deck)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
