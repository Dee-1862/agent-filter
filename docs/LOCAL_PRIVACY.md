# Local runtime and open-source stack

Meeting content stays on the machine running this demo. GitHub holds source code
and documentation; it must never receive meeting audio, transcripts, consent
records, model inputs, or generated notes.

## Runtime path

| Component | Runs where | Meeting data it handles |
|---|---|---|
| LiveKit server | `127.0.0.1:7880` | Participant media and room signaling |
| Meeting page | Locally served at `127.0.0.1:8765` | Each participant's room media and approved transcript |
| Recorder and ASR | Local Python process | Only opted-in audio; provisional text in memory |
| Privacy pipeline | Same Python process | Opted-in text; releases approved lines only |

The recorder starts with `auto_subscribe=False`. A participant's own button
enables subscription to their audio track. Stop revokes that person's consent,
unsubscribes, and discards pending text. A sensitive policy flag also pauses
that person's capture. The shared browser stream contains only approved lines,
deletion IDs, and text-free status. No audio files or transcript database are
created by the live path.

Model weights are downloaded before a meeting into the ignored `models/`
directory. At runtime, `load_whisper` requires local weights and refuses to
download. Run with `HF_HUB_OFFLINE=1` as an additional guard. The meeting page
serves its LiveKit JavaScript bundle, CSS, and JavaScript locally; it loads no
CDN, analytics, or hosted model script. The current live pipeline uses local
rules and regexes. Deekshith's local model work will extend that policy.

## Open-source components

- [LiveKit server](https://github.com/livekit/livekit) and its [browser](https://github.com/livekit/client-sdk-js) and [Python](https://github.com/livekit/python-sdks) SDKs use Apache-2.0. The vendored browser bundle's license and notice are in `demo/static/livekit-client.LICENSE` and `demo/static/livekit-client.NOTICE`.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://github.com/OpenNMT/CTranslate2), and the [local base.en model](https://huggingface.co/Systran/faster-whisper-base.en) use MIT.
- The app also uses open-source FastAPI, Uvicorn, and Python libraries installed from the requirements files. Check transitive licenses before distributing a packaged binary.

The project is **planned as open source**. The repository is currently private;
publication and its project license can be set with the repository owner when
the team is ready.

## Verification and limits

On 2026-10-22, a real local LiveKit SDK smoke showed an audio track unsubscribed
before opt-in, subscribed after opt-in, and unsubscribed after Stop. A two-person
headless browser check showed one person recording and the other unrecorded,
then both unrecorded after Stop. Browser requests observed in that check went
only to the local web server and local LiveKit server. An end-to-end test using
synthetic speech generated on this Mac went through the meeting page's join and
consent API, LiveKit audio, local Whisper, policy hold, and approved transcript.
A second clip after opt-out added no transcript line. The 42-test suite passed.
These checks do not prove that the sensitive-content classifier catches every
HR or numeric disclosure.

The same-machine `--dev` server uses placeholder credentials. Do not expose
this demo server to a LAN or the internet as-is. LAN use needs its own keys,
HTTPS, access control, and a local network egress check. Other participants
can still hear a person whose notetaker consent is OFF; OFF means the notetaker
does not subscribe to that person's track.
