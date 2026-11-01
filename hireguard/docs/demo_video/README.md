# Demo video kit

The finished 3-minute demo video and everything that builds it.

| Path | What |
|---|---|
| `out/HireGuard_demo_3min.mp4` | The video: 3:00, 1920×1080, narration and captions. Not in git (too large): share it from the team drive |
| [`script.md`](script.md) | What is said and shown, second by second, and how the video was made |
| [`slides/`](slides/) | 14 slides, 1920×1080 PNG, numbers read from `eval/results/*.json` |
| [`overlays/`](overlays/) | Transparent lower thirds and a "Fictional demo data" tag, for a hand-edited cut |
| [`build_slides.py`](build_slides.py) | Rebuilds `slides/` and `overlays/` (Python 3 + Chrome or Edge, no packages) |
| [`video/`](video/) | The pipeline: `narration.json` (lines and shots), `capture.mjs`, `voice.py`, `stage.html`, `render.mjs` |

## Rebuild the video

Needs Node 22+, Chrome or Edge, Python 3, and once: `pip install edge-tts imageio-ffmpeg` (in any venv). `voice.py` sends
only the narration text to Microsoft's online voice service.

```powershell
# 1. App seeded with the model reachable (Ollama with qwen3:8b), then running
cd hireguard; .\run.ps1 -Seed     # copy the 5 printed passwords into a private file: "email password" per line
# 2. Screenshots of the dashboard (signs in as the demo users; drafts an offer, approves it once, tries to run it, ...)
cd docs\demo_video\video
node capture.mjs --accounts C:\private\accounts.txt
# 3. Slides, narration and timeline, then the video
python ..\build_slides.py
python voice.py
node render.mjs --ffmpeg (python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
```

`capture.mjs` changes data, so run it once per fresh seed; `--only id,id` re-takes some shots and keeps the others.
`render.mjs --stills 12,47` writes single frames to check, and `--from 40 --to 60` renders a short preview. Rendering the
full video takes about 10 minutes.

To change what is said, edit `narration.json` (`say` is read aloud, `show` is the caption if it differs) and re-run
`voice.py` and `render.mjs`. If the narration no longer fits in 3:00, `voice.py` stops and says by how much.

## Slides alone

```powershell
python hireguard/docs/demo_video/build_slides.py
```

Business facts that are not decided yet (pricing, market size, interview results, the ask) are in `FILL_IN` at the top of
`build_slides.py`; until they are filled in, slides 09 and 12 show an amber **TBD** chip. They are not used in the 3-minute
video. Charts: HireGuard is indigo (`#4338CA`, the app's primary colour) and the standard screener orange (`#eb6834`); the
pair passes the dataviz palette check, and every bar carries its k/n, so colour is never the only cue.
