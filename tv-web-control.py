#!/usr/bin/env python3
"""
Retro TV Web Control - Multi-channel view with themes
Shows what's playing on all channels simultaneously
"""
from flask import Flask, render_template_string, request, jsonify
import os
import sys
import json
from datetime import datetime

# Add bin/ to path for schedule_manager
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bin"))
import schedule_manager as sm

app = Flask(__name__)

BASE = "/home/retro"
MEDIA = f"{BASE}/media"
STATE = f"{BASE}/state"
CHANNELS_TSV = f"{STATE}/channels.tsv"
CHANNEL_CMD = f"{STATE}/channel_cmd"
MPV_SOCKET = "/tmp/mpv-socket"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Retro TV Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root {
            --primary: #00ff00;
            --bg-dark: #1a1a1a;
            --bg-black: #000;
            --bg-dark-hover: #002200;
            --bg-active: #001100;
            --border-dim: #003300;
            --text-dim: rgba(0, 255, 0, 0.7);
        }
        
        [data-theme="blue"] {
            --primary: #00d4ff;
            --bg-dark: #0a1a2a;
            --bg-black: #000810;
            --bg-dark-hover: #002244;
            --bg-active: #001133;
            --border-dim: #003366;
            --text-dim: rgba(0, 212, 255, 0.7);
        }
        
        [data-theme="red"] {
            --primary: #ff3333;
            --bg-dark: #2a0a0a;
            --bg-black: #100000;
            --bg-dark-hover: #442200;
            --bg-active: #331100;
            --border-dim: #663300;
            --text-dim: rgba(255, 51, 51, 0.7);
        }
        
        [data-theme="amber"] {
            --primary: #ffaa00;
            --bg-dark: #2a1a0a;
            --bg-black: #100800;
            --bg-dark-hover: #443300;
            --bg-active: #332200;
            --border-dim: #664400;
            --text-dim: rgba(255, 170, 0, 0.7);
        }
        
        [data-theme="mono"] {
            --primary: #ffffff;
            --bg-dark: #1a1a1a;
            --bg-black: #000000;
            --bg-dark-hover: #333333;
            --bg-active: #222222;
            --border-dim: #555555;
            --text-dim: rgba(255, 255, 255, 0.7);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Courier New', monospace;
            background: var(--bg-dark);
            color: var(--primary);
            padding: 20px;
            transition: all 0.3s;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        h1 {
            text-shadow: 0 0 10px var(--primary);
            font-size: 2em;
        }
        .theme-selector {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .theme-btn {
            width: 35px;
            height: 35px;
            border: 2px solid var(--primary);
            border-radius: 50%;
            cursor: pointer;
            transition: all 0.3s;
            background: var(--bg-black);
        }
        .theme-btn:hover {
            transform: scale(1.1);
            box-shadow: 0 0 15px var(--primary);
        }
        .theme-btn.active {
            box-shadow: 0 0 20px var(--primary);
            border-width: 3px;
        }
        .theme-btn.green { border-color: #00ff00; background: #001100; }
        .theme-btn.blue { border-color: #00d4ff; background: #001133; }
        .theme-btn.red { border-color: #ff3333; background: #331100; }
        .theme-btn.amber { border-color: #ffaa00; background: #332200; }
        .theme-btn.mono { border-color: #ffffff; background: #222222; }
        
        .channels-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .channel-card {
            background: var(--bg-black);
            border: 2px solid var(--primary);
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.5);
            transition: all 0.3s;
        }
        .channel-card.active {
            box-shadow: 0 0 30px var(--primary);
            background: var(--bg-active);
        }
        .channel-card.disabled {
            opacity: 0.5;
            border-color: var(--border-dim);
        }
        .channel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--primary);
        }
        .channel-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .channel-number {
            font-size: 2em;
            font-weight: bold;
            text-shadow: 0 0 10px var(--primary);
        }
        .channel-name {
            font-size: 1.3em;
            font-weight: bold;
        }
        .channel-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .toggle-switch {
            position: relative;
            width: 60px;
            height: 30px;
        }
        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: #333;
            transition: .4s;
            border-radius: 30px;
            border: 2px solid var(--primary);
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background-color: var(--primary);
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background-color: var(--bg-dark-hover);
        }
        input:checked + .slider:before {
            transform: translateX(30px);
            box-shadow: 0 0 10px var(--primary);
        }
        .tune-btn {
            background: var(--bg-black);
            color: var(--primary);
            border: 2px solid var(--primary);
            padding: 8px 20px;
            cursor: pointer;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            transition: all 0.3s;
        }
        .tune-btn:hover {
            background: var(--primary);
            color: var(--bg-black);
            box-shadow: 0 0 15px var(--primary);
        }
        .now-playing {
            margin: 15px 0;
        }
        .now-playing-label {
            color: var(--text-dim);
            font-size: 0.9em;
            margin-bottom: 5px;
        }
        .now-playing-file {
            color: var(--primary);
            font-size: 1em;
            word-break: break-all;
            line-height: 1.4;
        }
        .progress-container {
            background: var(--bg-dark-hover);
            height: 30px;
            border: 2px solid var(--primary);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
            margin: 10px 0;
        }
        .progress-bar {
            height: 100%;
            background: var(--primary);
            transition: width 1s linear;
            box-shadow: 0 0 10px var(--primary);
            opacity: 0.8;
        }
        .progress-time {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: var(--bg-black);
            font-weight: bold;
            text-shadow: 0 0 3px var(--primary);
            z-index: 1;
            font-size: 0.9em;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            background: var(--primary);
            color: var(--bg-black);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        .status {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--bg-black);
            border: 2px solid var(--primary);
            padding: 10px 20px;
            border-radius: 4px;
            display: none;
            animation: fadeIn 0.3s;
            z-index: 1000;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .reload-btn {
            background: var(--bg-black);
            color: var(--primary);
            border: 2px solid var(--primary);
            padding: 10px 30px;
            cursor: pointer;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            display: block;
            margin: 20px auto;
        }
        .reload-btn:hover {
            background: var(--primary);
            color: var(--bg-black);
        }
        /* Parental lock modal */
        .pin-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.85);
            z-index: 2000;
            align-items: center;
            justify-content: center;
        }
        .pin-overlay.active { display: flex; }
        .pin-modal {
            background: var(--bg-black);
            border: 2px solid #ff3333;
            padding: 30px;
            text-align: center;
            border-radius: 8px;
            min-width: 300px;
        }
        .pin-modal h2 { color: #ff3333; margin-bottom: 20px; }
        .pin-input {
            font-family: 'Courier New', monospace;
            font-size: 2em;
            text-align: center;
            width: 200px;
            padding: 10px;
            background: #111;
            color: var(--primary);
            border: 2px solid #ff3333;
            letter-spacing: 8px;
            border-radius: 4px;
        }
        .pin-error { color: #ff3333; margin-top: 10px; font-size: 0.9em; }
        .pin-btn {
            margin-top: 15px;
            padding: 10px 30px;
            background: #ff3333;
            color: #fff;
            border: none;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            cursor: pointer;
            border-radius: 4px;
        }
        .locked-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            background: #ff3333;
            color: #fff;
        }
        /* EAS Section */
        /* Remote control — fixed sidebar left */
        .remote-control {
            position: fixed;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            display: flex;
            flex-direction: column;
            gap: 16px;
            padding: 16px 12px;
            background: var(--bg-black);
            border: 2px solid var(--primary);
            border-left: none;
            border-radius: 0 8px 8px 0;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.7);
            z-index: 1000;
        }
        .remote-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }
        .remote-group-label {
            color: var(--text-dim);
            font-size: 0.7em;
            letter-spacing: 1px;
        }
        .remote-btn {
            background: var(--bg-black);
            color: var(--primary);
            border: 2px solid var(--primary);
            width: 48px;
            height: 48px;
            cursor: pointer;
            border-radius: 50%;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            font-size: 1.2em;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .remote-btn:hover {
            background: var(--primary);
            color: var(--bg-black);
            box-shadow: 0 0 15px var(--primary);
        }
        .remote-btn:active {
            transform: scale(0.9);
        }
        @media (max-width: 600px) {
            .remote-control {
                top: auto;
                bottom: 0;
                left: 0;
                right: 0;
                transform: none;
                flex-direction: row;
                justify-content: center;
                border-radius: 8px 8px 0 0;
                border: 2px solid var(--primary);
                border-bottom: none;
                border-left: 2px solid var(--primary);
                padding: 10px 16px;
                gap: 24px;
            }
            .remote-group {
                flex-direction: row;
                gap: 6px;
            }
            .remote-btn {
                width: 42px;
                height: 42px;
                font-size: 1em;
            }
            body {
                padding-bottom: 80px;
            }
        }

        .eas-section {
            margin-top: 30px;
            border: 2px solid #cc0000;
            border-radius: 8px;
            padding: 20px;
            background: #1a0000;
        }
        .eas-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #cc0000;
        }
        .eas-header h2 {
            color: #ff3333;
            text-shadow: 0 0 10px #ff3333;
            font-size: 1.5em;
        }
        .eas-status-badge {
            display: inline-block;
            padding: 6px 16px;
            border-radius: 12px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .eas-status-idle { background: #333; color: #888; }
        .eas-status-active { background: #cc0000; color: #fff; animation: pulse 1s infinite; }
        .eas-status-disabled { background: #333; color: #555; }
        .eas-row {
            display: flex;
            gap: 15px;
            align-items: center;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .eas-row label {
            color: #ff6666;
            font-weight: bold;
            min-width: 120px;
        }
        .eas-input {
            font-family: 'Courier New', monospace;
            padding: 8px 12px;
            background: #111;
            color: #ff6666;
            border: 2px solid #cc0000;
            border-radius: 4px;
            font-size: 1em;
        }
        .eas-btn {
            background: #1a0000;
            color: #ff3333;
            border: 2px solid #cc0000;
            padding: 8px 20px;
            cursor: pointer;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
            transition: all 0.3s;
        }
        .eas-btn:hover {
            background: #cc0000;
            color: #fff;
            box-shadow: 0 0 15px #cc0000;
        }
        .eas-btn-danger {
            background: #cc0000;
            color: #fff;
            border: 2px solid #ff3333;
        }
        .eas-btn-danger:hover {
            background: #ff3333;
            box-shadow: 0 0 20px #ff3333;
        }
        .eas-alert-types {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 8px;
            margin: 10px 0;
        }
        .eas-alert-type {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            background: #0a0000;
            border: 1px solid #330000;
            border-radius: 4px;
        }
        .eas-alert-type input[type="checkbox"] {
            accent-color: #cc0000;
            width: 18px;
            height: 18px;
        }
        .eas-alert-type .code { color: #ff3333; font-weight: bold; }
        .eas-alert-type .desc { color: #aa6666; font-size: 0.85em; }
        .eas-coords {
            color: #886666;
            font-size: 0.85em;
            margin-left: 10px;
        }
    </style>
</head>
<body data-theme="green">
    <div class="container">
        <div class="header">
            <h1>📺 RETRO TV CONTROL</h1>
            <div class="theme-selector">
                <div class="theme-btn green active" onclick="setTheme('green')" title="Green"></div>
                <div class="theme-btn blue" onclick="setTheme('blue')" title="Blue"></div>
                <div class="theme-btn red" onclick="setTheme('red')" title="Red"></div>
                <div class="theme-btn amber" onclick="setTheme('amber')" title="Amber"></div>
                <div class="theme-btn mono" onclick="setTheme('mono')" title="Mono"></div>
            </div>
        </div>
        
        <div class="channels-grid" id="channels-grid"></div>

        <div class="eas-section">
            <div class="eas-header">
                <h2>EMERGENCY ALERT SYSTEM</h2>
                <span class="eas-status-badge eas-status-disabled" id="eas-status">DISABLED</span>
            </div>

            <div class="eas-row">
                <label>EAS ENABLED:</label>
                <label class="toggle-switch">
                    <input type="checkbox" id="eas-enabled" onchange="easToggle(this.checked)">
                    <span class="slider" style="border-color:#cc0000;"></span>
                </label>
            </div>

            <div class="eas-row">
                <label>ZIP CODE:</label>
                <input type="text" class="eas-input" id="eas-zip" placeholder="e.g. 90210"
                       maxlength="5" style="width:120px;">
                <button class="eas-btn" onclick="easSetLocation()">SET LOCATION</button>
                <span class="eas-coords" id="eas-coords"></span>
            </div>

            <div class="eas-row">
                <label>ALERT TYPES:</label>
            </div>
            <div class="eas-alert-types" id="eas-alert-types"></div>

            <div class="eas-row" style="margin-top:20px;">
                <button class="eas-btn eas-btn-danger" onclick="easTestAlert()">
                    SEND TEST ALERT
                </button>
            </div>
        </div>

        <button class="reload-btn" onclick="location.reload()">↻ RELOAD PAGE</button>
    </div>

    <div class="status" id="status"></div>

    <div class="remote-control">
        <div class="remote-group">
            <div class="remote-group-label">CH</div>
            <button class="remote-btn" onclick="remoteCmd('/api/channel/up')">&#9650;</button>
            <button class="remote-btn" onclick="remoteCmd('/api/channel/down')">&#9660;</button>
        </div>
        <div class="remote-group">
            <div class="remote-group-label">VOL</div>
            <button class="remote-btn" onclick="remoteCmd('/api/volume', {delta: 5})">&#9650;</button>
            <button class="remote-btn" onclick="remoteCmd('/api/volume', {delta: -5})">&#9660;</button>
        </div>
        <div class="remote-group">
            <div class="remote-group-label">MUTE</div>
            <button class="remote-btn" onclick="remoteCmd('/api/mute')">&#9744;</button>
        </div>
    </div>

    <script>
        let channels = {{ channels|tojson }};
        let currentChannel = null;

        // Theme management
        function setTheme(theme) {
            document.body.setAttribute('data-theme', theme);
            localStorage.setItem('tv-theme', theme);
            
            // Update active button
            document.querySelectorAll('.theme-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            document.querySelector(`.theme-btn.${theme}`).classList.add('active');
        }

        // Load saved theme
        const savedTheme = localStorage.getItem('tv-theme') || 'green';
        setTheme(savedTheme);

        function showStatus(message) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.style.display = 'block';
            setTimeout(() => status.style.display = 'none', 2000);
        }

        function toggleChannel(channel, enabled) {
            fetch('/api/toggle', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel, enabled})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                const ch = channels.find(c => c.number === channel);
                if (ch) ch.enabled = enabled;
                renderChannels();
            })
            .catch(err => {
                showStatus('Error: ' + err);
            });
        }

        function tuneChannel(channel) {
            fetch('/api/tune', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                currentChannel = channel;
                renderChannels();
            })
            .catch(err => {
                showStatus('Error: ' + err);
            });
        }

        function formatTime(seconds) {
            if (!seconds || isNaN(seconds)) return '--:--';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        }

        let lockedChannels = [];

        function toggleLock(channel) {
            fetch('/api/parental/toggle-lock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({channel})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                lockedChannels = data.locked || [];
                renderChannels();
            });
        }

        function updateAllChannelStatus() {
            fetch('/api/all-status')
                .then(r => r.json())
                .then(data => {
                    currentChannel = data.current_channel;
                    lockedChannels = data.locked_channels || [];

                    channels.forEach(ch => {
                        const statusData = data.channels[ch.number];
                        if (statusData) {
                            ch.nowPlaying = statusData.filename;
                            ch.position = statusData.position;
                            ch.duration = statusData.duration;
                            ch.percent = statusData.percent;
                        }
                    });

                    renderChannels();
                })
                .catch(err => {
                    console.error('Status update error:', err);
                });
        }

        function renderChannels() {
            const container = document.getElementById('channels-grid');
            container.innerHTML = '';
            
            channels.forEach(ch => {
                const card = document.createElement('div');
                const isActive = ch.number === currentChannel;
                const isDisabled = !ch.enabled;
                
                card.className = 'channel-card';
                if (isActive) card.className += ' active';
                if (isDisabled) card.className += ' disabled';
                
                const percent = ch.percent || 0;
                const timeStr = formatTime(ch.position) + ' / ' + formatTime(ch.duration);
                const filename = ch.nowPlaying || 'Loading...';
                const isLocked = lockedChannels.includes(String(ch.number));

                card.innerHTML = `
                    <div class="channel-header">
                        <div class="channel-info">
                            <div class="channel-number">${ch.number}</div>
                            <div>
                                <div class="channel-name">${ch.name}</div>
                                ${isActive ? '<span class="status-badge">● LIVE</span>' : ''}
                                ${isLocked ? '<span class="locked-badge">LOCKED</span>' : ''}
                            </div>
                        </div>
                        <div class="channel-controls">
                            <button class="tune-btn" style="font-size:0.7em;padding:4px 8px;${isLocked ? 'border-color:#ff3333;color:#ff3333;' : 'border-color:#555;color:#555;'}"
                                    onclick="toggleLock('${ch.number}')">${isLocked ? 'UNLOCK' : 'LOCK'}</button>
                            <label class="toggle-switch">
                                <input type="checkbox" ${ch.enabled ? 'checked' : ''}
                                       onchange="toggleChannel('${ch.number}', this.checked)">
                                <span class="slider"></span>
                            </label>
                            <button class="tune-btn" onclick="tuneChannel('${ch.number}')">TUNE</button>
                        </div>
                    </div>
                    
                    <div class="now-playing">
                        <div class="now-playing-label">NOW PLAYING:</div>
                        <div class="now-playing-file">${filename}</div>
                    </div>
                    
                    <div class="progress-container">
                        <div class="progress-bar" style="width: ${percent}%"></div>
                        <div class="progress-time">${timeStr}</div>
                    </div>
                `;
                
                container.appendChild(card);
            });
        }

        function remoteCmd(url, body) {
            fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body || {})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                setTimeout(updateAllChannelStatus, 300);
            })
            .catch(err => showStatus('Error: ' + err));
        }

        renderChannels();
        updateAllChannelStatus();
        setInterval(updateAllChannelStatus, 2000);

        // === EAS Functions ===
        const alertTypeDescs = {
            TOR: 'Tornado Warning',
            SVR: 'Severe Thunderstorm Warning',
            FFW: 'Flash Flood Warning',
            EWW: 'Extreme Wind Warning',
            SMW: 'Special Marine Warning',
            SPS: 'Special Weather Statement',
            WSW: 'Winter Storm Warning',
            HUW: 'Hurricane Warning',
            TSW: 'Tsunami Warning',
            FRW: 'Fire Warning',
            CFW: 'Coastal Flood Warning',
            EAN: 'Emergency Action Notification',
            CDW: 'Civil Danger Warning'
        };

        function easLoadConfig() {
            fetch('/api/eas/config')
                .then(r => r.json())
                .then(cfg => {
                    document.getElementById('eas-enabled').checked = cfg.enabled;
                    document.getElementById('eas-zip').value = cfg.zip_code || '';
                    if (cfg.latitude && cfg.longitude && cfg.latitude !== 0) {
                        document.getElementById('eas-coords').textContent =
                            `(${cfg.latitude.toFixed(4)}, ${cfg.longitude.toFixed(4)})`;
                    }
                    renderAlertTypes(cfg.alert_types || {});
                    easUpdateStatus(cfg.enabled);
                })
                .catch(() => {});
        }

        function renderAlertTypes(types) {
            const container = document.getElementById('eas-alert-types');
            container.innerHTML = '';
            for (const [code, desc] of Object.entries(alertTypeDescs)) {
                const checked = types[code] ? 'checked' : '';
                container.innerHTML += `
                    <div class="eas-alert-type">
                        <input type="checkbox" ${checked}
                               onchange="easToggleType('${code}', this.checked)">
                        <span class="code">${code}</span>
                        <span class="desc">${desc}</span>
                    </div>
                `;
            }
        }

        function easUpdateStatus(enabled) {
            const badge = document.getElementById('eas-status');
            fetch('/api/eas/status')
                .then(r => r.json())
                .then(data => {
                    if (!data.enabled) {
                        badge.className = 'eas-status-badge eas-status-disabled';
                        badge.textContent = 'DISABLED';
                    } else if (data.active) {
                        badge.className = 'eas-status-badge eas-status-active';
                        badge.textContent = 'ACTIVE';
                    } else {
                        badge.className = 'eas-status-badge eas-status-idle';
                        badge.textContent = 'IDLE';
                    }
                })
                .catch(() => {});
        }

        function easToggle(enabled) {
            fetch('/api/eas/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                easUpdateStatus(enabled);
            });
        }

        function easToggleType(code, enabled) {
            fetch('/api/eas/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({alert_types: {[code]: enabled}})
            })
            .then(r => r.json())
            .then(data => showStatus(data.message));
        }

        function easSetLocation() {
            const zip = document.getElementById('eas-zip').value.trim();
            if (!zip || zip.length !== 5) {
                showStatus('Enter a valid 5-digit ZIP code');
                return;
            }
            showStatus('Geocoding...');
            fetch('/api/eas/set-location', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({zip_code: zip})
            })
            .then(r => r.json())
            .then(data => {
                showStatus(data.message);
                if (data.latitude) {
                    document.getElementById('eas-coords').textContent =
                        `(${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)})`;
                }
            })
            .catch(err => showStatus('Error: ' + err));
        }

        function easTestAlert() {
            if (!confirm('Send a test EAS alert? This will interrupt current programming.')) return;
            fetch('/api/eas/test', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(r => r.json())
            .then(data => showStatus(data.message))
            .catch(err => showStatus('Error: ' + err));
        }

        easLoadConfig();
        setInterval(() => easUpdateStatus(), 5000);
    </script>
</body>
</html>
"""

def read_channels():
    """Read channels from channels.tsv"""
    channels = []
    if not os.path.exists(CHANNELS_TSV):
        return channels
    
    with open(CHANNELS_TSV, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 3:
                channels.append({
                    'number': parts[0],
                    'name': parts[1].upper(),
                    'enabled': parts[2] == '1'
                })
    return channels

def write_channels(channels):
    """Write channels back to channels.tsv"""
    with open(CHANNELS_TSV, 'w') as f:
        for ch in channels:
            enabled = '1' if ch['enabled'] else '0'
            f.write(f"{ch['number']}\t{ch['name']}\t{enabled}\n")

def get_current_channel_number():
    """Get the currently tuned channel number"""
    try:
        with open(f"{STATE}/current_channel_number", 'r') as f:
            return f.read().strip()
    except:
        return None

YOUTUBE_CONFIG = f"{BASE}/config/youtube_channels.json"

def get_youtube_channels():
    try:
        with open(YOUTUBE_CONFIG) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

def calculate_epoch_position(station, channel_number=None):
    """Calculate what should be playing on a station right now.

    Uses the schedule first to determine the correct show, then
    calculates epoch position within that show's episodes only.
    Falls back to full-station epoch if no schedule is active.
    """
    try:
        # MTV channels — show currently playing from mtv_meta state
        if station.upper().startswith('MTV'):
            meta_file = f"{STATE}/mtv_meta"
            label = station.upper()
            if os.path.exists(meta_file):
                try:
                    with open(meta_file) as mf:
                        parts = mf.read().strip().split('\t')
                    artist = parts[0] if len(parts) > 0 else ''
                    title = parts[1] if len(parts) > 1 else ''
                    label = f"{artist} - {title}" if artist and title else label
                except Exception:
                    pass
            return {
                'filename': label,
                'position': 0,
                'duration': 0,
                'percent': 0
            }

        # YouTube live stream channels
        yt_channels = get_youtube_channels()
        if station.upper() in yt_channels:
            entry = yt_channels[station.upper()]
            return {
                'filename': entry.get('name', station.upper()) + ' (LIVE)',
                'position': 0,
                'duration': 0,
                'percent': 0
            }
        idx_file = f"{MEDIA}/channels/{station}/index.tsv"
        if not os.path.exists(idx_file):
            return None

        entries = []
        with open(idx_file, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    path = parts[0]
                    duration = int(parts[1])
                    entries.append({'path': path, 'duration': duration})

        if not entries:
            return None

        # Try schedule-aware lookup
        if channel_number:
            try:
                cfg = sm.load_config()
                state = sm.load_state()
                result = sm.resolve_now(cfg, state, channel_number)
                if result:
                    show_id = result.get("show_id", "")
                    if show_id in ("SIGNOFF", "SIGNON"):
                        return {
                            'filename': result["show"].get("title", show_id),
                            'position': 0,
                            'duration': 0,
                            'percent': 0
                        }
                    show_path = result.get("show", {}).get("path", "")
                    if show_path:
                        # Filter index to only this show's episodes
                        show_entries = [e for e in entries if e['path'].startswith(show_path)]
                        if show_entries:
                            total = sum(e['duration'] for e in show_entries)
                            if total > 0:
                                now = int(datetime.now().timestamp())
                                pos = now % total
                                acc = 0
                                for entry in show_entries:
                                    if pos < acc + entry['duration']:
                                        offset = pos - acc
                                        return {
                                            'filename': os.path.basename(entry['path']),
                                            'position': offset,
                                            'duration': entry['duration'],
                                            'percent': (offset / entry['duration'] * 100) if entry['duration'] > 0 else 0
                                        }
                                    acc += entry['duration']
            except Exception:
                pass

        # Fallback: full-station epoch
        total_duration = sum(e['duration'] for e in entries)
        if total_duration == 0:
            return None

        now = int(datetime.now().timestamp())
        position_in_cycle = now % total_duration

        accumulated = 0
        for entry in entries:
            if position_in_cycle < accumulated + entry['duration']:
                offset = position_in_cycle - accumulated
                return {
                    'filename': os.path.basename(entry['path']),
                    'position': offset,
                    'duration': entry['duration'],
                    'percent': (offset / entry['duration'] * 100) if entry['duration'] > 0 else 0
                }
            accumulated += entry['duration']

        return None
    except Exception:
        return None

@app.route('/')
def index():
    channels = read_channels()
    return render_template_string(HTML_TEMPLATE, channels=channels)

@app.route('/api/all-status')
def all_status():
    """Get status for all channels"""
    channels = read_channels()
    current_channel = get_current_channel_number()
    
    pcfg = get_parental_config()
    locked_channels = [str(x) for x in pcfg.get("locked_channels", [])]

    result = {
        'current_channel': current_channel,
        'locked_channels': locked_channels,
        'channels': {}
    }
    
    # Get actual mpv state for the active channel
    mpv_path = get_mpv_property("path")
    mpv_position = get_mpv_property("time-pos") or 0
    mpv_duration = get_mpv_property("duration") or 0

    for ch in channels:
        station = ch['name'].lower()

        if str(ch['number']) == str(current_channel):
            # Active channel: use actual mpv data
            if mpv_path:
                try:
                    pos = float(mpv_position)
                    dur = float(mpv_duration) if mpv_duration else 0
                    pct = (pos / dur * 100) if dur > 0 else 0
                except (ValueError, TypeError, ZeroDivisionError):
                    pos, dur, pct = 0, 0, 0
                result['channels'][ch['number']] = {
                    'filename': os.path.basename(str(mpv_path)),
                    'position': pos,
                    'duration': dur,
                    'percent': pct
                }
            else:
                result['channels'][ch['number']] = {
                    'filename': 'No content',
                    'position': 0,
                    'duration': 0,
                    'percent': 0
                }
        else:
            # Inactive channels: use schedule-aware epoch estimate
            status = calculate_epoch_position(station, ch['number'])
            if status:
                result['channels'][ch['number']] = status
            else:
                result['channels'][ch['number']] = {
                    'filename': 'No content',
                    'position': 0,
                    'duration': 0,
                    'percent': 0
                }

    return jsonify(result)

@app.route('/api/toggle', methods=['POST'])
def toggle_channel():
    data = request.json
    channel_num = data.get('channel')
    enabled = data.get('enabled')
    
    channels = read_channels()
    for ch in channels:
        if ch['number'] == channel_num:
            ch['enabled'] = enabled
            break
    
    write_channels(channels)
    
    return jsonify({
        'success': True,
        'message': f'Channel {channel_num} {"enabled" if enabled else "disabled"}'
    })

@app.route('/api/tune', methods=['POST'])
def tune_channel():
    data = request.json
    channel_num = data.get('channel')

    with open(CHANNEL_CMD, 'w') as f:
        f.write(channel_num)

    return jsonify({
        'success': True,
        'message': f'Tuned to channel {channel_num}'
    })

@app.route('/api/channel/up', methods=['POST'])
def channel_up():
    with open(CHANNEL_CMD, 'w') as f:
        f.write('up')
    return jsonify({'success': True, 'message': 'Channel up'})

@app.route('/api/channel/down', methods=['POST'])
def channel_down():
    with open(CHANNEL_CMD, 'w') as f:
        f.write('down')
    return jsonify({'success': True, 'message': 'Channel down'})

@app.route('/api/volume', methods=['POST'])
def volume_adjust():
    data = request.json
    delta = data.get('delta', 5)
    with open(f"{STATE}/volume", 'w') as f:
        f.write(str(delta))
    return jsonify({'success': True, 'message': f'Volume {"+" if delta > 0 else ""}{delta}'})

@app.route('/api/mute', methods=['POST'])
def mute_toggle():
    with open(f"{STATE}/mute", 'w') as f:
        f.write('1')
    return jsonify({'success': True, 'message': 'Mute toggled'})

def get_mpv_property(prop):
    """Query mpv IPC socket for a property."""
    import subprocess
    try:
        cmd = f'printf \'{{ "command": ["get_property", "{prop}"] }}\\n\' | socat - UNIX-CONNECT:{MPV_SOCKET}'
        result = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True, timeout=2)
        if result.stdout:
            data = json.loads(result.stdout)
            if data.get("error") == "success":
                return data.get("data")
    except Exception:
        pass
    return None

PARENTAL_CONFIG = f"{BASE}/config/parental_lock.json"
PARENTAL_UNLOCKED = f"{STATE}/parental_unlocked"

def get_parental_config():
    try:
        with open(PARENTAL_CONFIG) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"pin": "42069", "locked_channels": []}

@app.route('/api/parental/status')
def parental_status():
    cfg = get_parental_config()
    current = get_current_channel_number()
    locked = [str(x) for x in cfg.get("locked_channels", [])]
    is_locked = current in locked
    is_unlocked = os.path.exists(PARENTAL_UNLOCKED)
    return jsonify({
        'locked': is_locked and not is_unlocked,
        'channel_is_restricted': is_locked,
    })

def send_mpv_cmd(cmd_json):
    """Send a command to mpv via IPC."""
    import subprocess
    try:
        subprocess.run(
            ['bash', '-c', f"printf '{cmd_json}\\n' | socat - UNIX-CONNECT:{MPV_SOCKET}"],
            capture_output=True, timeout=3
        )
    except Exception:
        pass

@app.route('/api/parental/toggle-lock', methods=['POST'])
def parental_toggle_lock():
    data = request.json
    channel_num = str(data.get('channel', ''))
    cfg = get_parental_config()
    locked = [str(x) for x in cfg.get("locked_channels", [])]
    current = get_current_channel_number()

    if channel_num in locked:
        locked.remove(channel_num)
        msg = f'Channel {channel_num} unlocked (parental lock removed)'
        # If this is the active channel, remove scramble + unmute immediately
        if str(channel_num) == str(current):
            send_mpv_cmd('{ "command": ["vf", "remove", "@scramble"] }')
            send_mpv_cmd('{ "command": ["set_property", "mute", false] }')
            try:
                os.remove(PARENTAL_UNLOCKED)
            except OSError:
                pass
    else:
        locked.append(channel_num)
        msg = f'Channel {channel_num} marked as adult (parental lock added)'
        # If this is the active channel, apply scramble immediately
        if str(channel_num) == str(current):
            send_mpv_cmd('{ "command": ["vf", "add", "@scramble:lavfi=[hue=H=t*90:s=3,noise=alls=80:allf=t,rgbashift=rh=30:bh=-30:gv=20]"] }')
            send_mpv_cmd('{ "command": ["set_property", "mute", true] }')

    cfg["locked_channels"] = locked
    with open(PARENTAL_CONFIG, 'w') as f:
        json.dump(cfg, f, indent=2)
    return jsonify({'success': True, 'message': msg, 'locked': locked})

@app.route('/api/parental/unlock', methods=['POST'])
def parental_unlock():
    data = request.json
    pin = data.get('pin', '')
    cfg = get_parental_config()
    if pin == cfg.get('pin', ''):
        # Write unlock flag and send mpv commands to remove scramble
        with open(PARENTAL_UNLOCKED, 'w') as f:
            f.write('1')
        # Remove scramble via mpv IPC (labeled filter)
        send_mpv_cmd('{ "command": ["vf", "remove", "@scramble"] }')
        send_mpv_cmd('{ "command": ["set_property", "mute", false] }')
        return jsonify({'success': True, 'message': 'Channel unlocked'})
    return jsonify({'success': False, 'message': 'Incorrect PIN'}), 403

###############################################################################
# EAS API
###############################################################################
EAS_CONFIG = f"{BASE}/config/eas_config.json"
EAS_PENDING = f"{STATE}/eas_pending"
EAS_ACTIVE_FLAG = f"{STATE}/eas_active_flag"

def get_eas_config():
    try:
        with open(EAS_CONFIG) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "zip_code": "", "latitude": 0, "longitude": 0,
                "poll_interval_seconds": 45, "alert_types": {}, "exempt_channels": ["WEATHER"]}

def save_eas_config(cfg):
    with open(EAS_CONFIG, 'w') as f:
        json.dump(cfg, f, indent=2)

@app.route('/api/eas/config', methods=['GET'])
def eas_get_config():
    return jsonify(get_eas_config())

@app.route('/api/eas/config', methods=['POST'])
def eas_update_config():
    data = request.json
    cfg = get_eas_config()

    if 'enabled' in data:
        cfg['enabled'] = bool(data['enabled'])
    if 'poll_interval_seconds' in data:
        cfg['poll_interval_seconds'] = int(data['poll_interval_seconds'])
    if 'alert_types' in data:
        for code, enabled in data['alert_types'].items():
            cfg.setdefault('alert_types', {})[code] = bool(enabled)

    save_eas_config(cfg)
    return jsonify({'success': True, 'message': 'EAS config updated'})

@app.route('/api/eas/set-location', methods=['POST'])
def eas_set_location():
    data = request.json
    zip_code = data.get('zip_code', '').strip()
    if not zip_code or len(zip_code) != 5:
        return jsonify({'success': False, 'message': 'Invalid ZIP code'}), 400

    import subprocess
    try:
        result = subprocess.run(
            ['python3', f'{BASE}/bin/eas_geocode.py', zip_code],
            capture_output=True, text=True, timeout=20
        )
        geo = json.loads(result.stdout)
        if 'error' in geo:
            return jsonify({'success': False, 'message': geo['error']}), 400

        cfg = get_eas_config()
        cfg['zip_code'] = zip_code
        cfg['latitude'] = geo['latitude']
        cfg['longitude'] = geo['longitude']
        save_eas_config(cfg)

        return jsonify({
            'success': True,
            'message': f'Location set: {geo["latitude"]:.4f}, {geo["longitude"]:.4f}',
            'latitude': geo['latitude'],
            'longitude': geo['longitude']
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Geocoding failed: {e}'}), 500

@app.route('/api/eas/test', methods=['POST'])
def eas_test_alert():
    import time as _time
    os.makedirs(EAS_PENDING, exist_ok=True)
    test_alert = {
        "id": f"test-{int(_time.time())}",
        "event": "Civil Danger Warning",
        "event_code": "CDW",
        "headline": "THIS IS A TEST of the Emergency Alert System",
        "description": "This is a test of the Emergency Alert System. "
                       "This is only a test. If this had been an actual emergency, "
                       "you would have been instructed where to tune for official "
                       "information and news. This concludes this test.",
        "areas": "Your Area",
        "expires": "",
        "severity": "Extreme",
        "urgency": "Immediate",
        "sender": "RetroTV EAS Test",
        "timestamp": _time.time(),
    }
    path = os.path.join(EAS_PENDING, f"test-{int(_time.time())}.json")
    with open(path, 'w') as f:
        json.dump(test_alert, f, indent=2)
    return jsonify({'success': True, 'message': 'Test alert sent'})

@app.route('/api/eas/status')
def eas_status():
    cfg = get_eas_config()
    active = os.path.exists(EAS_ACTIVE_FLAG)
    pending_count = len([f for f in os.listdir(EAS_PENDING)
                         if f.endswith('.json')]) if os.path.isdir(EAS_PENDING) else 0
    return jsonify({
        'enabled': cfg.get('enabled', False),
        'active': active,
        'pending': pending_count,
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
