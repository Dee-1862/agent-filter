"""Near-field gate: speech much quieter than the speaker's own level is dropped before transcription."""
import array
import math

from otr.ingest.stt import SR, UtteranceChunker


def tone(seconds: float, amp: int) -> bytes:
    n = int(SR * seconds)
    return array.array("h", (int(amp * math.sin(2 * math.pi * 220 * i / SR)) for i in range(n))).tobytes()


def silence(seconds: float) -> bytes:
    return bytes(int(SR * seconds) * 2)


def feed_utterance(ch: UtteranceChunker, amp: int):
    out = ch.feed(tone(1.0, amp))
    out += ch.feed(silence(1.2))
    return out


def make(ratio=None):
    calls = []

    def transcribe(_audio):
        calls.append(1)
        return "hello there"

    ch = UtteranceChunker(transcribe, energy_thresh=200, partial_every=float("inf"))
    if ratio is not None:
        ch.nearfield_ratio = ratio
    return ch, calls


def test_background_quiet_speech_is_dropped_after_the_speaker_level_is_known():
    ch, calls = make()
    for _ in range(3):
        assert feed_utterance(ch, 8000)          # the speaker talking normally
    assert len(calls) == 3
    quiet = feed_utterance(ch, 1500)             # someone talking far from the microphone
    assert quiet == [] and len(calls) == 3       # never transcribed
    assert ch.dropped_quiet == 1
    assert feed_utterance(ch, 8000)              # the speaker is still heard
    assert len(calls) == 4


def test_gate_can_be_disabled():
    ch, calls = make(ratio=0)
    for _ in range(3):
        feed_utterance(ch, 8000)
    assert feed_utterance(ch, 1500)
    assert ch.dropped_quiet == 0


def test_first_utterances_are_never_dropped():
    ch, calls = make()
    assert feed_utterance(ch, 1500)              # no reference level yet: accept
