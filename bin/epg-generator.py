#!/usr/bin/env python3
"""
epg-generator.py — Retro TV EPG Channel Frame Renderer

Renders PNG frames to /home/retro/state/epg/ on a ~10s cycle.
Each frame is a 1920x1080 image with:
  - Top-left quarter: weather info (current conditions / 3-day forecast / radar)
  - Top-right quarter: random ad image from /media/images/ads/
  - Bottom half: schedule grid (channels as rows, times as columns)

Weather data fetched from NWS API, cached every 15 minutes.
"""

import json
import logging
import os
import random
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# -- paths --
BASE = Path("/home/retro")
EPG_DIR = BASE / "state" / "epg"
ADS_DIR = BASE / "media" / "images" / "ads"
EAS_CONFIG = BASE / "config" / "eas_config.json"
WEATHER_CACHE = EPG_DIR / "weather_cache.json"
FRAME_PATH = EPG_DIR / "current.png"
FRAME_TMP = EPG_DIR / "current.tmp.png"

# -- add bin to path so we can import schedule_manager --
sys.path.insert(0, str(BASE / "bin"))
import schedule_manager

# -- constants --
WIDTH, HEIGHT = 1920, 1080
HALF_H = HEIGHT // 2          # 540 — top half / bottom half split
HALF_W = WIDTH // 2            # 960 — left quarter / right quarter split
WEATHER_CACHE_TTL = 900        # 15 minutes
CYCLE_INTERVAL = 10            # seconds between frames
SLOTS_VISIBLE = 8              # half-hour time columns visible per page
CHANNELS_PER_PAGE = 5          # max channels per grid page

# -- colors --
BG_COLOR = (20, 20, 60)
GRID_BG = (25, 25, 70)
GRID_LINE = (60, 60, 120)
GRID_TEXT = (220, 220, 240)
GRID_HEADER_BG = (50, 50, 120)
HIGHLIGHT_BG = (80, 60, 30)
WEATHER_BG = (30, 30, 80)
TIME_COLOR = (255, 220, 100)
CHANNEL_COLOR = (100, 200, 255)
DIVIDER_COLOR = (80, 80, 140)

# -- fonts --
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] EPG: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("epg")


def load_font(size, bold=False):
    path = FONT_BOLD_PATH if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# Preload fonts
FONT_LARGE = load_font(28, bold=True)
FONT_MEDIUM = load_font(22)
FONT_MEDIUM_BOLD = load_font(22, bold=True)
FONT_SMALL = load_font(18)
FONT_SMALL_BOLD = load_font(18, bold=True)
FONT_TINY = load_font(14)
FONT_WEATHER_BIG = load_font(72, bold=True)
FONT_WEATHER_MED = load_font(28)
FONT_WEATHER_SMALL = load_font(22)
FONT_WEATHER_DESC = load_font(32)
FONT_GRID = load_font(20)
FONT_GRID_BOLD = load_font(20, bold=True)


# =============================================================================
# Weather
# =============================================================================

