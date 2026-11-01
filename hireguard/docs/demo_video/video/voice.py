"""Narration for the 3-minute demo video: one neural-voice clip per sentence, studio clean-up, a quiet music bed,
then the timeline.

    python voice.py                    # build/narration.wav and build/timeline.json
    python voice.py --rate +3%         # faster voice if the script no longer fits in the duration
    python voice.py --voice en-US-AvaMultilingualNeural
    python voice.py --no-music         # voice only
    python voice.py --samples          # one line in a few female voices, in ../out/voice_samples/, to choose by ear

Needs `pip install edge-tts imageio-ffmpeg numpy`. Only the narration text is sent, to Microsoft's online voice service.
The voice is requested at 96 kbit/s (the library's default is 48), then cleaned up: high-pass, a little warmth and
presence, gentle compression, a short room so it does not sound pasted on, and loudness at -16 LUFS. Pauses follow the
punctuation of the script: a short breath between sentences, longer where a sentence asks for it ("pause"), and the
spare time goes to the pauses between scenes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import wave
from array import array
from pathlib import Path

import edge_tts.communicate as _comm
import imageio_ffmpeg
import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
AUDIO = BUILD / "audio"
RATE_HZ = 48000
GAP_SENTENCE = 0.36   # seconds between sentences of one scene (a breath)
GAP_JITTER = 0.06     # +/- so the rhythm is not mechanical (seeded: the same script gives the same timing)
GAP_SCENE = 0.80      # minimum pause between scenes
GAP_SCENE_MAX = 1.45  # spare time is spread over scene pauses up to this length
FORMAT = "audio-24khz-96kbitrate-mono-mp3"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# edge-tts hard-codes 48 kbit/s; the service also serves 96 kbit/s. Load a copy of its module that asks for it.
_src = Path(_comm.__file__).read_text(encoding="utf-8")
_ns = {"__name__": "edge_tts.communicate", "__package__": "edge_tts", "__file__": _comm.__file__}
exec(compile(_src.replace('"outputFormat":"audio-24khz-48kbitrate-mono-mp3"', f'"outputFormat":"{FORMAT}"'), _comm.__file__, "exec"), _ns)
Communicate = _ns["Communicate"]

# Voice clean-up, applied to the whole narration track
VOICE_CHAIN = ",".join([
    "highpass=f=75",
    "equalizer=f=180:t=q:w=1.0:g=1.5",    # warmth
    "equalizer=f=3400:t=q:w=1.4:g=1.8",   # presence
    "equalizer=f=7600:t=q:w=2.0:g=-2.0",  # tame sibilance
    "acompressor=threshold=-21dB:ratio=2.4:attack=6:release=140:makeup=1.5",
    "aecho=0.9:0.55:19|31|47:0.07|0.05|0.035",  # a small room
])


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


async def synth(text: str, mp3: Path, voice: str, rate: str, pitch: str) -> None:
    for attempt in range(5):
        try:
            data = b""
            async for chunk in Communicate(text, voice, rate=rate, pitch=pitch).stream():
                if chunk["type"] == "audio":
                    data += chunk["data"]
            mp3.write_bytes(data)
            return
        except Exception:  # the online service drops a request now and then
            if attempt == 4:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))


async def synth_all(items: list[tuple[str, Path, str, str, str]]) -> None:
    sem = asyncio.Semaphore(3)

    async def one(text: str, mp3: Path, voice: str, rate: str, pitch: str) -> None:
        async with sem:
            await synth(text, mp3, voice, rate, pitch)

    await asyncio.gather(*(one(*it) for it in items))


def to_wav(mp3: Path, wav: Path) -> float:
    """Mono 48 kHz (long resampling filter), leading and trailing silence trimmed. Returns the length in seconds."""
    trim = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.02"
    ffmpeg("-i", str(mp3), "-af", f"aresample={RATE_HZ}:filter_size=64:cutoff=0.98,{trim},areverse,{trim},areverse",
           "-ac", "1", "-ar", str(RATE_HZ), "-sample_fmt", "s16", str(wav))
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def split_caption(text: str, limit: int = 84) -> list[str]:
    """Caption cards of at most two short lines, cut at punctuation where possible."""
    if len(text) <= limit:
        return [text]
    cut = max((text.rfind(p, 0, limit) for p in (": ", "; ", ", ", ". ")), default=-1)
    if cut < limit // 3:
        cut = text.rfind(" ", 0, limit)
    head, tail = text[: cut + 1].strip(), text[cut + 1:].strip()
    return [head] + split_caption(tail, limit)


# ---------------------------------------------------------------- music bed

def music_bed(seconds: float, speech: list[tuple[float, float]]) -> np.ndarray:
    """A quiet, slow pad (A minor, F, C, G; 8 s per chord) with a soft bell on each change. Stereo float32 in [-1, 1].
    Louder over the title and the end card, ducked under the voice."""
    sr, n = RATE_HZ, int(seconds * RATE_HZ)
    t = np.arange(n) / sr
    chords = [[57, 60, 64, 71], [53, 57, 60, 67], [48, 55, 60, 64], [55, 59, 62, 67]]  # Am(add9-ish), F, C, G (MIDI)
    hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)
    span, fade = 8.0, 3.0
    out = np.zeros((n, 2), dtype=np.float32)  # float32 halves the memory; each chord is computed in float64
    rng = np.random.default_rng(7)
    for k in range(int(seconds // span) + 2):
        notes = chords[k % len(chords)]
        a, b = max(0.0, k * span - fade / 2), min(seconds, (k + 1) * span + fade / 2)
        if a >= seconds:
            break
        i0, i1 = int(a * sr), int(b * sr)
        tt = t[i0:i1] - a
        dur = b - a
        env = np.minimum(1.0, tt / fade) * np.minimum(1.0, (dur - tt) / fade)
        env = np.sin(env * np.pi / 2) ** 2
        for j, m in enumerate(notes):
            f = hz(m)
            for side, det in ((0, -0.18), (1, 0.18)):  # a slight detune between left and right
                ph = rng.uniform(0, 2 * np.pi)
                w = 2 * np.pi * (f + det) * tt + ph
                tone = np.sin(w) + 0.32 * np.sin(2 * w) + 0.12 * np.sin(3 * w)  # soft, organ-like
                trem = 1 + 0.08 * np.sin(2 * np.pi * (0.11 + 0.03 * j) * tt + ph)
                out[i0:i1, side] += 0.05 * env * trem * tone
        root = hz(notes[0] - 12)
        out[i0:i1, :] += (0.07 * env * np.sin(2 * np.pi * root * tt))[:, None]
        # a soft bell at the change
        bt = int(min(seconds, k * span) * sr)
        bl = min(int(3.5 * sr), n - bt)
        if bl > 0:
            tb = np.arange(bl) / sr
            bell = np.exp(-tb * 1.6) * (np.sin(2 * np.pi * hz(notes[-1] + 12) * tb) + 0.25 * np.sin(2 * np.pi * hz(notes[-1] + 24) * tb))
            out[bt:bt + bl, 0] += 0.022 * bell
            out[bt:bt + bl, 1] += 0.018 * bell
    # level: higher with no voice, ducked under speech (smooth 0.35 s ramps)
    gain = np.full(n, 1.0)
    for s, e in speech:
        gain[int(max(0, s - 0.25) * sr):int(min(seconds, e + 0.2) * sr)] = 0.38
    k = int(0.35 * sr)  # moving average through a cumulative sum: a direct convolution of this length is far too slow
    c = np.concatenate(([0.0], np.cumsum(np.pad(gain, (k // 2, k - k // 2 - 1), mode="edge"))))
    gain = (c[k:] - c[:-k]) / k
    edge = np.minimum(1.0, np.minimum(t / 1.2, (seconds - t) / 2.5))
    out *= (gain * np.clip(edge, 0, 1))[:, None]
    return out / max(1e-9, np.abs(out).max()) * 0.5


def write_wav(path: Path, data: np.ndarray) -> None:
    pcm = (np.clip(data, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(data.shape[1] if data.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(RATE_HZ)
        w.writeframes(pcm.tobytes())


def samples() -> None:
    line = "Venidis reads every CV closely, and it acts only when a person approves. The AI reads. Code decides. People approve."
    out = HERE.parent / "out" / "voice_samples"
    out.mkdir(parents=True, exist_ok=True)
    voices = ["en-US-EmmaMultilingualNeural", "en-US-AvaMultilingualNeural", "en-GB-SoniaNeural", "en-US-JennyNeural"]
    asyncio.run(synth_all([(line, out / f"{v}.mp3", v, "-2%", "-1Hz") for v in voices]))
    print("wrote", ", ".join(f"{v}.mp3" for v in voices), "in", out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rate", help="voice speed, e.g. +3%% (default: narration.json)")
    ap.add_argument("--voice", help="edge-tts voice (default: narration.json)")
    ap.add_argument("--no-music", action="store_true", help="voice only, no music bed")
    ap.add_argument("--samples", action="store_true", help="write voice samples to choose from, then stop")
    args = ap.parse_args()
    if args.samples:
        return samples()
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    voice, rate, pitch = args.voice or spec["voice"], args.rate or spec["rate"], spec.get("pitch", "+0Hz")
    AUDIO.mkdir(parents=True, exist_ok=True)

    sentences = [(si, s) for si, scene in enumerate(spec["scenes"]) for s in scene["sentences"]]
    jobs = []
    for i, (_, s) in enumerate(sentences):
        mp3 = AUDIO / f"s{i:02d}.mp3"
        stamp = AUDIO / f"s{i:02d}.txt"
        r = s.get("rate", rate)
        key = f"{voice}|{r}|{pitch}|{FORMAT}|{s['say']}"
        if not (mp3.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == key):
            jobs.append((s["say"], mp3, voice, r, pitch))
            stamp.write_text(key, encoding="utf-8")
    if jobs:
        print(f"synthesising {len(jobs)} of {len(sentences)} sentences with {voice} at {rate}")
        asyncio.run(synth_all(jobs))
    lengths = [to_wav(AUDIO / f"s{i:02d}.mp3", AUDIO / f"s{i:02d}.wav") for i in range(len(sentences))]

    # Pauses: a breath between sentences (or the sentence's own "pause"), spare time to the scene changes.
    rnd = random.Random(11)
    gaps = []
    for si, scene in enumerate(spec["scenes"]):
        for j, s in enumerate(scene["sentences"]):
            last = j == len(scene["sentences"]) - 1
            gaps.append(None if last else s.get("pause", GAP_SENTENCE + rnd.uniform(-GAP_JITTER, GAP_JITTER)))
    n_scenes = len(spec["scenes"])
    scene_extra = [scene["sentences"][-1].get("pause", 0.0) for scene in spec["scenes"]]
    speech = sum(lengths) + sum(g for g in gaps if g)
    natural = spec["intro"] + speech + GAP_SCENE * (n_scenes - 1) + sum(scene_extra[:-1]) + spec["end_hold_min"]
    spare = spec["duration"] - natural
    if spare < 0:
        raise SystemExit(f"Narration is {natural:.1f}s, over {spec['duration']}s by {-spare:.1f}s: "
                         f"raise --rate (now {rate}) or shorten a sentence.")
    gap_scene = min(GAP_SCENE_MAX, GAP_SCENE + spare / max(1, n_scenes - 1))

    t, timed, i = spec["intro"], [], 0
    for si, scene in enumerate(spec["scenes"]):
        for j, s in enumerate(scene["sentences"]):
            timed.append({"scene": si, "start": round(t, 3), "end": round(t + lengths[i], 3), "sentence": s})
            t += lengths[i] + (gaps[i] or 0)
            i += 1
        if si < n_scenes - 1:
            t += gap_scene + scene_extra[si]
    speech_end = t

    # Mix the clips into one track, clean it up, then lay it over the music bed.
    total = int(spec["duration"] * RATE_HZ)
    mix = array("h", bytes(2 * total))
    for k, item in enumerate(timed):
        with wave.open(str(AUDIO / f"s{k:02d}.wav")) as w:
            clip = array("h", w.readframes(w.getnframes()))
        at = int(item["start"] * RATE_HZ)
        mix[at:at + len(clip)] = clip[: max(0, total - at)]
    raw = BUILD / "narration_raw.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE_HZ)
        w.writeframes(mix.tobytes())
    voice_wav = BUILD / "voice.wav"
    ffmpeg("-i", str(raw), "-af", f"{VOICE_CHAIN},loudnorm=I=-16:TP=-2:LRA=9", "-ar", str(RATE_HZ), "-ac", "1", str(voice_wav))
    out = BUILD / "narration.wav"
    if args.no_music:
        ffmpeg("-i", str(voice_wav), "-ac", "2", "-ar", str(RATE_HZ), str(out))
    else:
        bed = BUILD / "music.wav"
        write_wav(bed, music_bed(spec["duration"], [(x["start"], x["end"]) for x in timed]))
        # music sits about 20 dB under the voice; a gentle echo makes the pad roomy
        ffmpeg("-i", str(voice_wav), "-i", str(bed), "-filter_complex",
               "[1:a]aecho=0.8:0.6:120|260:0.25|0.15,volume=0.28[m];[0:a]pan=stereo|c0=c0|c1=c0[v];"
               "[v][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=10",
               "-ar", str(RATE_HZ), "-ac", "2", str(out))

    # Captions: each sentence's text, cut into cards timed by their share of characters.
    captions = []
    for item in timed:
        text = item["sentence"].get("show", item["sentence"]["say"])
        cards = split_caption(text)
        span, start = item["end"] - item["start"], item["start"]
        for card in cards:
            dur = span * len(card) / sum(len(c) for c in cards)
            captions.append({"start": round(start, 3), "end": round(start + dur, 3), "text": card})
            start += dur

    # Shots: each 'shot' starts with its sentence (or at a fraction of it) and lasts until the next one.
    usages = [{"id": "slide:01_title", "start": 0.0, "cam": [["full", 0]], "box": [], "click": []}]
    for item in timed:
        shot = item["sentence"].get("shot")
        if not shot:
            continue
        span = item["end"] - item["start"]
        for u in shot if isinstance(shot, list) else [shot]:
            usages.append({"id": u["id"], "start": round(item["start"] + span * u.get("at", 0) - 0.15, 3),
                           "cam": u.get("cam", [["full", 0]]), "box": u.get("box", []), "click": u.get("click", [])})
    for a, b in zip(usages, usages[1:] + [None]):
        a["end"] = b["start"] if b else spec["duration"]
    # Absolute times for keyframes; consecutive uses of one picture merge into one shot (no crossfade).
    shots = []
    for u in usages:
        dur = u["end"] - u["start"]
        absolute = {
            "cam": [[name, round(u["start"] + f * dur, 3)] for name, f in u["cam"]],
            "box": [[bx[0], round(u["start"] + bx[1] * dur, 3), round(u["start"] + bx[2] * dur, 3), *(bx[3:4])] for bx in u["box"]],
            "click": [[name, round(u["start"] + f * dur, 3)] for name, f in u["click"]],
        }
        if shots and shots[-1]["id"] == u["id"]:
            last = shots[-1]
            last["end"] = u["end"]
            for k in absolute:
                last[k] += absolute[k]
        else:
            shots.append({"id": u["id"], "start": u["start"], "end": u["end"], **absolute})

    chips = []
    for si, scene in enumerate(spec["scenes"]):
        mine = [x for x in timed if x["scene"] == si]
        nxt = [x for x in timed if x["scene"] == si + 1]
        chips.append({"start": round(mine[0]["start"] - 0.2, 3), "end": round(nxt[0]["start"] - 0.2 if nxt else speech_end, 3),
                      "text": scene["chip"], "module": scene.get("module", "")})

    timeline = {"fps": 30, "duration": spec["duration"], "shots": shots, "captions": captions, "chips": chips}
    (BUILD / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False), encoding="utf-8")
    srt = []
    for n, c in enumerate(captions, 1):
        fmt = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round(s % 1 * 1000)) % 1000:03d}"
        srt.append(f"{n}\n{fmt(c['start'])} --> {fmt(c['end'])}\n{c['text']}\n")
    (BUILD / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    words = sum(len(s["say"].split()) for _, s in sentences)
    print(f"speech {sum(lengths):.1f}s ({words} words, {60 * words / sum(lengths):.0f} wpm) · pauses between scenes {gap_scene:.2f}s "
          f"· speech ends {speech_end:.1f}s · end card {spec['duration'] - speech_end:.1f}s · {len(shots)} shots · {len(captions)} captions")


if __name__ == "__main__":
    main()
