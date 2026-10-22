# Local runtime and open-source stack

Meeting content stays on the machine running this demo. GitHub holds source code
and documentation; it must never receive meeting audio, transcripts, consent
records, model inputs, or generated notes.

## Runtime path

| Component | Runs where | Meeting data it handles |
|---|---|---|
| LiveKit server | `127.0.0.1:7880` | Participant media and room signaling |
| Meeting page | Locally served at `127.0.0.1:8765` by default | Room media, each person's own approved draft, and the final transcript only after an explicit request |
| Recorder and ASR | Local Python process | Only opted-in audio; provisional text in memory |
| Privacy pipeline | Same Python process | Opted-in text; releases approved lines only |

The recorder starts with `auto_subscribe=False`. A participant's own button
enables subscription to their audio track. Stop revokes that person's consent,
unsubscribes, and discards pending text. A sensitive policy flag also pauses
that person's capture. Each browser stream carries only that speaker's approved
draft lines and removal IDs. Other participants see notes on/off, but receive
neither that speaker's draft nor a private sensitive-pause reason. Speakers can
remove draft lines, then explicitly finish their notes. The combined final is
served only after every admitted participant finishes and someone opens the
final report or requests a copy. The report shows counts of locally suppressed
and removed lines without their text, reasons, or speaker breakdown. Lines
that were never transcribed because notes were OFF are not counted. The page
never exports the final automatically. No audio files or transcript database
are created by the live path.

After finishing their notes, participants can separately opt in to an email
copy of the final transcript. Joining with an email address does not opt them
in. Only the host can retrieve opted-in addresses, and only once the combined
final transcript is ready. When closing the room, the host can review the
approved transcript and open a prefilled draft in their mail app. This app
does not send mail. The host can also end without an email. Opening the draft
may sync that final transcript through the host's mail provider, which is
outside this local runtime. Meeting audio, provisional text, withheld lines,
and other participants' live drafts never go into the mail draft.

The instant-meeting entry flow keeps room IDs, guest requests, unverified email
labels, and host admission decisions in the local Python process. A guest does
not receive a LiveKit room token until the host admits them. Ending the room
clears that meeting's in-memory state. Creating a room on a loopback address
produces a link usable only on the host machine. A second device needs a
reachable local address, a browser-trusted HTTPS origin for microphone/camera
access, and production-length LiveKit credentials before this demo can be
shared on a network. The current localhost preview is not a remote invite.
See [SECURE_LAN.md](SECURE_LAN.md) for the local HTTPS/WSS launch paths. Its
default local-certificate mode requires trust on each guest device; the
public-certificate mode does not.

The planned no-install guest link uses `meeting.lancestreuber.com` and a
browser-trusted certificate while the app and LiveKit stay on the meeting host.
Namecheap DNS and certificate validation handle the hostname and proof of
domain control, not meeting content. Vercel does not serve this meeting app,
process its media, or consume its hosting allowance. A DNS record and trusted
certificate are still required before that link can be used.

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

In the instant-meeting UI on 2026-10-22, a host in Brave created a room and
admitted a guest in a separate visible Chrome session. The host saw the guest's
video tile and notes state. With notes enabled, the guest's private drawer
displayed approved lines from a looping synthetic voice after the local hold.
The backend's per-viewer stream tests keep guest lines out of the host stream.
The same sentence repeated because the
test audio looped. A separate local LiveKit SDK run returned the expected line
through Whisper and the policy pipeline. The current demo test suite has 45
passing tests. The secure LAN launcher served HTTPS successfully from the host
Mac, but a second physical device has not yet been tested with its certificate.

The same-machine `--dev` server uses placeholder credentials. Do not expose
this demo server to a LAN or the internet as-is. LAN use needs its own keys,
HTTPS, access control, and a local network egress check. Other participants
can still hear a person whose notetaker consent is OFF; OFF means the notetaker
does not subscribe to that person's track. The ASR and policy process runs on
the local meeting host, so this prototype does not keep processing on each
participant's device. The host retains approved draft lines in memory during
the session; each speaker controls whether their lines enter the combined final.
The sensitive-content rules are an imperfect filter, not a guarantee that every
HR detail or number is caught.
