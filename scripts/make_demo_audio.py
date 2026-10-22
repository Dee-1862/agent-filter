"""Generate a small multi-speaker demo (per-speaker WAVs) from a demo script with LOCAL TTS.

Uses Windows SAPI (System.Speech via PowerShell). Nothing is downloaded. Optional tool:
if no TTS is available it says so and exits with code 3; the rest of OTR does not need it.

  python scripts/make_demo_audio.py [--script demo/scripts/demo_main.txt] [--out demo_audio]

Writes into --out:
  <speaker>.wav   one per speaker, all the same length, silent while others talk (time-aligned,
                  like LiveKit per-participant tracks)   -> python -m otr.app --source audio --audio demo_audio
  mixed.wav       the sum of all tracks                  -> --audio demo_audio/mixed.wav --turns demo_audio/turns.json
  turns.json      [{speaker,start,end}] ground-truth speaker turns
  timing.json     per line: speaker, text, start, end, voice
SAPI on a stock Windows has only 2 voices (David, Zira), so 4 speakers share them with
different speaking rates. That is fine for a pipeline demo, not for diarization research.
Output is 16 kHz mono 16-bit PCM.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SR = 16000

PS_LIST = ("Add-Type -AssemblyName System.Speech; "
           "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
           "$s.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object "
           "{ $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Gender }")

PS_SYNTH = r"""
param([string]$Jobs)
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 $Jobs | ConvertFrom-Json
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($it in $items) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($it.voice)
  $s.Rate = [int]$it.rate
  $s.SetOutputToWaveFile($it.out, $fmt)
  $s.Speak($it.text)
  $s.Dispose()
}
"""


def _powershell(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", *args], capture_output=True,
                          text=True, timeout=timeout)


def list_voices() -> list[tuple[str, str]]:
    """[(name, gender)] of installed SAPI voices; [] when SAPI is unavailable."""
    if sys.platform != "win32":
        return []
    try:
        r = _powershell(["-Command", PS_LIST], timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        name, _, gender = line.strip().partition("|")
        if name:
            out.append((name, gender))
    return out


def parse_lines(path: Path) -> list[tuple[str, str, float]]:
    """(speaker, text, pause_before) per spoken line; '@pause N' adds N seconds."""
    out, pause, last = [], 0.0, "Unknown"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@pause"):
            try:
                pause += float(line.split()[1])
            except (IndexError, ValueError):
                pass
            continue
        name, sep, rest = line.partition(":")
        name = name.strip()
        if sep and name and len(name.split()) <= 3 and not any(c.isdigit() for c in name):
            last, body = name, rest.strip()
        else:
            body = line
        if body:
            out.append((last, body, pause))
            pause = 0.0
    return out


def assign_voices(speakers: list[str], voices: list[tuple[str, str]]) -> dict[str, tuple[str, int]]:
    """speaker -> (voice name, rate). Alternates female/male voices; repeats get a different rate."""
    female = [v for v, g in voices if g.lower() == "female"]
    male = [v for v, g in voices if g.lower() == "male"]
    pool: list[str] = []
    for i in range(max(len(female), len(male))):
        pool += female[i:i + 1] + male[i:i + 1]
    pool = pool or [v for v, _ in voices]
    rates = [0, 2, -2, 3, -3]
    return {sp: (pool[i % len(pool)], rates[(i // len(pool)) % len(rates)]) for i, sp in enumerate(speakers)}


def read_pcm(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("int32")


def write_wav(path: Path, samples) -> None:
    import numpy as np
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.clip(samples, -32768, 32767).astype("<i2").tobytes())


def build(script: Path, out: Path, gap: float = 0.5) -> int:
    import numpy as np
    voices = list_voices()
    if not voices:
        print("[make_demo_audio] No local TTS available (needs Windows SAPI / System.Speech with at least "
              "one installed voice). Nothing was generated. This tool is optional: record your own "
              "per-speaker WAVs and use  python -m otr.app --source audio --audio <folder>.", file=sys.stderr)
        return 3
    lines = parse_lines(script)
    if not lines:
        print(f"[make_demo_audio] no spoken lines in {script}", file=sys.stderr)
        return 2
    speakers = list(dict.fromkeys(sp for sp, _, _ in lines))
    assign = assign_voices(speakers, voices)
    print("[make_demo_audio] voices: " + ", ".join(f"{s}={v}(rate {r})" for s, (v, r) in assign.items()))
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        jobs = [{"voice": assign[sp][0], "rate": assign[sp][1], "text": text, "out": str(tdp / f"l{i:03d}.wav")}
                for i, (sp, text, _) in enumerate(lines)]
        (tdp / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        (tdp / "synth.ps1").write_text(PS_SYNTH, encoding="utf-8-sig")
        r = _powershell(["-ExecutionPolicy", "Bypass", "-File", str(tdp / "synth.ps1"), str(tdp / "jobs.json")])
        if r.returncode != 0 or not all(Path(j["out"]).is_file() for j in jobs):
            print("[make_demo_audio] SAPI synthesis failed:\n" + (r.stderr or r.stdout), file=sys.stderr)
            return 3
        t = 0.0
        placed = []  # (speaker, text, start, end, voice, pcm)
        for (sp, text, pause), job in zip(lines, jobs):
            pcm = read_pcm(Path(job["out"]))
            t += pause
            placed.append((sp, text, t, t + len(pcm) / SR, job["voice"], pcm))
            t += len(pcm) / SR + gap
        total = int((t + 1.0) * SR)
        tracks = {sp: np.zeros(total, dtype="int32") for sp in speakers}
        for sp, _, a, _, _, pcm in placed:
            i = int(a * SR)
            tracks[sp][i:i + len(pcm)] += pcm
    for sp, tr in tracks.items():
        write_wav(out / f"{sp.lower()}.wav", tr)
    write_wav(out / "mixed.wav", sum(tracks.values()) // 1)
    turns = [{"speaker": sp, "start": round(a, 3), "end": round(b, 3)} for sp, _, a, b, _, _ in placed]
    (out / "turns.json").write_text(json.dumps(turns, indent=1), encoding="utf-8")
    (out / "timing.json").write_text(json.dumps(
        [{"speaker": sp, "text": tx, "start": round(a, 3), "end": round(b, 3), "voice": v}
         for sp, tx, a, b, v, _ in placed], indent=1), encoding="utf-8")
    print(f"[make_demo_audio] wrote {len(speakers)} speaker tracks + mixed.wav, {total / SR:.1f}s each, to {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--script", default=str(ROOT / "demo" / "scripts" / "demo_main.txt"))
    ap.add_argument("--out", default=str(ROOT / "demo_audio"))
    ap.add_argument("--gap", type=float, default=0.5, help="seconds of silence between lines")
    a = ap.parse_args(argv)
    return build(Path(a.script), Path(a.out), a.gap)


if __name__ == "__main__":
    sys.exit(main())
