# Demo video kit

The finished 3-minute Venidis demo video and everything that builds it. Look and colours: [`brand/README.md`](../../brand/README.md)
(ink, paper, one yellow). No team member's name appears anywhere in the video.

| Path | What |
|---|---|
| `out/Venidis_demo_3min.mp4` | The video: 3:00, 1920×1080, narration, music bed, captions and on-screen labels. Not in git (too large): share it from the team drive |
| `out/voice_samples/` | One line in four female voices, to choose the narrator by ear (`voice.py --samples`) |
| [`script.md`](script.md) | What is said and shown, second by second, and how the video was made |
| [`slides/`](slides/) | 15 slides, 1920×1080 PNG, numbers read from `eval/results/*.json`. The video uses 01 to 07, 13 and 14 |
| [`overlays/`](overlays/) | Transparent lower thirds and a "Fictional demo data" tag, for a hand-edited cut |
| [`build_slides.py`](build_slides.py) | Rebuilds `slides/` and `overlays/` (Python 3 + Chrome or Edge, no packages) |
| [`video/`](video/) | The pipeline: `narration.json` (lines, shots and labels), `capture.mjs`, `voice.py`, `stage.html`, `render.mjs` |

## Rebuild the video

Needs Node 22+, Chrome or Edge, Python 3, and once: `pip install edge-tts imageio-ffmpeg numpy` (in any venv). `voice.py` sends
only the narration text to Microsoft's online voice service.

```powershell
# 1. App seeded and running. With the model reachable (.env.modal or Ollama) the CVs are read by the model; without it every
#    candidate shows "offline extraction", and the video says so in its corner tag and on the end card.
cd hireguard; .\run.ps1 -Seed     # copy the 5 printed passwords into a private file: "email password" per line
# 2. Screenshots of the dashboard (signs in as the demo users, one tab at a time; drafts an offer, approves it once, tries to run it, ...)
cd docs\demo_video\video
node capture.mjs --accounts C:\private\accounts.txt          # --base http://127.0.0.1:5180 for another port
# 3. Slides, narration and timeline, then the video
python ..\build_slides.py
python voice.py
node render.mjs --ffmpeg (python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
```

`capture.mjs` changes data, so run it once per fresh seed; `--only id,id` re-takes some shots and keeps the others.
`render.mjs --stills 12,47` writes single frames to check, and `--from 40 --to 60` renders a short preview. Rendering the
full video takes about 10 minutes.

To change what is said, edit `narration.json` (`say` is read aloud, `show` is the caption if it differs, `pause` the silence
after it, and the fourth item of a `box` is its on-screen label) and re-run `voice.py` and `render.mjs`. If the narration no
longer fits in 3:00, `voice.py` stops and says by how much. `voice.py --voice <name>` tries another narrator and
`--no-music` drops the music bed.

## The voice

A neural voice (Microsoft Emma, multilingual) requested at 96 kbit/s instead of the library's 48, then cleaned up: high-pass,
a little warmth and presence, gentle compression, a small room, -16 LUFS. A breath between sentences, longer pauses where a
sentence asks for one, and the spare time spread over the scene changes. A quiet pad (generated, no samples) sits about
20 dB under the voice and rises over the title and the end card.

## Slides alone

```powershell
python hireguard/docs/demo_video/build_slides.py               # all
python hireguard/docs/demo_video/build_slides.py --only 06_proof
```

Business facts that are not decided yet (pricing, market size, interview results, the ask) are in `FILL_IN` at the top of
`build_slides.py`; until they are filled in, slides 09 and 12 show an outlined **TBD**. They are not used in the video.
Charts: Venidis is yellow and the standard screener grey, so yellow stays the one accent; every bar carries its k/n, so colour
is never the only cue.
