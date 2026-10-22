(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const text = (id, value) => { $(id).textContent = value; };
  let room = null, me = null, eventSource = null, participants = {}, lines = {};
  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
    return body;
  }
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function renderPeople() {
    const box = $("participants"); box.replaceChildren();
    const members = Object.entries(participants);
    text("participant-count", String(members.length));
    for (const [identity, p] of members) {
      const row = element("div", "person");
      row.append(element("span", "person-name", `${p.name || identity}${identity === me ? " (you)" : ""}`));
      row.append(element("span", `status ${p.recording ? "on" : ""}`,
        p.recording ? "RECORDING" : p.sensitive_paused ? "SENSITIVE PAUSE" : "NOT RECORDED"));
      box.append(row);
    }
    if (me && participants[me]) {
      const on = participants[me].recording;
      $("consent-panel").classList.toggle("on", on);
      text("my-status", on ? "Recording me" : participants[me].sensitive_paused ? "Paused for sensitive content" : "Not recorded");
      text("my-explanation", on ? "Your track is subscribed by the local notetaker. Approved lines may appear below." :
        participants[me].sensitive_paused ? "The notetaker stopped subscribing to your audio and discarded the pending line. Restart only when you are ready." :
          "Your audio is shared with meeting participants, but the notetaker is not subscribed to your track.");
      const button = $("consent-button");
      button.textContent = on ? "Stop recording me" : participants[me].sensitive_paused ? "Restart recording me" : "Start recording me";
      button.className = on ? "stop" : "start";
      text("pending", participants[me].sensitive_paused ?
        "Sensitive content was detected. The pending line was discarded and your capture is paused. Use your button to restart." :
        "No sensitive pause. Your button controls capture at any time.");
    }
  }
  function renderLines() {
    const box = $("transcript"); box.replaceChildren();
    const approved = Object.values(lines).filter(x => !x.removed);
    if (!approved.length) { box.append(element("div", "empty", "No approved transcript yet. Speech from people who are off is not transcribed.")); return; }
    for (const line of approved) {
      const row = element("div", "line");
      row.append(element("span", "speaker", line.name || line.speaker));
      row.append(element("span", "words", line.text));
      box.append(row);
    }
    box.scrollTop = box.scrollHeight;
  }
  function connectStream() {
    eventSource = new EventSource("/stream");
    eventSource.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.type === "participants") { participants = message.participants; renderPeople(); }
      if (message.type === "service") { text("connection", message.status); $("connection").className = "chip"; }
      if (message.type === "snapshot") {
        lines = Object.fromEntries(message.lines.map(line => [line.id, line]));
        renderLines();
      }
      if (message.type === "transcript") {
        for (const change of message.changes) {
          if (change.kind === "committed") lines[change.line.id] = change.line;
          if (change.kind === "removed") delete lines[change.id];
        }
        renderLines();
      }
    };
    eventSource.onerror = () => { text("connection", "Reconnecting…"); $("connection").className = "chip"; };
    eventSource.onopen = () => { text("connection", "Live · local room"); $("connection").className = "chip online"; };
  }
  async function join() {
    const button = $("join-button"); button.disabled = true;
    text("join-error", "");
    try {
      const name = $("name").value.trim();
      const config = await api("/api/config");
      const access = await post("/api/join", { name });
      me = access.identity;
      room = new LivekitClient.Room({ adaptiveStream: true, dynacast: true });
      room.on(LivekitClient.RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === LivekitClient.Track.Kind.Audio) {
          const media = track.attach();
          media.dataset.livekitAudio = "true";
          document.body.append(media);
        }
      });
      room.on(LivekitClient.RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach(media => media.remove());
      });
      await room.connect(config.url, access.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      room.on(LivekitClient.RoomEvent.Disconnected, () => {
        text("connection", "Disconnected"); $("connection").className = "chip";
      });
      text("room-name", config.room);
      $("join").classList.add("hidden"); $("meeting").classList.remove("hidden");
      const initial = await api("/api/me");
      participants = initial.participants;
      lines = Object.fromEntries(initial.lines.map(line => [line.id, line]));
      renderPeople(); renderLines(); connectStream();
    } catch (error) {
      text("join-error", error.message);
      if (room) { room.disconnect(); room = null; }
      if (me) { try { await post("/api/leave", {}); } catch (_) {} me = null; }
    } finally { button.disabled = false; }
  }
  $("join-button").onclick = join;
  $("name").onkeydown = event => { if (event.key === "Enter") join(); };
  $("consent-button").onclick = async () => {
    const button = $("consent-button"); button.disabled = true;
    try { await post("/api/consent", { recording: !participants[me].recording }); }
    catch (error) { alert(error.message); }
    finally { button.disabled = false; }
  };
  $("mic-button").onclick = async () => {
    if (!room) return;
    const enabled = room.localParticipant.isMicrophoneEnabled;
    await room.localParticipant.setMicrophoneEnabled(!enabled);
    text("mic-button", enabled ? "Unmute microphone" : "Mute microphone");
  };
  $("leave-button").onclick = async () => {
    if (me) { try { await post("/api/leave", {}); } catch (error) { console.error(error); } }
    if (eventSource) eventSource.close();
    if (room) await room.disconnect();
    location.reload();
  };
})();
