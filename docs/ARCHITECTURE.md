# Architecture: how voice becomes notes

Mermaid diagrams of the running system, drawn from the code on `master` (`otr/`, `demo/`). They render on GitHub and in VS Code with a Mermaid preview extension.

**Status legend** (applies to every diagram): nothing below the browser has been run against real voices yet. The LiveKit path, real speech-to-text and the Ollama language-model calls are untested end to end; the pipeline, runtime and demo server are covered by offline tests (`python -m pytest tests -q`).

## 1. End to end: voice in the browser to text on screen

Two demo modes share the same engine. They differ in who captures the voice and who sees the output.

```mermaid
flowchart LR
  subgraph Browser["Browser (each participant)"]
    MIC["Microphone"]
    CONSENT["live.html + live.js<br/>join, consent toggle, mic on/off"]
    VIEW["index.html meeting view<br/>tiles, captions, Insights, Why?, Live"]
    MIC --> CONSENT
  end

  subgraph LK["LiveKit server (docker, local)"]
    ROOM["Room: one audio track per participant"]
  end

  CONSENT -- "WebRTC publish<br/>identity = person-uuid" --> ROOM

  subgraph Ingest["otr/ingest"]
    SUB["LiveKitSource<br/>subscribes per track,<br/>only if that person consented"]
    VAD["Energy VAD<br/>utterance chunking"]
    STT["faster-whisper CPU int8<br/>LocalAgreement-2 confirm"]
    SUB --> VAD --> STT
  end
  ROOM -- "audio frames" --> SUB

  STT -- "Segment: speaker, text, t_start, t_end" --> ENGINE

  subgraph Engine["Privacy engine"]
    ENGINE["Pipeline<br/>see diagram 2"]
  end

  ENGINE -- "Event: held, committed, redacted,<br/>pending_confirm, retro_removed, state_change" --> SERVER

  subgraph Server["demo/server.py (FastAPI)"]
    SERVER["StreamRunner<br/>one worker thread, wall-clock ticker<br/>SSE history for reconnect"]
    LIVE["LiveSession<br/>consent mode: one Pipeline per speaker<br/>approved-only transcript"]
  end

  SERVER -- "SSE /stream" --> VIEW
  LIVE -- "SSE /stream approved lines" --> CONSENT
  VIEW -- "POST /api/confirm, /api/hold, /api/say" --> SERVER
  CONSENT -- "POST /api/join, /api/consent, /api/leave" --> LIVE
```

Which pieces serve which mode:

| Mode (`python -m demo.server ...`) | Voices come from | Page served | Engine wiring |
|---|---|---|---|
| `--source livekit` (per-person consent, Lance) | Browsers join through `live.html`; mic published to LiveKit | `live.html` | `LiveSession`: one Pipeline per speaker; a sensitive hold pauses only that speaker |
| `--source livekit-stream` (shared view) | Any LiveKit client in the room (e.g. the LiveKit Meet app) | `index.html` | `StreamRunner`: one Pipeline over all speakers |
| `--source replay --script FILE` | Script file, no audio | `index.html` | `StreamRunner` |

**Gap to close:** `index.html` (the new meeting view) has no microphone capture of its own. Live voice enters only through `live.html` or another LiveKit client. Unifying them (mic and consent inside the meeting view) is the main frontend task left.

## 2. Inside the Pipeline: what happens to one Segment

```mermaid
flowchart TD
  A["push(Segment, now)"] --> B{"Duplicate id?"}
  B -- yes --> Z0["ignore"]
  B -- no --> C{"Arrived before already processed<br/>t_start?"}
  C -- yes --> C2["roll back state machine,<br/>replay in time order"]
  C -- no --> D
  C2 --> D["PII pass<br/>Presidio if installed else regex<br/>mask in place: EMAIL, PHONE, SSN, CARD"]
  D --> E["Cue detector<br/>ASR-noise repair, then regex, then false-alarm check"]
  E --> F{"Cue type"}
  F -- "start: off the record,<br/>between us" --> G["state = OFF<br/>cue line redacted"]
  F -- "scope end: back on the record" --> H["state = ON<br/>cue line dropped"]
  F -- "retroactive: strike that,<br/>forget what I said about X" --> I["resolve target<br/>LLM ids, else keyword overlap,<br/>else previous line within strike_window"]
  F -- "false alarm: movie title, quote,<br/>negation" --> J
  F -- none --> J{"State"}
  I --> I2{"Target where?"}
  I2 -- "in hold buffer" --> I3["redacted, reason retro:match"]
  I2 -- "already committed" --> I4["retro_removed, logged in audit"]
  J -- OFF --> K{"Scope still open?"}
  K -- "explicit end cue, LLM verdict,<br/>pivot phrase, 3 off-topic lines,<br/>or 90 s timeout" --> L["state = ON"]
  K -- otherwise --> M["redacted, reason scope:off<br/>tentative lines held until settled"]
  J -- ON --> N["Sensitivity check<br/>LLM classifier, keyword fallback"]
  L --> N
  N -- "sensitive: salary, health, HR, layoffs" --> O["state = PENDING_CONFIRM<br/>event pending_confirm<br/>nothing after it is released"]
  N -- "not sensitive" --> P["hold buffer<br/>event held"]
  P --> Q["tick(now): older than hold_seconds"]
  Q --> R["committed<br/>into notes"]
  O --> S{"confirm(segment_id, keep_out)"}
  S -- "keep_out true" --> T["redacted, related follow-ups kept out"]
  S -- "keep_out false" --> P
  O -- "flush before answer" --> T
```

