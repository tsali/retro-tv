#!/usr/bin/env python3
"""
EAS Poller — polls the NWS API for active alerts and writes pending
alert JSON files for the EAS watcher to pick up.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "/home/retro"
CONFIG_PATH = f"{BASE}/config/eas_config.json"
SEEN_IDS_PATH = f"{BASE}/state/eas_seen_ids.json"
PENDING_DIR = f"{BASE}/state/eas_pending"

# NWS event name → SAME code mapping
EVENT_TO_SAME = {
    "Tornado Warning": "TOR",
    "Severe Thunderstorm Warning": "SVR",
    "Flash Flood Warning": "FFW",
    "Extreme Wind Warning": "EWW",
    "Special Marine Warning": "SMW",
    "Special Weather Statement": "SPS",
    "Winter Storm Warning": "WSW",
    "Hurricane Warning": "HUW",
    "Tsunami Warning": "TSW",
    "Fire Warning": "FRW",
    "Coastal Flood Warning": "CFW",
    "Emergency Action Notification": "EAN",
    "Civil Danger Warning": "CDW",
}

USER_AGENT = "RetroTV-EAS/1.0 (retro-tv@local; contact=none)"


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"enabled": False}


def load_seen_ids():
    try:
        with open(SEEN_IDS_PATH) as f:
            return set(json.load(f))
    except (OSError, json.JSONDecodeError):
        return set()


def save_seen_ids(seen):
    # Keep only the most recent 200 IDs to avoid unbounded growth
    recent = list(seen)[-200:]
    with open(SEEN_IDS_PATH, 'w') as f:
        json.dump(recent, f)


def fetch_alerts(lat, lon):
    """Fetch active alerts from NWS API for a given point."""
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode())
    return data.get("features", [])


def process_alert(feature, enabled_types):
    """Extract relevant info from a NWS alert feature. Returns dict or None."""
    props = feature.get("properties", {})
    alert_id = props.get("id", "")
    event = props.get("event", "")
    same_code = EVENT_TO_SAME.get(event, "")

    # Skip if we don't have a mapping or the type isn't enabled
    if not same_code:
        return None
    if not enabled_types.get(same_code, False):
        return None

    # Extract areas
    areas_list = props.get("areaDesc", "")

    return {
        "id": alert_id,
        "event": event,
        "event_code": same_code,
        "headline": props.get("headline", ""),
        "description": props.get("description", ""),
        "areas": areas_list,
        "expires": props.get("expires", ""),
        "severity": props.get("severity", ""),
        "urgency": props.get("urgency", ""),
        "onset": props.get("onset", ""),
        "sender": props.get("senderName", ""),
        "timestamp": time.time(),
    }


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] EAS-POLLER: {msg}", flush=True)


def main():
    os.makedirs(PENDING_DIR, exist_ok=True)
    backoff = 0

    log("Starting EAS poller")

    while True:
        config = load_config()

        if not config.get("enabled", False):
            time.sleep(10)
            continue

        lat = config.get("latitude", 0)
        lon = config.get("longitude", 0)
        poll_interval = config.get("poll_interval_seconds", 45)
        enabled_types = config.get("alert_types", {})

        if lat == 0 and lon == 0:
            # No location configured
            time.sleep(poll_interval)
            continue

        try:
            features = fetch_alerts(lat, lon)
            backoff = 0  # Reset backoff on success

            seen = load_seen_ids()
            new_count = 0

            for feature in features:
                alert = process_alert(feature, enabled_types)
                if alert is None:
                    continue

                if alert["id"] in seen:
                    continue

                # New alert — write to pending directory
                seen.add(alert["id"])
                safe_id = "".join(
                    c if c.isalnum() or c in '-_' else '_'
                    for c in alert["id"]
                )
                pending_path = os.path.join(
                    PENDING_DIR, f"{safe_id}.json"
                )
                with open(pending_path, 'w') as f:
                    json.dump(alert, f, indent=2)

                log(f"NEW ALERT: {alert['event_code']} - {alert['headline']}")
                new_count += 1

            save_seen_ids(seen)

            if new_count > 0:
                log(f"Wrote {new_count} new alert(s) to pending")

        except urllib.error.HTTPError as e:
            if e.code == 503:
                backoff = min(backoff + 30, 300)
                log(f"NWS API 503 — backing off {backoff}s")
                time.sleep(backoff)
                continue
            else:
                log(f"HTTP error: {e.code}")
        except Exception as e:
            log(f"Error polling NWS: {e}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
