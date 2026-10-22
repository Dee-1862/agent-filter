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
  function brief(t) { var m = String(t || "").match(/^[^.]*\./); return m ? m[0] : String(t || ""); }
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
    awaiting: { label: "Waiting for your answer", cls: "st-wait" },
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

  // Recording-state band plus its legend, appended to `box`. Shared by the side panel and the pop-out page.
  function renderTimeline(box, timeline, now) {
    var tl = timelineSvg(timeline, now);
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
    return tl;
  }

  // What the system did with a kept-out item, from its rule family only (never from text).
  // Returns {key, label, text}. Shared by the transcript rows, the explain view and the pop-out table.
  function actionOf(trail) {
    var f = String((trail && trail.family) || "");
    if (f === "retro") return { key: "removed_after_approval", label: "Removed after approval",
      text: "The line had been released to your notes, then a later retraction removed it." };
    if (f === "presidio" || f === "regex") return { key: "masked", label: "Masked contact details",
      text: "Contact or ID details were masked before the line could reach your notes." };
    return { key: "kept_out", label: "Kept out before approval",
      text: "The line was held, then kept out. It never reached your notes." };
  }

  // The facts shown when a kept-out row is opened: [label, value] pairs, plain language, no text.
  function explainFacts(item, holdSeconds) {
    var trail = (item && item.trail) || {}, cat = byKey[item && item.category] || byKey.other;
    var act = actionOf(trail);
    return [
      ["What", act.label],
      ["Why", brief(cat ? cat.rule : "")],
      ["When", typeof trail.held_s === "number" ? "Decided " + secs(trail.held_s) + " after it was said" : ""]
    ].filter(function (r) { return r[1]; });
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
    function tile(n, txt) {
      var d = el("div", "iv-tile");
      d.appendChild(el("b", null, String(n))); d.appendChild(el("span", null, txt)); tiles.appendChild(d);
    }
    tile(data.approved || 0, (data.labels && data.labels.approved) || "In your notes");
    tile(total, "Kept private");
    box.appendChild(tiles);

    var list = el("ul", "iv-list");
    CATS.forEach(function (c) {
      var n = counts[c.key] || 0;
      if (!n) return;
      var li = el("li", "has");
      li.setAttribute("data-category", c.key);
      li.appendChild(el("span", "iv-name", c.short));
      li.appendChild(el("b", "iv-n", String(n)));
      list.appendChild(li);
    });
    if (total) box.appendChild(list);
    else box.appendChild(el("p", "dim", "Nothing kept private yet."));

    if (data.timeline && data.timeline.length > 1) renderTimeline(box, data.timeline, data.now);
    return { total: total, text: summaryText(counts) };
  }

  // ---------------------------------------------------------------- EXPLAINABILITY
  // state: { selected: categoryKey|null, item: {category, trail:{family,before,after,held_s}}|null,
  //          counts: {key:n}, holdSeconds: n }
  // opts:  { onSelect(key), reveal: function(item) -> string|null   (operator replay mode only) }
  function ruleSteps(trail, holdSeconds) {
    var f = FAMS[trail.family] || FAMS.other || { label: "Rule", text: "" };
    return [
      ["Heard", "It waited a moment" + (holdSeconds ? " (" + secs(holdSeconds) + ")" : "") + " before reaching the notes."],
      ["Checked", f.label + (f.engine === "llm" ? " (local model)" : " (rule)") + " flagged it."],
      ["Result", "Kept out of the notes" + (typeof trail.held_s === "number" ? ", " + secs(trail.held_s) + " after it was said." : ".")]
    ];
  }

  function renderExplain(box, state, opts) {
    clear(box);
    state = state || {}; opts = opts || {};
    var sel = state.selected, item = state.item;
    box.appendChild(el("p", "ex-intro", "Every line waits a moment, gets checked, then goes to the notes or stays private."));

    var grid = el("div", "ex-grid");
    CATS.forEach(function (c) {
      var b = el("button", "ex-card" + (sel === c.key ? " on" : ""));
      b.type = "button";
      b.setAttribute("data-category", c.key);
      b.setAttribute("aria-pressed", sel === c.key ? "true" : "false");
      b.appendChild(el("b", null, c.short));
      b.onclick = function () { if (opts.onSelect) opts.onSelect(c.key); };
      grid.appendChild(b);
    });
    box.appendChild(grid);

    var detail = el("section", "ex-detail");
    detail.setAttribute("aria-live", "polite");
    box.appendChild(detail);
    if (!sel) return;
    var cat = byKey[sel];
    if (!item) {
      detail.appendChild(el("p", null, brief(cat.rule)));
      return;
    }
    var ol = el("ol", "ex-trail steps");
    ruleSteps(item.trail || {}, state.holdSeconds).forEach(function (st) {
      var li = el("li"); li.appendChild(el("b", null, st[0])); li.appendChild(el("span", null, st[1])); ol.appendChild(li);
    });
    detail.appendChild(ol);
    if (typeof opts.reveal === "function") {
      var rb = el("button", "ex-reveal", "Show text");
      rb.type = "button"; rb.setAttribute("aria-expanded", "false");
      var tx = el("div", "ex-text"); tx.hidden = true;
      rb.onclick = function () {
        tx.hidden = !tx.hidden;
        tx.textContent = tx.hidden ? "" : (opts.reveal(item) || "(no text recorded)");
        rb.textContent = tx.hidden ? "Show text" : "Hide text";
        rb.setAttribute("aria-expanded", tx.hidden ? "false" : "true");
      };
      detail.appendChild(rb); detail.appendChild(tx);
    }
  }

  root.OTRViews = {
    categories: CATS, families: FAMS, categorize: categorize, family: family, label: label, shortLabel: shortLabel,
    stateKey: stateKey, stateLabel: stateLabel, summaryText: summaryText, chip: chip,
    renderInsights: renderInsights, renderExplain: renderExplain, renderTimeline: renderTimeline,
    actionOf: actionOf, explainFacts: explainFacts, states: STATES, fmt: fmt, secs: secs
  };
  if (typeof module !== "undefined" && module.exports) module.exports = root.OTRViews;
})(typeof window !== "undefined" ? window : globalThis);
