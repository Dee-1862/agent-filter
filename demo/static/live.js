(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const setText = (node, value) => { node.textContent = value; };
  const LiveKit = window.LivekitClient;
  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
  const MIC_OFF_SVG = '<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28m-4.02.17c0-.06.02-.11.02-.17V5a3 3 0 0 0-6 0v.18l5.98 5.99M4.27 3 3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3Z"/></svg>';

  let room = null, me = null, eventSource = null;
  let participants = {};
  let lines = new Map();
  let finalized = false, readyForFinal = false, finalizedCount = null, contributorCount = null;
  let redactionCounts = null;
  let myNotesOn = false, sensitivePaused = false, sensitiveSeen = false;
  let speaking = new Set(), muted = new Map();
  const videoTracks = new Map(), videoMuted = new Set();
  let toastTimer = null, meRefreshTimer = null, drawerLastFocus = null;
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
      tile.querySelector(".muted-badge").classList.toggle("hidden", !isMuted);
      setText(tile.querySelector(".tile-mic"), isMuted ? "Muted" : "");
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

  function renderLines() {
    const box = $("my-lines");
    box.replaceChildren();
    const mine = [...lines.values()].filter(line => !line.removed && isMyLine(line));
    $("my-lines-empty").classList.toggle("hidden", mine.length > 0);
    const badge = $("drawer-badge");
    badge.classList.toggle("hidden", !mine.length);
    setText(badge, String(mine.length));
    for (const line of mine) {
      const li = element("li", "line");
      li.append(element("span", "words", line.text));
      const remove = element("button", null, "✕");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove line: ${line.text}`);
      remove.disabled = finalized;
      remove.onclick = () => removeLine(line.id, remove);
      li.append(remove);
      box.append(li);
    }
  }

  function renderNotesControl() {
    const button = $("notes-button");
    const paused = sensitivePaused && !finalized;
    button.classList.toggle("on", myNotesOn);
    button.classList.toggle("paused", paused);
    button.disabled = finalized;
    button.setAttribute("aria-pressed", String(myNotesOn));
    if (finalized) setText($("notes-label"), "Notes finished");
    else if (paused) setText($("notes-label"), "Notes paused — restart");
    else if (myNotesOn) setText($("notes-label"), "Stop notes for me");
    else setText($("notes-label"), "Notes off");
    const shortStatus = $("capture-status");
    shortStatus.className = "capture-status" + (paused ? " paused" : myNotesOn ? " on" : "");
    if (finalized) setText(shortStatus, "Your notes are finished.");
    else if (paused) setText(shortStatus, "Your notes paused. Pending text was discarded.");
    else if (myNotesOn) setText(shortStatus, "Your audio is being transcribed locally for notes.");
    else setText(shortStatus, "Your notes are off. Others can still hear you.");
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
    else if (myNotesOn) setText(explanation, "The local meeting host is transcribing your audio. Approved lines appear below after a short safety hold.");
    else setText(explanation, "Notes are off for you. The call still sends your audio to other people when your microphone is on.");

    const list = $("drawer-people");
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
    renderRedactionCounts();
    if (!readyForFinal) {
      $("copy-result").className = "waiting";
      setText($("copy-result"), "");
    }
    if (readyForFinal) setText(status, "The final transcript is ready to copy.");
    else if (finalized) setText(status, finalizedCount != null && contributorCount != null
      ? `Waiting for other contributors — ${finalizedCount} of ${contributorCount} finished.`
      : "Waiting for other contributors to finish their notes.");
    else setText(status, "Review or remove lines above, then finish your notes. Finishing keeps notes off.");
  }

  function renderAll() {
    renderTiles();
    renderLines();
    renderNotesControl();
    renderDrawer();
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
    try { applyMe(await api("/api/me")); } catch (_) { }
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
        if (Array.isArray(message.lines)) lines = indexLines(message.lines);
        renderLines();
      } else if (message.type === "transcript") {
        let changed = false;
        for (const change of message.changes || []) {
          if (change.kind === "committed" && change.line && isMyLine(change.line)) {
            lines.set(change.line.id, change.line);
            changed = true;
          }
          if (change.kind === "removed" && lines.delete(change.id)) changed = true;
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
    button.querySelector(".icon-mic").classList.toggle("hidden", isMuted);
    button.querySelector(".icon-mic-off").classList.toggle("hidden", !isMuted);
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
      setText($("meeting-room-name"), `Meeting ${config.room}`);
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

  function openDrawer() {
    const drawer = $("notes-drawer");
    drawer.hidden = false;
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
  $("drawer-button").onclick = () => {
    if ($("notes-drawer").hidden) openDrawer();
    else closeDrawer();
  };
  $("drawer-close").onclick = closeDrawer;
  $("drawer-backdrop").onclick = closeDrawer;
  $("finalize-button").onclick = finalize;
  $("copy-button").onclick = copyFinal;
  $("report-button").onclick = viewFinalReport;
  $("leave-button").onclick = async () => {
    clearInterval(lobbyTimer);
    clearInterval(waitingTimer);
    clearInterval(roomTimer);
    if (me) {
      try {
        if (role === "host" && roomId) await post(`/api/meetings/${encodeURIComponent(roomId)}/end`, {});
        else await post("/api/leave", {});
      } catch (error) { showToast(`Could not leave: ${escapeHtml(error.message)}`, "err"); return; }
    }
    if (eventSource) eventSource.close();
    if (room) await room.disconnect();
    location.href = "/";
  };
  document.addEventListener("keydown", event => {
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
