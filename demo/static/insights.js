/* Pop-out Insights and explanation page for the consent meeting (served at /insights and /m/<room>/insights).
 *
 * Privacy contract: this page only ever receives kinds, counts, rule families, state names, timings and the
 * participant's own display state from GET /api/me and GET /api/diagnostics. The server never sends the text of
 * anything that was kept out, so there is nothing here to leak. DOM is built with textContent only; there are no
 * inline styles or handlers (strict CSP). It polls /api/me with the same cookie as the meeting page.
 */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const Views = window.OTRViews;
  const POLL_MS = Number(window.OTR_POLL_MS) || 1500, DIAG_MS = 3000;
  const HIDDEN_STOP_MS = Number(window.OTR_HIDDEN_STOP_MS) || 60000;

  let tab = "insights", highlight = "";
  let me = null, diag = null, diagState = "wait";   // diagState: wait | ok | none
  let session = "wait";                              // wait | ok | none | gone
  let sessionDetail = "";
  let conn = "connecting";                           // connecting | live | lost
  let timer = null, stopped = false, hiddenAt = document.hidden ? Date.now() : 0, lastDiag = 0, busy = false;
  const openCodes = new Set();
  const signatures = {};

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function clock(t) {
    const total = Math.max(0, Math.round(Number(t) || 0)), pad = n => (n < 10 ? "0" : "") + n;
    return pad(Math.floor(total / 60)) + ":" + pad(total % 60);
  }
  function setText(node, value) { if (node.textContent !== value) node.textContent = value; }
  // Re-render a block only when its data changed, so open details and text selection survive the polling.
  function renderIfChanged(name, data, draw) {
    const sig = JSON.stringify(data);
    if (signatures[name] === sig) return;
    signatures[name] = sig;
    draw();
  }

  // ---------------------------------------------------------------- data
  async function getJson(path) {
    try {
      const response = await fetch(path, { credentials: "same-origin", cache: "no-store" });
      let body = null;
      try { body = await response.json(); } catch (_) { body = {}; }
      return { ok: response.ok, status: response.status, body: body || {} };
    } catch (_) {
      return { ok: false, status: 0, body: {} };
    }
  }
  function setConn(next) {
    conn = next;
    const chip = $("conn");
    chip.className = "conn" + (next === "live" ? " live" : next === "lost" ? " lost" : "");
    setText(chip, next === "live" ? "Live" : next === "lost" ? "Connection lost, retrying" : "Connecting");
    $("banner").classList.toggle("hidden", next !== "lost");
    $("main").classList.toggle("stale", next === "lost");
  }
  async function pollMe() {
    const r = await getJson("/api/me");
    if (r.ok) { me = r.body; session = "ok"; setConn("live"); }
    else if (r.status === 0 || r.status >= 500) setConn("lost");
    else {
      // 401: no session. 403/404: not admitted yet, or the meeting ended. Keep trying slowly in case the person joins.
      session = r.status === 404 ? "gone" : "none";
      sessionDetail = String(r.body.detail || "");
      me = null; setConn("live");
    }
  }
  async function pollDiag() {
    if (session !== "ok") return;
    const r = await getJson("/api/diagnostics");
    if (r.ok) { diag = r.body; diagState = "ok"; }
    else if (r.status === 0) diagState = diag ? "ok" : "wait";
    else { diag = null; diagState = "none"; }
  }
  async function tick() {
    timer = null;
    if (document.hidden && hiddenAt && Date.now() - hiddenAt > HIDDEN_STOP_MS) { stopped = true; return; }
    busy = true;
    try {
      await pollMe();
      if (Date.now() - lastDiag >= DIAG_MS) { lastDiag = Date.now(); await pollDiag(); }
      render();
    } finally { busy = false; }
    timer = setTimeout(tick, session === "ok" ? POLL_MS : 3000);
  }
  function start() { if (!timer && !busy) tick(); }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { hiddenAt = Date.now(); return; }
    hiddenAt = 0;
    if (stopped) { stopped = false; clearTimeout(timer); timer = null; lastDiag = 0; start(); }
  });

  // ---------------------------------------------------------------- tabs
  function showTab(name) {
    tab = name === "how" ? "how" : "insights";
    for (const [key, id] of [["insights", "tab-insights"], ["how", "tab-how"]]) {
      const button = $(id), on = key === tab;
      button.classList.toggle("on", on);
      button.setAttribute("aria-selected", String(on));
      button.tabIndex = on ? 0 : -1;
    }
    render();
  }
  function readHash() {
    const raw = String(location.hash || "").replace(/^#/, "");
    const m = /^how(?:=([\w-]+))?$/.exec(raw);
    highlight = m && m[1] ? m[1] : "";
    if (m) tab = "how"; else if (raw === "insights") tab = "insights";
    showTab(tab);
  }
  $("tab-insights").onclick = () => showTab("insights");
  $("tab-how").onclick = () => showTab("how");
  for (const id of ["tab-insights", "tab-how"]) {
    $(id).addEventListener("keydown", event => {
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") { showTab(tab === "how" ? "insights" : "how"); $(tab === "how" ? "tab-how" : "tab-insights").focus(); }
    });
  }
  window.addEventListener("hashchange", readHash);

  // ---------------------------------------------------------------- Insights tab
  function stateLine() {
    const mine = (me.participants || {})[me.identity] || {};
    const steps = (me.insights && me.insights.timeline) || [];
    const last = steps.length ? steps[steps.length - 1].state : "off";
    if (me.finalized) return "Your notes are finished";
    if (mine.sensitive_paused) return "Waiting: notes are paused for a sensitive topic";
    if (mine.recording) return last === "off_record" ? "Recording" : "Recording: notes are on for you";
    return last === "off_record" ? "Off the record: nothing from you is kept" : "Notes off: nothing from you is transcribed";
  }
  function renderTiles(ins) {
    const approved = Number(ins.approved) || 0, kept = Number(ins.total) || 0, removed = Number(ins.removed) || 0;
    const seen = approved + kept;
    const share = seen ? Math.round(kept / seen * 100) + "%" : "0%";
    const box = $("tiles");
    box.replaceChildren();
    for (const [n, label] of [[approved, "Approved lines"], [kept, "Kept out"], [removed, "Removed after approval"], [share, "Share kept out"]]) {
      const tile = el("div", "iv-tile");
      tile.append(el("b", null, String(n)), el("span", null, label));
      box.append(tile);
    }
  }
  function renderEvents(events) {
    const box = $("events");
    box.replaceChildren();
    if (!events.length) { box.append(el("p", "empty", "Nothing has been kept out so far in this meeting.")); return; }
    const wrap = el("div", "tbl-wrap"), table = el("table", "events");
    table.setAttribute("aria-label", "Kept-out events in this meeting");
    const head = el("tr");
    for (const name of ["Time", "Kind", "Rule", "State", "Held", "Action"]) { const th = el("th", null, name); th.setAttribute("scope", "col"); head.append(th); }
    const thead = el("thead"); thead.append(head);
    const body = el("tbody");
    for (const e of events) {
      const fam = Views.families[e.family] || Views.families.other || { label: "Rule", engine: "rule" };
      const act = Views.actionOf({ family: e.family });
      const row = el("tr");
      row.setAttribute("data-seq", String(e.seq));
      row.setAttribute("data-category", e.category);
      row.append(el("td", "num", clock(e.t)), el("td", null, Views.label(e.category)));
      const rule = el("td");
      rule.append(el("span", null, fam.label + (fam.engine === "llm" ? " (language model)" : "")));
      const details = el("details");
      details.append(el("summary", null, "Reason code"), el("code", null, String(e.code || "")));
      details.open = openCodes.has(e.seq);
      details.addEventListener("toggle", () => { if (details.open) openCodes.add(e.seq); else openCodes.delete(e.seq); });
      rule.append(details);
      row.append(rule, el("td", null, Views.stateLabel(e.before) + " to " + Views.stateLabel(e.after)),
        el("td", "num", Views.secs(e.held_s)), el("td", null, act.label));
      body.append(row);
    }
    table.append(thead, body);
    wrap.append(table);
    box.append(wrap);
  }
  function audioText(mine) {
    switch (mine && mine.state) {
      case "hearing_you": return "The notes engine is hearing you";
      case "waiting_for_audio": return "Waiting for audio";
      case "silent": return "Silent: the notes engine hears no speech right now";
      case "not_subscribed": return "Notes are off for you, nothing is being transcribed";
      case "error": return (mine.error && String(mine.error)) || "The notes engine reported an error";
      default: return "Audio state not known yet";
    }
  }
  function modelRows(models) {
    const rows = [];
    const w = models && models.whisper, l = models && models.llm, p = models && models.presidio;
    if (w) rows.push("Speech model" + (w.name ? " (" + w.name + ")" : "") + ": " + (w.loaded ? "ready" : "loading") +
      (typeof w.rtf === "number" ? ", " + w.rtf.toFixed(2) + "x real time" : ""));
    if (l) rows.push("Local language model" + (l.name ? " (" + l.name + ")" : "") + ": " +
      (l.reachable ? (l.warm ? "ready" : "reachable, warming up") : "not reachable, rules only"));
    if (p) rows.push("Personal-details detector" + (p.model ? " (" + p.model + ")" : "") + ": " + (p.available ? "ready" : "not available"));
    return rows;
  }
  function renderRunning(state) {
    const box = $("running");
    box.replaceChildren();
    if (state.status === "none") { box.append(el("p", null, "Status is not available from this server.")); return; }
    if (state.status !== "ok") { box.append(el("p", null, "Checking the notes engine...")); return; }
    box.append(el("p", "live-audio", audioText(state.me)));
    const waiting = Number(state.me && state.me.waiting_lines) || 0;
    box.append(el("p", null, waiting ? `Listening, ${waiting} ${waiting === 1 ? "line" : "lines"} waiting in the short hold` : "No lines waiting in the short hold"));
    if (state.hold) box.append(el("p", null, "Hold window: " + Views.secs(state.hold)));
    for (const row of modelRows(state.models)) box.append(el("p", null, row));
  }
  function renderInsightsTab() {
    const ins = me.insights || {};
    setText($("state-line"), stateLine());
    renderIfChanged("tiles", [ins.approved, ins.total, ins.removed], () => renderTiles(ins));
    renderIfChanged("timeline", [ins.timeline, ins.now], () => {
      const box = $("timeline");
      box.replaceChildren();
      Views.renderTimeline(box, ins.timeline, ins.now);
    });
    renderIfChanged("events", me.kept_out_events || [], () => renderEvents(me.kept_out_events || []));
    const d = diagState === "ok" && diag ? diag : null;
    renderIfChanged("running", [diagState, d && d.models, d && d.me, d && d.hold_seconds], () =>
      renderRunning({ status: diagState, models: d && d.models, me: d && d.me, hold: d && d.hold_seconds }));
  }

  // ---------------------------------------------------------------- How it decides tab
  const EXAMPLES = {
    retracted: "A phrase such as \"strike that\", \"scratch that\" or \"forget what I just said\" after a line you regret.",
    off_record: "A phrase such as \"off the record\" or \"between us\", until someone says the stretch is over.",
    contact: "An email address, a phone number, a card number or an ID number read out loud.",
    personal_health: "Talk about a diagnosis, a medical visit, a family matter or a personal struggle.",
    pay_hr: "Talk about what a named person earns, a raise or bonus, a hiring or firing decision, or a performance review.",
    legal_business: "Talk about a lawsuit, a contract in negotiation, an unreleased deal or other confidential company business.",
    other: "Something the filter flagged under another name, or a question you did not answer before the talk moved on."
  };
  const DOES = {
    retracted: "Takes the retracted line out of your notes, even if it was already approved. The retraction request itself is never kept.",
    off_record: "Keeps this line and everything after it out of your notes until the private stretch ends.",
    contact: "Masks the detail before the line can enter your notes."
  };
  const DOES_DEFAULT = "Keeps the line out of your notes. You see a placeholder with the kind, never the words.";
  const DOES_NOT = "It does not store audio. The words of anything kept out are never sent to this page or to your browser, so this window cannot show what was said.";
  function renderHow(counts, hold) {
    const flow = $("flow");
    flow.replaceChildren();
    const steps = [
      ["1. Listen", "While your notes are on, your microphone audio is turned into text on this computer. Audio is not stored."],
      ["2. Wait in a short hold", "Each line waits" + (hold ? " " + Views.secs(hold) : " a few seconds") + " before anything can reach your notes."],
      ["3. Check", "Rules and a local language model read the line, and the lines before it, for the kinds listed below."],
      ["4. Release or keep out", "If nothing was flagged, the line is released to your notes. Otherwise it is kept out, masked or removed, and only a placeholder remains."]
    ];
    for (const [name, text] of steps) { const li = el("li"); li.append(el("b", null, name), el("span", null, text)); flow.append(li); }
    const cards = $("cards");
    cards.replaceChildren();
    for (const cat of Views.categories) {
      const card = el("section", "card" + (highlight === cat.key ? " on" : ""));
      card.id = "kind-" + cat.key;
      card.setAttribute("data-category", cat.key);
      const title = el("h3", null, cat.label);
      title.append(el("span", "n", (counts[cat.key] || 0) + " in this meeting"));
      card.append(title);
      const families = (cat.families || []).map(k => (Views.families[k] || {}).label).filter(Boolean).join(", ");
      for (const [k, v] of [["Rule", cat.rule], ["Example of what triggers it", EXAMPLES[cat.key] || ""],
        ["Rule families", families], ["What the system does", DOES[cat.key] || DOES_DEFAULT], ["What it does not do", DOES_NOT]]) {
        const row = el("div"); row.append(el("span", "k", k), el("span", "v", v)); card.append(row);
      }
      cards.append(card);
    }
    if (highlight) {
      const target = $("kind-" + highlight);
      if (target && target.scrollIntoView) { try { target.scrollIntoView({ block: "start" }); } catch (_) { } }
    }
  }
  function renderHowTab() {
    const ins = (me && me.insights) || {};
    const hold = ins.hold_seconds || (diag && diag.hold_seconds) || 0;
    renderIfChanged("how", [ins.kept_out, hold, highlight], () => renderHow(ins.kept_out || {}, hold));
  }

  // ---------------------------------------------------------------- render
  function render() {
    const ok = session === "ok" && me;
    const gate = $("gate");
    gate.classList.toggle("hidden", !!ok || session === "wait");
    $("pane-insights").classList.toggle("hidden", !ok || tab !== "insights");
    $("pane-how").classList.toggle("hidden", !ok || tab !== "how");
    $("tab-insights").parentNode.classList.toggle("hidden", !ok);
    if (!ok) {
      if (session === "gone") {
        setText($("gate-title"), "This meeting is not available");
        setText($("gate-text"), "It may have ended. Start or join a meeting from the start page.");
      } else if (session === "none") {
        setText($("gate-title"), "Join the meeting first");
        setText($("gate-text"), sessionDetail && sessionDetail !== "Join the meeting first" ? sessionDetail + "." :
          "This window shows your own notes activity. Join a meeting in your browser, then open this window again from the Off The Record panel.");
      }
      return;
    }
    if (tab === "insights") renderInsightsTab(); else renderHowTab();
  }

  readHash();
  render();
  start();
})();
