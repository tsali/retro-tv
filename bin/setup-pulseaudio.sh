#!/usr/bin/env bash
pactl set-default-sink alsa_output.platform-fef00700.hdmi.hdmi-stereo
mkdir -p ~/.config/pulse
echo "set-default-sink alsa_output.platform-fef00700.hdmi.hdmi-stereo" >> ~/.config/pulse/default.pa
pactl info | grep "Default Sink"
echo "PulseAudio configured for HDMI!"
