/* Stub-DOM harness: runs the real page scripts (demo/static/*.js, the inline script of index.html) against a
 * tiny fake DOM, fake fetch, fake EventSource and fake LiveKit. No browser, no network, no audio.
 *
 *   node tests/js/harness.js        (exit code 0 = all checks passed)
 *
 * It exercises: the lobby / admission flow (host and guest), the single Meet-style side panel in consent mode
 * (Off The Record, What was kept out, How it decides, People, Meeting details), the three views of the operator
 * console, and the privacy contract on the page:
 * a planted secret never reaches the DOM, Insights has only category rows, and "Reveal text" exists
 * only in the operator console.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const STATIC = path.join(__dirname, "..", "..", "demo", "static");
const SECRET = "salary 150,000";
let failures = 0, checks = 0;
function check(cond, msg) {
  checks++;
  if (!cond) { failures++; console.error("FAIL: " + msg); }
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ------------------------------------------------------------------ fake DOM
class ClassList {
  constructor(el) { this.el = el; }
  _set() { return new Set(String(this.el.className || "").split(/\s+/).filter(Boolean)); }
  _save(s) { this.el.className = [...s].join(" "); }
  add(...c) { const s = this._set(); c.forEach(x => s.add(x)); this._save(s); }
  remove(...c) { const s = this._set(); c.forEach(x => s.delete(x)); this._save(s); }
  contains(c) { return this._set().has(c); }
  toggle(c, force) {
    const on = force === undefined ? !this.contains(c) : !!force;
    on ? this.add(c) : this.remove(c);
    return on;
  }
}
function matchSimple(el, sel) {
  if (!el || !el.tagName) return false;
  const re = /([#.][\w-]+|\[[^\]]+\]|^[a-zA-Z][\w-]*)/g;
  let m, any = false;
  while ((m = re.exec(sel))) {
    any = true;
    const t = m[1];
    if (t[0] === "#") { if (el.id !== t.slice(1)) return false; }
    else if (t[0] === ".") { if (!el.classList.contains(t.slice(1))) return false; }
    else if (t[0] === "[") {
      const am = /^\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]$/.exec(t);
      if (!am) return false;
      const v = el.getAttribute(am[1]);
      if (v == null || (am[2] !== undefined && v !== am[2])) return false;
    } else if (el.tagName.toLowerCase() !== t.toLowerCase()) return false;
  }
  return any;
}
function matchChain(el, parts, root) {
  if (!matchSimple(el, parts[parts.length - 1])) return false;
  let i = parts.length - 2, cur = el.parentNode;
  while (i >= 0) {
    while (cur && cur !== root && !matchSimple(cur, parts[i])) cur = cur.parentNode;
    if (!cur || cur === root) return false;
    cur = cur.parentNode; i--;
  }
  return true;
}
class El {
  constructor(tag, doc) {
    this.tagName = String(tag).toUpperCase();
    this.ownerDocument = doc;
    this.children = [];
    this.parentNode = null;
    this.attrs = {};
    this.className = "";
    this.classList = new ClassList(this);
    this.style = { setProperty() {}, };
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.tabIndex = 0;
    this.value = "";
    this.checked = false;
    this.id = "";
    this._text = "";
    this._listeners = {};
    this.scrollTop = 0; this.scrollHeight = 0; this.clientHeight = 0;
    this.focused = false;
  }
  get id_() { return this.id; }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === "id") { this.id = String(v); this.ownerDocument._ids.set(this.id, this); }
    if (k === "class") this.className = String(v);
    if (k === "hidden") this.hidden = true;
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(v);
  }
  getAttribute(k) {
    if (k === "class") return this.className || null;
    if (k === "id") return this.id || null;
    return k in this.attrs ? this.attrs[k] : null;
  }
  removeAttribute(k) { delete this.attrs[k]; }
  _adopt(n) {
    if (typeof n === "string") { const t = new El("#text", this.ownerDocument); t._text = n; t.isText = true; return t; }
    if (n.parentNode) n.remove();
    n.parentNode = this; return n;
  }
  appendChild(n) { n = this._adopt(n); n.parentNode = this; this.children.push(n); return n; }
  append(...ns) { ns.forEach(n => this.appendChild(n)); }
  prepend(...ns) { ns.reverse().forEach(n => { n = this._adopt(n); n.parentNode = this; this.children.unshift(n); }); }
  insertBefore(n, ref) {
    n = this._adopt(n); n.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(n); else this.children.splice(i, 0, n);
    return n;
  }
  removeChild(n) { const i = this.children.indexOf(n); if (i >= 0) { this.children.splice(i, 1); n.parentNode = null; } return n; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  replaceChildren(...ns) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; ns.forEach(n => this.appendChild(n)); }
  get firstChild() { return this.children[0] || null; }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  get textContent() { return this.isText ? this._text : this._text + this.children.map(c => c.textContent).join(""); }
  set textContent(v) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; this._text = String(v == null ? "" : v); }
  set innerHTML(v) { this.children = []; this._text = String(v).replace(/<[^>]*>/g, ""); }
  get innerHTML() { return this._text; }
  get offsetParent() { return this.parentNode; }
  insertAdjacentText() {}
  addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); }
  removeEventListener() {}
  dispatch(type, ev) {
    ev = Object.assign({ type, target: this, key: "", preventDefault() {}, stopPropagation() {} }, ev || {});
    const h = this["on" + type];
    if (typeof h === "function") h.call(this, ev);
    (this._listeners[type] || []).forEach(fn => fn.call(this, ev));
    return ev;
  }
  click() { if (!this.disabled) return this.dispatch("click"); }
  focus() { this.focused = true; this.ownerDocument.activeElement = this; }
  contains(n) { while (n) { if (n === this) return true; n = n.parentNode; } return false; }
  querySelectorAll(sel) {
    const out = [];
    for (const one of sel.split(",")) {
      const parts = one.trim().split(/\s+/);
      const walk = n => { n.children.forEach(c => { if (!c.isText && matchChain(c, parts, this)) out.push(c); walk(c); }); };
      walk(this);
    }
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  getContext() { return null; }
  detach() { return []; }
  attach() { return new El("audio", this.ownerDocument); }
  all() { const o = []; const w = n => n.children.forEach(c => { o.push(c); w(c); }); w(this); return o; }
}
class Doc {
  constructor() {
    this._ids = new Map();
    this.activeElement = null;
    this.listeners = {};
    this.body = new El("body", this);
    this.head = new El("head", this);
    this.documentElement = new El("html", this);
    this.cookie = "";
  }
  createElement(t) { return new El(t, this); }
  createElementNS(ns, t) { return new El(t, this); }
  createTextNode(s) { const t = new El("#text", this); t._text = s; t.isText = true; return t; }
  getElementById(id) { return this._ids.get(id) || null; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener() {}
  dispatch(type, ev) {
    ev = Object.assign({ type, target: this.body, key: "", ctrlKey: false, metaKey: false, altKey: false,
      preventDefault() {}, stopPropagation() {} }, ev || {});
    (this.listeners[type] || []).forEach(fn => fn(ev));
  }
  querySelectorAll(sel) { return this.body.querySelectorAll(sel); }
  querySelector(sel) { return this.body.querySelector(sel); }
}
// Build the body from the static HTML (tags with ids / classes / hidden / data-*), nested by tag structure.
function buildDom(html, doc) {
  const body = html.slice(html.indexOf("<body"), html.lastIndexOf("</body>"));
  const voids = new Set(["input", "br", "img", "meta", "link", "hr", "path", "rect", "circle"]);
  const stack = [doc.body];
  const re = /<(\/?)([a-zA-Z][\w-]*)([^>]*?)(\/?)>|([^<]+)/g;
  let m, skipScript = false;
  while ((m = re.exec(body))) {
    if (m[5] !== undefined) {
      if (!skipScript && m[5].trim()) { const t = doc.createTextNode(m[5].replace(/\s+/g, " ")); stack[stack.length - 1].appendChild(t); }
      continue;
    }
    const closing = m[1] === "/", tag = m[2].toLowerCase(), attrs = m[3] || "";
    if (tag === "script") { skipScript = !closing; continue; }
    if (skipScript) continue;
    if (closing) { if (stack.length > 1 && !voids.has(tag)) stack.pop(); continue; }
    const el = doc.createElement(tag);
    const ar = /([\w:-]+)(?:=(?:"([^"]*)"|'([^']*)'))?/g;
    let a;
    while ((a = ar.exec(attrs))) {
      const k = a[1], v = a[2] !== undefined ? a[2] : a[3] !== undefined ? a[3] : "";
      if (k === "hidden") el.hidden = true;
      else if (k === "checked") el.checked = true;
      else if (k === "disabled") el.disabled = true;
      else el.setAttribute(k, v);
    }
    if (el.attrs.value !== undefined) el.value = el.attrs.value;
    stack[stack.length - 1].appendChild(el);
    if (!voids.has(tag) && !m[4] && !m[0].endsWith("/>")) stack.push(el);
  }
  return doc.body;
}

// ------------------------------------------------------------------ fake network / livekit
function makeEnv(html, opts) {
  opts = opts || {};
  const doc = new Doc();
  buildDom(html, doc);
  // Reflect `hidden` attribute semantic: the page toggles both .hidden class and .hidden property.
  const calls = [];
  const sources = [];
  class FakeES {
    constructor(url) { this.url = url; this.closed = false; this.readyState = 1; sources.push(this); setTimeout(() => this.onopen && this.onopen(), 0); }
    close() { this.closed = true; this.readyState = 2; }
    push(msg) { if (this.onmessage) this.onmessage({ data: JSON.stringify(msg), lastEventId: "" }); }
  }
  class Participant {
    constructor() { this.isMicrophoneEnabled = false; this.isCameraEnabled = false; }
    async setMicrophoneEnabled(v) { this.isMicrophoneEnabled = v; }
    async setCameraEnabled(v) { this.isCameraEnabled = v; }
    getTrackPublication() { return null; }
  }
  const rooms = [];
  class Room {
    constructor() { this.handlers = {}; this.localParticipant = new Participant(); this.canPlaybackAudio = true; rooms.push(this); }
    on(ev, fn) { this.handlers[ev] = fn; return this; }
    async connect(url, token) { this.url = url; this.token = token; }
    async disconnect() { this.disconnected = true; }
    async startAudio() {}
  }
  const LivekitClient = {
    Room,
    RoomEvent: new Proxy({}, { get: (_, k) => String(k) }),
    Track: { Kind: { Audio: "audio", Video: "video" }, Source: { Camera: "camera", Microphone: "microphone" } },
  };
  const routes = opts.routes || {};
  async function fetchStub(url, init) {
    init = init || {};
    const method = (init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, url, body });
    const key = method + " " + url;
    let res = routes[key];
    if (typeof res === "function") res = res(body);
    if (res instanceof Error) throw res;
    if (res === undefined) res = { status: 404, json: { detail: "not found: " + key } };
    if (!("json" in res) && !("rawHtml" in res)) res = { status: 200, json: res };   // routes may return {status, json} or a bare body
    return { ok: res.status < 400, status: res.status,
      json: async () => { if (res.rawHtml) throw new SyntaxError("Unexpected token '<'"); return res.json; },
      text: async () => res.rawHtml || JSON.stringify(res.json) };
  }
  const store = opts.store || {};
  const sandbox = {
    document: doc, console, setTimeout, clearTimeout, setInterval, clearInterval, Promise, JSON, Math, Date, Object, Array,
    Map, Set, String, Number, Boolean, Error, RegExp, Symbol, Proxy, parseInt, parseFloat, isNaN, URL, URLSearchParams,
    encodeURIComponent, decodeURIComponent, performance, globalThis: undefined,
    fetch: fetchStub, EventSource: FakeES, requestAnimationFrame: fn => setTimeout(fn, 0),
    localStorage: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
    navigator: { clipboard: { writeText: async () => {} }, mediaDevices: {}, sendBeacon() {} },
    location: { origin: "http://127.0.0.1:8000", pathname: opts.pathname || "/", search: "", href: "", reload() {} },
    history: { replaceState() {} },
    LivekitClient, isSecureContext: true, AudioContext: undefined,
  };
  sandbox.window = sandbox; sandbox.globalThis = sandbox;
  sandbox.window.isSecureContext = true;
  const ctx = vm.createContext(sandbox);
  return { doc, ctx, calls, sources, rooms, store, sandbox, run(code, name) { vm.runInContext(code, ctx, { filename: name }); } };
}
function loadScripts(env, html, only) {
  for (const m of html.matchAll(/<script(?: src="([^"]+)")?[^>]*>([\s\S]*?)<\/script>/g)) {
    const src = m[1];
    if (src) {
      const name = src.replace("/static/", "");
      if (name === "livekit-client.umd.js") continue;
      if (name === "categories.js") { env.run(taxonomyJs(), name); continue; }
      env.run(fs.readFileSync(path.join(STATIC, name), "utf8"), name);
    } else if (m[2].trim()) env.run(m[2], "inline");
  }
}
let _tax = null;
function taxonomyJs() {
  if (_tax) return _tax;
  const { execFileSync } = require("child_process");
  const py = process.env.PYTHON || "python";
  _tax = execFileSync(py, ["-c", "from demo.categories import js_source; import sys; sys.stdout.write(js_source())"],
    { cwd: path.join(__dirname, "..", ".."), encoding: "utf8" });
  return _tax;
}
const text = el => el.textContent;
const visible = el => { for (let n = el; n; n = n.parentNode) { if (n.hidden || (n.classList && n.classList.contains("hidden"))) return false; } return true; };
const all = (env, pred) => env.doc.body.all().filter(pred);

// ------------------------------------------------------------------ scenario 1: consent page, host + lobby + three views
async function consentHost() {
  const html = fs.readFileSync(path.join(STATIC, "live.html"), "utf8");
  let recordingOn = false;
  let approvedLines = [];
  const insights = { approved: 1, kept_out: { pay_hr: 1, off_record: 2 }, total: 3, removed: 0,
    timeline: [{ t: 0, state: "off" }, { t: 1.2, state: "recording" }, { t: 20, state: "off_record" }], now: 40, hold_seconds: 10 };
  const env = makeEnv(html, {
    pathname: "/",
    routes: {
      "POST /api/meetings": { room_id: "room1", join_url: "http://127.0.0.1:8000/m/room1", identity: "person-host", name: "Hana",
        role: "host", token: "tok", url: "ws://127.0.0.1:7880", room: "room1" },
      "GET /api/config": { mode: "livekit", url: "ws://127.0.0.1:7880", room: "room1", categories: [] },
      "GET /api/me": () => ({ identity: "person-host", participants: { "person-host": { name: "Hana", recording: recordingOn } },
        lines: approvedLines, kept_out: [], insights, redaction_counts: { suppressed: 0, removed: 0, total: 0 }, finalized: false,
        ready_for_final: false, finalized_count: 0, contributor_count: 1 }),
      "GET /api/meetings/room1/status": { status: "admitted", role: "host", identity: "person-host", name: "Hana", token: "tok",
        url: "ws://127.0.0.1:7880", room: "room1",
        pending: [{ request_id: "r1", name: "Guest Gail", email: "gail@example.com" }] },
      "POST /api/meetings/room1/admit": { ok: true },
      "POST /api/consent": body => { recordingOn = body.recording; return { identity: "person-host", recording: recordingOn }; },
      "GET /api/notes/final": { text: "Hana: Plan the launch", redaction_counts: { suppressed: 0, removed: 0 } },
      "GET /api/meetings/room1/mail-recipients": { recipients: [] },
      "POST /api/meetings/room1/end": { ok: true },
    },
  });
  loadScripts(env, html);
  const $ = id => env.doc.getElementById(id);
  check(visible($("home-screen")) && !visible($("meeting")), "home screen first, meeting hidden");
  $("create-button").click();
  check(visible($("host-setup")), "create opens host setup");
  $("host-name").value = "Hana"; $("host-email").value = "hana@example.com";
  $("host-create-button").click();
  await sleep(30);
  check(visible($("share-screen")) && $("share-link").value.endsWith("/m/room1"), "share screen shows the meeting link");
  check(env.calls.some(c => c.url === "/api/meetings" && c.body.name === "Hana"), "host created the meeting");
  check(JSON.parse(env.store["otr-person-details-v1"]).email === "hana@example.com", "successful host setup remembers name and email locally");
  const returnVisit = makeEnv(html, { store: env.store });
  loadScripts(returnVisit, html);
  const savedField = id => returnVisit.doc.getElementById(id);
  check(savedField("host-name").value === "Hana" && savedField("guest-name").value === "Hana"
    && savedField("host-email").value === "hana@example.com" && savedField("guest-email").value === "hana@example.com",
    "name and email prefill both forms on a return visit");
  savedField("host-setup").all().find(e => e.classList.contains("forget-details")).click();
  check(!env.store["otr-person-details-v1"] && !savedField("host-name").value && !savedField("guest-email").value,
    "Forget them removes saved details and clears the forms");
  $("share-join-button").click();
  await sleep(60);
  check(visible($("meeting")) && visible($("control-bar")), "meeting and control bar shown after entering");
  check(text($("notes-label")) === "Turn on notes", "notes switch labels the action while notes are off");
  check($("notes-control").getAttribute("aria-pressed") === "false" && $("notes-control").classList.contains("notes-off")
    && $("notes-control").getAttribute("aria-label") === "Turn on notes for me", "control-bar notes button starts visibly off");
  check(env.rooms.length === 1 && env.rooms[0].token === "tok", "joined the LiveKit room with the server-issued token");
  check(visible($("host-lobby")), "host sees the lobby");
  await sleep(10);
  check(text($("lobby-list")).includes("Guest Gail"), "lobby lists the waiting guest");
  const admitBtn = $("lobby-list").all().find(e => e.tagName === "BUTTON" && text(e) === "Admit");
  admitBtn.click(); await sleep(20);
  check(env.calls.some(c => c.url === "/api/meetings/room1/admit" && c.body.request_id === "r1"), "host admitted the guest");

  // Meet-style call: no tab bar, no status pill, no presenter button on the stage
  check(!$("view-tabs") && !$("tab-realtime") && !$("status-pill") && !$("present-button"),
    "consent page has no tab bar, status pill or presenter button");
  // The lobby request opened the People panel for the host
  check(visible($("side-panel")) && visible($("panel-people")) && !visible($("panel-agent")), "a waiting guest opens the People panel");
  check(!$("people-badge").classList.contains("hidden") && text($("people-badge")) === "1", "people button shows the waiting count");
  const es = env.sources[0];
  check(es && es.url === "/stream", "stream opened");
  es.push({ type: "snapshot", lines: [{ id: "approved-before-opt-in", speaker: "person-g", name: "Gail", text: "Approved before my opt in", seq: 0 }], kept_out: [] });
  check(text($("captions")).includes("Approved before my opt in"), "an off viewer sees another speaker's approved transcript");
  es.push({ type: "participants", participants: { "person-host": { name: "Hana", recording: true } } });
  recordingOn = true;
  es.push({ type: "snapshot", lines: [], kept_out: [] });
  es.push({ type: "status", ...insights });
  es.push({ type: "transcript", changes: [{ kind: "committed", owner: "person-host",
    line: { id: "l1", speaker: "person-host", name: "Hana", text: "Plan the launch", seq: 1 } }] });
  es.push({ type: "transcript", changes: [{ kind: "committed", owner: "person-g",
    line: { id: "l2", speaker: "person-g", name: "Gail", text: "I will send the agenda", seq: 3 } }] });
  approvedLines = [{ id: "l1", speaker: "person-host", name: "Hana", text: "Plan the launch", seq: 1 },
    { id: "l2", speaker: "person-g", name: "Gail", text: "I will send the agenda", seq: 3 }];
  // A hostile / buggy server message that tries to smuggle text into the kept-out marker and status.
  es.push({ type: "transcript", changes: [{ kind: "kept_out", id: "k1", owner: "person-host", category: "pay_hr", seq: 2,
    text: SECRET, trail: { family: "kw", before: "ON", after: "PENDING_CONFIRM", held_s: 2.4, text: SECRET } }] });
  es.push({ type: "status", ...insights, text: SECRET, items: [{ text: SECRET }] });
  await sleep(10);
  check(text($("people-list")).includes("Hana") && text($("people-list")).includes("Notes on"), "People panel lists who has notes on");

  // The Off The Record agent button opens the one side panel
  $("agent-button").click();
  check(visible($("side-panel")) && visible($("panel-agent")) && !visible($("panel-people")) && !visible($("view-insights")), "agent button opens the agent panel");
  check($("agent-button").getAttribute("aria-expanded") === "true", "agent button reports expanded");
  check(text($("panel-title")) === "Off The Record" && !visible($("panel-back")), "panel title, no back arrow at the root");
  check(text($("capture-status")) === "Notes are on for you" && $("notes-button").getAttribute("aria-checked") === "true",
    "one-line status and switch show notes on");
  check(text($("notes-label")) === "Turn off notes", "notes switch labels the action while notes are on");
  check($("notes-control").getAttribute("aria-pressed") === "true" && $("notes-control").classList.contains("notes-on")
    && $("notes-control").getAttribute("aria-label") === "Turn off notes for me", "call control mirrors the on state");
  const caps = text($("captions"));
  check(caps.includes("Plan the launch") && caps.includes("I will send the agenda") && caps.includes("Gail"),
    "shared live transcript shows approved lines from both speakers");
  check($("captions").all().filter(e => e.className === "remove").length === 1, "only the viewer's own line has Remove");
  const chip = $("captions").all().find(e => e.tagName === "BUTTON" && e.getAttribute("data-category") === "pay_hr");
  check(!!chip && text(chip).includes("Pay and HR"), "kept-out marker chip shows the kind only");
  check(!text(env.doc.body).includes(SECRET), "the planted secret never reaches the page (realtime)");
  check(!visible($("live-button")), "Jump to latest is hidden while following");
  $("captions").scrollHeight = 600; $("captions").clientHeight = 100; $("captions").scrollTop = 0;
  $("captions").dispatch("scroll");
  check(visible($("live-button")) && text($("live-button")).includes("Jump to latest"), "Jump to latest appears when scrolled up");
  $("live-button").click();
  check(!visible($("live-button")), "Jump to latest returns to the newest line and hides");

  // Meet-style captions on the stage
  check(!visible($("stage-captions")), "stage captions off by default");
  $("captions-button").click();
  check(visible($("stage-captions")) && text($("stage-captions")).includes("Plan the launch") && !text($("stage-captions")).includes(SECRET),
    "captions button shows approved lines on the stage");
  $("captions-button").click();
  check(!visible($("stage-captions")), "captions button toggles off");

  // What was kept out: a plain link inside the same panel, with a back arrow
  $("link-insights").click();
  check(visible($("view-insights")) && !visible($("panel-agent")) && visible($("panel-back")) && text($("panel-title")) === "What was kept out",
    "What was kept out opens inside the panel with a back arrow");
  const ins = text($("view-insights"));
  check(ins.includes("Off the record (you asked)") && ins.includes("Pay and HR"), "insights lists the kinds");
  check(ins.includes("Off the record x2") && ins.includes("Pay and HR x1"), "insights summary has kinds and counts");
  const rows = $("view-insights").all().filter(e => e.tagName === "LI");
  check(rows.length === 7, "insights has exactly one row per kind (7), no per-item rows: " + rows.length);
  check(!ins.includes("Plan the launch") && !ins.includes("Hana") && !ins.includes(SECRET) && !ins.includes("k1") && !ins.includes("l1"),
    "insights has no lines, speakers, ids or secrets");
  check($("view-insights").all().some(e => e.tagName === "SVG" && e.className === "tl"), "insights has the recording-state timeline");
  check(!$("view-insights").all().some(e => String(e.className).includes("iv-bar")), "no progress bars in the kind list");
  check($("view-insights").all().filter(e => e.className === "iv-tile").length === 3, "three flat stat tiles");
  $("panel-back").click();
  check(visible($("panel-agent")) && !visible($("view-insights")), "back arrow returns to the agent panel");

  // How it decides, then via a marker
  $("link-explain").click();
  check(visible($("view-explain")) && text($("panel-title")) === "How it decides", "How it decides opens inside the panel");
  const ex = text($("view-explain"));
  for (const label of ["Off the record (you asked)", "Retracted by the speaker (strike that)", "Personal and health", "Pay and HR",
    "Legal and confidential business", "Contact details masked", "Other sensitive"]) check(ex.includes(label), "explain lists " + label);
  check(!$("view-explain").all().some(e => text(e).includes("Reveal text")), "no Reveal text in consent mode");
  $("panel-back").click();
  $("captions").all().find(e => e.getAttribute && e.getAttribute("data-category") === "pay_hr").click();
  check(visible($("view-explain")), "opening the marker goes to How it decides");
  const trail = text($("view-explain"));
  check(trail.includes("Keyword rule") && trail.includes("Recording") && trail.includes("Needs your OK") && trail.includes("2.4 s"),
    "marker trail shows rule family, state before/after and hold timing");
  check(!trail.includes(SECRET) && !trail.includes("150,000"), "trail has no private text");
  check($("view-explain").all().some(e => e.getAttribute && e.getAttribute("data-category") === "pay_hr" && e.getAttribute("aria-pressed") === "true"), "the category is selected");
  const cardOff = $("view-explain").all().find(e => e.getAttribute && e.getAttribute("data-category") === "off_record" && e.tagName === "BUTTON");
  cardOff.click();
  check(text($("view-explain")).includes("Rule families that can produce this kind"), "choosing a kind shows its generic rule");

  // Meeting details, Escape, and the agent button closing the panel
  $("info-button").click();
  check(visible($("panel-info")) && $("info-link").value.endsWith("/m/room1"), "Meeting details shows the meeting link");
  env.doc.dispatch("keydown", { key: "Escape", target: env.doc.body });
  check(!visible($("side-panel")), "Escape closes the side panel");
  $("agent-button").click();
  $("agent-button").click();
  check(!visible($("side-panel")), "agent button toggles the panel closed");
  env.doc.dispatch("keydown", { key: "l", target: env.doc.body });
  check(visible($("panel-agent")), "l opens the panel at the latest lines");

  // consent / mic / camera controls
  $("notes-control").click(); await sleep(20);
  check(env.calls.some(c => c.url === "/api/consent" && c.body.recording === false), "Notes button posts the opposite consent choice");
  check($("notes-control").getAttribute("aria-pressed") === "false" && text($("captions")).includes("Plan the launch")
    && text($("captions")).includes("I will send the agenda") && visible($("panel-agent")),
    "turning notes off keeps the shared transcript open");
  check(!env.calls.some(c => c.url === "/api/confirm"), "consent page never calls /api/confirm");
  $("leave-button").click(); await sleep(20);
  check(visible($("end-dialog")) && text($("end-summary")).includes("final transcript is ready"),
    "host can review the final transcript before ending normally");
  $("end-without-email").click(); await sleep(20);
  check(env.calls.some(c => c.method === "POST" && c.url === "/api/meetings/room1/end")
    && env.rooms[0].disconnected && env.sandbox.location.href === "/",
    "normal end closes the server meeting and disconnects the local call");
  return env;
}

async function consentCreateFailure() {
  const html = fs.readFileSync(path.join(STATIC, "live.html"), "utf8");
  const cases = [
    ["HTML gateway error", {status: 502, rawHtml: "<h1>Bad Gateway</h1>"}, "Meeting host is temporarily unavailable. Try again in a moment."],
    ["service unavailable", {status: 503, json: {}}, "Meeting host is temporarily unavailable. Try again in a moment."],
    ["gateway timeout", {status: 504, json: {}}, "Meeting host is temporarily unavailable. Try again in a moment."],
    ["network failure", new TypeError("Failed to fetch"), "Meeting host is temporarily unavailable. Try again in a moment."],
    ["validation error", {status: 400, json: {detail: "Enter your name"}}, "Enter your name"],
    ["capacity error", {status: 429, json: {detail: "Too many meetings"}}, "Too many meetings"],
  ];
  for (const [label, response, expected] of cases) {
    const env = makeEnv(html, {routes: {"POST /api/meetings": response}});
    loadScripts(env, html);
    const $ = id => env.doc.getElementById(id);
    $("create-button").click();
    $("host-name").value = "Hana";
    $("host-email").value = "hana@example.com";
    $("host-create-button").click();
    await sleep(5);
    check(text($("host-error")) === expected, `create meeting ${label} gives useful feedback`);
    check(!$("host-create-button").disabled, `create meeting ${label} allows retry`);
  }
}

// ------------------------------------------------------------------ scenario 1b: server session expired while the host is in LiveKit
async function consentHostExpired() {
  const html = fs.readFileSync(path.join(STATIC, "live.html"), "utf8");
  const baseRoutes = {
    "POST /api/meetings": { room_id: "expired-room", join_url: "http://127.0.0.1:8000/m/expired-room", identity: "person-host",
      name: "Hana", role: "host", token: "tok", url: "ws://127.0.0.1:7880", room: "expired-room" },
    "GET /api/config": { mode: "livekit", url: "ws://127.0.0.1:7880", room: "expired-room" },
    "GET /api/me": { identity: "person-host", participants: { "person-host": { name: "Hana", recording: false } },
      lines: [], kept_out: [], insights: {}, redaction_counts: {}, finalized: false },
    "GET /api/meetings/expired-room/status": { status: "admitted", role: "host", identity: "person-host",
      name: "Hana", token: "tok", url: "ws://127.0.0.1:7880", room: "expired-room", pending: [] },
  };
  for (const failedStep of ["draft", "end"]) {
    const routes = { ...baseRoutes,
      "GET /api/notes/final": failedStep === "draft" ? { status: 401, json: { detail: "Join the meeting first" } }
        : { text: "Hana: Plan the launch", redaction_counts: {} },
      "GET /api/meetings/expired-room/mail-recipients": { recipients: [] },
      "POST /api/meetings/expired-room/end": { status: 401, json: { detail: "Join the meeting first" } },
    };
    const env = makeEnv(html, { routes });
    loadScripts(env, html);
    const $ = id => env.doc.getElementById(id);
    $("create-button").click();
    $("host-name").value = "Hana";
    $("host-email").value = "hana@example.com";
    $("host-create-button").click(); await sleep(20);
    $("share-join-button").click(); await sleep(40);
    $("leave-button").click(); await sleep(20);
    if (failedStep === "draft") {
      check(text($("end-summary")).includes("server session expired")
        && text($("end-without-email")) === "Leave this call"
        && !text($("end-error")),
      "expired session explains why no draft is available and offers local leave");
    }
    $("end-without-email").click(); await sleep(20);
    check(env.rooms[0].disconnected && env.sandbox.location.href === "/"
      && !text($("end-error")).includes("Could not end meeting"),
      `expired session at ${failedStep} still disconnects local call without a misleading end error`);
    check(env.calls.filter(c => c.method === "POST" && c.url === "/api/meetings/expired-room/end").length === (failedStep === "draft" ? 0 : 1),
      `server end ${failedStep === "draft" ? "is skipped after known expiry" : "is attempted before handling expiry"}`);
  }
}

// ------------------------------------------------------------------ scenario 2: guest waits, then is admitted
async function consentGuest() {
  const html = fs.readFileSync(path.join(STATIC, "live.html"), "utf8");
  let polls = 0;
  const env = makeEnv(html, {
    pathname: "/m/room1",
    routes: {
      "GET /api/meetings/room1/status": () => (++polls === 1 ? { status: 401, json: { detail: "Request to join first" } }
        : polls === 2 ? { status: 200, json: { status: "waiting", role: "guest", request_id: "q1" } }
        : { status: 200, json: { status: "admitted", role: "guest", request_id: "q1", identity: "person-g", name: "Gail", token: "gt", url: "ws://127.0.0.1:7880", room: "room1" } }),
      "POST /api/meetings/room1/request": { request_id: "q1", status: "waiting" },
      "GET /api/config": { mode: "livekit", url: "ws://127.0.0.1:7880", room: "room1" },
      "GET /api/me": { identity: "person-g", participants: { "person-g": { name: "Gail", recording: false } }, lines: [], kept_out: [],
        insights: { approved: 0, kept_out: {}, total: 0, removed: 0, timeline: [], now: 0 }, redaction_counts: { suppressed: 0, removed: 0, total: 0 },
        finalized: false, ready_for_final: false, finalized_count: 0, contributor_count: 1 },
    },
  });
  loadScripts(env, html);
  const $ = id => env.doc.getElementById(id);
  await sleep(20);
  check(visible($("guest-setup")), "a guest following /m/room1 sees the request form first");
  $("guest-name").value = "Gail"; $("guest-email").value = "gail@example.com";
  $("guest-join-button").click();
  await sleep(30);
  check(visible($("waiting-screen")), "guest waits for the host");
  check(!visible($("meeting")), "guest is not in the meeting before admission");
  check(env.calls.every(c => c.url !== "/api/join" && c.url !== "/api/consent"), "no join or consent before admission");
  await sleep(1700);
  check(visible($("meeting")) && env.rooms.length === 1 && env.rooms[0].token === "gt", "admitted guest enters with the server token");
  check(!visible($("host-lobby")), "guest does not get the host lobby");
  return env;
}

// ------------------------------------------------------------------ scenario 3: operator console (replay / stream)
async function operatorConsole() {
  const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
  const env = makeEnv(html, { pathname: "/", routes: {} });
  loadScripts(env, html);
  const $ = id => env.doc.getElementById(id);
  await sleep(10);
  const es = env.sources[0];
  check(es && es.url === "/stream", "console opens the stream");
  const seg = (id, who, txt, t) => es.push({ type: "segment", t, segment: { id, speaker: who, text: txt, t_start: t, t_end: t } });
  const ev = (kind, id, who, t, state, reason, txt) => ({ kind, segment_id: id, speaker: who, t, state, reason: reason || "", text: txt || "" });
  es.push({ type: "reset", hold_seconds: 10, pipeline: "fake" });
  seg("s1", "Ana", "Plan the launch", 1);
  seg("s2", "Ben", "Her " + SECRET, 3);
  seg("s3", "Cy", "off the record", 6);
  es.push({ type: "events", notes: [], audit: [], events: [ev("held", "s1", "Ana", 1, "ON", "", "Plan the launch")] });
  es.push({ type: "events", notes: [], audit: [], events: [ev("held", "s2", "Ben", 3, "ON", "", "Her " + SECRET),
    ev("state_change", "s2", "Ben", 3, "PENDING_CONFIRM", "kw:salary"), ev("pending_confirm", "s2", "Ben", 3, "PENDING_CONFIRM", "kw:salary", "Her " + SECRET)] });
  es.push({ type: "events", notes: [], audit: [], events: [ev("redacted", "s2", "Ben", 4, "ON", "confirm:keep_out", "Her " + SECRET),
    ev("state_change", "s2", "Ben", 4, "ON", "confirm")] });
  es.push({ type: "events", notes: [], audit: [], events: [ev("redacted", "s3", "Cy", 6, "OFF", "cue:off_the_record"), ev("state_change", "s3", "Cy", 6, "OFF", "cue:off_the_record")] });
  es.push({ type: "events", notes: [{ id: "s1", speaker: "Ana", text: "Plan the launch" }], audit: [], events: [ev("committed", "s1", "Ana", 11, "OFF", "hold_elapsed", "Plan the launch")] });
  await sleep(20);
  check(text($("captions")).includes("Plan the launch"), "console shows the approved caption");
  check(!text($("captions")).includes("150,000"), "console captions never print kept-out text");
  const chips = $("captions").all().filter(e => e.getAttribute && e.getAttribute("data-category"));
  check(chips.map(c => c.getAttribute("data-category")).join() === "other,off_record", "chips carry taxonomy kinds: " + chips.map(c => c.getAttribute("data-category")));
  $("tab-insights").click();
  const ins = text($("view-insights"));
  check(ins.includes("Off the record x1") && ins.includes("Other x1"), "console insights summarises kinds: " + ins.slice(0, 200));
  check(!ins.includes("Ben") && !ins.includes("Ana") && !ins.includes("Plan the launch") && !ins.includes("150,000"), "console insights lists no speakers, quotes or items");
  check($("view-insights").all().filter(e => e.tagName === "LI").length === 7, "console insights has only the 7 kind rows");
  // explain via the chip -> operator may reveal
  $("tab-realtime").click();
  chips[0].click();
  check(visible($("view-explain")), "console chip opens Explainability");
  const exText = text($("view-explain"));
  check(exText.includes("Confirmation answer") && !exText.includes("150,000"), "trail names the rule family, not the content");
  const reveal = $("view-explain").all().find(e => e.tagName === "BUTTON" && text(e).startsWith("Reveal text"));
  check(!!reveal, "operator console has Reveal text");
  reveal.click();
  check(text($("view-explain")).includes("150,000"), "reveal shows the text only after the operator asks");
  $("tab-insights").click();
  check(!text($("view-insights")).includes("150,000"), "leaving Explainability hides revealed text again");
  // pending card still works for the operator
  seg("s4", "Dee", "My salary is 90k", 20);
  es.push({ type: "events", notes: [], audit: [], events: [ev("pending_confirm", "s4", "Dee", 20, "PENDING_CONFIRM", "llm:salary", "My salary is 90k")] });
  check($("pendcard").style.display === "block" && text($("pendcard")).includes("Keep that out of the notes?"), "operator sees the confirm card");
  return env;
}

(async () => {
  try {
    await consentHost();
    await consentCreateFailure();
    await consentHostExpired();
    await consentGuest();
    await operatorConsole();
  } catch (e) {
    failures++; console.error("EXCEPTION", e && e.stack || e);
  }
  console.log(`${checks - failures}/${checks} checks passed`);
  process.exit(failures ? 1 : 0);
})();
