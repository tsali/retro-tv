#!/usr/bin/env python3
"""
EAS Video Generator — takes a pending alert JSON file and produces
a complete .mp4 with SAME header tones, attention signal, TTS, and EOM tones.
"""

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import wave

from PIL import Image, ImageDraw, ImageFont

BASE = "/home/retro"
STATE = f"{BASE}/state"
EAS_ACTIVE_DIR = f"{STATE}/eas_active"

# SAME AFSK parameters
SAMPLE_RATE = 44100
MARK_FREQ = 2083.3   # mark tone Hz
SPACE_FREQ = 1562.5  # space tone Hz
BAUD_RATE = 520.83   # bits per second
SAMPLES_PER_BIT = int(SAMPLE_RATE / BAUD_RATE)

# SAME event code to full name mapping
EVENT_NAMES = {
    "TOR": "TORNADO WARNING",
    "SVR": "SEVERE THUNDERSTORM WARNING",
    "FFW": "FLASH FLOOD WARNING",
    "EWW": "EXTREME WIND WARNING",
    "SMW": "SPECIAL MARINE WARNING",
    "SPS": "SPECIAL WEATHER STATEMENT",
    "WSW": "WINTER STORM WARNING",
    "HUW": "HURRICANE WARNING",
    "TSW": "TSUNAMI WARNING",
    "FRW": "FIRE WARNING",
    "CFW": "COASTAL FLOOD WARNING",
    "EAN": "EMERGENCY ACTION NOTIFICATION",
    "CDW": "CIVIL DANGER WARNING",
}


def generate_afsk_byte(byte_val):
    """Generate AFSK audio samples for one byte (LSB first)."""
    samples = []
    for bit_idx in range(8):
        bit = (byte_val >> bit_idx) & 1
        freq = MARK_FREQ if bit == 1 else SPACE_FREQ
        for s in range(SAMPLES_PER_BIT):
            t = s / SAMPLE_RATE
            val = int(32767 * 0.8 * math.sin(2 * math.pi * freq * t))
            samples.append(val)
    return samples


def generate_afsk_data(data_bytes):
    """Generate AFSK samples for a sequence of bytes."""
    samples = []
    for b in data_bytes:
        samples.extend(generate_afsk_byte(b))
    return samples


def generate_silence(duration_sec):
    """Generate silence samples."""
    return [0] * int(SAMPLE_RATE * duration_sec)


def write_wav(samples, filename):
    """Write 16-bit mono WAV file."""
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        raw = struct.pack(f'<{len(samples)}h', *samples)
        wf.writeframes(raw)


def generate_same_header(event_code, areas="000000", duration="0100",
                         callsign="RETROTV "):
    """Generate SAME header tones (preamble + ZCZC header × 3 with gaps)."""
    # Build SAME header string
    # Format: ZCZC-ORG-EEE-PSSCCC+TTTT-JJJHHMM-CALLSIGN-
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    jjj = now.strftime("%j")
    hhmm = now.strftime("%H%M")

    header = f"ZCZC-WXR-{event_code}-{areas}+{duration}-{jjj}{hhmm}-{callsign}-"

    # Preamble: 16 bytes of 0xAB
    preamble = [0xAB] * 16

    all_samples = []
    for burst in range(3):
        # Preamble
        all_samples.extend(generate_afsk_data(preamble))
        # Header bytes
        all_samples.extend(generate_afsk_data([ord(c) for c in header]))
        # 1 second silence between bursts
        if burst < 2:
            all_samples.extend(generate_silence(1.0))

    return all_samples


def generate_eom():
    """Generate End of Message tones (NNNN × 3 with gaps)."""
    preamble = [0xAB] * 16
    eom_str = "NNNN"

    all_samples = []
    for burst in range(3):
        all_samples.extend(generate_afsk_data(preamble))
        all_samples.extend(generate_afsk_data([ord(c) for c in eom_str]))
        if burst < 2:
            all_samples.extend(generate_silence(1.0))

    return all_samples


