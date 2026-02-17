#!/usr/bin/env python3
"""
schedule_web.py — Retro TV Schedule Web Interface

Flask app on port 8081 for viewing/editing the TV schedule.
Runs alongside the existing tv-web-control.py (port 8080) without conflict.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

# Add bin/ to path so we can import schedule_manager
sys.path.insert(0, str(Path(__file__).parent))
import schedule_manager as sm

app = Flask(__name__)

DAYS = sm.DAYS
DAY_LABELS = {
    "monday": "Mon", "tuesday": "Tue", "wednesday": "Wed",
    "thursday": "Thu", "friday": "Fri", "saturday": "Sat", "sunday": "Sun",
}

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retro TV Schedule</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Courier New", monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #16213e 0%, #0f3460 100%);
    padding: 16px 24px;
    border-bottom: 3px solid #e94560;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .header h1 {
    color: #e94560;
    font-size: 1.4em;
    text-shadow: 0 0 10px rgba(233,69,96,0.5);
  }
  .header .now-playing {
    color: #53d769;
    font-size: 0.9em;
  }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px; }

  /* Tabs */
  .tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .tab {
    padding: 8px 16px;
    background: #16213e;
    border: 1px solid #333;
    color: #999;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.9em;
  }
  .tab:hover { color: #e0e0e0; border-color: #e94560; }
  .tab.active {
    background: #0f3460;
    color: #e94560;
    border-color: #e94560;
  }

  /* Schedule grid — vertical mode (time down left, channels across top) */
  .schedule-grid.vertical {
    display: grid;
    grid-template-columns: 80px repeat(var(--channels), 1fr);
    gap: 2px;
    margin-bottom: 20px;
  }
  .vertical .grid-header {
    background: #0f3460;
    padding: 8px;
    text-align: center;
    font-weight: bold;
    font-size: 0.85em;
    color: #e94560;
  }
  .vertical .time-label {
    background: #16213e;
    padding: 6px 8px;
    font-size: 0.8em;
    color: #888;
    text-align: right;
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }
  .vertical .slot {
    background: #16213e;
    padding: 6px 8px;
    font-size: 0.8em;
    min-height: 36px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
    display: flex;
    align-items: center;
  }
  .vertical .slot:hover { border-color: #e94560; background: #1a2744; }
  .vertical .slot.has-show {
    background: #1a2744;
    color: #53d769;
    border-left: 3px solid #53d769;
  }
  .vertical .slot.now-active {
    background: #2a1a44;
    border-left: 3px solid #e94560;
    color: #e94560;
    font-weight: bold;
  }
  .vertical .slot.continuation {
    background: #152030;
    color: rgba(83, 215, 105, 0.45);
    border-left: 3px solid rgba(83, 215, 105, 0.3);
    font-style: italic;
  }
  .vertical .slot.continuation.now-active {
    background: #1f1535;
    color: rgba(233, 69, 96, 0.5);
    border-left: 3px solid rgba(233, 69, 96, 0.5);
  }

  /* Schedule grid — horizontal mode (channels down left, time across top) */
  .schedule-scroll {
    overflow-x: auto;
    margin-bottom: 20px;
    border: 1px solid #222;
  }
  .schedule-grid.horizontal {
    display: grid;
    grid-template-columns: 120px repeat(var(--timeslots), minmax(54px, 1fr));
    gap: 1px;
    min-width: max-content;
  }
  .horizontal .grid-header {
    background: #0f3460;
    padding: 6px 4px;
    text-align: center;
    font-weight: bold;
    font-size: 0.75em;
    color: #e94560;
    white-space: nowrap;
  }
  .grid-corner {
    background: #0a0a1a;
    position: sticky;
    left: 0;
    z-index: 3;
  }
  .channel-label {
    background: #0f3460;
    padding: 8px 10px;
    font-weight: bold;
    font-size: 0.85em;
    color: #e94560;
    white-space: nowrap;
    display: flex;
    align-items: center;
    position: sticky;
    left: 0;
    z-index: 2;
  }
  .horizontal .time-label {
    background: #0f3460;
    padding: 6px 4px;
    font-size: 0.75em;
    color: #e94560;
    text-align: center;
    font-weight: bold;
    white-space: nowrap;
  }
  .horizontal .slot {
    background: #16213e;
    padding: 4px 6px;
    font-size: 0.7em;
    min-height: 40px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    overflow: hidden;
  }
  .horizontal .slot:hover { border-color: #e94560; background: #1a2744; }
  .horizontal .slot.has-show {
    background: #1a2744;
    color: #53d769;
    border-top: 3px solid #53d769;
  }
  .horizontal .slot.now-active {
    background: #2a1a44;
    border-top: 3px solid #e94560;
    color: #e94560;
    font-weight: bold;
  }
  .horizontal .slot.continuation {
    background: #152030;
    color: rgba(83, 215, 105, 0.45);
    border-top: 3px solid rgba(83, 215, 105, 0.3);
    font-style: italic;
  }
  .horizontal .slot.continuation.now-active {
    background: #1f1535;
    color: rgba(233, 69, 96, 0.5);
    border-top: 3px solid rgba(233, 69, 96, 0.5);
  }

  /* Toggle switch */
  .layout-toggle {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    font-size: 0.85em;
  }
  .layout-toggle span { color: #888; }
  .layout-toggle span.active-label { color: #e94560; }
  .toggle-track {
    width: 44px;
    height: 22px;
    background: #16213e;
    border: 1px solid #555;
    border-radius: 11px;
    cursor: pointer;
    position: relative;
    transition: background 0.2s;
  }
  .toggle-track.on { background: #0f3460; border-color: #e94560; }
  .toggle-knob {
    width: 18px;
    height: 18px;
    background: #e94560;
    border-radius: 50%;
    position: absolute;
    top: 1px;
    left: 1px;
    transition: left 0.2s;
  }
  .toggle-track.on .toggle-knob { left: 23px; }

  /* Modal */
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: #16213e;
    border: 2px solid #e94560;
    padding: 24px;
    min-width: 320px;
    max-width: 500px;
  }
  .modal h2 { color: #e94560; margin-bottom: 16px; font-size: 1.1em; }
  .modal label { display: block; color: #888; margin: 8px 0 4px; font-size: 0.85em; }
  .modal select, .modal input {
    width: 100%;
    padding: 8px;
    background: #1a1a2e;
    color: #e0e0e0;
    border: 1px solid #333;
    font-family: inherit;
    font-size: 0.9em;
  }
  .modal-buttons {
    display: flex;
    gap: 8px;
    margin-top: 16px;
    justify-content: flex-end;
  }
  .btn {
    padding: 8px 16px;
    font-family: inherit;
    font-size: 0.85em;
    cursor: pointer;
    border: 1px solid #333;
  }
  .btn-primary { background: #e94560; color: #fff; border-color: #e94560; }
  .btn-danger { background: #8b0000; color: #fff; border-color: #8b0000; }
  .btn-secondary { background: #333; color: #e0e0e0; }
  .btn:hover { opacity: 0.85; }

  /* Day checkboxes in modal */
  .day-checks {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 4px;
  }
  .day-check {
    display: flex;
    align-items: center;
    gap: 4px;
    background: #1a1a2e;
    border: 1px solid #333;
    padding: 4px 8px;
    cursor: pointer;
    font-size: 0.8em;
    color: #888;
    user-select: none;
  }
  .day-check.checked {
    border-color: #e94560;
    color: #e94560;
    background: #1a1a2e;
  }
  .day-check input { display: none; }

  /* Now playing panel — floating sidebar */
  .now-panel {
    position: fixed;
    top: 70px;
    left: 10px;
    width: 200px;
    background: #16213e;
    border: 1px solid #333;
    padding: 10px;
    z-index: 50;
    max-height: calc(100vh - 100px);
    overflow-y: auto;
    font-size: 0.75em;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
  }
  .now-panel h2 { color: #e94560; font-size: 0.9em; margin-bottom: 8px; }
  .now-item {
    display: flex;
    flex-direction: column;
    padding: 4px 0;
    border-bottom: 1px solid #222;
  }
  .now-ch { color: #e94560; font-weight: bold; }
  .now-show { color: #53d769; }
  .now-time { color: #888; font-size: 0.85em; }

  /* Offset main content so it doesn't hide behind the floating panel */
  .container { margin-left: 220px; }

  /* Status bar */
  .status-bar {
    background: #0a0a1a;
    padding: 8px 24px;
    font-size: 0.75em;
    color: #555;
    position: fixed;
    bottom: 0;
    width: 100%;
    display: flex;
    justify-content: space-between;
  }
</style>
</head>
<body>

<div class="header">
  <h1>RETRO TV SCHEDULE</h1>
  <div class="now-playing" id="clock"></div>
</div>

<div class="now-panel" id="nowPanel">
  <h2>NOW PLAYING</h2>
  <div id="nowList">Loading...</div>
</div>

<div class="container">
  <div class="tabs" id="dayTabs"></div>

  <div class="layout-toggle">
    <span id="lbl-vert">Vertical</span>
    <div class="toggle-track" id="layoutToggle" onclick="toggleLayout()">
      <div class="toggle-knob"></div>
    </div>
    <span id="lbl-horiz">Horizontal</span>
  </div>

  <div id="scheduleArea"></div>

  <div style="margin-top: 16px; display: flex; gap: 8px;">
    <button class="btn btn-secondary" onclick="resetSchedule()">Reset to Defaults</button>
  </div>
</div>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <h2 id="modalTitle">Edit Block</h2>
    <label>Show</label>
    <select id="modalShow"></select>
    <label>Start Time</label>
    <input type="time" id="modalStart">
    <label>End Time</label>
    <input type="time" id="modalEnd">
    <label>Apply to Days</label>
    <div class="day-checks" id="modalDays"></div>
    <div class="modal-buttons">
      <button class="btn btn-danger" id="modalDelete" onclick="deleteBlock()">Delete</button>
      <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="saveBlock()">Save</button>
    </div>
  </div>
</div>

<div class="status-bar">
  <span>Schedule Manager v1.0</span>
  <span>Port 8081 | Alongside existing TV system</span>
</div>

<script>
const DAYS = ['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const DAY_LABELS = {monday:'Mon',tuesday:'Tue',wednesday:'Wed',thursday:'Thu',friday:'Fri',saturday:'Sat',sunday:'Sun'};
const HOURS = [];
for (let h = 0; h < 24; h++) {
  HOURS.push(String(h).padStart(2,'0') + ':00');
  HOURS.push(String(h).padStart(2,'0') + ':30');
}

let config = {};
let state = {};
let currentDay = DAYS[new Date().getDay() === 0 ? 6 : new Date().getDay() - 1];
let editCtx = {};
let layoutMode = localStorage.getItem('scheduleLayout') || 'vertical';

function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString('en-US', {hour12: true});
}
setInterval(updateClock, 1000);
updateClock();

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

async function loadAll() {
  config = await fetchJSON('/api/config');
  state = await fetchJSON('/api/state');
  buildTabs();
  renderSchedule();
  refreshNow();
}

function buildTabs() {
  const el = document.getElementById('dayTabs');
  el.innerHTML = '';
  DAYS.forEach(d => {
    const btn = document.createElement('button');
    btn.className = 'tab' + (d === currentDay ? ' active' : '');
    btn.textContent = DAY_LABELS[d];
    btn.onclick = () => { currentDay = d; buildTabs(); renderSchedule(); };
    el.appendChild(btn);
  });
}

function getScheduleForDay(day) {
  const sched = state.schedule || {};
  const def = config.default_schedule || {};
  return sched[day] || def[day] || {};
}

function updateToggleUI() {
  const track = document.getElementById('layoutToggle');
  const lblV = document.getElementById('lbl-vert');
  const lblH = document.getElementById('lbl-horiz');
  if (layoutMode === 'horizontal') {
    track.classList.add('on');
    lblV.classList.remove('active-label');
    lblH.classList.add('active-label');
  } else {
    track.classList.remove('on');
    lblV.classList.add('active-label');
    lblH.classList.remove('active-label');
  }
}

function toggleLayout() {
  layoutMode = (layoutMode === 'vertical') ? 'horizontal' : 'vertical';
  localStorage.setItem('scheduleLayout', layoutMode);
  updateToggleUI();
  renderSchedule();
}

function renderSchedule() {
  updateToggleUI();
  const channels = (config.channels || []).sort((a,b) => a.number - b.number);
  const shows = {};
  (config.shows || []).forEach(s => shows[s.id] = s);
  const dayData = getScheduleForDay(currentDay);

  const now = new Date();
  const nowDay = DAYS[now.getDay() === 0 ? 6 : now.getDay() - 1];
  const nowTime = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');

  const area = document.getElementById('scheduleArea');

  if (layoutMode === 'horizontal') {
    renderHorizontal(area, channels, shows, dayData, nowDay, nowTime);
  } else {
    renderVertical(area, channels, shows, dayData, nowDay, nowTime);
  }
}

// Find which block (if any) covers a given time slot
function findCoveringBlock(blocks, time) {
  for (const b of blocks) {
    const start = b.start || '00:00';
    const end = (!b.end || b.end === '00:00') ? '24:00' : b.end;
    if (start <= time && time < end) {
      return {block: b, isStart: b.start === time};
    }
  }
  return null;
}

function renderVertical(area, channels, shows, dayData, nowDay, nowTime) {
  area.style.setProperty('--channels', channels.length);

  let html = '<div class="schedule-grid vertical">';
  html += '<div class="grid-header">Time</div>';
  channels.forEach(c => { html += `<div class="grid-header">CH${c.number} ${c.name}</div>`; });

  HOURS.forEach(time => {
    html += `<div class="time-label">${time}</div>`;
    channels.forEach(c => {
      const station = c.station || c.name;
      const blocks = dayData[station] || [];
      const match = findCoveringBlock(blocks, time);
      let cls = 'slot';
      let label = '';
      if (match) {
        const show = shows[match.block.show_id] || {};
        label = show.title || match.block.show_id;
        cls += match.isStart ? ' has-show' : ' has-show continuation';
        const end = (!match.block.end || match.block.end === '00:00') ? '24:00' : match.block.end;
        if (currentDay === nowDay && match.block.start <= nowTime && end > nowTime) {
          cls += ' now-active';
        }
      }
      html += `<div class="${cls}" onclick="openModal('${currentDay}','${station}','${time}')">${label}</div>`;
    });
  });

  html += '</div>';
  area.innerHTML = html;
}

function renderHorizontal(area, channels, shows, dayData, nowDay, nowTime) {
  area.style.setProperty('--timeslots', HOURS.length);

  let html = '<div class="schedule-scroll"><div class="schedule-grid horizontal">';
  html += '<div class="grid-header grid-corner"></div>';
  HOURS.forEach(time => {
    html += `<div class="time-label">${time}</div>`;
  });

  channels.forEach(c => {
    const station = c.station || c.name;
    html += `<div class="channel-label">CH${c.number} ${c.name}</div>`;
    const blocks = dayData[station] || [];
    HOURS.forEach(time => {
      const match = findCoveringBlock(blocks, time);
      let cls = 'slot';
      let label = '';
      if (match) {
        const show = shows[match.block.show_id] || {};
        label = show.title || match.block.show_id;
        cls += match.isStart ? ' has-show' : ' has-show continuation';
        const end = (!match.block.end || match.block.end === '00:00') ? '24:00' : match.block.end;
        if (currentDay === nowDay && match.block.start <= nowTime && end > nowTime) {
          cls += ' now-active';
        }
      }
      html += `<div class="${cls}" onclick="openModal('${currentDay}','${station}','${time}')">${label}</div>`;
    });
  });

  html += '</div></div>';
  area.innerHTML = html;
}

async function refreshNow() {
  try {
    const data = await fetchJSON('/api/now');
    const el = document.getElementById('nowList');
    let html = '';
    Object.keys(data).sort((a,b) => parseInt(a) - parseInt(b)).forEach(ch => {
      const item = data[ch];
      html += `<div class="now-item">
        <span class="now-ch">CH${ch} ${item.channel}</span>
        <span class="now-show">${item.title}</span>
        <span class="now-time">${item.start || ''} - ${item.end || ''}</span>
      </div>`;
    });
    el.innerHTML = html || '<div style="color:#555">No channels configured</div>';
  } catch(e) {
    console.error(e);
  }
}
setInterval(refreshNow, 30000);

function openModal(day, station, time) {
  editCtx = {day, station, time};
  const dayData = getScheduleForDay(day);
  const blocks = dayData[station] || [];
  const existing = blocks.find(b => b.start === time);

  document.getElementById('modalTitle').textContent = `${DAY_LABELS[day]} ${station} @ ${time}`;
  document.getElementById('modalStart').value = time;
  document.getElementById('modalEnd').value = existing ? (existing.end || '') : '';
  document.getElementById('modalDelete').style.display = existing ? '' : 'none';

  const sel = document.getElementById('modalShow');
  sel.innerHTML = '<option value="">-- No Show --</option>';
  (config.shows || []).forEach(s => {
    // Only show shows belonging to this station, or universal shows (empty station = SIGNOFF/SIGNON)
    if (s.station && s.station !== station) return;
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = s.title || s.id;
    if (existing && existing.show_id === s.id) opt.selected = true;
    sel.appendChild(opt);
  });

  // Build day checkboxes — current day pre-checked
  const daysEl = document.getElementById('modalDays');
  daysEl.innerHTML = '';
  DAYS.forEach(d => {
    const lbl = document.createElement('label');
    lbl.className = 'day-check' + (d === day ? ' checked' : '');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = d;
    cb.checked = (d === day);
    cb.onchange = () => lbl.classList.toggle('checked', cb.checked);
    lbl.appendChild(cb);
    lbl.appendChild(document.createTextNode(DAY_LABELS[d]));
    daysEl.appendChild(lbl);
  });

  document.getElementById('modalOverlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('active');
}

async function saveBlock() {
  const show_id = document.getElementById('modalShow').value;
  if (!show_id) { closeModal(); return; }
  const start = document.getElementById('modalStart').value;
  let end = document.getElementById('modalEnd').value;
  // Default to 30-min block if no end time provided
  if (!end) {
    const [h, m] = start.split(':').map(Number);
    const endMin = m + 30;
    const endH = h + Math.floor(endMin / 60);
    end = String(endH % 24).padStart(2,'0') + ':' + String(endMin % 60).padStart(2,'0');
  }
  // Save to all checked days (handle midnight wrap-around)
  const checkedDays = [...document.querySelectorAll('#modalDays input:checked')].map(cb => cb.value);
  if (checkedDays.length === 0) { closeModal(); return; }
  const wrapsmidnight = (end < start);  // e.g. start=23:30, end=02:30
  for (const day of checkedDays) {
    if (wrapsmidnight) {
      // Split: start→24:00 on this day, 00:00→end on next day
      await fetchJSON('/api/schedule/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          day: day, station: editCtx.station,
          start: start, end: '00:00', show_id: show_id,
        })
      });
      const nextDay = DAYS[(DAYS.indexOf(day) + 1) % 7];
      await fetchJSON('/api/schedule/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          day: nextDay, station: editCtx.station,
          start: '00:00', end: end, show_id: show_id,
        })
      });
    } else {
      await fetchJSON('/api/schedule/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          day: day, station: editCtx.station,
          start: start, end: end, show_id: show_id,
        })
      });
    }
  }
  state = await fetchJSON('/api/state');
  renderSchedule();
  refreshNow();
  closeModal();
}

async function deleteBlock() {
  const checkedDays = [...document.querySelectorAll('#modalDays input:checked')].map(cb => cb.value);
  const daysToDelete = checkedDays.length > 0 ? checkedDays : [editCtx.day];
  for (const day of daysToDelete) {
    await fetchJSON('/api/schedule/remove', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        day: day, station: editCtx.station, start: editCtx.time,
      })
    });
  }
  state = await fetchJSON('/api/state');
  renderSchedule();
  refreshNow();
  closeModal();
}

async function resetSchedule() {
  if (!confirm('Reset schedule to config defaults?')) return;
  await fetchJSON('/api/schedule/reset', {method: 'POST'});
  state = await fetchJSON('/api/state');
  renderSchedule();
  refreshNow();
}

loadAll();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/config")
def api_config():
    config = sm.load_config()
    # Inject channel list from channels.tsv, excluding MTV year channels
    # (MTV year channels play random videos and don't use the scheduler)
    import re
    channels = sm.get_channels()
    config["channels"] = sorted(
        [c for c in channels.values() if not re.match(r'^MTV\d{4}$', c.get('station', ''))],
        key=lambda c: c["number"]
    )
    return jsonify(config)


@app.route("/api/state")
def api_state():
    return jsonify(sm.load_state())


@app.route("/api/now")
def api_now():
    return jsonify(sm.what_is_on())


@app.route("/api/schedule/set", methods=["POST"])
def api_set():
    data = request.get_json()
    sm.set_block(
        data["day"], data["station"], data["start"],
        data.get("end") or "", data["show_id"],
    )
    return jsonify({"ok": True})


@app.route("/api/schedule/remove", methods=["POST"])
def api_remove():
    data = request.get_json()
    sm.remove_block(data["day"], data["station"], data["start"])
    return jsonify({"ok": True})


@app.route("/api/schedule/reset", methods=["POST"])
def api_reset():
    sm.reset_schedule()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)
