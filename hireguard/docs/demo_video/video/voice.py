"""Narration for the 3-minute demo video: one neural-voice clip per sentence, then the timeline.

    python voice.py                 # build/narration.wav and build/timeline.json
    python voice.py --rate +8%      # faster voice if the script no longer fits in the duration

Needs `pip install edge-tts imageio-ffmpeg`. Only the narration text is sent, to Microsoft's online voice service.
The timeline places each sentence after the previous one, gives the spare time to the pauses between scenes, and lists
when each screenshot or slide is on screen (render.mjs draws it).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import wave
from array import array
from pathlib import Path

import edge_tts
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
AUDIO = BUILD / "audio"
RATE_HZ = 48000
GAP_SENTENCE = 0.16   # seconds between sentences of one scene
GAP_SCENE = 0.40      # minimum pause between scenes
GAP_SCENE_MAX = 1.10  # spare time is spread over scene pauses up to this length
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


async def synth(text: str, mp3: Path, voice: str, rate: str) -> None:
    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(mp3))
            return
        except Exception:  # the online service drops a request now and then
            if attempt == 3:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))


async def synth_all(items: list[tuple[str, Path]], voice: str, rate: str) -> None:
    sem = asyncio.Semaphore(4)

    async def one(text: str, mp3: Path) -> None:
        async with sem:
            await synth(text, mp3, voice, rate)

    await asyncio.gather(*(one(t, p) for t, p in items))


def to_wav(mp3: Path, wav: Path) -> float:
    """Mono 48 kHz, leading and trailing silence trimmed. Returns the length in seconds."""
    trim = "silenceremove=start_periods=1:start_threshold=-48dB"
    ffmpeg("-i", str(mp3), "-af", f"{trim},areverse,{trim},areverse", "-ac", "1", "-ar", str(RATE_HZ),
           "-sample_fmt", "s16", str(wav))
    with wave.open(str(wav)) as w:
        return w.getnframes() / w.getframerate()


def split_caption(text: str, limit: int = 96) -> list[str]:
    """Caption cards of at most two short lines, cut at punctuation where possible."""
    if len(text) <= limit:
        return [text]
    cut = max((text.rfind(p, 0, limit) for p in (": ", "; ", ", ", ". ")), default=-1)
    if cut < limit // 3:
        cut = text.rfind(" ", 0, limit)
    head, tail = text[: cut + 1].strip(), text[cut + 1:].strip()
    return [head] + split_caption(tail, limit)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rate", help="voice speed, e.g. +6%% (default: narration.json)")
    ap.add_argument("--voice", help="edge-tts voice (default: narration.json)")
    args = ap.parse_args()
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    voice, rate = args.voice or spec["voice"], args.rate or spec["rate"]
    AUDIO.mkdir(parents=True, exist_ok=True)

    sentences = [(si, s) for si, scene in enumerate(spec["scenes"]) for s in scene["sentences"]]
    jobs = []
    for i, (_, s) in enumerate(sentences):
        mp3 = AUDIO / f"s{i:02d}.mp3"
        stamp = AUDIO / f"s{i:02d}.txt"
        key = f"{voice}|{rate}|{s['say']}"
        if not (mp3.exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == key):
            jobs.append((s["say"], mp3))
            stamp.write_text(key, encoding="utf-8")
    if jobs:
        print(f"synthesising {len(jobs)} of {len(sentences)} sentences with {voice} at {rate}")
        asyncio.run(synth_all(jobs, voice, rate))
    lengths = [to_wav(AUDIO / f"s{i:02d}.mp3", AUDIO / f"s{i:02d}.wav") for i in range(len(sentences))]

    # Natural length, then spread the spare time over the pauses between scenes.
    n_scenes = len(spec["scenes"])
    speech = sum(lengths) + GAP_SENTENCE * sum(len(sc["sentences"]) - 1 for sc in spec["scenes"])
    natural = spec["intro"] + speech + GAP_SCENE * (n_scenes - 1) + spec["end_hold_min"]
    spare = spec["duration"] - natural
    if spare < 0:
        raise SystemExit(f"Narration is {natural:.1f}s, over {spec['duration']}s by {-spare:.1f}s: "
                         f"raise --rate (now {rate}) or shorten a sentence.")
    gap_scene = min(GAP_SCENE_MAX, GAP_SCENE + spare / max(1, n_scenes - 1))

    t, timed, i = spec["intro"], [], 0
    for si, scene in enumerate(spec["scenes"]):
        for j, s in enumerate(scene["sentences"]):
            timed.append({"scene": si, "start": round(t, 3), "end": round(t + lengths[i], 3), "sentence": s})
            t += lengths[i] + (GAP_SENTENCE if j < len(scene["sentences"]) - 1 else 0)
            i += 1
        if si < n_scenes - 1:
            t += gap_scene
    speech_end = t

    # Mix the clips into one track.
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
    ffmpeg("-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(RATE_HZ), "-ac", "1", str(BUILD / "narration.wav"))

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
            "box": [[name, round(u["start"] + a * dur, 3), round(u["start"] + b * dur, 3)] for name, a, b in u["box"]],
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
        chips.append({"start": round(mine[0]["start"] - 0.2, 3),
                      "end": round(nxt[0]["start"] - 0.2 if nxt else speech_end, 3), "text": scene["chip"]})

    timeline = {"fps": 30, "duration": spec["duration"], "shots": shots, "captions": captions, "chips": chips}
    (BUILD / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False), encoding="utf-8")
    srt = []
    for n, c in enumerate(captions, 1):
        fmt = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(round(s % 1 * 1000)) % 1000:03d}"
        srt.append(f"{n}\n{fmt(c['start'])} --> {fmt(c['end'])}\n{c['text']}\n")
    (BUILD / "captions.srt").write_text("\n".join(srt), encoding="utf-8")
    print(f"speech {sum(lengths):.1f}s · pauses between scenes {gap_scene:.2f}s · speech ends {speech_end:.1f}s "
          f"· end card {spec['duration'] - speech_end:.1f}s · {len(shots)} shots · {len(captions)} captions")


if __name__ == "__main__":
    main()
