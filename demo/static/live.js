(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const setText = (node, value) => { node.textContent = value; };
  const LiveKit = window.LivekitClient;
  const Views = window.OTRViews;
  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const MIC_OFF_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28m-4.02.17c0-.06.02-.11.02-.17V5a3 3 0 0 0-6 0v.18l5.98 5.99M4.27 3 3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3Z"/></svg>';
  const MIC_ON_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3m5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z"/></svg>';

  let room = null, me = null, eventSource = null;
  let participants = {};
  let lines = new Map();
  let finalized = false, readyForFinal = false, finalizedCount = null, contributorCount = null;
  let redactionCounts = null;
  // Text-free aggregates and placeholders from the server; see demo/live_session.py insights_for().
  let insights = { approved: 0, kept_out: {}, total: 0, removed: 0, timeline: [], now: 0, hold_seconds: null };
  const chips = new Map();   // segment id -> {id, category, seq, trail}; never any text
  let panelView = null, panelLastFocus = null, captionsOn = false, explainSel = null, explainItem = null;
  let capFollow = true, newCount = 0, pendingSeen = 0;
  // Transcript bookkeeping. Ids and numbers only; the text of a kept-out line never reaches this page.
  let insightsAt = Date.now(), waitingLines = 0, primed = false, announceTimer = null, announceNew = 0, announceOut = 0;
  const expandedRows = new Set();   // kept-out row ids opened in place
  const rowSeq = new Map();         // id -> seq of the approved line a removal replaced, so the placeholder keeps its place
  const firstSeen = new Map();      // "l:id" / "k:id" -> seconds, when this browser first saw the row
  const serverT = new Map();        // same keys -> seconds from the server's detail payload (preferred)
  const knownRows = new Set();
  let myNotesOn = false, sensitivePaused = false, sensitiveSeen = false;
  let speaking = new Set(), muted = new Map();
  const connectedPeople = new Set();
  const videoTracks = new Map(), videoMuted = new Set(), videoEls = new Map();
  let toastTimer = null, meRefreshTimer = null, clockTimer = null;
  let deliveryEmail = "", emailOptedIn = false, emailChoiceDirty = false;
  let endDialogLastFocus = null, endEmailBody = "", endNeedsCopy = false, endCopied = false;
  let roomId = null, role = null, joinAccess = null, lobbyTimer = null, waitingTimer = null, roomTimer = null;
  let admissionCheckInProgress = false, admissionFailures = 0, joinInProgress = false;
  const ENTRY_SCREENS = ["home-screen", "host-setup", "guest-setup", "share-screen", "waiting-screen", "join"];
  function showEntry(id) {
    for (const screen of ENTRY_SCREENS) $(screen).classList.toggle("hidden", screen !== id);
    placeDeviceCheck(id);
  }
  function meetingIdFromLink(value) {
    const raw = value.trim();
    if (!raw) throw new Error("Enter a meeting link or code");
    if (!raw.includes("/") && !raw.includes(":")) return raw;
    let url;
    try { url = new URL(raw); } catch (_) { throw new Error("Enter a valid meeting link or code"); }
    if (url.origin !== location.origin) throw new Error("This link belongs to a different meeting host");
    const match = url.pathname.match(/^\/m\/([^/]+)\/?$/);
    if (!match) throw new Error("Enter a valid meeting link");
    return decodeURIComponent(match[1]);
  }
  function renderLobby(pending) {
    const list = $("lobby-list");
    list.replaceChildren();
    $("lobby-count").textContent = String(pending.length);
    $("lobby-empty").classList.toggle("hidden", pending.length > 0);
    const badge = $("people-badge");
    badge.classList.toggle("hidden", pending.length === 0);
    setText(badge, String(pending.length));
    if (pending.length > pendingSeen && panelView !== "people") showPanel("people");
    pendingSeen = pending.length;
    for (const request of pending) {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${request.name} · ${request.email}`;
      const admit = document.createElement("button");
      admit.type = "button";
      admit.textContent = "Admit";
      admit.onclick = async () => {
        admit.disabled = true;
        try { await post(`/api/meetings/${encodeURIComponent(roomId)}/admit`, {request_id: request.request_id}); await pollLobby(); }
        catch (error) { showToast(escapeHtml(error.message), "err"); admit.disabled = false; }
      };
      const deny = document.createElement("button");
      deny.type = "button";
      deny.textContent = "Deny";
      deny.onclick = async () => {
        deny.disabled = true;
        try { await post(`/api/meetings/${encodeURIComponent(roomId)}/deny`, {request_id: request.request_id}); await pollLobby(); }
        catch (error) { showToast(escapeHtml(error.message), "err"); deny.disabled = false; }
      };
      item.append(label, admit, deny);
      list.append(item);
    }
  }
  async function pollLobby() {
    if (!roomId || role !== "host") return;
    try { renderLobby((await api(`/api/meetings/${encodeURIComponent(roomId)}/status`)).pending || []); }
    catch (_) { /* A temporary network failure should not end the call. */ }
  }
  function startLobby() {
    if (role !== "host") return;
    $("host-lobby").classList.remove("hidden");
    $("info-link").value = `${location.origin}/m/${encodeURIComponent(roomId)}`;
    pollLobby();
    clearInterval(lobbyTimer);
    lobbyTimer = setInterval(pollLobby, 1500);
  }
  function startRoomStatus() {
    if (role !== "guest" || !roomId) return;
    clearInterval(roomTimer);
    roomTimer = setInterval(async () => {
      try { await api(`/api/meetings/${encodeURIComponent(roomId)}/status`); }
      catch (error) {
        if (error.status !== 401 && error.status !== 404) return;
        clearInterval(roomTimer);
        if (eventSource) eventSource.close();
        if (room) await room.disconnect();
        location.href = "/?ended=1";
      }
    }, 3000);
  }
  function setWaitingState(state, error = "") {
    const connecting = state === "connecting", failed = state === "failed" || state === "status-error";
    setText($("waiting-title"), connecting ? "Connecting to the meeting" : failed ? "Could not connect" : "Waiting for the host");
    setText($("waiting-message"), connecting
      ? "The host admitted you. Connecting your call…"
      : state === "failed" ? "The host admitted you, but the call did not connect. Try again."
        : state === "status-error" ? "We lost contact with the meeting. Try connecting again."
        : "Your request has been sent. Stay on this page and you’ll join when the host lets you in.");
    setText($("waiting-error"), error);
    $("waiting-retry-button").classList.toggle("hidden", !failed);
    $("waiting-retry-button").disabled = connecting;
    setText($("waiting-cancel-button"), state === "waiting" ? "Cancel request" : "Back to home");
  }
  async function connectAdmittedGuest(status) {
    if (joinInProgress) return;
    clearInterval(waitingTimer);
    waitingTimer = null;
    joinAccess = status;
    showEntry("waiting-screen");
    setWaitingState("connecting");
    try {
      const connected = await join(status, status);
      if (!connected) setWaitingState("failed", "If it keeps failing, ask the host to check the meeting connection.");
    } catch (_) {
      setWaitingState("failed", "If it keeps failing, ask the host to check the meeting connection.");
    }
  }
  async function pollAdmission() {
    if (!roomId || role !== "guest" || admissionCheckInProgress || joinInProgress) return;
    admissionCheckInProgress = true;
    try {
      const status = await api(`/api/meetings/${encodeURIComponent(roomId)}/status`);
      admissionFailures = 0;
      if (status.status === "denied") {
        clearInterval(waitingTimer);
        waitingTimer = null;
        showEntry("guest-setup");
        setText($("guest-error"), "The host did not admit this request.");
      } else if (status.status === "admitted") {
        await connectAdmittedGuest(status);
      } else if (status.status === "waiting" && !waitingTimer) {
        joinAccess = null;
        setWaitingState("waiting");
        waitingTimer = setInterval(pollAdmission, 1500);
      }
    } catch (error) {
      if (error.status === 401 || error.status === 404) {
        clearInterval(waitingTimer);
        waitingTimer = null;
        joinAccess = null;
        showEntry("guest-setup");
        setText($("guest-error"), error.status === 404
          ? "This meeting is no longer available. Ask the host for a new link."
          : "Your join request expired. Ask to join again.");
      } else if (++admissionFailures >= 3 || !waitingTimer) {
        clearInterval(waitingTimer);
        waitingTimer = null;
        setWaitingState("status-error", "Check your connection and try again.");
      }
    } finally { admissionCheckInProgress = false; }
  }
  const tileEls = {};

  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    let body = null;
    try { body = await response.json(); } catch (_) { body = {}; }
    if (!response.ok) {
      const error = new Error(body.detail || body.message || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return body;
  }
  const post = (path, body) => api(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, ch => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
  }
  function notesOn(p) { return p && (p.notes === true || p.recording === true); }
  function initials(name) {
    const parts = String(name || "?").trim().split(/\s+/).filter(Boolean);
    return ((parts[0] || "?")[0] + (parts[1] ? parts[1][0] : "")).toUpperCase();
  }
  function isMyLine(line) {
    if (!me) return true;
    const owner = line.speaker ?? line.identity ?? "";
    return !owner || owner === me;
  }
  function indexLines(arr) {
    const map = new Map();
    for (const line of arr || []) if (line && line.id != null) map.set(line.id, line);
    return map;
  }

  function announce(message) { setText($("note-state-live"), message); }
  function setConnection(label, cls) {
    setText($("connection"), label);
    $("connection").className = "chip" + (cls ? " " + cls : "");
  }
  function showToast(html, kind) {
    const toast = $("toast");
    toast.classList.remove("warn", "err");
    if (kind) toast.classList.add(kind);
    $("toast-text").innerHTML = html;
    toast.classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("visible"), 8000);
  }

  function updateTileFlags() {
    for (const [identity, tile] of Object.entries(tileEls)) {
      const connected = identity === me || connectedPeople.has(identity);
      tile.classList.toggle("not-connected", !connected);
      tile.classList.toggle("speaking", connected && speaking.has(identity));
      const isMuted = identity === me
        ? (room ? !room.localParticipant.isMicrophoneEnabled : false)
        : muted.get(identity) === true;
      const state = tile.querySelector(".mic-state");
      state.classList.toggle("muted", isMuted);
      state.setAttribute("aria-label", isMuted ? "Microphone off" : "Microphone on");
      const note = tile.querySelector(".tile-mic");
      if (note) setText(note, connected ? "" : "Not connected yet");
    }
  }

  function updateVideoTile(identity) {
    const tile = tileEls[identity];
    if (!tile) return;
    const track = videoMuted.has(identity) ? null : videoTracks.get(identity);
    const avatar = tile.querySelector(".avatar");
    let video = videoEls.get(identity);
    if (video && video._livekitTrack !== track) {
      video._livekitTrack.detach(video);
      video.remove();
      videoEls.delete(identity);
      video = null;
    }
    if (track && !video) {
      video = document.createElement("video");
      video.className = "tile-video";
      video.autoplay = true;
      video.playsInline = true;
      video.setAttribute("playsinline", "");
      video.muted = identity === me;   // a video track carries no sound; remote voices play from their audio element
      video._livekitTrack = track;
      track.attach(video);
      videoEls.set(identity, video);
    }
    if (video && video.parentNode !== avatar) {
      avatar.prepend(video);
      if (video.play) { try { const played = video.play(); if (played && played.catch) played.catch(() => {}); } catch (_) { } }
    }
    tile.classList.toggle("has-video", !!track);
  }

  function setVideoTrack(identity, track) {
    if (track) videoTracks.set(identity, track);
    else videoTracks.delete(identity);
    updateVideoTile(identity);
  }

  function renderCameraButton() {
    const button = $("camera-button");
    if (!button) return;
    const enabled = !!(room && room.localParticipant.isCameraEnabled);
    button.setAttribute("aria-pressed", String(enabled));
    button.classList.toggle("camera-off", !enabled);
    const label = enabled ? "Turn off camera" : "Turn on camera";
    button.setAttribute("aria-label", label);
    button.title = label;
    setText($("camera-label"), label);
  }

  function renderTiles() {
    const grid = $("tile-grid");
    grid.replaceChildren();
    for (const key of Object.keys(tileEls)) delete tileEls[key];
    const members = Object.entries(participants);
    members.sort((a, b) => (a[0] === me ? -1 : b[0] === me ? 1 : 0));
    if (!members.length) {
      grid.append(element("p", "grid-empty", "Waiting for people to join..."));
      return;
    }
    for (const [identity, p] of members) {
      const on = notesOn(p);
      const tile = element("div", "tile" + (identity === me ? " self" : ""));
      const avatar = element("div", "avatar", initials(p.name || identity));
      const mic = element("span", "mic-state");
      mic.setAttribute("role", "img");
      const micOn = element("span", "m-on");
      micOn.innerHTML = MIC_ON_SVG;
      const micOff = element("span", "m-off");
      micOff.innerHTML = MIC_OFF_SVG;
      mic.append(micOn, micOff);
      const label = element("div", "tile-label");
      label.append(element("span", "tile-name", `${p.name || identity}${identity === me ? " (you)" : ""}`));
      const notes = element("span", "tile-notes" + (on ? " on" : ""), on ? "Notes on" : "Notes off");
      notes.prepend(element("span", "dot"));
      label.append(notes);
      label.append(element("span", "tile-mic"));
      tile.append(avatar, mic, label);
      if (identity === me) {
        const level = element("canvas", "tile-level");
        level.width = 36; level.height = 16;
        level.setAttribute("role", "img");
        level.setAttribute("aria-label", "Your microphone level");
        tile.append(level);
      }
      grid.append(tile);
      tileEls[identity] = tile;
    }
    updateTileFlags();
    for (const [identity, video] of [...videoEls]) {
      if (tileEls[identity]) continue;
      video._livekitTrack.detach(video);
      video.remove();
      videoEls.delete(identity);
    }
    for (const identity of Object.keys(tileEls)) updateVideoTile(identity);
  }

  function renderLines() {
    renderCaptions();
  }

  // ------------------------------------------------------------ Realtime transcript
  // One chronological list ordered by server seq: your approved lines, plus text-free placeholders for what was
  // kept out ("Kept out, Pay and HR") or removed after approval. A placeholder opens in place to say why.
  function setInsights(next) { insights = next; insightsAt = Date.now(); }
  function elapsed() { return Math.max(0, (Number(insights.now) || 0) + (Date.now() - insightsAt) / 1000); }
  function rowTime(kind, id) {
    const key = kind + ":" + id;
    if (serverT.has(key)) return serverT.get(key);
    if (!firstSeen.has(key)) firstSeen.set(key, elapsed());
    return firstSeen.get(key);
  }
  function clock(t) {
    const total = Math.max(0, Math.round(t)), pad = n => (n < 10 ? "0" : "") + n;
    return pad(Math.floor(total / 60)) + ":" + pad(total % 60);
  }
  function isRemovalChip(chip) { return Views.actionOf(chip.trail).key === "removed_after_approval"; }
  function captionItems() {
    const items = [];
    let order = 0;
    for (const line of lines.values()) {
      const gone = chips.get(line.id);
      if (!line.removed && isMyLine(line) && !(gone && isRemovalChip(gone))) items.push({ type: "line", seq: line.seq || 0, order: order++, line });
    }
    for (const chip of chips.values()) {
      const seq = rowSeq.has(chip.id) ? rowSeq.get(chip.id) : (chip.seq || 0);
      items.push({ type: "chip", seq, order: order++, chip });
    }
    items.sort((a, b) => (a.seq - b.seq) || (a.order - b.order));
    return items;
  }
  const CHEVRON_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>';
  function lineRow(line) {
    const row = element("div", "cap line");
    row.dataset.id = String(line.id);
    const meta = element("div", "cap-meta");
    meta.append(element("span", "who", line.name || "You"), element("span", "time", clock(rowTime("l", line.id))));
    const remove = element("button", "remove", "Remove");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove line: ${line.text}`);
    remove.disabled = finalized;
    remove.onclick = () => removeLine(line.id, remove);
    meta.append(remove);
    row.append(meta, element("p", "words", line.text));
    return row;
  }
  function keptRow(chip) {
    const removal = isRemovalChip(chip), open = expandedRows.has(chip.id);
    const row = element("div", "cap out" + (removal ? " removed" : "") + (open ? " open" : ""));
    row.dataset.id = String(chip.id);
    const label = removal ? "Removed after approval" : `Kept out, ${Views.shortLabel(chip.category)}`;
    const time = clock(rowTime("k", chip.id));
    const head = element("button", "out-head");
    head.type = "button";
    head.setAttribute("data-category", chip.category);
    head.setAttribute("aria-expanded", String(open));
    head.setAttribute("aria-controls", "why-" + chip.id);
    head.setAttribute("aria-label", `${label}, ${time}. ${open ? "Hide" : "Show"} why.`);
    const caret = element("span", "caret");
    caret.innerHTML = CHEVRON_SVG;
    head.append(element("span", "out-label", label), element("span", "time", time), caret);
    head.onclick = () => {
      if (expandedRows.has(chip.id)) expandedRows.delete(chip.id); else expandedRows.add(chip.id);
      renderCaptions();
      const box = $("captions");
      const again = [...box.children].find(r => r.dataset && r.dataset.id === String(chip.id));
      const button = again && again.querySelector(".out-head");
      if (button) button.focus();
    };
    row.append(head);
    if (open) {
      const detail = element("div", "out-detail");
      detail.id = "why-" + chip.id;
      for (const [name, value] of Views.explainFacts(chip, insights.hold_seconds)) {
        const fact = element("div", "fact");
        fact.append(element("b", null, name), element("span", null, value));
        detail.append(fact);
      }
      const more = element("button", "secondary out-more", "See the full explanation");
      more.type = "button";
      more.onclick = () => openInsights("how=" + encodeURIComponent(chip.category));
      detail.append(more);
      row.append(detail);
    }
    return row;
  }
  let shownCaptions = 0;
  function noteNewRows(items) {
    let fresh = 0, out = 0;
    for (const item of items) {
      const key = item.type === "line" ? "l:" + item.line.id : "k:" + item.chip.id;
      if (knownRows.has(key)) continue;
      knownRows.add(key);
      if (primed) { fresh++; if (item.type === "chip") out++; }
    }
    if (!fresh) return;
    announceNew += fresh; announceOut += out;
    if (announceTimer) return;
    // One polite message per burst, counts only, never the words of a kept-out line.
    announceTimer = setTimeout(() => {
      announceTimer = null;
      announce(`${announceNew} new ${announceNew === 1 ? "row" : "rows"} in the transcript${announceOut ? `, ${announceOut} kept out` : ""}.`);
      announceNew = announceOut = 0;
    }, 2000);
  }
  function renderTranscriptStatus() {
    const paused = sensitivePaused && !finalized;
    $("notes-off-row").classList.toggle("hidden", myNotesOn);
    let message = "Your notes are off, nothing from you is transcribed.", action = "Turn on notes";
    if (finalized) { message = "Your notes are finished, nothing more from you is transcribed."; action = ""; }
    else if (paused) { message = "Your notes are paused, nothing from you is transcribed."; action = "Resume notes"; }
    setIfChanged($("notes-off-text"), message);
    $("notes-off-toggle").classList.toggle("hidden", !action);
    if (action) setIfChanged($("notes-off-toggle"), action);
    const waiting = myNotesOn ? waitingLines : 0;
    $("cap-status").classList.toggle("hidden", waiting <= 0);
    if (waiting > 0) setIfChanged($("cap-status"), `Listening, ${waiting} ${waiting === 1 ? "line" : "lines"} waiting`);
  }
  function renderCaptions() {
    const box = $("captions");
    const items = captionItems();
    const keep = box.scrollTop;
    box.replaceChildren();
    if (!items.length) {
      box.append(element("p", "cap-empty", myNotesOn
        ? "Listening. Lines you approve appear here after a short safety hold."
        : "Nothing is transcribed while your notes are off."));
    }
    for (const item of items) box.append(item.type === "line" ? lineRow(item.line) : keptRow(item.chip));
    noteNewRows(items);
    if (items.length > shownCaptions && !capFollow) newCount += items.length - shownCaptions;
    shownCaptions = items.length;
    if (capFollow) box.scrollTop = box.scrollHeight; else box.scrollTop = keep;
    renderStageCaptions(items);
    renderTranscriptStatus();
    renderLive();
  }
  function renderStageCaptions(items) {
    const stage = $("stage-captions");
    stage.classList.toggle("hidden", !captionsOn);
    if (!captionsOn) return;
    stage.replaceChildren();
    for (const item of items.filter(entry => entry.type === "line").slice(-2)) {
      const row = element("p", "stage-cap");
      row.append(element("span", "who", item.line.name || "You"), element("span", "words", item.line.text));
      stage.append(row);
    }
    if (!stage.children.length) stage.append(element("p", "stage-cap", "Captions show the lines you approve."));
  }
  function renderLive() {
    const button = $("live-button");
    const behind = !capFollow;
    button.classList.toggle("hidden", !behind);
    $("live-count").classList.toggle("hidden", !behind || newCount === 0);
    setText($("live-count"), newCount > 99 ? "99+ new" : `${newCount} new`);
    button.setAttribute("aria-label", behind ? `Jump to latest, ${newCount} new` : "Jump to latest");
  }
  function goLive() {
    if (panelView !== "agent") showPanel("agent");
    capFollow = true; newCount = 0;
    const box = $("captions");
    box.scrollTop = box.scrollHeight;
    renderLive();
  }

  // ------------------------------------------------------------ the side panel (one at a time)
  const PANEL_TITLES = { agent: "Off The Record", insights: "What was kept out", explain: "How it decides", people: "People", info: "Meeting details" };
  const PANEL_VIEWS = { agent: "panel-agent", insights: "view-insights", explain: "view-explain", people: "panel-people", info: "panel-info" };
  const PANEL_ROOT = { agent: "agent", insights: "agent", explain: "agent", people: "people", info: "info" };
  const PANEL_BUTTONS = { agent: "agent-button", people: "people-button", info: "info-button" };
  // The detail page opens as a separate small window, so the meeting and the live panel stay where they are.
  // The room path lets the server pick this meeting's cookie. A blocked pop-up falls back to a normal tab.
  function insightsUrl(fragment) {
    return (roomId ? `/m/${encodeURIComponent(roomId)}/insights` : "/insights") + (fragment ? "#" + fragment : "");
  }
  function openInsights(fragment) {
    const url = insightsUrl(fragment);
    let win = null;
    try { win = window.open(url, "otr-insights", "popup=yes,width=520,height=760,noopener=no"); } catch (_) { win = null; }
    if (win) { try { win.focus(); } catch (_) { } return; }
    try { win = window.open(url, "_blank"); } catch (_) { win = null; }
    showToast(win ? "Your browser blocked the pop-up window, so the insights page opened in a new tab."
      : "Your browser blocked the pop-up. Allow pop-ups for this site, then try again.", "warn");
  }
  function renderInsightsView() {
    Views.renderInsights($("view-insights"), Object.assign({}, insights, {
      labels: { approved: "In your notes" },
    }));
  }
  function renderExplainView() {
    Views.renderExplain($("view-explain"), {
      selected: explainSel,
      item: explainItem,
      counts: insights.kept_out,
      holdSeconds: insights.hold_seconds,
    }, {
      onSelect: key => { explainSel = key; explainItem = null; renderViews(true); },
      // No `reveal` here: in consent mode the server never sends text that was kept out.
    });
  }
  let viewSignature = "";
  function renderViews(force) {
    if (panelView !== "insights" && panelView !== "explain") { viewSignature = ""; return; }
    // The server repeats unchanged status often; skip identical renders so focus and selection are not lost.
    const signature = JSON.stringify([panelView, insights, explainSel, explainItem && explainItem.id]);
    if (!force && signature === viewSignature) return;
    viewSignature = signature;
    if (panelView === "insights") renderInsightsView();
    else renderExplainView();
  }
  function renderPanelButtons() {
    for (const [name, id] of Object.entries(PANEL_BUTTONS)) {
      const open = !!panelView && PANEL_ROOT[panelView] === name;
      const button = $(id);
      button.setAttribute("aria-expanded", String(open));
      button.classList.toggle("on", open);
    }
  }
  function showPanel(name) {
    if (!panelView) panelLastFocus = document.activeElement;
    panelView = name;
    $("side-panel").classList.remove("hidden");
    for (const [key, id] of Object.entries(PANEL_VIEWS)) $(id).classList.toggle("hidden", key !== name);
    setText($("panel-title"), PANEL_TITLES[name]);
    $("panel-back").classList.toggle("hidden", PANEL_ROOT[name] === name);
    $("panel-popout").classList.toggle("hidden", PANEL_ROOT[name] !== "agent");
    renderPanelButtons();
    renderViews(true);
    if (name === "agent" && capFollow) { const box = $("captions"); box.scrollTop = box.scrollHeight; }
    $("panel-title").focus();
  }
  function closePanel() {
    if (!panelView) return;
    panelView = null;
    $("side-panel").classList.add("hidden");
    renderPanelButtons();
    if (panelLastFocus && panelLastFocus.isConnected) panelLastFocus.focus();
    panelLastFocus = null;
  }
  function togglePanel(name) {
    if (panelView && PANEL_ROOT[panelView] === name) closePanel();
    else showPanel(name);
  }
  function setCaptions(on) {
    captionsOn = on;
    const button = $("captions-button");
    button.classList.toggle("on", on);
    button.setAttribute("aria-pressed", String(on));
    const label = on ? "Turn off captions" : "Turn on captions";
    button.setAttribute("aria-label", label);
    button.title = label + " (c)";
    renderCaptions();
  }
  function tickClock() {
    setText($("meeting-clock"), new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
  }

  function renderNotesControl() {
    const button = $("notes-button");
    const paused = sensitivePaused && !finalized;
    button.disabled = finalized;
    button.setAttribute("aria-checked", String(myNotesOn));
    let state, line;
    if (finalized) { state = "Finished"; line = "Notes are finished"; }
    else if (paused) { state = "Paused"; line = "Notes are paused for you"; }
    else if (myNotesOn) { state = "On"; line = "Notes are on for you"; }
    else { state = "Off"; line = "Notes are off"; }
    setText($("notes-label"), state);
    setText($("capture-status"), line);
    $("agent-dot").classList.toggle("hidden", !myNotesOn);
    const agent = $("agent-button");
    agent.setAttribute("aria-label", `Off The Record. ${line}.`);
    agent.title = `Off The Record: ${line.toLowerCase()}`;
  }

  function renderRedactionCounts() {
    const node = $("my-redaction-counts");
    if (!redactionCounts) { node.classList.add("hidden"); return; }
    const suppressed = Number(redactionCounts.suppressed) || 0;
    const removed = Number(redactionCounts.removed) || 0;
    setText(node, `For you: ${suppressed} kept out before the draft · ${removed} removed from the draft. No withheld words are shown.`);
    node.classList.remove("hidden");
  }

  function renderFinalReport(data) {
    const node = $("final-report");
    const counts = data && data.redaction_counts;
    if (!counts) { node.classList.add("hidden"); return; }
    const suppressed = Number(counts.suppressed) || 0;
    const removed = Number(counts.removed) || 0;
    node.replaceChildren();
    node.append(element("h4", null, "Final note report"));
    node.append(element("p", null, `${suppressed} utterances kept out before the draft`));
    node.append(element("p", null, `${removed} approved lines removed later`));
    node.append(element("p", null, "Counts cover this meeting. Withheld content is not included."));
    node.classList.remove("hidden");
  }

  function renderPanelState() {
    const list = $("people-list");
    list.replaceChildren();
    for (const [identity, p] of Object.entries(participants)) {
      const on = notesOn(p);
      const li = element("li");
      li.append(element("span", "person-name", `${p.name || identity}${identity === me ? " (you)" : ""}`));
      const status = element("span", "person-notes" + (on ? " on" : ""), on ? "Notes on" : "Notes off");
      status.prepend(element("span", "dot"));
      li.append(status);
      list.append(li);
    }

    const status = $("finalize-status");
    $("finalize-button").classList.toggle("hidden", finalized);
    $("report-button").classList.toggle("hidden", !readyForFinal);
    $("copy-button").classList.toggle("hidden", !readyForFinal);
    $("email-choice").classList.toggle("hidden", !finalized);
    if (!emailChoiceDirty) {
      $("delivery-email").value = deliveryEmail;
      $("email-opt-in").checked = emailOptedIn;
    }
    renderRedactionCounts();
    if (!readyForFinal) {
      $("copy-result").className = "waiting";
      setText($("copy-result"), "");
    }
    if (readyForFinal) setText(status, "The final transcript is ready to copy.");
    else if (finalized) setText(status, finalizedCount != null && contributorCount != null
      ? `Waiting for other contributors: ${finalizedCount} of ${contributorCount} finished.`
      : "Waiting for other contributors to finish their notes.");
    else setText(status, "Review or remove lines above, then finish your notes. Finishing keeps notes off.");
  }

  function renderAll() {
    renderTiles();
    renderLines();
    renderNotesControl();
    renderPanelState();
  }

  function applyMe(data) {
    if (!data) return;
    if (data.identity) me = data.identity;
    if (data.participants) participants = data.participants;
    if (typeof data.finalized === "boolean") finalized = data.finalized;
    if (typeof data.ready_for_final === "boolean") readyForFinal = data.ready_for_final;
    if (typeof data.finalized_count === "number") finalizedCount = data.finalized_count;
    if (typeof data.contributor_count === "number") contributorCount = data.contributor_count;
    if (Array.isArray(data.lines)) lines = indexLines(data.lines);
    if (data.redaction_counts) redactionCounts = data.redaction_counts;
    if (data.insights) setInsights(data.insights);
    if (Array.isArray(data.kept_out_events)) for (const e of data.kept_out_events) serverT.set("k:" + e.id, e.t);
    if (data.line_times && typeof data.line_times === "object") for (const [id, t] of Object.entries(data.line_times)) serverT.set("l:" + id, t);
    if (typeof data.waiting === "number" && (!diag || diagGone)) waitingLines = data.waiting;
    if (Array.isArray(data.kept_out)) setChips(data.kept_out);
    if (typeof data.delivery_email === "string") deliveryEmail = data.delivery_email;
    if (typeof data.email_opted_in === "boolean") emailOptedIn = data.email_opted_in;
    const mine = participants[me] || {};
    const nowPaused = mine.sensitive_paused === true;
    if (nowPaused && !sensitiveSeen) {
      sensitiveSeen = true;
      showToast("<strong>Sensitive pause.</strong> Your last pending line was discarded and notes stopped for you. Restart when you're ready.", "warn");
    }
    if (!nowPaused) sensitiveSeen = false;
    sensitivePaused = nowPaused;
    myNotesOn = !finalized && !sensitivePaused && notesOn(mine);
    renderAll();
    renderViews();
  }

  async function refreshMe(immediate) {
    if (!immediate) {
      clearTimeout(meRefreshTimer);
      meRefreshTimer = setTimeout(() => refreshMe(true), 1500);
      return;
    }
    meRefreshTimer = null;
    try { applyMe(await api("/api/me")); } catch (_) { }
  }

  function setChips(list) {
    chips.clear();
    for (const chip of list || []) if (chip && chip.id != null) chips.set(chip.id, chip);
    renderCaptions();
  }

  function mergeProgress(message) {
    let changed = false;
    if (typeof message.finalized === "boolean") { finalized = message.finalized; changed = true; }
    if (typeof message.ready_for_final === "boolean") { readyForFinal = message.ready_for_final; changed = true; }
    if (typeof message.finalized_count === "number") { finalizedCount = message.finalized_count; changed = true; }
    if (typeof message.contributor_count === "number") { contributorCount = message.contributor_count; changed = true; }
    if (changed) { renderNotesControl(); renderPanelState(); }
  }

  function connectStream() {
    eventSource = new EventSource("/stream");
    eventSource.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.type === "participants") applyMe({ participants: message.participants });
      else if (message.type === "service") setConnection(message.status, "warn");
      else if (message.type === "snapshot") {
        if (Array.isArray(message.lines)) lines = indexLines(message.lines);
        if (Array.isArray(message.kept_out)) chips.clear(), message.kept_out.forEach(c => chips.set(c.id, c));
        renderLines();
        primed = true;   // rows that exist at connect time are not announced
      } else if (message.type === "status") {
        const { type, ...rest } = message;
        setInsights(rest);
        renderViews();
      } else if (message.type === "transcript") {
        let changed = false;
        for (const change of message.changes || []) {
          if (change.kind === "committed" && change.line && isMyLine(change.line)) {
            lines.set(change.line.id, change.line);
            changed = true;
          }
          if (change.kind === "removed" && lines.delete(change.id)) changed = true;
          if (change.kind === "kept_out" && change.id != null) {
            if (lines.has(change.id)) rowSeq.set(change.id, lines.get(change.id).seq);   // a removal keeps the line's place
            // Category key and generic trail only. The server never sends the text that was kept out.
            chips.set(change.id, { id: change.id, category: change.category, seq: change.seq, trail: change.trail });
            changed = true;
          }
        }
        if (changed) renderLines();
      } else if (message.type === "redaction_counts" && message.redaction_counts) {
        redactionCounts = message.redaction_counts;
        renderRedactionCounts();
      }
      mergeProgress(message);
      refreshMe(false);
    };
    eventSource.onerror = () => setConnection("Reconnecting…", "warn");
    eventSource.onopen = () => setConnection("Live · local room", "online");
  }

  function renderMicButton() {
    const isMuted = room ? !room.localParticipant.isMicrophoneEnabled : false;
    const button = $("mic-button");
    button.classList.toggle("muted-on", isMuted);
    button.setAttribute("aria-pressed", String(!isMuted));
    const label = isMuted ? "Turn on microphone" : "Turn off microphone";
    button.setAttribute("aria-label", label);
    button.title = label;
    setText($("mic-label"), isMuted ? "Unmute" : "Mute");
  }

  // ------------------------------------------------------------ devices, level meters, notes-engine status
  // Camera and microphone belong to the call. They are separate from notes: the camera is never transcribed or
  // sent to the notes pipeline, and turning notes off does not mute the microphone or switch the camera off.
  const DEV_STORE = "otr.devices";
  const SOUND_RMS = 0.012, SILENCE_MS = 3000, HOLD_MS = 700, BARS = 12;
  const WHAT = { audioinput: "microphone", videoinput: "camera", audiooutput: "speaker" };
  const KINDS = ["audioinput", "audiooutput", "videoinput"];
  const CHECK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>';
  const METER_TEXT = {
    listening: "Say something to test your microphone",
    sound: "Your browser is picking up sound",
    silent: "No sound detected, check the selected microphone",
    ended: "The microphone stopped, check the selected microphone",
    unsupported: "The level meter is not available in this browser",
    idle: "",
  };
  const PALETTES = { light: ["--blue", "--line"], call: ["--call-active", "--call-ink-2"], panel: ["--p-blue", "--p-line"] };
  function loadDevPrefs() {
    try { const v = JSON.parse(sessionStorage.getItem(DEV_STORE) || "{}"); return v && typeof v === "object" ? v : {}; }
    catch (_) { return {}; }
  }
  function saveDevPrefs() { try { sessionStorage.setItem(DEV_STORE, JSON.stringify(devPrefs)); } catch (_) { } }
  let devPrefs = loadDevPrefs();
  function supportsSinkId() {
    try { return !!(window.HTMLMediaElement && "setSinkId" in window.HTMLMediaElement.prototype); } catch (_) { return false; }
  }
  function mediaSupport() {
    if (window.isSecureContext === false) return "insecure";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return "unsupported";
    return "";
  }
  function mediaProblem(err, what) {
    const reason = mediaSupport();
    if (reason === "insecure") {
      const port = location.port ? ":" + location.port : "";
      return `This browser only allows the ${what} on a secure address. Open this page at http://127.0.0.1${port} or http://localhost${port} on this computer, or use https.`;
    }
    if (reason === "unsupported") return "This browser cannot reach the microphone or camera.";
    const name = (err && err.name) || "";
    if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError")
      return `Permission to use the ${what} was denied. Allow it in the browser address bar, then try again.`;
    if (name === "NotFoundError" || name === "DevicesNotFoundError") return `No ${what} found. Plug one in or choose another device.`;
    if (name === "OverconstrainedError") return `The ${what} you chose is not available. Choose another one.`;
    if (name === "NotReadableError" || name === "TrackStartError" || name === "AbortError")
      return `The ${what} is in use by another app or browser tab. Close it there, then try again.`;
    return `Could not start the ${what}${err && err.message ? ": " + err.message : "."}`;
  }
  function cssVar(name, fallback) {
    try { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback; } catch (_) { return fallback; }
  }
  function ctx2d(canvas) {
    try { return canvas && canvas.getContext ? canvas.getContext("2d") : null; } catch (_) { return null; }
  }
  function drawWave(canvas, values, palette) {
    const c = ctx2d(canvas);
    if (!c) return;
    const on = cssVar(PALETTES[palette][0], "#1a73e8"), off = cssVar(PALETTES[palette][1], "#9aa0a6");
    const w = canvas.width, h = canvas.height, n = values.length, gap = 2;
    const bw = Math.max(1, Math.floor((w - gap * (n - 1)) / n));
    c.clearRect(0, 0, w, h);
    values.forEach((v, i) => {
      const bh = Math.max(2, Math.round(h * Math.min(1, v)));
      c.fillStyle = v > 0.04 ? on : off;
      c.fillRect(i * (bw + gap), Math.round((h - bh) / 2), bw, bh);
    });
  }
  function drawStrip(canvas, level, palette) {
    const c = ctx2d(canvas);
    if (!c) return;
    const on = cssVar(PALETTES[palette][0], "#1a73e8"), off = cssVar(PALETTES[palette][1], "#9aa0a6");
    const w = canvas.width, h = canvas.height, gap = 2, bw = Math.max(1, Math.floor((w - gap * (BARS - 1)) / BARS));
    const clamped = Math.max(0, Math.min(1, level));
    const lit = Math.round(clamped * BARS);
    c.clearRect(0, 0, w, h);
    for (let i = 0; i < BARS; i++) { c.fillStyle = i < lit ? on : off; c.fillRect(i * (bw + gap), 0, bw, h); }
    canvas.dataset.level = clamped.toFixed(2);
  }
  // Web Audio level meter over a MediaStream. targets() returns [[canvas, palette], ...] to draw into.
  function createMeter(targets, onState) {
    let audio = null, analyser = null, samples = null, timer = null, track = null, lastSound = 0;
    const m = { state: "idle", rms: 0, soundSince: 0 };
    const set = next => { if (next !== m.state) { m.state = next; if (onState) onState(next); } };
    function tick() {
      const now = performance.now();
      const values = new Array(BARS).fill(0);
      let rms = 0;
      if (track && track.readyState === "ended") set("ended");
      else if (analyser) {
        if (audio.state === "suspended" && audio.resume) { try { audio.resume().catch(() => {}); } catch (_) { } }
        analyser.getFloatTimeDomainData(samples);
        const seg = Math.floor(samples.length / BARS);
        let total = 0;
        for (let i = 0; i < BARS; i++) {
          let sum = 0;
          for (let j = 0; j < seg; j++) { const v = samples[i * seg + j]; sum += v * v; }
          values[i] = Math.min(1, Math.sqrt(sum / seg) * 6);
          total += sum;
        }
        rms = Math.sqrt(total / (seg * BARS));
        if (rms > SOUND_RMS) { lastSound = now; if (m.state !== "sound") { if (!m.soundSince) m.soundSince = now; set("sound"); } }
        else if (now - lastSound > SILENCE_MS) { m.soundSince = 0; set("silent"); }
        else if (m.state === "sound" && now - lastSound > HOLD_MS) set("listening");
      }
      m.rms = rms;
      for (const [canvas, palette] of targets()) { drawWave(canvas, values, palette); canvas.dataset.level = rms.toFixed(3); }
    }
    m.attach = stream => {
      m.stop();
      const AC = window.AudioContext || window.webkitAudioContext;
      track = stream && stream.getAudioTracks ? stream.getAudioTracks()[0] : null;
      if (!AC || !track) { set(AC ? "ended" : "unsupported"); return; }
      audio = new AC();
      const source = audio.createMediaStreamSource(stream);
      analyser = audio.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);   // never connected to the speakers, so there is no echo
      samples = new Float32Array(analyser.fftSize);
      lastSound = performance.now();
      m.soundSince = 0;
      set("listening");
      timer = setInterval(tick, 60);
    };
    m.stop = () => {
      clearInterval(timer); timer = null;
      if (audio && audio.close) { try { audio.close(); } catch (_) { } }
      audio = analyser = track = null;
      m.soundSince = 0; m.rms = 0;
      set("idle");
      for (const [canvas, palette] of targets()) drawWave(canvas, new Array(BARS).fill(0), palette);
    };
    return m;
  }
  async function listDevices() {
    const out = { audioinput: [], videoinput: [], audiooutput: [] };
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return out;
    try { for (const d of await navigator.mediaDevices.enumerateDevices()) if (out[d.kind]) out[d.kind].push(d); } catch (_) { }
    return out;
  }
  function deviceLabel(d, index, kind) {
    return d.label || `${{ audioinput: "Microphone", videoinput: "Camera", audiooutput: "Speaker" }[kind]} ${index + 1}`;
  }
  function currentDeviceId(list, wanted) {
    if (wanted && list.some(d => d.deviceId === wanted)) return wanted;
    const fallback = list.find(d => d.deviceId === "default") || list[0];
    return fallback ? fallback.deviceId : "";
  }
  function activeDeviceId(kind) {
    return (room && room.getActiveDevice && room.getActiveDevice(kind)) || devPrefs[kind] || "";
  }
  function stopTracks(stream) { if (stream) for (const t of stream.getTracks()) t.stop(); }

  // ---- lobby device check
  const check = { audio: null, video: null, meter: null, busy: false };
  function renderCheckStatus(state) {
    const node = $("check-mic-status");
    setText(node, METER_TEXT[state] || "");
    node.setAttribute("data-state", state);
  }
  async function openStream(kind) {
    const key = kind === "audioinput" ? "audio" : "video", what = WHAT[kind];
    if (mediaSupport()) throw new Error(mediaProblem(null, what));
    const id = devPrefs[kind];
    try {
      return { stream: await navigator.mediaDevices.getUserMedia({ [key]: id ? { deviceId: { exact: id } } : true }), fellBack: false };
    } catch (error) {
      if (id && (error.name === "OverconstrainedError" || error.name === "NotFoundError")) {
        delete devPrefs[kind]; saveDevPrefs();
        try { return { stream: await navigator.mediaDevices.getUserMedia({ [key]: true }), fellBack: true }; }
        catch (second) { throw new Error(mediaProblem(second, what)); }
      }
      throw new Error(mediaProblem(error, what));
    }
  }
  function fillSelect(select, list, kind, wanted) {
    select.replaceChildren();
    list.forEach((d, i) => {
      const option = element("option", null, deviceLabel(d, i, kind));
      option.value = d.deviceId;
      select.append(option);
    });
    if (!list.length) { const none = element("option", null, `No ${WHAT[kind]} found`); none.value = ""; select.append(none); }
    select.disabled = !list.length;
    select.value = currentDeviceId(list, wanted);
  }
  async function refreshCheckLists() {
    const lists = await listDevices();
    const trackId = stream => { try { return stream.getTracks()[0].getSettings().deviceId; } catch (_) { return ""; } };
    fillSelect($("check-mic"), lists.audioinput, "audioinput", devPrefs.audioinput || (check.audio && trackId(check.audio)));
    fillSelect($("check-cam"), lists.videoinput, "videoinput", devPrefs.videoinput || (check.video && trackId(check.video)));
    const sinks = supportsSinkId() && lists.audiooutput.length > 0;
    $("check-spk-row").classList.toggle("hidden", !sinks);
    if (sinks) fillSelect($("check-spk"), lists.audiooutput, "audiooutput", devPrefs.audiooutput);
  }
  async function startDeviceCheck(only) {
    if (check.busy) return;
    check.busy = true;
    const problems = new Set();
    setText($("check-error"), "");
    try {
      for (const kind of ["audioinput", "videoinput"]) {
        if (only && only !== kind) continue;
        const slot = kind === "audioinput" ? "audio" : "video";
        stopTracks(check[slot]); check[slot] = null;
        if (slot === "audio" && check.meter) check.meter.stop();
        try {
          const opened = await openStream(kind);
          check[slot] = opened.stream;
          if (opened.fellBack) problems.add(`The saved ${WHAT[kind]} is not available any more. Using the default ${WHAT[kind]}.`);
        } catch (error) { problems.add(error.message); }
      }
      const video = $("check-video");
      video.srcObject = check.video;
      if (check.video && video.play) { try { const p = video.play(); if (p && p.catch) p.catch(() => {}); } catch (_) { } }
      $("check-video-off").classList.toggle("hidden", !!check.video);
      $("check-camera-on").disabled = !check.video;
      if (!check.video) { $("check-camera-on").checked = false; devPrefs.cameraOn = false; }
      $("device-check-live").classList.remove("hidden");
      if (check.audio) {
        if (!check.meter) check.meter = createMeter(() => [[$("check-meter"), "light"]], renderCheckStatus);
        check.meter.attach(check.audio);
      } else renderCheckStatus("idle");
      await refreshCheckLists();
    } finally { check.busy = false; }
    setText($("check-error"), [...problems].join(" "));
  }
  function stopDeviceCheck() {
    stopTracks(check.audio); stopTracks(check.video);
    check.audio = check.video = null;
    if (check.meter) check.meter.stop();
    const video = $("check-video");
    if (video) video.srcObject = null;
    $("device-check-live").classList.add("hidden");
  }
  function placeDeviceCheck(id) {
    const block = $("device-check");
    const anchor = { "share-screen": "share-join-button", "guest-setup": "guest-join-button" }[id];
    if (!anchor) { block.classList.add("hidden"); stopDeviceCheck(); return; }
    const before = $(anchor);
    before.parentNode.insertBefore(block, before);
    block.classList.remove("hidden");
    if (mediaSupport() && !check.audio) setText($("check-error"), mediaProblem(null, "microphone"));
  }

  // ---- in-call device menu (Meet-style chevrons beside the mic and camera buttons)
  const localMeter = createMeter(() => {
    const out = [];
    const tile = me && tileEls[me] && tileEls[me].querySelector(".tile-level");
    if (tile) out.push([tile, "call"]);
    if (deviceMenuOpen()) out.push([$("menu-meter"), "panel"]);
    if (panelView === "agent" && !$("engine").classList.contains("hidden")) out.push([$("engine-browser-meter"), "panel"]);
    return out;
  }, state => {
    setText($("menu-mic-status"), METER_TEXT[state] || "");
    $("menu-mic-status").setAttribute("data-state", state);
    renderDiagnostics();
  });
  function localMicStream() {
    const pub = room && room.localParticipant.getTrackPublication(LiveKit.Track.Source.Microphone);
    const t = pub && pub.track && pub.track.mediaStreamTrack;
    return t && typeof MediaStream !== "undefined" ? new MediaStream([t]) : null;
  }
  function rebindLocalMeter() {
    const stream = localMicStream();
    if (stream && room.localParticipant.isMicrophoneEnabled) localMeter.attach(stream);
    else localMeter.stop();
  }
  function deviceMenuOpen() { return !$("device-menu").classList.contains("hidden"); }
  function fillMenuList(listId, list, kind) {
    const ul = $(listId);
    ul.replaceChildren();
    const active = currentDeviceId(list, activeDeviceId(kind));
    if (!list.length) { ul.append(element("li", "device-none", `No ${WHAT[kind]} found`)); return; }
    list.forEach((d, i) => {
      const li = element("li");
      const button = element("button", "device-item", deviceLabel(d, i, kind));
      button.type = "button";
      button.setAttribute("role", "menuitemradio");
      button.setAttribute("aria-checked", String(d.deviceId === active));
      button.setAttribute("data-device-id", d.deviceId);
      const mark = element("span", "device-check");
      mark.innerHTML = CHECK_SVG;
      button.append(mark);
      button.onclick = () => chooseDevice(kind, d.deviceId);
      li.append(button);
      ul.append(li);
    });
  }
  async function renderDeviceMenu() {
    const lists = await listDevices();
    fillMenuList("menu-mic", lists.audioinput, "audioinput");
    fillMenuList("menu-cam", lists.videoinput, "videoinput");
    const sinks = supportsSinkId();
    $("menu-spk").classList.toggle("hidden", !sinks);
    $("menu-spk-note").classList.toggle("hidden", sinks);
    if (sinks) fillMenuList("menu-spk", lists.audiooutput, "audiooutput");
  }
  async function chooseDevice(kind, id) {
    setText($("menu-error"), "");
    try {
      if (room) await room.switchActiveDevice(kind, id, true);
      devPrefs[kind] = id;
      saveDevPrefs();
      if (kind === "audioinput") rebindLocalMeter();
      announce(`${WHAT[kind][0].toUpperCase()}${WHAT[kind].slice(1)} changed.`);
    } catch (error) { setText($("menu-error"), mediaProblem(error, WHAT[kind])); }
    await renderDeviceMenu();
  }
  function openDeviceMenu(group) {
    $("device-menu").classList.remove("hidden");
    for (const id of ["mic-chevron", "camera-chevron"]) $(id).setAttribute("aria-expanded", "true");
    setText($("menu-error"), "");
    rebindLocalMeter();
    renderDeviceMenu().then(() => {
      const first = $(group || "menu-mic").querySelector("button");
      if (first) first.focus();
    });
  }
  function closeDeviceMenu() {
    if (!deviceMenuOpen()) return;
    $("device-menu").classList.add("hidden");
    for (const id of ["mic-chevron", "camera-chevron"]) $(id).setAttribute("aria-expanded", "false");
  }
  function toggleDeviceMenu(group) { if (deviceMenuOpen()) closeDeviceMenu(); else openDeviceMenu(group); }
  async function testSpeaker(statusId) {
    const AC = window.AudioContext || window.webkitAudioContext;
    const out = $(statusId);
    setText(out, "");
    if (!AC) { setText(out, "This browser cannot play a test tone."); return; }
    try {
      const ctx = new AC();
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.frequency.value = 440;
      gain.gain.value = 0.15;
      osc.connect(gain);
      let sink = null;
      if (supportsSinkId() && ctx.createMediaStreamDestination) {
        const dest = ctx.createMediaStreamDestination();
        gain.connect(dest);
        sink = document.createElement("audio");
        sink.srcObject = dest.stream;
        const id = activeDeviceId("audiooutput");
        if (id && sink.setSinkId) await sink.setSinkId(id);
        await sink.play();
      } else gain.connect(ctx.destination);
      osc.start();
      setTimeout(() => {
        try { osc.stop(); } catch (_) { }
        if (sink) sink.srcObject = null;
        try { ctx.close(); } catch (_) { }
      }, 700);
    } catch (error) { setText(out, mediaProblem(error, "speaker")); }
  }
  let deviceChangeBound = false;
  async function onDeviceChange() {
    const lists = await listDevices();
    for (const kind of KINDS) {
      const id = (room && room.getActiveDevice && room.getActiveDevice(kind)) || devPrefs[kind];
      if (!id || id === "default" || lists[kind].some(d => d.deviceId === id)) continue;
      delete devPrefs[kind];
      saveDevPrefs();
      const note = `Your ${WHAT[kind]} was disconnected. Using the default ${WHAT[kind]}.`;
      if (room) {
        try { await room.switchActiveDevice(kind, "default"); } catch (_) { }
        showToast(escapeHtml(note), "warn");
        if (kind === "audioinput") rebindLocalMeter();
      } else setText($("check-error"), note);
    }
    if (!$("device-check-live").classList.contains("hidden") && !room) {
      if (!check.audio || check.audio.getTracks().every(t => t.readyState === "ended")) await startDeviceCheck("audioinput");
      await refreshCheckLists();
    }
    if (deviceMenuOpen()) await renderDeviceMenu();
  }
  function bindDeviceChange() {
    if (deviceChangeBound || !navigator.mediaDevices || !navigator.mediaDevices.addEventListener) return;
    deviceChangeBound = true;
    navigator.mediaDevices.addEventListener("devicechange", onDeviceChange);
  }

  // ---- notes engine status (text-free, from GET /api/diagnostics)
  let diagTimer = null, diagBusy = false, diagGone = false, diag = null;
  function engineModelRows(models) {
    const rows = [];
    const w = models && models.whisper, l = models && models.llm, p = models && models.presidio;
    if (w) rows.push(`Whisper ${w.name || ""}: ${w.loaded ? "ready" : "loading"}${typeof w.rtf === "number" ? `, ${w.rtf.toFixed(2)}x real time` : ""}`);
    if (l) rows.push(`Local model ${l.name || ""}: ${l.reachable ? (l.warm ? "ready" : "reachable, warming up") : "not reachable"}`);
    if (p) rows.push(`Presidio ${p.model || ""}: ${p.available ? "ready" : "not available"}`);
    return rows;
  }
  function engineInputText(mine) {
    const state = mine && mine.state;
    if (state === "hearing_you") return "The notes engine is hearing you";
    if (state === "waiting_for_audio") return "Waiting for audio";
    if (state === "silent") return "Silent";
    if (state === "not_subscribed") return "Notes are off for you, nothing is being transcribed";
    if (state === "error") return (mine.error && String(mine.error)) || "The notes engine reported an error";
    return "";
  }
  function setIfChanged(node, value) { if (node.textContent !== value) setText(node, value); }
  function renderDiagnostics() {
    const block = $("engine");
    if (!block) return;
    const known = diag && !diagGone && diag.me && typeof diag.me.waiting_lines === "number";
    if (known) waitingLines = diag.me.waiting_lines;
    renderTranscriptStatus();
    if (!diag || diagGone) { block.classList.add("hidden"); return; }
    block.classList.remove("hidden");
    const rows = engineModelRows(diag.models);
    const list = $("engine-models");
    const signature = rows.join("|");
    if (list.dataset.signature !== signature) {
      list.dataset.signature = signature;
      list.replaceChildren(...rows.map(r => element("li", null, r)));
    }
    const mine = diag.me || {};
    setIfChanged($("engine-input"), engineInputText(mine));
    $("engine-input").setAttribute("data-state", mine.state || "");
    drawStrip($("engine-server-meter"), typeof mine.audio_level === "number" ? mine.audio_level : 0, "panel");
    // The browser hears sound but the notes engine does not: say so in plain words.
    const hearsSound = localMeter.state === "sound" && localMeter.soundSince && performance.now() - localMeter.soundSince > SILENCE_MS;
    const stale = mine.state === "waiting_for_audio" || mine.last_frame_age_s == null || mine.last_frame_age_s > 5;
    const noFrames = !!(hearsSound && mine.subscribed && mine.notes_on && mine.state !== "hearing_you" && mine.state !== "error" && stale);
    const warn = $("engine-warning");
    warn.classList.toggle("hidden", !noFrames);
    setIfChanged(warn, noFrames
      ? "Your microphone is picking up sound, but no audio is reaching the notes engine. Check that the LiveKit server is running, then leave and join again."
      : "");
  }
  async function pollDiagnostics() {
    if (diagBusy || diagGone || !room || document.hidden) return;
    diagBusy = true;
    try { diag = await api("/api/diagnostics"); renderDiagnostics(); }
    catch (error) {
      if (error.status === 404 || error.status === 405) { diagGone = true; diag = null; renderDiagnostics(); stopDiagnostics(); }
    } finally { diagBusy = false; }
  }
  function startDiagnostics() {
    stopDiagnostics();
    diagGone = false;
    diagTimer = setInterval(pollDiagnostics, 500);
    pollDiagnostics();
  }
  function stopDiagnostics() { clearInterval(diagTimer); diagTimer = null; }
  function renderAudioButton() {
    $("audio-button").classList.toggle("hidden", !(room && room.canPlaybackAudio === false));
  }

  async function join(accessOverride = null, configOverride = null) {
    if (joinInProgress) return false;
    joinInProgress = true;
    const button = $("join-button");
    setText($("join-error"), "");
    setText($("share-error"), "");
    const name = $("name").value.trim();
    if (!accessOverride && !name) {
      setText($("join-error"), "Enter a display name");
      joinInProgress = false;
      return false;
    }
    button.disabled = true;
    setText(button, "Joining…");
    setConnection("Joining…", "warn");
    try {
      const config = configOverride || await api("/api/config");
      const access = accessOverride || await post("/api/join", { name });
      me = access.identity;
      stopDeviceCheck();
      const roomOptions = { adaptiveStream: true, dynacast: true };
      if (devPrefs.audioinput) roomOptions.audioCaptureDefaults = { deviceId: devPrefs.audioinput };
      if (devPrefs.videoinput) roomOptions.videoCaptureDefaults = { deviceId: devPrefs.videoinput };
      if (devPrefs.audiooutput && supportsSinkId()) roomOptions.audioOutput = { deviceId: devPrefs.audiooutput };
      room = new LiveKit.Room(roomOptions);
      connectedPeople.clear();
      room.on(LiveKit.RoomEvent.ParticipantConnected, participant => {
        connectedPeople.add(participant.identity);
        updateTileFlags();
      });
      room.on(LiveKit.RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === LiveKit.Track.Kind.Audio) {
          const media = track.attach();
          media.dataset.livekitAudio = "true";
          media.muted = false;
          if (participant) media.dataset.participant = participant.identity;
          document.body.append(media);
          renderAudioButton();
          if (participant) muted.set(participant.identity, publication.isMuted);
          updateTileFlags();
        } else if (participant && publication.source === LiveKit.Track.Source.Camera) {
          if (publication.isMuted) videoMuted.add(participant.identity);
          else videoMuted.delete(participant.identity);
          setVideoTrack(participant.identity, track);
        }
      });
      room.on(LiveKit.RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
        if (track.kind === LiveKit.Track.Kind.Audio) {
          track.detach().forEach(media => media.remove());
          if (participant) muted.delete(participant.identity);
          updateTileFlags();
        } else if (participant && publication.source === LiveKit.Track.Source.Camera) {
          setVideoTrack(participant.identity, null);
          videoMuted.delete(participant.identity);
        }
      });
      room.on(LiveKit.RoomEvent.TrackMuted, (publication, participant) => {
        if (participant && publication.kind === LiveKit.Track.Kind.Audio)
          muted.set(participant.identity, true);
        else if (participant && publication.source === LiveKit.Track.Source.Camera) {
          videoMuted.add(participant.identity);
          updateVideoTile(participant.identity);
        }
        updateTileFlags();
      });
      room.on(LiveKit.RoomEvent.TrackUnmuted, (publication, participant) => {
        if (participant && publication.kind === LiveKit.Track.Kind.Audio)
          muted.delete(participant.identity);
        else if (participant && publication.source === LiveKit.Track.Source.Camera) {
          videoMuted.delete(participant.identity);
          updateVideoTile(participant.identity);
        }
        updateTileFlags();
      });
      room.on(LiveKit.RoomEvent.LocalTrackPublished, publication => {
        if (publication.source === LiveKit.Track.Source.Microphone) rebindLocalMeter();
        if (publication.source === LiveKit.Track.Source.Camera) {
          videoMuted.delete(me);
          setVideoTrack(me, publication.videoTrack || publication.track);
          renderCameraButton();
        }
      });
      room.on(LiveKit.RoomEvent.LocalTrackUnpublished, publication => {
        if (publication.source === LiveKit.Track.Source.Microphone) localMeter.stop();
        if (publication.source === LiveKit.Track.Source.Camera) {
          setVideoTrack(me, null);
          renderCameraButton();
        }
      });
      room.on(LiveKit.RoomEvent.ParticipantDisconnected, participant => {
        connectedPeople.delete(participant.identity);
        setVideoTrack(participant.identity, null);
        videoMuted.delete(participant.identity);
        muted.delete(participant.identity);
        updateTileFlags();
      });
      room.on(LiveKit.RoomEvent.Reconnecting, () => setConnection("Reconnecting…", "warn"));
      room.on(LiveKit.RoomEvent.Reconnected, () => {
        setConnection("Live · local room", "online");
        renderCameraButton();
      });
      room.on(LiveKit.RoomEvent.ActiveSpeakersChanged, speakers => {
        speaking = new Set(speakers.map(p => p.identity));
        updateTileFlags();
      });
      room.on(LiveKit.RoomEvent.Disconnected, () => { setConnection("Disconnected", "off"); stopDiagnostics(); localMeter.stop(); });
      room.on(LiveKit.RoomEvent.AudioPlaybackStatusChanged, renderAudioButton);
      room.on(LiveKit.RoomEvent.ActiveDeviceChanged, kind => { if (kind === "audioinput") rebindLocalMeter(); });
      room.on(LiveKit.RoomEvent.MediaDevicesError, error =>
        showToast(escapeHtml(mediaProblem(error, "microphone or camera")), "warn"));
      try { await room.connect(config.url, access.token); }
      catch (_) {
        throw new Error("Could not connect to the call server. Check that LiveKit is running and reachable from this browser, then try again.");
      }
      for (const identity of room.remoteParticipants.keys()) connectedPeople.add(identity);
      setText($("room-chip"), `Room ${config.room}`);
      $("room-chip").classList.remove("hidden");
      for (const screen of ENTRY_SCREENS) $(screen).classList.add("hidden");
      $("meeting").classList.remove("hidden");
      $("control-bar").classList.remove("hidden");
      setText($("meeting-room-name"), roomId || config.room);
      tickClock();
      clearInterval(clockTimer);
      clockTimer = setInterval(tickClock, 30000);
      startLobby();
      bindDeviceChange();
      renderAudioButton();
      startDiagnostics();
      startRoomStatus();
      renderMicButton();
      renderCameraButton();
      setConnection("Live · local room", "online");
      api("/api/me").then(applyMe).catch(() => {});
      connectStream();
      room.localParticipant.setMicrophoneEnabled(true).then(() => {
        renderMicButton();
        updateTileFlags();
        rebindLocalMeter();
      }).catch(error => {
        renderMicButton();
        updateTileFlags();
        showToast(`Microphone is off. ${escapeHtml(mediaProblem(error, "microphone"))}`, "warn");
      });
      if (devPrefs.cameraOn) {
        room.localParticipant.setCameraEnabled(true).then(renderCameraButton).catch(error => {
          renderCameraButton();
          showToast(`Camera is off. ${escapeHtml(mediaProblem(error, "camera"))}`, "warn");
        });
      }
      return true;
    } catch (error) {
      const reason = error && error.message ? error.message : "Could not connect to the meeting.";
      setText($("join-error"), reason);
      setText($("share-error"), reason);
      if (accessOverride) showToast(`Could not join the meeting: ${escapeHtml(reason)} Try again or ask the host to check the connection.`, "err");
      setConnection("Not connected", "off");
      if (room) { try { await room.disconnect(); } catch (_) { } room = null; }
      if (me && !accessOverride) { try { await post("/api/leave", {}); } catch (_) { } }
      me = null;
      return false;
    } finally {
      joinInProgress = false;
      button.disabled = false;
      setText(button, "Join");
    }
  }

  async function toggleNotes() {
    if (finalized) return;
    const button = $("notes-button");
    button.disabled = true;
    try {
      const target = sensitivePaused ? true : !myNotesOn;
      await post("/api/consent", { recording: target });
      announce(target ? "Notes on." : "Notes stopped.");
      await refreshMe(true);
    } catch (error) {
      showToast(`<strong>Couldn't update notes.</strong> ${escapeHtml(error.message)}`, "err");
    } finally {
      button.disabled = false;
    }
  }

  async function removeLine(id, removeButton) {
    removeButton.disabled = true;
    try {
      await post("/api/notes/remove", { id });
      lines.delete(id);
      renderLines();
      announce("Line removed.");
    } catch (error) {
      showToast(`<strong>Couldn't remove the line.</strong> ${escapeHtml(error.message)}`, "err");
      removeButton.disabled = false;
    }
  }

  async function finalize() {
    const button = $("finalize-button");
    button.disabled = true;
    try {
      await post("/api/notes/finalize", {});
      finalized = true;
      announce("Notes finished.");
      await refreshMe(true);
    } catch (error) {
      showToast(`<strong>Couldn't finish notes.</strong> ${escapeHtml(error.message)}`, "err");
      button.disabled = false;
    }
  }

  async function copyText(value) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const area = document.createElement("textarea");
    area.value = value;
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.style.top = "0";
    document.body.append(area);
    area.focus();
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    if (!ok) throw new Error("Clipboard unavailable in this browser.");
  }

  async function copyFinal() {
    const button = $("copy-button");
    const result = $("copy-result");
    button.disabled = true;
    result.className = "waiting";
    setText(result, "");
    try {
      const data = await api("/api/notes/final");
      renderFinalReport(data);
      const textToCopy = typeof data.text === "string" && data.text
        ? data.text
        : (Array.isArray(data.lines) ? data.lines.map(line => {
          const who = line.name || line.speaker || "";
          return `${who ? who + ": " : ""}${line.text}`;
        }).join("\n") : "");
      if (!textToCopy) throw new Error("The final transcript is empty.");
      await copyText(textToCopy);
      result.classList.add("ok");
      setText(result, "Copied to clipboard.");
      announce("Final transcript copied to clipboard.");
    } catch (error) {
      result.classList.add("err");
      setText(result, error.status === 409
        ? "The final transcript isn't ready yet."
        : `Couldn't copy: ${error.message}`);
    } finally {
      button.disabled = false;
    }
  }

  async function viewFinalReport() {
    const button = $("report-button");
    button.disabled = true;
    try {
      renderFinalReport(await api("/api/notes/final"));
      if ($("final-report").classList.contains("hidden"))
        setText($("copy-result"), "This meeting has no redaction report yet.");
    } catch (error) {
      showToast(`Could not load the final report: ${escapeHtml(error.message)}`, "err");
    } finally { button.disabled = false; }
  }

  function officialTranscript(data) {
    if (typeof data.text === "string" && data.text) return data.text;
    return Array.isArray(data.lines) ? data.lines.map(line => {
      const who = line.name || line.speaker || "";
      return `${who ? who + ": " : ""}${line.text}`;
    }).join("\n") : "";
  }

  function emailAddress(value) {
    const address = value.trim();
    const probe = document.createElement("input");
    probe.type = "email";
    probe.value = address;
    if (!address || /[\r\n,;<>]/.test(address) || !probe.checkValidity())
      throw new Error("Enter one valid email address.");
    return address;
  }

  async function saveEmailChoice() {
    const button = $("save-email-choice");
    const result = $("email-choice-result");
    button.disabled = true;
    result.className = "waiting";
    setText(result, "");
    try {
      const enabled = $("email-opt-in").checked;
      const address = enabled ? emailAddress($("delivery-email").value) : $("delivery-email").value.trim();
      const saved = await post("/api/notes/email-opt-in", {email: address, enabled});
      deliveryEmail = saved.email;
      emailOptedIn = saved.enabled;
      emailChoiceDirty = false;
      renderPanelState();
      result.classList.add("ok");
      setText(result, enabled ? "Saved. The host can include this address in the final email draft." : "Saved. Your address will not be in the host's draft.");
    } catch (error) {
      result.classList.add("err");
      setText(result, error.status === 409 ? "Finish your notes before choosing email delivery." : error.message);
    } finally { button.disabled = false; }
  }

  function closeEndDialog() {
    $("end-dialog").classList.add("hidden");
    $("end-backdrop").classList.add("hidden");
    if (endDialogLastFocus && endDialogLastFocus.isConnected) endDialogLastFocus.focus();
    endDialogLastFocus = null;
  }

  async function showEndDialog() {
    closePanel();
    endDialogLastFocus = document.activeElement;
    $("end-dialog").classList.remove("hidden");
    $("end-backdrop").classList.remove("hidden");
    $("end-email-review").classList.add("hidden");
    $("end-without-email").classList.remove("hidden");
    $("end-confirm").classList.add("hidden");
    setText($("end-summary"), "Checking whether the final transcript is ready…");
    setText($("end-error"), "");
    $("end-cancel").focus();
    try {
      const [finalData, recipientData] = await Promise.all([
        api("/api/notes/final"),
        api(`/api/meetings/${encodeURIComponent(roomId)}/mail-recipients`)
      ]);
      if ($("end-dialog").classList.contains("hidden")) return;
      const transcript = officialTranscript(finalData);
      const recipients = recipientData.recipients || [];
      $("end-transcript").value = transcript || "(No approved lines)";
      const counts = finalData.redaction_counts || {};
      const suppressed = Number(counts.suppressed) || 0;
      const removed = Number(counts.removed) || 0;
      setText($("end-redactions"), `Privacy report: ${suppressed} utterances kept out before the draft; ${removed} lines removed later. Withheld words are not included.`);
      if (!recipients.length) {
        setText($("end-summary"), "The final transcript is ready. No one opted in to email, so you can copy it from My notes or end the meeting.");
        return;
      }
      const addresses = recipients.map(item => emailAddress(item.email));
      setText($("end-summary"), "Review the final transcript and recipients before opening an email draft.");
      setText($("end-recipients"), `To: ${recipients.map(item => `${item.name} <${item.email}>`).join(", ")}`);
      const report = `Privacy report: ${suppressed} utterances kept out before the draft; ${removed} lines removed later. Withheld words are not included.`;
      endEmailBody = `Official meeting transcript\n\n${transcript || "(No approved lines)"}\n\n${report}`;
      const subject = "Meeting transcript";
      const prefix = `mailto:${addresses.map(address => encodeURIComponent(address).replace("%40", "@")).join(",")}?subject=${encodeURIComponent(subject)}`;
      if (prefix.length > 1800) throw new Error("Too many email addresses for one mail draft. Copy the transcript from My notes or end without email.");
      const fullLink = `${prefix}&body=${encodeURIComponent(endEmailBody)}`;
      endNeedsCopy = fullLink.length > 1800;
      endCopied = !endNeedsCopy;
      $("end-mail-limit").classList.toggle("hidden", !endNeedsCopy);
      const link = $("end-email-link");
      link.href = endNeedsCopy ? prefix : fullLink;
      link.classList.toggle("disabled", endNeedsCopy);
      link.setAttribute("aria-disabled", String(endNeedsCopy));
      $("end-email-review").classList.remove("hidden");
      $("end-without-email").classList.add("hidden");
      $("end-confirm").classList.remove("hidden");
    } catch (error) {
      if (error.status === 409) setText($("end-summary"), "The final transcript is still waiting for contributors to finish. You can keep the meeting open or end without email.");
      else {
        setText($("end-summary"), "Could not prepare an email draft.");
        setText($("end-error"), error.message);
      }
    }
  }

  async function endMeeting() {
    try {
      if (role === "host" && roomId) await post(`/api/meetings/${encodeURIComponent(roomId)}/end`, {});
      else await post("/api/leave", {});
      clearInterval(lobbyTimer);
      clearInterval(waitingTimer);
      clearInterval(roomTimer);
      stopDiagnostics();
      localMeter.stop();
      closeDeviceMenu();
      if (eventSource) eventSource.close();
      if (room) await room.disconnect();
      location.href = "/";
    } catch (error) {
      if (role === "host") setText($("end-error"), `Could not end meeting: ${error.message}`);
      else showToast(`Could not leave: ${escapeHtml(error.message)}`, "err");
    }
  }

  $("join-button").onclick = () => join();
  $("name").onkeydown = event => { if (event.key === "Enter") join(); };
  $("create-button").onclick = () => showEntry("host-setup");
  for (const back of document.querySelectorAll("[data-back-home]")) {
    back.onclick = () => showEntry("home-screen");
  }
  $("home-join-button").onclick = () => {
    try {
      setText($("home-error"), "");
      location.href = `/m/${encodeURIComponent(meetingIdFromLink($("home-meeting-code").value))}`;
    } catch (error) { setText($("home-error"), error.message); }
  };
  $("home-meeting-code").onkeydown = event => { if (event.key === "Enter") $("home-join-button").click(); };
  $("host-create-button").onclick = async () => {
    const button = $("host-create-button");
    button.disabled = true;
    setText(button, "Starting...");
    setText($("host-error"), "");
    try {
      const access = await post("/api/meetings", {name: $("host-name").value.trim(), email: $("host-email").value.trim()});
      roomId = access.room_id;
      role = "host";
      joinAccess = access;
      history.replaceState(null, "", `/m/${encodeURIComponent(roomId)}`);
      $("share-link").value = access.join_url;
      showEntry("share-screen");
    } catch (error) { setText($("host-error"), error.message); }
    finally { button.disabled = false; setText(button, "Start meeting"); }
  };
  $("copy-link-button").onclick = async () => {
    try { await navigator.clipboard.writeText($("share-link").value); setText($("copy-link-button"), "Copied"); }
    catch (error) { showToast(`Could not copy link: ${escapeHtml(error.message)}`, "err"); }
  };
  $("share-join-button").onclick = () => {
    if (joinAccess) join(joinAccess, joinAccess);
  };
  $("guest-join-button").onclick = async () => {
    const button = $("guest-join-button");
    button.disabled = true;
    setText(button, "Asking to join…");
    setText($("guest-error"), "");
    try {
      await post(`/api/meetings/${encodeURIComponent(roomId)}/request`,
        {name: $("guest-name").value.trim(), email: $("guest-email").value.trim()});
      setText($("waiting-room-label"), `Meeting ${roomId}`);
      showEntry("waiting-screen");
      setWaitingState("waiting");
      clearInterval(waitingTimer);
      waitingTimer = setInterval(pollAdmission, 1500);
      pollAdmission();
    } catch (error) { setText($("guest-error"), error.message); }
    finally { button.disabled = false; setText(button, "Ask to join"); }
  };
  $("waiting-cancel-button").onclick = async () => {
    clearInterval(waitingTimer);
    if (!joinAccess) {
      try { await post(`/api/meetings/${encodeURIComponent(roomId)}/cancel`, {}); } catch (_) { }
    }
    location.href = "/";
  };
  $("waiting-retry-button").onclick = () => pollAdmission();
  $("share-meeting-link-button").onclick = async () => {
    const link = `${location.origin}/m/${encodeURIComponent(roomId)}`;
    try { await navigator.clipboard.writeText(link); announce("Meeting link copied."); }
    catch (error) { showToast(`Could not copy link: ${escapeHtml(error.message)}`, "err"); }
  };
  $("mic-button").onclick = async () => {
    if (!room) return;
    const enabled = room.localParticipant.isMicrophoneEnabled;
    try { await room.localParticipant.setMicrophoneEnabled(!enabled); }
    catch (error) { showToast(`Microphone is off. ${escapeHtml(mediaProblem(error, "microphone"))}`, "warn"); }
    rebindLocalMeter();
    renderMicButton();
    updateTileFlags();
    announce(enabled ? "Microphone muted." : "Microphone on.");
  };
  $("camera-button").onclick = async () => {
    if (!room) return;
    const button = $("camera-button");
    button.disabled = true;
    const enabled = room.localParticipant.isCameraEnabled;
    try {
      await room.localParticipant.setCameraEnabled(!enabled);
      const publication = room.localParticipant.getTrackPublication(LiveKit.Track.Source.Camera);
      setVideoTrack(me, publication && (publication.videoTrack || publication.track));
      renderCameraButton();
      announce(enabled ? "Camera off." : "Camera on.");
    } catch (error) {
      renderCameraButton();
      showToast(`Camera is off. ${escapeHtml(mediaProblem(error, "camera"))}`, "warn");
    } finally { button.disabled = false; }
  };
  $("check-devices-button").onclick = () => startDeviceCheck();
  $("check-mic").onchange = () => { devPrefs.audioinput = $("check-mic").value; saveDevPrefs(); startDeviceCheck("audioinput"); };
  $("check-cam").onchange = () => { devPrefs.videoinput = $("check-cam").value; saveDevPrefs(); startDeviceCheck("videoinput"); };
  $("check-spk").onchange = () => { devPrefs.audiooutput = $("check-spk").value; saveDevPrefs(); };
  $("check-camera-on").onchange = () => { devPrefs.cameraOn = $("check-camera-on").checked; saveDevPrefs(); };
  $("check-test-speaker").onclick = () => testSpeaker("check-error");
  $("mic-chevron").onclick = () => toggleDeviceMenu("menu-mic");
  $("camera-chevron").onclick = () => toggleDeviceMenu("menu-cam");
  $("test-speaker-button").onclick = () => testSpeaker("menu-error");
  $("audio-button").onclick = async () => { try { await room.startAudio(); } catch (_) { } renderAudioButton(); };
  document.addEventListener("click", event => {
    if (!deviceMenuOpen()) return;
    const inside = n => n && (n === event.target || n.contains(event.target));
    if (!inside($("device-menu")) && !inside($("mic-chevron")) && !inside($("camera-chevron"))) closeDeviceMenu();
  });
  $("notes-button").onclick = toggleNotes;
  $("live-button").onclick = goLive;
  $("captions-button").onclick = () => setCaptions(!captionsOn);
  $("captions").addEventListener("scroll", () => {
    const box = $("captions");
    capFollow = box.scrollHeight - box.scrollTop - box.clientHeight < 12;
    if (capFollow) newCount = 0;
    renderLive();
  });
  $("agent-button").onclick = () => togglePanel("agent");
  $("people-button").onclick = () => togglePanel("people");
  $("info-button").onclick = () => togglePanel("info");
  $("panel-close").onclick = closePanel;
  $("panel-back").onclick = () => showPanel("agent");
  $("panel-popout").onclick = () => openInsights(panelView === "explain" ? "how" + (explainSel ? "=" + encodeURIComponent(explainSel) : "") : "");
  $("notes-off-toggle").onclick = toggleNotes;
  $("link-insights").onclick = () => showPanel("insights");
  $("link-explain").onclick = () => showPanel("explain");
  $("finalize-button").onclick = finalize;
  $("copy-button").onclick = copyFinal;
  $("report-button").onclick = viewFinalReport;
  $("email-opt-in").onchange = () => { emailChoiceDirty = true; setText($("email-choice-result"), ""); };
  $("delivery-email").oninput = () => { emailChoiceDirty = true; setText($("email-choice-result"), ""); };
  $("save-email-choice").onclick = saveEmailChoice;
  $("end-cancel").onclick = closeEndDialog;
  $("end-keep-open").onclick = closeEndDialog;
  $("end-backdrop").onclick = closeEndDialog;
  $("end-without-email").onclick = endMeeting;
  $("end-confirm").onclick = endMeeting;
  $("end-copy-transcript").onclick = async () => {
    try {
      await copyText(endEmailBody);
      endCopied = true;
      $("end-email-link").classList.remove("disabled");
      $("end-email-link").setAttribute("aria-disabled", "false");
      $("end-mail-limit").classList.remove("hidden");
      setText($("end-mail-limit"), endNeedsCopy
        ? "Copied. Open the addressed draft, then paste and send it in your mail app. End the meeting here when you're ready."
        : "Copied. You can paste the transcript if your mail app does not open. End the meeting here when you're ready.");
    } catch (error) { setText($("end-error"), `Could not copy transcript: ${error.message}`); }
  };
  $("end-email-link").onclick = event => {
    if (endNeedsCopy && !endCopied) { event.preventDefault(); return; }
    // Opening a mail app can fail silently, so ending the meeting requires a separate click.
  };
  $("leave-button").onclick = async () => {
    if (role === "host" && roomId) await showEndDialog();
    else await endMeeting();
  };
  document.addEventListener("keydown", event => {
    if (!$("end-dialog").classList.contains("hidden")) {
      if (event.key === "Escape") { closeEndDialog(); return; }
      if (event.key === "Tab") {
        const nodes = [...$("end-dialog").querySelectorAll(FOCUSABLE)]
          .filter(node => node.offsetParent !== null || node === document.activeElement);
        if (nodes.length) {
          const first = nodes[0], last = nodes[nodes.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }
      return;
    }
    const tag = event.target && event.target.tagName;
    if (!["INPUT", "TEXTAREA", "SELECT"].includes(tag) && !event.ctrlKey && !event.metaKey && !event.altKey
        && !$("meeting").classList.contains("hidden")) {
      const key = String(event.key).toLowerCase();
      if (key === "l") goLive();
      else if (key === "c") setCaptions(!captionsOn);
    }
    if (event.key === "Escape" && deviceMenuOpen()) { const from = $("mic-chevron"); closeDeviceMenu(); from.focus(); return; }
    if (event.key === "Escape" && panelView) closePanel();
  });
  const initialRoom = location.pathname.match(/^\/m\/([^/]+)\/?$/);
  if (initialRoom) {
    roomId = decodeURIComponent(initialRoom[1]);
    role = "guest";
    showEntry("guest-setup");
    api(`/api/meetings/${encodeURIComponent(roomId)}/status`).then(status => {
      if (status.role === "host" && status.status === "admitted") {
        role = "host";
        joinAccess = status;
        $("share-link").value = `${location.origin}/m/${encodeURIComponent(roomId)}`;
        showEntry("share-screen");
      } else if (status.status === "waiting") {
        setText($("waiting-room-label"), `Meeting ${roomId}`);
        showEntry("waiting-screen");
        setWaitingState("waiting");
        waitingTimer = setInterval(pollAdmission, 1500);
      } else if (status.status === "admitted") {
        setText($("waiting-room-label"), `Meeting ${roomId}`);
        connectAdmittedGuest(status);
      } else if (status.status === "denied") {
        setText($("guest-error"), "The host did not admit this request.");
      }
    }).catch(() => {});
  } else {
    showEntry("home-screen");
    if (new URLSearchParams(location.search).has("ended"))
      setText($("home-error"), "The host ended the meeting.");
  }
})();