def load_eas_config():
    try:
        with open(EAS_CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


def fetch_weather():
    """Fetch weather from NWS API. Returns dict with conditions + forecast."""
    import urllib.request
    import urllib.error

    cfg = load_eas_config()
    lat = cfg.get("latitude")
    lon = cfg.get("longitude")
    if not lat or not lon:
        log.warning("No lat/lon in eas_config.json")
        return None

    headers = {"User-Agent": "(retro-tv-epg, wasituna@gmail.com)", "Accept": "application/geo+json"}

    try:
        # Step 1: get metadata (forecast URLs, radar station)
        points_url = f"https://api.weather.gov/points/{lat},{lon}"
        req = urllib.request.Request(points_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            points = json.loads(resp.read())

        props = points.get("properties", {})
        forecast_url = props.get("forecast", "")
        forecast_hourly_url = props.get("forecastHourly", "")
        radar_station = props.get("radarStation", "")

        result = {"radar_station": radar_station, "fetched": time.time()}

        # Step 2: get current conditions from hourly forecast
        if forecast_hourly_url:
            req = urllib.request.Request(forecast_hourly_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                hourly = json.loads(resp.read())
            periods = hourly.get("properties", {}).get("periods", [])
            if periods:
                cur = periods[0]
                result["current"] = {
                    "temp": cur.get("temperature", "?"),
                    "unit": cur.get("temperatureUnit", "F"),
                    "description": cur.get("shortForecast", ""),
                    "wind": cur.get("windSpeed", ""),
                    "wind_dir": cur.get("windDirection", ""),
                    "humidity": cur.get("relativeHumidity", {}).get("value", ""),
                    "icon": cur.get("icon", ""),
                }

        # Step 3: get multi-day forecast
        if forecast_url:
            req = urllib.request.Request(forecast_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                forecast = json.loads(resp.read())
            periods = forecast.get("properties", {}).get("periods", [])
            result["forecast"] = []
            for p in periods[:6]:  # 3 days (day+night each)
                result["forecast"].append({
                    "name": p.get("name", ""),
                    "temp": p.get("temperature", "?"),
                    "unit": p.get("temperatureUnit", "F"),
                    "short": p.get("shortForecast", ""),
                })

        log.info("Weather data fetched successfully")
        return result

    except Exception as e:
        log.error(f"Weather fetch failed: {e}")
        return None


def fetch_radar_image(radar_station):
    """Fetch radar image from NWS. Returns PIL Image or None."""
    import urllib.request
    import io

    if not radar_station:
        return None

    url = f"https://radar.weather.gov/ridge/standard/{radar_station}_loop.gif"
    headers = {"User-Agent": "(retro-tv-epg, wasituna@gmail.com)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        log.info(f"Radar image fetched: {radar_station}")
        return img
    except Exception as e:
        log.error(f"Radar fetch failed: {e}")
        return None


def load_weather_cache():
    """Load cached weather data, or fetch if stale."""
    weather = None
    radar_img = None

    if WEATHER_CACHE.exists():
        try:
            with open(WEATHER_CACHE) as f:
                weather = json.load(f)
            if time.time() - weather.get("fetched", 0) < WEATHER_CACHE_TTL:
                radar_path = EPG_DIR / "radar.png"
                if radar_path.exists():
                    radar_img = Image.open(radar_path).convert("RGB")
                return weather, radar_img
        except Exception:
            pass

    weather = fetch_weather()
    if weather:
        try:
            WEATHER_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(WEATHER_CACHE, "w") as f:
                json.dump(weather, f)
        except Exception:
            pass

        radar_img = fetch_radar_image(weather.get("radar_station"))
        if radar_img:
            try:
                radar_img.save(EPG_DIR / "radar.png")
            except Exception:
                pass

    return weather, radar_img


# =============================================================================
# Schedule Data
# =============================================================================

SKIP_STATIONS = {"EPG", "bumpers", "commercials"}


def get_epg_channels():
    """Get channels to display in the EPG grid.
    Includes all channels that have schedules or are tunable,
    skipping only EPG itself and internal pseudo-channels.
    """
    channels = schedule_manager.get_channels()
    result = []
    for num in sorted(channels.keys(), key=lambda x: int(x)):
        ch = channels[num]
        name = ch.get("name", "")
        if name in SKIP_STATIONS:
            continue
        result.append({"number": num, "name": name})
    return result


def get_schedule_for_channel(station, day=None):
    """Get schedule blocks for a station on a given day."""
    config = schedule_manager.load_config()
    state = schedule_manager.load_state()
    sched = schedule_manager.get_schedule(config, state)
    if day is None:
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day = days[datetime.now().weekday()]
    blocks = sched.get(day, {}).get(station, [])
    shows = schedule_manager.get_shows(config)
    result = []
    for b in blocks:
        show_id = b.get("show_id", "")
        show = shows.get(show_id, {})
        result.append({
            "start": b.get("start", ""),
            "end": b.get("end", ""),
            "show_id": show_id,
            "title": show.get("title", show_id),
        })
    return result


# =============================================================================
# Ad Images
# =============================================================================

def get_random_ad():
    """Load a random ad image from the ads directory."""
    if not ADS_DIR.exists():
        return None
    ads = [f for f in ADS_DIR.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")]
    if not ads:
        return None
    path = random.choice(ads)
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


# =============================================================================
# Drawing Helpers
# =============================================================================

def draw_text_centered(draw, x, y, w, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text((x + (w - tw) // 2, y), text, font=font, fill=fill)


def draw_text_clipped(draw, x, y, max_w, text, font, fill):
    """Draw text, truncating with '...' if it exceeds max_w."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    if tw <= max_w:
        draw.text((x, y), text, font=font, fill=fill)
        return
    while len(text) > 1:
        text = text[:-1]
        bbox = draw.textbbox((0, 0), text + "...", font=font)
        if bbox[2] - bbox[0] <= max_w:
            break
    draw.text((x, y), text + "...", font=font, fill=fill)


# =============================================================================
# Frame Rendering — Top-Left: Weather (1/4)
# =============================================================================

def render_weather_box(img, draw, weather, radar_img, cycle_phase):
    """Render weather in the top-left quarter."""
    box_w = HALF_W
    box_h = HALF_H

    draw.rectangle([0, 0, box_w - 1, box_h - 1], fill=WEATHER_BG)

    if not weather:
        draw_text_centered(draw, 0, box_h // 2 - 14, box_w,
                           "Weather Unavailable", FONT_MEDIUM, (180, 180, 180))
        return

    phase = cycle_phase % 3

    if phase == 0:
        # Current conditions + today's forecast
        cur = weather.get("current", {})
        temp = cur.get("temp", "?")
        unit = cur.get("unit", "F")
        desc = cur.get("description", "")
        wind = cur.get("wind", "")
        wind_dir = cur.get("wind_dir", "")
        humidity = cur.get("humidity", "")

        y = 20
        draw.text((30, y), "CURRENT CONDITIONS", font=FONT_MEDIUM_BOLD, fill=TIME_COLOR)
        y += 40

        draw.text((30, y), f"{temp}\u00b0{unit}", font=FONT_WEATHER_BIG, fill=(255, 255, 255))
        y += 90

        draw.text((30, y), desc, font=FONT_WEATHER_DESC, fill=GRID_TEXT)
        y += 45

        if wind:
            draw.text((30, y), f"Wind: {wind_dir} {wind}", font=FONT_WEATHER_MED, fill=GRID_TEXT)
            y += 38

        if humidity:
            draw.text((30, y), f"Humidity: {humidity}%", font=FONT_WEATHER_MED, fill=GRID_TEXT)
            y += 38

        # Show next 2 forecast periods below current conditions
        forecasts = weather.get("forecast", [])
        if forecasts and y < box_h - 80:
            y += 10
            draw.line([(30, y), (box_w - 30, y)], fill=GRID_LINE, width=1)
            y += 15
            for fc in forecasts[:2]:
                name = fc.get("name", "")
                ftemp = fc.get("temp", "?")
                funit = fc.get("unit", "F")
                short = fc.get("short", "")
                line = f"{name}: {ftemp}\u00b0{funit} - {short}"
                draw_text_clipped(draw, 30, y, box_w - 60, line, FONT_WEATHER_SMALL, GRID_TEXT)
                y += 30

        # Time is shown via mpv OSD overlay (always accurate)

    elif phase == 1:
        # Extended forecast
        forecasts = weather.get("forecast", [])
        y = 20
        draw.text((30, y), "EXTENDED FORECAST", font=FONT_MEDIUM_BOLD, fill=TIME_COLOR)
        y += 50

        for fc in forecasts[:6]:
            name = fc.get("name", "")
            temp = fc.get("temp", "?")
            unit = fc.get("unit", "F")
            short = fc.get("short", "")

            # Name and temp on one line, big
            draw.text((30, y), f"{name}:", font=FONT_WEATHER_MED, fill=CHANNEL_COLOR)
            bbox = draw.textbbox((0, 0), f"{name}: ", font=FONT_WEATHER_MED)
            name_w = bbox[2] - bbox[0]
            draw.text((30 + name_w, y), f"{temp}\u00b0{unit}", font=FONT_WEATHER_MED, fill=(255, 255, 255))
            y += 34

            # Description on next line
            draw_text_clipped(draw, 50, y, box_w - 80, short, FONT_WEATHER_SMALL, GRID_TEXT)
            y += 34
            if y > box_h - 40:
                break

    elif phase == 2:
        # Radar image
        draw.text((30, 25), "RADAR", font=FONT_MEDIUM_BOLD, fill=TIME_COLOR)
        if radar_img:
            rw, rh = radar_img.size
            margin = 60
            scale = min((box_w - margin) / rw, (box_h - 80) / rh)
            new_w = int(rw * scale)
            new_h = int(rh * scale)
            resized = radar_img.resize((new_w, new_h), Image.LANCZOS)
            paste_x = (box_w - new_w) // 2
            paste_y = 60 + (box_h - 80 - new_h) // 2
            img.paste(resized, (paste_x, paste_y))
        else:
            draw_text_centered(draw, 0, box_h // 2 - 14, box_w,
                               "Radar Unavailable", FONT_MEDIUM, (180, 180, 180))


# =============================================================================
# Frame Rendering — Top-Right: Ad (1/4)
# =============================================================================

def render_ad_box(img, draw, ad_img):
    """Render ad in the top-right quarter."""
    box_x = HALF_W
    box_w = HALF_W
    box_h = HALF_H

    draw.rectangle([box_x, 0, WIDTH - 1, box_h - 1], fill=(30, 25, 50))

    if ad_img:
        # Crop-to-fill: scale up to cover the entire box, then center-crop
        aw, ah = ad_img.size
        scale = max(box_w / aw, box_h / ah)
        new_w = int(aw * scale)
        new_h = int(ah * scale)
        resized = ad_img.resize((new_w, new_h), Image.LANCZOS)
        # Center-crop to box size
        crop_x = (new_w - box_w) // 2
        crop_y = (new_h - box_h) // 2
        cropped = resized.crop((crop_x, crop_y, crop_x + box_w, crop_y + box_h))
        img.paste(cropped, (box_x, 0))
    else:
        draw_text_centered(draw, box_x, box_h // 2 - 14, box_w,
                           "RETRO TV", FONT_LARGE, (100, 100, 140))


# =============================================================================
# Frame Rendering — Bottom Half: Schedule Grid (1/2)
# =============================================================================

def render_schedule_grid(draw, channels):
    """Render schedule grid in the bottom half.
    Channels as rows on the left, time slots as columns across the top.
    Always starts at the current half-hour.
    """
    y_start = HALF_H
    grid_h = HALF_H  # bottom half = 540px

    now = datetime.now()
    # Round down to current half-hour
    base_min = (now.minute // 30) * 30
    base_time = now.replace(minute=base_min, second=0, microsecond=0)

    time_slots = []
    for i in range(SLOTS_VISIBLE):
        t = base_time + timedelta(minutes=i * 30)
        time_slots.append(t)

    # Layout dimensions
    ch_col_w = 220  # channel name column width
    num_channels = min(len(channels), CHANNELS_PER_PAGE)
    if num_channels == 0:
        draw_text_centered(draw, 0, y_start + 40, WIDTH,
                           "No Scheduled Channels", FONT_MEDIUM, GRID_TEXT)
        return

    time_col_w = (WIDTH - ch_col_w) // SLOTS_VISIBLE
    header_h = 40  # time header row height
    row_h = (grid_h - header_h - 25) // CHANNELS_PER_PAGE

    # --- Header row: time labels across the top ---
    draw.rectangle([0, y_start, WIDTH - 1, y_start + header_h - 1], fill=GRID_HEADER_BG)
    # Channel column header left blank — live OSD clock goes here

    for ti, slot_time in enumerate(time_slots):
        x = ch_col_w + ti * time_col_w
        time_label = slot_time.strftime("%I:%M")
        # First column is the current time slot
        color = TIME_COLOR if ti == 0 else (200, 200, 220)
        draw_text_centered(draw, x, y_start + (header_h - 20) // 2, time_col_w,
                           time_label, FONT_GRID_BOLD, color)
        # Vertical line
        draw.line([(x, y_start), (x, y_start + header_h + num_channels * row_h)],
                  fill=GRID_LINE, width=1)

    # Horizontal line under header
    draw.line([(0, y_start + header_h), (WIDTH, y_start + header_h)], fill=GRID_LINE, width=2)

    # Pre-fetch schedules
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    today = days[now.weekday()]
    channel_schedules = {}
    for ch in channels[:num_channels]:
        name = ch["name"]
        # MTV channels don't have schedules — handled specially below
        if not name.startswith("MTV"):
            channel_schedules[name] = get_schedule_for_channel(name, today)

    # --- Channel rows ---
    for ri, ch in enumerate(channels[:num_channels]):
        row_y = y_start + header_h + ri * row_h
        bg = GRID_BG if ri % 2 == 0 else (30, 30, 75)

        draw.rectangle([0, row_y, WIDTH - 1, row_y + row_h - 1], fill=bg)

        # Channel label
        label = f"CH{ch['number']} {ch['name']}"
        draw_text_clipped(draw, 10, row_y + (row_h - 20) // 2,
                          ch_col_w - 20, label, FONT_GRID_BOLD, CHANNEL_COLOR)

        is_mtv = ch["name"].startswith("MTV")

        # Show cells for each time slot
        blocks = channel_schedules.get(ch["name"], [])
        for ti, slot_time in enumerate(time_slots):
            x = ch_col_w + ti * time_col_w
            slot_str = slot_time.strftime("%H:%M")

            # Highlight current time column
            if ti == 0:
                draw.rectangle([x + 1, row_y, x + time_col_w - 1, row_y + row_h - 1],
                               fill=HIGHLIGHT_BG)

            if is_mtv:
                show_title = "Music Videos"
            else:
                show_title = ""
                for b in blocks:
                    start = b.get("start", "")
                    end = b.get("end", "")
                    end_eff = "24:00" if (not end or end == "00:00") else end
                    if start <= slot_str < end_eff:
                        show_title = b.get("title", b.get("show_id", ""))
                        break
                if not show_title:
                    show_title = "\u2014"

            draw_text_clipped(draw, x + 6, row_y + (row_h - 20) // 2,
                              time_col_w - 12, show_title, FONT_GRID, GRID_TEXT)

            # Vertical line
            draw.line([(x, row_y), (x, row_y + row_h)], fill=GRID_LINE, width=1)

        # Horizontal line under row
        draw.line([(0, row_y + row_h), (WIDTH, row_y + row_h)], fill=GRID_LINE, width=1)

    # Bottom info bar
    info_y = y_start + header_h + num_channels * row_h + 5
    if info_y < HEIGHT - 25:
        draw.text((15, HEIGHT - 22), "RETRO TV ELECTRONIC PROGRAM GUIDE",
                  font=FONT_TINY, fill=(100, 100, 140))
        ts = datetime.now().strftime("%a %b %d, %Y  %I:%M:%S %p")
        draw.text((WIDTH - 300, HEIGHT - 22), ts, font=FONT_TINY, fill=(100, 100, 140))


# =============================================================================
# Frame Rendering — Main
# =============================================================================

def render_frame(weather, radar_img, page_channels, weather_phase):
    """Render a single EPG page frame."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    ad_img = get_random_ad()

    # Top-left quarter: weather
    render_weather_box(img, draw, weather, radar_img, weather_phase)
    # Top-right quarter: ad
    render_ad_box(img, draw, ad_img)
    # Divider line between top and bottom halves
    draw.line([(0, HALF_H), (WIDTH, HALF_H)], fill=DIVIDER_COLOR, width=2)
    # Bottom half: schedule grid (this page's channels)
    render_schedule_grid(draw, page_channels)

    return img


# =============================================================================
# Main Loop — renders pages at :25 and :55 past each hour
# =============================================================================

def seconds_until_next_render():
    """Calculate seconds until the next :25 or :55 mark."""
    now = datetime.now()
    minute = now.minute

    if minute < 25:
        target_min = 25
    elif minute < 55:
        target_min = 55
    else:
        target = now.replace(minute=25, second=0, microsecond=0) + timedelta(hours=1)
        return (target - now).total_seconds()

    target = now.replace(minute=target_min, second=0, microsecond=0)
    return (target - now).total_seconds()


def render_all_pages(weather, radar_img):
    """Render all channel pages as separate PNGs.
    Pages rotate through channels in groups of CHANNELS_PER_PAGE.
    Weather phase varies per page for visual variety.
    """
    all_channels = get_epg_channels()
    num_pages = max(1, (len(all_channels) + CHANNELS_PER_PAGE - 1) // CHANNELS_PER_PAGE)

    for page in range(num_pages):
        start = page * CHANNELS_PER_PAGE
        page_channels = all_channels[start:start + CHANNELS_PER_PAGE]
        weather_phase = page % 3  # cycle weather display per page

        img = render_frame(weather, radar_img, page_channels, weather_phase)

        page_path = EPG_DIR / f"page_{page}.png"
        page_tmp = EPG_DIR / f"page_{page}.tmp.png"
        img.save(str(page_tmp), "PNG")
        os.replace(str(page_tmp), str(page_path))

    # Write page count so the playback loop knows how many to cycle
    count_path = EPG_DIR / "page_count"
    with open(count_path, "w") as f:
        f.write(str(num_pages))

    # Also write page_0 as current.png for initial load
    import shutil
    page0 = EPG_DIR / "page_0.png"
    if page0.exists():
        shutil.copy2(str(page0), str(FRAME_PATH))

    log.info(f"Rendered {num_pages} pages at {datetime.now().strftime('%H:%M:%S')}")
    return num_pages


def main():
    EPG_DIR.mkdir(parents=True, exist_ok=True)

    log.info("EPG generator starting (renders at :25 and :55)")
    weather = None
    radar_img = None
    last_weather_fetch = 0

    while True:
        try:
            if time.time() - last_weather_fetch > WEATHER_CACHE_TTL:
                weather, radar_img = load_weather_cache()
                last_weather_fetch = time.time()

            render_all_pages(weather, radar_img)

            # Sleep until next :25 or :55
            wait = seconds_until_next_render()
            if wait < 5:
                wait += 1800
            log.info(f"Next render in {int(wait)}s")
            time.sleep(wait)

        except KeyboardInterrupt:
            log.info("EPG generator stopping")
            break
        except Exception:
            log.error(f"Frame render error: {traceback.format_exc()}")
            time.sleep(60)


if __name__ == "__main__":
    main()
