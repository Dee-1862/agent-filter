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
  let myNotesOn = false, sensitivePaused = false, sensitiveSeen = false;
  let speaking = new Set(), muted = new Map();
  const videoTracks = new Map(), videoMuted = new Set();
  let toastTimer = null, meRefreshTimer = null, clockTimer = null;
  let deliveryEmail = "", emailOptedIn = false, emailChoiceDirty = false;
  let endDialogLastFocus = null, endEmailBody = "", endNeedsCopy = false, endCopied = false;
  let roomId = null, role = null, joinAccess = null, lobbyTimer = null, waitingTimer = null, roomTimer = null;
  const ENTRY_SCREENS = ["home-screen", "host-setup", "guest-setup", "share-screen", "waiting-screen", "join"];
  function showEntry(id) {
    for (const screen of ENTRY_SCREENS) $(screen).classList.toggle("hidden", screen !== id);
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
  async function pollAdmission() {
    if (!roomId || role !== "guest") return;
    try {
      const status = await api(`/api/meetings/${encodeURIComponent(roomId)}/status`);
      if (status.status === "denied") {
        clearInterval(waitingTimer);
        showEntry("guest-setup");
        setText($("guest-error"), "The host did not admit this request.");
      } else if (status.status === "admitted") {
        clearInterval(waitingTimer);
        joinAccess = status;
        await join(status, status);
      }
    } catch (_) { /* Keep waiting through a transient connection failure. */ }
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
      tile.classList.toggle("speaking", speaking.has(identity));
      const isMuted = identity === me
        ? (room ? !room.localParticipant.isMicrophoneEnabled : false)
        : muted.get(identity) === true;
      const state = tile.querySelector(".mic-state");
      state.classList.toggle("muted", isMuted);
      state.setAttribute("aria-label", isMuted ? "Microphone off" : "Microphone on");
    }
  }

  function updateVideoTile(identity) {
    const tile = tileEls[identity];
    if (!tile) return;
    const track = videoMuted.has(identity) ? null : videoTracks.get(identity);
    const avatar = tile.querySelector(".avatar");
    const current = avatar.querySelector(".tile-video");
    if (current && current._livekitTrack !== track) {
      current._livekitTrack.detach(current);
      current.remove();
    }
    if (track && !avatar.querySelector(".tile-video")) {
      const video = document.createElement("video");
      video.className = "tile-video";
      video.autoplay = true;
      video.playsInline = true;
      video.muted = identity === me;
      video._livekitTrack = track;
      track.attach(video);
      avatar.prepend(video);
    }
    tile.classList.toggle("has-video", !!track);
  }

  function setVideoTrack(identity, track) {
    const old = videoTracks.get(identity);
    if (old && old !== track) {
      const tile = tileEls[identity];
      const video = tile && tile.querySelector(".tile-video");
      if (video) { old.detach(video); video.remove(); }
    }
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
    for (const tile of Object.values(tileEls)) {
      const video = tile.querySelector(".tile-video");
      if (video) video._livekitTrack.detach(video);
    }
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
      tile.append(avatar, mic, label);
      grid.append(tile);
      tileEls[identity] = tile;
    }
    updateTileFlags();
    for (const identity of Object.keys(tileEls)) updateVideoTile(identity);
  }

  function renderLines() {
    renderCaptions();
  }

  // ------------------------------------------------------------ Realtime captions (your approved lines + kept-out markers)
  function captionItems() {
    const items = [];
    let order = 0;
    for (const line of lines.values()) {
      if (!line.removed && isMyLine(line)) items.push({ type: "line", seq: line.seq || 0, order: order++, line });
    }
    for (const chip of chips.values()) items.push({ type: "chip", seq: chip.seq || 0, order: order++, chip });
    items.sort((a, b) => (a.seq - b.seq) || (a.order - b.order));
    return items;
  }
  let shownCaptions = 0;
  function renderCaptions() {
    const box = $("captions");
    const items = captionItems();
    box.replaceChildren();
    if (!items.length) {
      box.append(element("p", "cap-empty", "Lines you approve appear here after a short safety hold. Turn notes on to start."));
    }
    for (const item of items) {
      const row = element("div", "cap" + (item.type === "chip" ? " out" : ""));
      if (item.type === "line") {
        row.append(element("span", "who", item.line.name || "You"), element("span", "words", item.line.text));
        const remove = element("button", "remove", "Remove");
        remove.type = "button";
        remove.setAttribute("aria-label", `Remove line: ${item.line.text}`);
        remove.disabled = finalized;
        remove.onclick = () => removeLine(item.line.id, remove);
        row.append(remove);
      } else {
        row.append(Views.chip(item.chip.category, () => openMarker(item.chip)));
      }
      box.append(row);
    }
    if (items.length > shownCaptions && !capFollow) newCount += items.length - shownCaptions;
    shownCaptions = items.length;
    if (capFollow) box.scrollTop = box.scrollHeight;
    renderStageCaptions(items);
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
  function openMarker(chip) {
    explainSel = chip.category;
    explainItem = chip;
    showPanel("explain");
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
    if (Array.isArray(data.lines)) lines = indexLines(data.lines);
    if (typeof data.finalized === "boolean") finalized = data.finalized;
    if (typeof data.ready_for_final === "boolean") readyForFinal = data.ready_for_final;
    if (typeof data.finalized_count === "number") finalizedCount = data.finalized_count;
    if (typeof data.contributor_count === "number") contributorCount = data.contributor_count;
    if (data.redaction_counts) redactionCounts = data.redaction_counts;
    if (data.insights) insights = data.insights;
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
      } else if (message.type === "status") {
        const { type, ...rest } = message;
        insights = rest;
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

  async function join(accessOverride = null, configOverride = null) {
    const button = $("join-button");
    setText($("join-error"), "");
    const name = $("name").value.trim();
    if (!accessOverride && !name) {
      setText($("join-error"), "Enter a display name");
      return;
    }
    button.disabled = true;
    setText(button, "Joining…");
    setConnection("Joining…", "warn");
    try {
      const config = configOverride || await api("/api/config");
      const access = accessOverride || await post("/api/join", { name });
      me = access.identity;
      room = new LiveKit.Room({ adaptiveStream: true, dynacast: true });
      room.on(LiveKit.RoomEvent.TrackSubscribed, (track, publication, participant) => {
        if (track.kind === LiveKit.Track.Kind.Audio) {
          const media = track.attach();
          media.dataset.livekitAudio = "true";
          document.body.append(media);
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
        if (publication.source === LiveKit.Track.Source.Camera) {
          videoMuted.delete(me);
          setVideoTrack(me, publication.videoTrack || publication.track);
          renderCameraButton();
        }
      });
      room.on(LiveKit.RoomEvent.LocalTrackUnpublished, publication => {
        if (publication.source === LiveKit.Track.Source.Camera) {
          setVideoTrack(me, null);
          renderCameraButton();
        }
      });
      room.on(LiveKit.RoomEvent.ParticipantDisconnected, participant => {
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
      room.on(LiveKit.RoomEvent.Disconnected, () => setConnection("Disconnected", "off"));
      await room.connect(config.url, access.token);
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
      startRoomStatus();
      renderMicButton();
      renderCameraButton();
      setConnection("Live · local room", "online");
      api("/api/me").then(applyMe).catch(() => {});
      connectStream();
      room.localParticipant.setMicrophoneEnabled(true).then(() => {
        renderMicButton();
        updateTileFlags();
      }).catch(error => {
        renderMicButton();
        updateTileFlags();
        showToast(`Microphone is off. ${escapeHtml(error.message || "Allow microphone access to speak.")}`, "warn");
      });
    } catch (error) {
      setText($("join-error"), error.message);
      if (accessOverride) showToast(`Could not join the meeting: ${escapeHtml(error.message)}`, "err");
      setConnection("Not connected", "off");
      if (room) { room.disconnect(); room = null; }
      if (me && !accessOverride) { try { await post("/api/leave", {}); } catch (_) { } }
      me = null;
    } finally {
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
      $("end-copy-transcript").classList.toggle("hidden", !endNeedsCopy);
      const link = $("end-email-link");
      link.href = endNeedsCopy ? prefix : fullLink;
      link.classList.toggle("disabled", endNeedsCopy);
      link.setAttribute("aria-disabled", String(endNeedsCopy));
      $("end-email-review").classList.remove("hidden");
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
      clearInterval(waitingTimer);
      waitingTimer = setInterval(pollAdmission, 1500);
      pollAdmission();
    } catch (error) { setText($("guest-error"), error.message); }
    finally { button.disabled = false; setText(button, "Ask to join"); }
  };
  $("waiting-cancel-button").onclick = async () => {
    clearInterval(waitingTimer);
    try { await post(`/api/meetings/${encodeURIComponent(roomId)}/cancel`, {}); } catch (_) { }
    location.href = "/";
  };
  $("share-meeting-link-button").onclick = async () => {
    const link = `${location.origin}/m/${encodeURIComponent(roomId)}`;
    try { await navigator.clipboard.writeText(link); announce("Meeting link copied."); }
    catch (error) { showToast(`Could not copy link: ${escapeHtml(error.message)}`, "err"); }
  };
  $("mic-button").onclick = async () => {
    if (!room) return;
    const enabled = room.localParticipant.isMicrophoneEnabled;
    await room.localParticipant.setMicrophoneEnabled(!enabled);
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
      showToast(`Camera is off. ${escapeHtml(error.message || "Allow camera access to show video.")}`, "warn");
    } finally { button.disabled = false; }
  };
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
  $("end-copy-transcript").onclick = async () => {
    try {
      await copyText(endEmailBody);
      endCopied = true;
      $("end-email-link").classList.remove("disabled");
      $("end-email-link").setAttribute("aria-disabled", "false");
      setText($("end-mail-limit"), "Copied. Open the addressed draft, then paste and send it in your mail app.");
    } catch (error) { setText($("end-error"), `Could not copy transcript: ${error.message}`); }
  };
  $("end-email-link").onclick = event => {
    if (endNeedsCopy && !endCopied) { event.preventDefault(); return; }
    // The user's click opens a local mail app draft; the server never sends email.
    setTimeout(endMeeting, 0);
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
        waitingTimer = setInterval(pollAdmission, 1500);
      } else if (status.status === "admitted") {
        joinAccess = status;
        join(status, status);
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
