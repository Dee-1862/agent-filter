# Local synthetic-voice meeting test (2026-10-22)

I ran Piper-generated speech from several distinct voices through the local LiveKit room, the local `base.en` faster-whisper model, and the consent-gated demo. The audio, scenario manifests, and result JSON stayed in `/tmp`; none are part of this repository. Piper's voice weights were downloaded before the test. During the meeting runs, the app and LiveKit used loopback addresses and Whisper loaded local weights with `HF_HUB_OFFLINE=1`.

| Case | Observed result |
| --- | --- |
| Two consenting speakers talked at about the same time | Both public lines reached the shared transcript with the right speaker names. Recognition changed a few words. |
| One participant kept consent OFF | Their speech produced no approved line. |
| A consenting participant mentioned salary and an employee number together | That participant alone switched to a sensitive pause. Their line stayed out while another person's public line was approved. |
| A participant switched consent OFF after speaking | Later speech stayed out. An earlier line still in the 10-second hold window was discarded too. |
| A participant said a direct stop request | The first run failed: Whisper changed the last word of the request, the exact phrase rule missed it, and later speech was approved. The rule now accepts the clear opening words “stop recording”; a repeat run switched that participant OFF and kept later speech out. |
| A participant said “strike that” after a line had been approved | A timed snapshot showed the line before the request and no line afterward. Anyone who saw it during that interval could already have read it. |
| A participant gave only an employee number, without the word “salary” | **Failed:** the number appeared in the approved transcript. The present keyword fallback does not reliably identify HR identifiers. |

These runs establish that the basic per-person LiveKit path works. They do **not** establish that sensitive content is reliably excluded. In particular, the employee-number failure needs a policy fix and another audio test before using this with real HR conversations. The spoken stop still depends on speech recognition hearing the imperative; the visible consent control revokes consent without depending on recognition. Secondhand disclosure was outside this test.

## Repeat with synthetic WAV files

`experiments/livekit_sim.py` joins one local LiveKit participant per manifest entry, publishes each WAV, applies scheduled consent changes, and reads only the approved `/api/me` view. It rejects non-loopback app and LiveKit URLs and requires `"synthetic": true`. Install the demo and ingest requirements plus `ffmpeg`; run a local LiveKit server and the live demo first. Keep the generated WAVs, manifests, and result JSON outside the repository.

I used the [Piper CLI](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md) with the 18-speaker `en_US-arctic-medium` voice. To create your own synthetic files in `/tmp`, install `piper-tts` in an isolated environment, then run:

```bash
python -m piper.download_voices --data-dir /tmp/meeting-sim/models en_US-arctic-medium
python -m piper -m en_US-arctic-medium --data-dir /tmp/meeting-sim/models \
  -s 0 -f /tmp/meeting-sim/ada.wav -- "This is a synthetic test."
```

Change the speaker ID and sentence for the other WAVs. Downloading voice weights needs network access; speech generation and the meeting run use the local files afterward.

```json
{
  "synthetic": true,
  "observe_at": [8, 16],
  "participants": [
    {
      "name": "Ada",
      "actions": [
        {"at": 0, "recording": true},
        {"at": 1, "wav": "ada.wav"},
        {"at": 12, "recording": false}
      ]
    },
    {
      "name": "Ben",
      "actions": [
        {"at": 0, "recording": false},
        {"at": 2, "wav": "ben.wav"}
      ]
    }
  ]
}
```

Save that manifest beside the synthetic WAVs and run:

```bash
python experiments/livekit_sim.py /tmp/meeting-sim/scenario.json \
  --app http://127.0.0.1:8765 --settle 12 \
  --output /tmp/meeting-sim/results.json
```

`observe_at` is optional. Its snapshots help verify that a line appeared and was later removed. The result reports participant status and approved lines; it does not expose private held text. No WAVs or result files should be committed.
