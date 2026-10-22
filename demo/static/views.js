/* Shared views for the three ways of looking at one pipeline: REALTIME (page specific), INSIGHTS, EXPLAINABILITY.
 *
 * Used by live.html (consent mode) and index.html (operator console for replay / shared-stream modes).
 * Needs window.OTR_TAXONOMY from /static/categories.js, which is generated from demo/categories.py.
 *
 * Privacy contract of this file: it only ever receives category KEYS, counts, rule-family names, pipeline
 * state names and timings. It has no parameter that could carry a quote, a speaker or a per-item row, and it
 * builds DOM with textContent only. The single exception is the optional `reveal` callback in
 * renderExplain(): a page passes it only for the owner/operator in non-consent replay mode.
 * No inline style attributes are written (the consent page has a strict CSP); sizes use CSSOM or SVG attributes.
 */
(function (root) {
  "use strict";
  var T = root.OTR_TAXONOMY || { categories: [], families: {} };
  var CATS = T.categories || [];
  var FAMS = T.families || {};
  var byKey = {};
  var rx = CATS.map(function (c) { byKey[c.key] = c; return { key: c.key, re: new RegExp(c.pattern, "i") }; });

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svg(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function fmt(t) {
    t = Math.max(0, Math.round(t || 0));
    return Math.floor(t / 60) + ":" + (t % 60 < 10 ? "0" : "") + (t % 60);
  }
  function secs(x) { return (Math.round((x || 0) * 10) / 10).toFixed(1) + " s"; }

  // ---------------------------------------------------------------- taxonomy
  function categorize(reason, kind) {
    var r = String(reason || "").trim();
    if (kind === "retro_removed" && !r) return "retracted";
    for (var i = 0; i < rx.length; i++) if (rx[i].re.test(r)) return rx[i].key;
    return "other";
  }
  function family(reason) {
    var head = String(reason || "").trim().toLowerCase().split(/[:(]/)[0];
    return FAMS[head] ? head : "other";
  }
  function label(key) { return byKey[key] ? byKey[key].label : "Other sensitive"; }
  function shortLabel(key) { return byKey[key] ? byKey[key].short : "Other"; }

  // Recording-state vocabulary. Pipeline names (ON/OFF/PENDING_CONFIRM) and consent names share one set.
  var STATES = {
    recording: { label: "Recording", cls: "st-rec" },
    off_record: { label: "Off the record", cls: "st-off" },
    paused: { label: "Paused (sensitive topic)", cls: "st-wait" },
    awaiting: { label: "Needs your OK", cls: "st-wait" },
    off: { label: "Notes off", cls: "st-idle" }
  };
  var PIPE = { ON: "recording", OFF: "off_record", PENDING_CONFIRM: "awaiting" };
  function stateKey(s) { return PIPE[s] || (STATES[s] ? s : "recording"); }
  function stateLabel(s) { return STATES[stateKey(s)].label; }

  // "Off the record x2, Personal and health x1, ..." (taxonomy order, zero counts skipped)
  function summaryText(counts) {
    var parts = [];
    CATS.forEach(function (c) { var n = counts && counts[c.key]; if (n) parts.push(c.short + " x" + n); });
    return parts.length ? parts.join(", ") : "Nothing kept out so far";
  }

  // ---------------------------------------------------------------- shared small pieces
  function chip(key, onOpen, opts) {
    var b = el("button", "qchip", "Kept out: " + shortLabel(key));
    b.type = "button";
    b.setAttribute("data-category", key);
    b.setAttribute("aria-label", "Kept out of the notes, " + label(key) + ". Open how this was decided.");
    if (opts && opts.title) b.title = opts.title;
    b.onclick = function () { if (onOpen) onOpen(key); };
    return b;
  }

  function timelineSvg(timeline, now) {
    var W = 600, H = 30, bands = [], tl = (timeline || []).slice();
    var end = Math.max(now || 0, tl.length ? tl[tl.length - 1].t : 0, 1);
    var s = svg("svg", { "class": "tl", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img",
      "aria-label": "Recording state over time" });
    if (!tl.length || tl[0].t > 0) tl.unshift({ t: 0, state: tl.length ? "off" : "recording" });
    tl.forEach(function (step, i) {
      bands.push({ s: stateKey(step.state), a: step.t, b: i + 1 < tl.length ? tl[i + 1].t : end });
    });
    bands.forEach(function (b) {
      var x = b.a / end * W, w = Math.max(2, (b.b - b.a) / end * W);
      var r = svg("rect", { x: x.toFixed(1), y: 3, width: w.toFixed(1), height: H - 6, "class": STATES[b.s].cls });
      var t = svg("title"); t.textContent = STATES[b.s].label + ", " + fmt(b.a) + " to " + fmt(b.b);
      r.appendChild(t); s.appendChild(r);
    });
    return { svg: s, end: end, bands: bands };
  }

  // ---------------------------------------------------------------- INSIGHTS (aggregate only)
  // data: { approved:n, kept_out:{categoryKey:n}, total:n, removed:n?, timeline:[{t,state}], now:seconds,
  //         labels?: {approved:"In the notes"} }
  function renderInsights(box, data) {
    clear(box);
    data = data || {};
    var counts = data.kept_out || {}, total = 0;
    CATS.forEach(function (c) { total += counts[c.key] || 0; });
    box.setAttribute("data-total", String(total));

    var tiles = el("div", "iv-tiles");
    function tile(n, txt, cls) {
      var d = el("div", "iv-tile " + (cls || ""));
      d.appendChild(el("b", null, String(n))); d.appendChild(el("span", null, txt)); tiles.appendChild(d);
    }
    tile(data.approved || 0, (data.labels && data.labels.approved) || "In the notes", "ok");
    tile(total, "Kept out", "out");
    if (typeof data.removed === "number") tile(data.removed, "Removed by you", "");
    box.appendChild(tiles);

    box.appendChild(el("h3", null, "What kind of things were kept out"));
    box.appendChild(el("p", "iv-sum", summaryText(counts)));
    var list = el("ul", "iv-bars");
    var max = 1;
    CATS.forEach(function (c) { max = Math.max(max, counts[c.key] || 0); });
    CATS.forEach(function (c) {
      var n = counts[c.key] || 0, li = el("li", n ? "has" : "none");
      li.setAttribute("data-category", c.key);
      li.appendChild(el("span", "iv-name", c.label));
      var bar = svg("svg", { "class": "iv-bar", viewBox: "0 0 100 8", preserveAspectRatio: "none", "aria-hidden": "true" });
      bar.appendChild(svg("rect", { x: 0, y: 0, width: 100, height: 8, "class": "iv-track" }));
      if (n) bar.appendChild(svg("rect", { x: 0, y: 0, width: (n / max * 100).toFixed(1), height: 8, "class": "iv-fill" }));
      li.appendChild(bar);
      li.appendChild(el("b", "iv-n", String(n)));
      list.appendChild(li);
    });
    box.appendChild(list);

    box.appendChild(el("h3", null, "Recording state over time"));
    var tl = timelineSvg(data.timeline, data.now);
    box.appendChild(tl.svg);
    var legend = el("div", "iv-legend");
    ["recording", "off_record", "paused", "off"].forEach(function (k) {
      var seen = tl.bands.some(function (b) { return b.s === k; });
      if (!seen && k !== "recording") return;
      var sp = el("span", null, STATES[k].label);
      sp.insertBefore(el("i", STATES[k].cls), sp.firstChild);
      legend.appendChild(sp);
    });
    legend.appendChild(el("span", "iv-range", "0:00 to " + fmt(tl.end)));
    box.appendChild(legend);
    box.appendChild(el("p", "iv-note", "Only kinds and counts are shown. The words, the speakers and the individual lines that were kept out are never listed here."));
    return { total: total, text: summaryText(counts) };
  }

  // ---------------------------------------------------------------- EXPLAINABILITY
  // state: { selected: categoryKey|null, item: {category, trail:{family,before,after,held_s}}|null,
  //          counts: {key:n}, holdSeconds: n }
  // opts:  { onSelect(key), reveal: function(item) -> string|null   (operator replay mode only) }
  function ruleSteps(trail, holdSeconds) {
    var f = FAMS[trail.family] || FAMS.other || { label: "Rule", text: "" };
    var steps = [
      ["1. Line arrives", "It is held in a waiting buffer before it can reach the notes" + (holdSeconds ? " (hold window " + secs(holdSeconds) + ")" : "") + "."],
      ["2. A rule family decides", f.label + (f.engine === "llm" ? " (local language model)" : " (rule based)") + ". " + f.text],
      ["3. Recording state", stateLabel(trail.before) + "  ->  " + stateLabel(trail.after)],
      ["4. Hold timing", typeof trail.held_s === "number" ? "Decided " + secs(trail.held_s) + " after the line arrived." : "Timing not recorded."],
      ["5. Outcome", "The line stays out of the notes. Its words are not kept in this view."]
    ];
    return steps;
  }

  function renderExplain(box, state, opts) {
    clear(box);
    state = state || {}; opts = opts || {};
    var counts = state.counts || {}, sel = state.selected, item = state.item;
    box.appendChild(el("p", "ex-intro", "This is how the system decides what stays out of the notes. Pick a kind below to see its rule, or open a \"kept out\" marker in the live captions to see the trail for that moment. Nothing here shows what was said."));

    var grid = el("div", "ex-grid");
    CATS.forEach(function (c) {
      var b = el("button", "ex-card" + (sel === c.key ? " on" : ""));
      b.type = "button";
      b.setAttribute("data-category", c.key);
      b.setAttribute("aria-pressed", sel === c.key ? "true" : "false");
      b.appendChild(el("b", null, c.label));
      b.appendChild(el("span", "ex-count", (counts[c.key] || 0) + " so far"));
      b.appendChild(el("span", "ex-rule", c.rule));
      b.onclick = function () { if (opts.onSelect) opts.onSelect(c.key); };
      grid.appendChild(b);
    });
    box.appendChild(grid);

    var detail = el("section", "ex-detail");
    detail.setAttribute("aria-live", "polite");
    box.appendChild(detail);
    if (!sel) {
      detail.appendChild(el("p", "dim", "No kind selected."));
      return;
    }
    var cat = byKey[sel];
    detail.appendChild(el("h3", null, item ? "Trail for the marker you opened" : "How \"" + cat.label + "\" is decided"));
    if (!item) {
      detail.appendChild(el("p", null, cat.rule));
      detail.appendChild(el("h4", null, "Rule families that can produce this kind"));
      var fl = el("ul", "ex-trail");
      (cat.families || []).forEach(function (fk) {
        var f = FAMS[fk]; if (!f) return;
        var li = el("li"); li.appendChild(el("b", null, f.label + (f.engine === "llm" ? "  (language model)" : "  (rule based)")));
        li.appendChild(el("span", null, f.text)); fl.appendChild(li);
      });
      detail.appendChild(fl);
      detail.appendChild(el("p", "dim", "Every line takes the same path: wait in the hold buffer, get checked by these families in order, then either be released to the notes or kept out. The recording state before and after, and how long the line waited, are shown when you open a kept-out marker."));
      return;
    }
    var ol = el("ol", "ex-trail steps");
    ruleSteps(item.trail || {}, state.holdSeconds).forEach(function (st) {
      var li = el("li"); li.appendChild(el("b", null, st[0])); li.appendChild(el("span", null, st[1])); ol.appendChild(li);
    });
    detail.appendChild(ol);
    if (typeof opts.reveal === "function") {
      var rb = el("button", "ex-reveal", "Reveal text (operator only)");
      rb.type = "button"; rb.setAttribute("aria-expanded", "false");
      var tx = el("div", "ex-text"); tx.hidden = true;
      rb.onclick = function () {
        tx.hidden = !tx.hidden;
        tx.textContent = tx.hidden ? "" : (opts.reveal(item) || "(no text recorded)");
        rb.textContent = tx.hidden ? "Reveal text (operator only)" : "Hide text";
        rb.setAttribute("aria-expanded", tx.hidden ? "false" : "true");
      };
      detail.appendChild(rb); detail.appendChild(tx);
    }
  }

  root.OTRViews = {
    categories: CATS, families: FAMS, categorize: categorize, family: family, label: label, shortLabel: shortLabel,
    stateKey: stateKey, stateLabel: stateLabel, summaryText: summaryText, chip: chip,
    renderInsights: renderInsights, renderExplain: renderExplain, fmt: fmt, secs: secs
  };
  if (typeof module !== "undefined" && module.exports) module.exports = root.OTRViews;
})(typeof window !== "undefined" ? window : globalThis);
