#!/usr/bin/env python3
"""Generate a 61-second countdown video for the retro TV scheduler."""
import subprocess
import sys

output = "/home/retro/media/countdown.mp4"

vf = (
    "drawtext=textfile=/home/retro/media/countdown_text.txt"
    ":fontsize=72:fontcolor=0xe94560"
    ":x=(w-text_w)/2:y=(h/2)-100"
    ":borderw=2:bordercolor=black,"
    "drawtext=text='%{eif\\:61-t\\:d}'"
    ":fontsize=180:fontcolor=white"
    ":x=(w-text_w)/2:y=(h/2)+20"
    ":borderw=3:bordercolor=black"
)

cmd = [
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "color=c=0x1a1a2e:s=1920x1080:d=61:r=30",
    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
    "-vf", vf,
    "-c:v", "libx264", "-preset", "medium", "-crf", "23",
    "-c:a", "aac", "-b:a", "64k",
    "-shortest", "-t", "61",
    output,
]

print("Running:", " ".join(cmd[:6]), "...")
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode == 0:
    print(f"OK: {output}")
else:
    print("STDERR:", r.stderr[-800:])
    sys.exit(1)
