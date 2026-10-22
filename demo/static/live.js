(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const setText = (node, value) => { node.textContent = value; };
  const LiveKit = window.LivekitClient;
  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const MIC_OFF_SVG = '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28m-4.02.17c0-.06.02-.11.02-.17V5a3 3 0 0 0-6 0v.18l5.98 5.99M4.27 3 3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3Z"/></svg>';

  let room = null, me = null, eventSource = null;
  let participants = {};
  let finalized = false, readyForFinal = false, finalizedCount = null, contributorCount = null;
  let myNotesOn = false, sensitivePaused = false, sensitiveSeen = false;
  let speaking = new Set(), muted = new Map();
  const connectedPeople = new Set();
  const videoTracks = new Map(), videoMuted = new Set();
  let toastTimer = null, meRefreshTimer = null, drawerLastFocus = null;
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
    $("share-meeting-link-button").classList.remove("hidden");
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
      tile.querySelector(".muted-badge").classList.toggle("hidden", !connected || !isMuted);
      setText(tile.querySelector(".tile-mic"), !connected ? "Not connected yet" : isMuted ? "Muted" : "");
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
      grid.append(element("p", "grid-empty", "Waiting for people to join…"));
      return;
    }
    for (const [identity, p] of members) {
      const on = notesOn(p);
      const tile = element("div", "tile" + (identity === me ? " self" : ""));
      const notes = element("span", "tile-notes" + (on ? " on" : ""), on ? "Notes on" : "Notes off");
      notes.prepend(element("span", "dot"));
      const avatar = element("div", "avatar", initials(p.name || identity));
      const badge = element("span", "muted-badge hidden");
      badge.innerHTML = MIC_OFF_SVG;
      avatar.append(badge);
      const info = element("div", "tile-info");
      info.append(element("span", "tile-name", `${p.name || identity}${identity === me ? " (you)" : ""}`));
      info.append(element("span", "tile-mic", ""));
      tile.append(notes, avatar, info);
      grid.append(tile);
      tileEls[identity] = tile;
    }
    updateTileFlags();
    for (const identity of Object.keys(tileEls)) updateVideoTile(identity);
  }

  function renderNotesControl() {
    const button = $("notes-button");
    const paused = sensitivePaused && !finalized;
    button.classList.toggle("on", myNotesOn);
    button.classList.toggle("paused", paused);
    button.disabled = finalized;
    button.setAttribute("aria-pressed", String(myNotesOn));
    const label = finalized ? "Notes finished" : myNotesOn ? "Turn off notes" : "Turn on notes";
    setText($("notes-label"), label);
    button.setAttribute("aria-label", label);
    button.title = label;
    const shortStatus = $("capture-status");
    shortStatus.className = "capture-status" + (paused ? " paused" : myNotesOn ? " on" : "");
    if (finalized) setText(shortStatus, "Your notes are finished.");
    else if (paused) setText(shortStatus, "Your notes paused. Pending text was discarded.");
    else if (myNotesOn) setText(shortStatus, "Your audio is being transcribed locally for notes.");
    else setText(shortStatus, "Your notes are off. Others can still hear you.");
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

  function renderDrawer() {
    const paused = sensitivePaused && !finalized;
    const subtitle = $("drawer-subtitle");
    if (finalized) setText(subtitle, "Your notes are finished.");
    else if (paused) setText(subtitle, "Notes are paused for you after a sensitive pause.");
    else if (myNotesOn) setText(subtitle, "Notes are on — capture runs only for you.");
    else setText(subtitle, "Notes are off.");
    const explanation = $("note-state-explainer");
    if (finalized) setText(explanation, "Your notes are finished. Your speech can no longer be added to the transcript.");
    else if (paused) setText(explanation, "The local filter paused your notes and discarded the pending text. Nothing new is added until you restart notes yourself.");
    else if (myNotesOn) setText(explanation, "The meeting host is transcribing your audio for notes.");
    else setText(explanation, "Notes are off for you. The call still sends your audio to other people when your microphone is on.");

    const status = $("finalize-status");
    $("finalize-button").classList.toggle("hidden", finalized);
    $("report-button").classList.toggle("hidden", !readyForFinal);
    $("copy-button").classList.toggle("hidden", !readyForFinal);
    $("email-choice").classList.toggle("hidden", !finalized);
    if (!emailChoiceDirty) {
      $("delivery-email").value = deliveryEmail;
      $("email-opt-in").checked = emailOptedIn;
    }
    if (!readyForFinal) {
      $("copy-result").className = "waiting";
      setText($("copy-result"), "");
    }
    if (readyForFinal) setText(status, "The final transcript is ready to copy.");
    else if (finalized) setText(status, finalizedCount != null && contributorCount != null
      ? `Waiting for other contributors — ${finalizedCount} of ${contributorCount} finished.`
      : "Waiting for other contributors to finish their notes.");
    else setText(status, "Finish your notes when you are ready. Finishing keeps notes off.");
  }

  function renderAll() {
    renderTiles();
    renderNotesControl();
    renderDrawer();
    renderKept();
    renderViews(false);
  }

  function applyMe(data) {
    if (!data) return;
    if (data.identity) me = data.identity;
    if (data.participants) participants = data.participants;
    if (typeof data.finalized === "boolean") finalized = data.finalized;
    if (typeof data.ready_for_final === "boolean") readyForFinal = data.ready_for_final;
    if (typeof data.finalized_count === "number") finalizedCount = data.finalized_count;
    if (typeof data.contributor_count === "number") contributorCount = data.contributor_count;
    if (typeof data.delivery_email === "string") deliveryEmail = data.delivery_email;
    if (typeof data.email_opted_in === "boolean") emailOptedIn = data.email_opted_in;
    if (Array.isArray(data.kept_out_events)) keptEvents = data.kept_out_events;
    else if (Array.isArray(data.kept_out)) {
      keptEvents = data.kept_out.map(item => ({ id: item.id, seq: item.seq, category: item.category,
        family: item.trail && item.trail.family, before: item.trail && item.trail.before,
        after: item.trail && item.trail.after, held_s: item.trail && item.trail.held_s,
        action: item.trail && item.trail.family === "retro" ? "removed_after_approval" : "kept_out" }));
    }
    if (data.insights && typeof data.insights.hold_seconds === "number") holdSeconds = data.insights.hold_seconds;
    if (data.insights) insightsData = data.insights;
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
  }

  async function refreshMe(immediate) {
    if (!immediate) {
      clearTimeout(meRefreshTimer);
      meRefreshTimer = setTimeout(() => refreshMe(true), 1500);
      return;
    }
    meRefreshTimer = null;
    try { applyMe(await api("/api/me?summary=1")); } catch (_) { }
  }

  function mergeProgress(message) {
    let changed = false;
    if (typeof message.finalized === "boolean") { finalized = message.finalized; changed = true; }
    if (typeof message.ready_for_final === "boolean") { readyForFinal = message.ready_for_final; changed = true; }
    if (typeof message.finalized_count === "number") { finalizedCount = message.finalized_count; changed = true; }
    if (typeof message.contributor_count === "number") { contributorCount = message.contributor_count; changed = true; }
    if (changed) { renderNotesControl(); renderDrawer(); }
  }

  function connectStream() {
    eventSource = new EventSource("/stream");
    eventSource.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.type === "participants") applyMe({ participants: message.participants });
      else if (message.type === "service") setConnection(message.status, "warn");
      else if (message.type === "snapshot") {
        myLines.clear();
        for (const line of message.lines || []) myLines.set(line.id, line);
        renderViews(false);
      } else if (message.type === "transcript") {
        for (const change of message.changes || []) {
          if (change.kind === "committed" && change.line) myLines.set(change.line.id, change.line);
          else if (change.kind === "removed") myLines.delete(change.id);
        }
        renderViews(false);
      } else if (message.type === "status") {
        const { type: _t, ...fresh } = message;
        insightsData = fresh;
        renderViews(false);
      }
      // The compact meeting view does not render interim transcript events.
      mergeProgress(message);
      refreshMe(message.type === "status" || message.type === "transcript");
    };
    eventSource.onerror = () => setConnection("Reconnecting…", "warn");
    eventSource.onopen = () => setConnection("Live · local room", "online");
  }

  function renderMicButton() {
    const isMuted = room ? !room.localParticipant.isMicrophoneEnabled : false;
    const button = $("mic-button");
    button.classList.toggle("muted-on", isMuted);
    button.setAttribute("aria-pressed", String(!isMuted));
    button.querySelector(".icon-mic").classList.toggle("hidden", isMuted);
    button.querySelector(".icon-mic-off").classList.toggle("hidden", !isMuted);
    setText($("mic-label"), isMuted ? "Unmute" : "Mute");
  }

  // ------------------------------------------------------------ devices, level meter, notes-engine status
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
  function drawWave(canvas, values) {
    const c = ctx2d(canvas);
    if (!c) return;
    const on = cssVar("--blue", "#1a73e8"), off = cssVar("--outline", "#dadce0");
    const w = canvas.width, h = canvas.height, n = values.length, gap = 2;
    const bw = Math.max(1, Math.floor((w - gap * (n - 1)) / n));
    c.clearRect(0, 0, w, h);
    values.forEach((v, i) => {
      const bh = Math.max(2, Math.round(h * Math.min(1, v)));
      c.fillStyle = v > 0.04 ? on : off;
      c.fillRect(i * (bw + gap), Math.round((h - bh) / 2), bw, bh);
    });
  }
  // Web Audio level meter over a MediaStream. targets() returns the canvases to draw into.
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
      for (const canvas of targets()) { drawWave(canvas, values); canvas.dataset.level = rms.toFixed(3); }
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
      for (const canvas of targets()) drawWave(canvas, new Array(BARS).fill(0));
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

  // ---- device check before joining (create-meeting and ask-to-join screens)
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
        if (!check.meter) check.meter = createMeter(() => [$("check-meter")], renderCheckStatus);
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

  // ---- in-call device menu (opened from the Devices button in the control bar)
  const localMeter = createMeter(() => (deviceMenuOpen() ? [$("menu-meter")] : []), state => {
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
    const stream = room ? localMicStream() : null;
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
  function openDeviceMenu() {
    $("device-menu").classList.remove("hidden");
    $("devices-button").setAttribute("aria-expanded", "true");
    setText($("menu-error"), "");
    rebindLocalMeter();
    renderDeviceMenu().then(() => {
      const first = $("menu-mic").querySelector("button");
      if (first) first.focus();
    });
  }
  function closeDeviceMenu() {
    if (!deviceMenuOpen()) return;
    $("device-menu").classList.add("hidden");
    $("devices-button").setAttribute("aria-expanded", "false");
  }
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

  // ---- notes engine status (text-free, from GET /api/diagnostics; hidden when the server has no such endpoint)
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
    diagTimer = setInterval(pollDiagnostics, 1000);
    pollDiagnostics();
  }
  function stopDiagnostics() { clearInterval(diagTimer); diagTimer = null; }

  // ---- kept-out placeholders: the owner's own kept-out or removed lines, never their words
  let keptEvents = [], holdSeconds = 0;
  const keptOpen = new Set();
  function clock(t) {
    const total = Math.max(0, Math.round(Number(t) || 0)), pad = n => (n < 10 ? "0" : "") + n;
    return pad(Math.floor(total / 60)) + ":" + pad(total % 60);
  }
  function keptLabel(category) {
    const views = window.OTRViews;
    return views ? views.shortLabel(category) : String(category || "Other");
  }
  function keptFacts(item) {
    const views = window.OTRViews;
    if (views) return views.explainFacts({ category: item.category, trail: { family: item.family, before: item.before, after: item.after, held_s: item.held_s } }, holdSeconds);
    return [["Why", "This line was kept out of your notes."]];
  }
  function keptItem(item, index, prefix) {
    const key = String(item.id || index);
    const open = keptOpen.has(key);
    const li = element("li", "kept-item");
    li.setAttribute("data-category", item.category);
    const toggle = element("button", "kept-toggle");
    toggle.type = "button";
    toggle.setAttribute("data-key", key);
    toggle.setAttribute("aria-expanded", String(open));
    const detailId = `${prefix}-detail-${index}`;
    if (open) toggle.setAttribute("aria-controls", detailId);
    toggle.append(element("span", null, `${item.action === "removed_after_approval" ? "Removed" : "Kept out"}, ${keptLabel(item.category)}`),
      element("span", "kept-when", typeof item.t === "number" ? clock(item.t) : ""));
    toggle.onclick = () => {
      if (keptOpen.has(key)) keptOpen.delete(key); else keptOpen.add(key);
      renderKept();
      renderRealtime();
      const again = $(prefix === "rt" ? "rt-list" : "kept-out-list").querySelector(`button[data-key="${key}"]`);
      if (again) again.focus();
    };
    li.append(toggle);
    if (open) {
      const dl = element("dl", "kept-detail");
      dl.id = detailId;
      for (const [name, value] of keptFacts(item)) {
        const group = element("div");
        group.append(element("dt", null, name), element("dd", null, value));
        dl.append(group);
      }
      li.append(dl);
    }
    return li;
  }
  function renderKept() {
    const list = $("kept-out-list");
    $("kept-out-empty").classList.toggle("hidden", keptEvents.length > 0);
    list.replaceChildren();
    keptEvents.forEach((item, index) => list.append(keptItem(item, index, "kept")));
  }

  // ---- the Realtime, Insights and How it decides views (shared views.js; only the owner's own data, never kept-out text)
  const myLines = new Map();
  let insightsData = null, viewsTab = "realtime", explainSel = null, viewSignature = "";
  function viewsOpen() { return !$("views-panel").classList.contains("hidden"); }
  function renderRealtime() {
    if (!viewsOpen()) return;
    const rows = [...myLines.values()].map(line => ({ type: "line", seq: line.seq || 0, line }))
      .concat(keptEvents.map(item => ({ type: "kept", seq: item.seq || 0, item })));
    rows.sort((x, y) => x.seq - y.seq);
    $("rt-empty").classList.toggle("hidden", rows.length > 0);
    const list = $("rt-list");
    list.replaceChildren();
    rows.forEach((row, index) => {
      if (row.type === "kept") { list.append(keptItem(row.item, index, "rt")); return; }
      const li = element("li", "rt-line");
      li.append(element("b", null, row.line.name || "You"), document.createTextNode(row.line.text || ""));
      list.append(li);
    });
  }
  function renderViews(force) {
    if (!viewsOpen()) return;
    const views = window.OTRViews;
    for (const name of ["realtime", "insights", "explain"]) {
      const on = viewsTab === name;
      $("vp-" + name).classList.toggle("hidden", !on);
      $("vtab-" + name).classList.toggle("on", on);
      $("vtab-" + name).setAttribute("aria-selected", String(on));
    }
    if (viewsTab === "realtime") { renderRealtime(); return; }
    if (!views || !insightsData) return;
    const signature = JSON.stringify([viewsTab, insightsData, explainSel]);
    if (!force && signature === viewSignature) return;
    viewSignature = signature;
    if (viewsTab === "insights") views.renderInsights($("vp-insights"), Object.assign({}, insightsData, { labels: { approved: "In your notes" } }));
    else views.renderExplain($("vp-explain"), { selected: explainSel, item: null, counts: insightsData.kept_out, holdSeconds: insightsData.hold_seconds },
      { onSelect: key => { explainSel = key; renderViews(true); } });
  }
  function openViews() {
    $("views-panel").classList.remove("hidden");
    $("views-button").setAttribute("aria-expanded", "true");
    renderViews(true);
    $("views-close").focus();
  }
  function closeViews() {
    $("views-panel").classList.add("hidden");
    $("views-button").setAttribute("aria-expanded", "false");
    $("views-button").focus();
  }


  async function join(accessOverride = null, configOverride = null) {
    if (joinInProgress) return false;
    joinInProgress = true;
    const button = $("join-button");
    setText($("join-error"), "");
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
      // Close-talk capture: no automatic gain (it lifts room noise), keep noise suppression and echo cancellation.
      const roomOptions = { adaptiveStream: true, dynacast: true,
        audioCaptureDefaults: { autoGainControl: false, noiseSuppression: true, echoCancellation: true } };
      if (devPrefs.audioinput) roomOptions.audioCaptureDefaults = Object.assign({}, roomOptions.audioCaptureDefaults, { deviceId: devPrefs.audioinput });
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
      room.on(LiveKit.RoomEvent.ActiveDeviceChanged, kind => { if (kind === "audioinput") rebindLocalMeter(); });
      room.on(LiveKit.RoomEvent.MediaDevicesError, error =>
        showToast(escapeHtml(mediaProblem(error, "microphone or camera")), "warn"));
      await room.connect(config.url, access.token);
      for (const identity of room.remoteParticipants.keys()) connectedPeople.add(identity);
      setText($("room-chip"), `Room ${config.room}`);
      $("room-chip").classList.remove("hidden");
      for (const screen of ENTRY_SCREENS) $(screen).classList.add("hidden");
      $("meeting").classList.remove("hidden");
      $("control-bar").classList.remove("hidden");
      setText($("meeting-room-name"), `Meeting ${config.room}`);
      startLobby();
      startRoomStatus();
      renderMicButton();
      renderCameraButton();
      setConnection("Live · local room", "online");
      api("/api/me?summary=1").then(applyMe).catch(() => {});
      connectStream();
      bindDeviceChange();
      startDiagnostics();
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
        room.localParticipant.setCameraEnabled(true).then(() => renderCameraButton()).catch(error => {
          renderCameraButton();
          showToast(`Camera is off. ${escapeHtml(mediaProblem(error, "camera"))}`, "warn");
        });
      }
      return true;
    } catch (error) {
      setText($("join-error"), accessOverride ? "Could not connect to the call." : (error.message || "Could not connect to the meeting."));
      if (accessOverride) showToast("Could not join the meeting. Try again or ask the host to check the connection.", "err");
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
      renderDrawer();
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
    if (!$("notes-drawer").hidden) closeDrawer();
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

  function openDrawer() {
    const drawer = $("notes-drawer");
    drawer.hidden = false;
    document.body.classList.add("drawer-open");
    $("drawer-backdrop").classList.remove("hidden");
    requestAnimationFrame(() => drawer.classList.add("open"));
    $("drawer-button").setAttribute("aria-expanded", "true");
    drawerLastFocus = document.activeElement;
    $("drawer-close").focus();
  }

  function closeDrawer() {
    const drawer = $("notes-drawer");
    drawer.classList.remove("open");
    $("drawer-button").setAttribute("aria-expanded", "false");
    document.body.classList.remove("drawer-open");
    setTimeout(() => {
      drawer.hidden = true;
      $("drawer-backdrop").classList.add("hidden");
    }, 240);
    if (drawerLastFocus && drawerLastFocus.isConnected) drawerLastFocus.focus();
    drawerLastFocus = null;
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
    setText(button, "Creating…");
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
    finally { button.disabled = false; setText(button, "Create meeting"); }
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
    await room.localParticipant.setMicrophoneEnabled(!enabled);
    renderMicButton();
    updateTileFlags();
    rebindLocalMeter();
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
      devPrefs.cameraOn = !enabled;
      saveDevPrefs();
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
  $("check-test-speaker").onclick = () => testSpeaker("check-speaker-status");
  $("menu-test-speaker").onclick = () => testSpeaker("menu-speaker-status");
  $("devices-button").onclick = () => { if (deviceMenuOpen()) closeDeviceMenu(); else openDeviceMenu(); };
  document.addEventListener("click", event => {
    if (!deviceMenuOpen()) return;
    if ($("device-menu").contains(event.target) || $("devices-button").contains(event.target)) return;
    closeDeviceMenu();
  });
  $("popout-button").onclick = () => window.open("/insights", "otr-insights", "popup=yes,width=520,height=760");
  $("views-button").onclick = () => { if (viewsOpen()) closeViews(); else openViews(); };
  $("views-close").onclick = closeViews;
  for (const name of ["realtime", "insights", "explain"]) $("vtab-" + name).onclick = () => { viewsTab = name; renderViews(true); };
  $("notes-button").onclick = toggleNotes;
  $("drawer-button").onclick = () => {
    if ($("notes-drawer").hidden) openDrawer();
    else closeDrawer();
  };
  $("drawer-close").onclick = closeDrawer;
  $("drawer-backdrop").onclick = closeDrawer;
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
    if (event.key === "Escape" && deviceMenuOpen()) { closeDeviceMenu(); $("devices-button").focus(); return; }
    if (event.key === "Escape" && viewsOpen() && $("notes-drawer").hidden && $("end-dialog").classList.contains("hidden")) { closeViews(); return; }
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
    const drawer = $("notes-drawer");
    if (event.key === "Escape" && !drawer.hidden) { closeDrawer(); return; }
    if (!drawer.hidden && event.key === "Tab") {
      const nodes = [...drawer.querySelectorAll(FOCUSABLE)]
        .filter(node => node.offsetParent !== null || node === document.activeElement);
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
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