Key properties, each backed by a unit test in `tests/test_pipeline.py`:

- `hold_seconds` is read at release time, so the UI slider affects text already held.
- Only committed segments reach `notes()`; the summary step must never see held or redacted text.
- `Pipeline` is guarded by a lock, because the runtime calls `push`, `tick` and `confirm` from different threads.
- With `llm=None` everything above still runs on rules and keyword checks.

## 3. Sequences for the three demo beats

```mermaid
sequenceDiagram
  autonumber
  participant Mic as Browser mic
  participant LK as LiveKit
  participant Bot as LiveKitSource + STT
  participant P as Pipeline
  participant S as StreamRunner / SSE
  participant UI as Meeting view

  Note over Mic,UI: Beat 1: explicit off the record
  Mic->>LK: speech "this next bit is off the record"
  LK->>Bot: audio frames
  Bot->>P: Segment
  P-->>S: state_change OFF, redacted
  S-->>UI: status pill OFF THE RECORD
  Mic->>LK: "between us, the reorg is real"
  Bot->>P: Segment
  P-->>S: redacted, reason scope:off
  S-->>UI: chip "kept out of notes" (no text)
  Mic->>LK: "okay, back on the record"
  Bot->>P: Segment
  P-->>S: state_change ON

  Note over Mic,UI: Beat 2: strike that on held text
  Mic->>LK: "the beta goes to fifty customers"
  Bot->>P: Segment
  P-->>S: held
  Mic->>LK: "strike that"
  Bot->>P: Segment
  P-->>S: redacted, reason retro:match
  S-->>UI: held line removed before it ever committed

  Note over Mic,UI: Beat 3: implicit sensitive content
  Mic->>LK: "the new hire's salary is one forty"
  Bot->>P: Segment
  P-->>S: pending_confirm
  S-->>UI: card "Keep that out of the notes?" (text hidden)
  UI->>S: POST /api/confirm, keep_out true
  S->>P: confirm(segment_id, true)
  P-->>S: redacted, reason confirm:keep_out
```

## 4. Where the frontend sits

```mermaid
flowchart TD
  L0["Level 0: meeting view<br/>tiles, captions of committed lines only,<br/>status pill, Insights and Live buttons"]
  L1["Level 1: Insights<br/>counts, state timeline,<br/>final notes, kept-out list with reasons"]
  L2["Level 2: Why?<br/>rule that fired, state before and after,<br/>hold timeline, Reveal text on click"]
  LV["Live button<br/>count of new events while panels are open,<br/>one click back to real time"]
  L0 -- "click Insights or i" --> L1
  L1 -- "click Why?" --> L2
  L2 -- "Escape" --> L1
  L0 --- LV
  L1 --- LV
  L2 --- LV
```

Private text is never drawn on level 0 or 1. It still travels to the browser in the event stream, so it is visible in developer tools; it appears on screen only after clicking Reveal text or Show text.

## 5. Component map

| Layer | Files | Role |
|---|---|---|
| Contract | `otr/types.py` | `Segment`, `Event`, `Pipeline` interface; the seam between the two work streams |
| Ingest | `otr/ingest/livekit_source.py`, `stt.py`, `replay_source.py`, `diarize.py`, `mint_token.py` | LiveKit track subscription, per-person consent, speech-to-text, script replay, mixed-audio fallback |
| Engine | `otr/pipeline.py`, `hold_buffer.py`, `cue_detector.py`, `state_machine.py`, `pii.py`, `llm.py` | The privacy pipeline in diagram 2 |
| Runtime | `otr/runtime.py` | Runs pipeline calls on one worker thread, ticks on wall-clock time, fans out events |
| Server | `demo/server.py`, `demo/live_session.py` | HTTP and SSE endpoints; consent-mode session |
| Frontend | `demo/static/index.html`, `live.html`, `live.js` | Meeting view; consent and mic page |
| Evaluation | `bench/` | OTR-Bench items, systems A, B and C, metrics, hold sweep |