def generate_attention_wav(filename, duration=8):
    """Generate 853Hz + 960Hz dual-tone attention signal using ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"sine=frequency=853:duration={duration}",
        "-f", "lavfi", "-i",
        f"sine=frequency=960:duration={duration}",
        "-filter_complex", "amix=inputs=2:duration=longest",
        "-ar", str(SAMPLE_RATE), "-ac", "1",
        filename
    ], capture_output=True, timeout=30)


def generate_tts_wav(text, filename, tmpdir):
    """Generate TTS audio using ffmpeg's built-in flite filter.

    Uses textfile= instead of text= to avoid shell/lavfi escaping issues.
    """
    # Truncate text for TTS (keep it reasonable)
    if len(text) > 500:
        text = text[:497] + "..."

    # Write text to a temp file for flite's textfile= parameter
    text_path = os.path.join(tmpdir, "tts_input.txt")
    with open(text_path, "w") as f:
        f.write(text)

    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"flite=textfile={text_path}:voice=kal16",
        "-ar", str(SAMPLE_RATE), "-ac", "1",
        filename
    ], capture_output=True, timeout=120)


def generate_alert_image(event_code, headline, description, areas, expires,
                         filename):
    """Generate the EAS alert frame as a 960x540 PNG (SD — faster encode)."""
    from datetime import datetime

    width, height = 960, 540
    bg_color = (128, 0, 0)  # maroon #800000
    text_color = (255, 255, 255)
    header_color = (255, 255, 255)

    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Try to load a monospace font, fall back to default
    font_large = None
    font_medium = None
    font_small = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ]:
        if os.path.exists(font_path):
            try:
                font_large = ImageFont.truetype(font_path, 32)
                font_medium = ImageFont.truetype(font_path, 24)
                font_small = ImageFont.truetype(font_path, 16)
                break
            except Exception:
                continue

    if font_large is None:
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Draw white border
    border = 10
    draw.rectangle(
        [border, border, width - border, height - border],
        outline=text_color, width=3
    )

    # Header: EMERGENCY ALERT SYSTEM
    eas_text = "EMERGENCY ALERT SYSTEM"
    bbox = draw.textbbox((0, 0), eas_text, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, 25), eas_text, fill=header_color,
              font=font_large)

    # Separator line
    draw.line([(30, 65), (width - 30, 65)], fill=text_color, width=2)

    # Event type
    event_name = EVENT_NAMES.get(event_code, headline or event_code)
    bbox = draw.textbbox((0, 0), event_name, font=font_medium)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, 78), event_name, fill=(255, 255, 0),
              font=font_medium)

    # Issued timestamp
    issued_str = f"ISSUED: {datetime.now().strftime('%I:%M %p  %B %d, %Y')}"
    bbox = draw.textbbox((0, 0), issued_str, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, 108), issued_str, fill=(255, 200, 0),
              font=font_small)

    # Headline (if different from event name)
    y_pos = 135
    if headline and headline.upper() != event_name:
        wrapped = textwrap.fill(headline, width=55)
        for line in wrapped.split('\n')[:2]:
            draw.text((40, y_pos), line, fill=text_color, font=font_small)
            y_pos += 22

    # Separator
    y_pos += 5
    draw.line([(30, y_pos), (width - 30, y_pos)], fill=text_color, width=1)
    y_pos += 10

    # Description text - word wrapped
    if description:
        wrapped = textwrap.fill(description, width=70)
        for line in wrapped.split('\n')[:12]:
            draw.text((40, y_pos), line, fill=text_color, font=font_small)
            y_pos += 22

    # Areas affected
    if areas:
        y_pos += 10
        draw.text((40, y_pos), "AREAS:", fill=(255, 255, 0), font=font_small)
        y_pos += 22
        area_wrapped = textwrap.fill(areas, width=70)
        for line in area_wrapped.split('\n')[:4]:
            draw.text((40, y_pos), line, fill=text_color, font=font_small)
            y_pos += 22

    # Expiration at bottom
    if expires:
        y_bottom = height - 40
        exp_text = f"EXPIRES: {expires}"
        draw.text((40, y_bottom), exp_text, fill=(255, 200, 0),
                  font=font_small)

    img.save(filename)


def generate_eas_video(alert_json_path):
    """Main entry: takes alert JSON path, produces .mp4, returns output path."""
    with open(alert_json_path) as f:
        alert = json.load(f)

    event_code = alert.get("event_code", "EAN")
    headline = alert.get("headline", "")
    description = alert.get("description", "")
    areas = alert.get("areas", "")
    expires = alert.get("expires", "")
    alert_id = alert.get("id", str(int(time.time())))

    # Sanitize ID for filename
    safe_id = "".join(c if c.isalnum() or c in '-_' else '_' for c in alert_id)
    output_path = os.path.join(EAS_ACTIVE_DIR, f"eas_{safe_id}.mp4")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Generate SAME header tones WAV
        same_samples = generate_same_header(event_code)
        same_wav = os.path.join(tmpdir, "same_header.wav")
        write_wav(same_samples, same_wav)

        # 2. Generate attention signal WAV
        attn_wav = os.path.join(tmpdir, "attention.wav")
        generate_attention_wav(attn_wav, duration=8)

        # 3. Generate TTS WAV
        tts_text = f"{EVENT_NAMES.get(event_code, event_code)}. "
        if headline:
            tts_text += headline + ". "
        if description:
            # Truncate for TTS
            desc_short = description[:300]
            tts_text += desc_short
        if areas:
            tts_text += f". Affected areas: {areas[:150]}"

        tts_wav = os.path.join(tmpdir, "tts.wav")
        generate_tts_wav(tts_text, tts_wav, tmpdir)

        # 4. Generate EOM tones WAV
        eom_samples = generate_eom()
        eom_wav = os.path.join(tmpdir, "eom.wav")
        write_wav(eom_samples, eom_wav)

        # 5. Add 1s silence buffers between segments
        silence_wav = os.path.join(tmpdir, "silence.wav")
        write_wav(generate_silence(1.0), silence_wav)

        # 6. Concatenate audio segments
        concat_list = os.path.join(tmpdir, "concat.txt")
        with open(concat_list, 'w') as f:
            f.write(f"file '{same_wav}'\n")
            f.write(f"file '{silence_wav}'\n")
            f.write(f"file '{attn_wav}'\n")
            f.write(f"file '{silence_wav}'\n")
            f.write(f"file '{tts_wav}'\n")
            f.write(f"file '{silence_wav}'\n")
            f.write(f"file '{eom_wav}'\n")

        combined_audio = os.path.join(tmpdir, "combined.wav")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            combined_audio
        ], capture_output=True, timeout=30)

        # 7. Generate alert image
        alert_img = os.path.join(tmpdir, "alert.png")
        generate_alert_image(event_code, headline, description, areas,
                             expires, alert_img)

        # 8. Combine image + audio into video
        # -r 2: 2fps (still image, saves huge encoding time on Pi)
        subprocess.run([
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "2", "-i", alert_img,
            "-i", combined_audio,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-r", "2",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-movflags", "+faststart",
            output_path
        ], capture_output=True, timeout=120)

    if not os.path.exists(output_path):
        print(f"ERROR: Failed to generate {output_path}", file=sys.stderr)
        return None

    return output_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <alert.json>", file=sys.stderr)
        sys.exit(1)

    result = generate_eas_video(sys.argv[1])
    if result:
        print(result)
    else:
        sys.exit(1)
