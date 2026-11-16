# Scene Cut Detector

**Website and download: [olivaresrafael.github.io/scene-cut-detector](https://olivaresrafael.github.io/scene-cut-detector/)**

A small macOS app that finds every scene cut in a video and exports the result
for **DaVinci Resolve** (and other editors). Drop a video, click **Detect
Cuts**, and get a cut timeline, timeline markers, an EDL, a CSV and a readable
report.

- **Graphical interface** built with PySide6: drag and drop, sensible
  defaults, live progress and a cut list.
- **Fast**: a 21-minute video is typically analyzed in one or two minutes on
  an Apple silicon Mac with the default automatic downscaling; short clips
  finish in seconds.
- **Offline**: nothing is uploaded anywhere; detection runs locally with
  [PySceneDetect](https://www.scenedetect.com/).
- **Resolve-ready**: FCPXML cut timeline, marker EDL, CMX3600 cut EDL, CSV and
  TXT outputs.

> **Status: beta (v2.0.0-beta.1).** The GUI and all export formats are usable
> and tested, but this is an early public release. Feedback and bug reports are
> welcome in the [issue tracker](https://github.com/olivaresrafael/scene-cut-detector/issues).

---

## Quick start (macOS)

1. Double-click **`Install Dependencies.command`**.
   It creates an isolated `.venv` inside the project and installs PySceneDetect,
   OpenCV and PySide6. Your system Python is not modified.
2. Double-click **`Launch Scene Cut Detector.command`**.
3. Drag a video onto the window (or click the drop zone to browse).
4. Choose your options and click **Detect Cuts**.

You can also drag a video file directly onto the launcher:

```
Launch Scene Cut Detector.command  +  your-video.mp4
```

> The first time macOS may block the `.command` files. If that happens,
> right-click the file and choose **Open**, or run it from Terminal.

### Manual installation (any platform)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python gui.py
```

Requirements: Python 3.10+ and, strongly recommended, `ffmpeg`/`ffprobe`
(`brew install ffmpeg`). Without `ffprobe` the tool still works, but cannot read
embedded timecode and some metadata.

---

## Using the app

| Control | What it does |
|---|---|
| **Drop zone** | Drop a video or click to browse. |
| **Output folder** | Where the generated files are written. Defaults to `<video>_cuts` next to the video. |
| **Sensitivity** | `Normal` is a good starting point. `Sensitive` finds more cuts (soft or fast transitions); `Strict` avoids false positives from camera movement. |
| **Detector** | `Content` detects color/brightness/edge changes and is the best default. `Adaptive` adapts to motion (handheld, animation). `Hash` and `Histogram` are alternatives for difficult footage. |
| **Minimum shot** | Shots shorter than this are merged into the previous one. Default 0.5 s. |
| **Speed** | Analysis downscale. `Auto` picks a good value; use 2×/4×/8× for faster scans of high-resolution footage. |
| **Analyze from / to** | Optional range, in seconds (`83.5`) or `HH:MM:SS`. Leave blank for the whole video. |
| **Outputs** | Pick any combination of FCPXML, marker EDL, cut EDL, CSV and TXT. |
| **Markers inside FCPXML** | Exports a single clip with a marker at every cut instead of a pre-cut timeline. |
| **Marker color** | Color of the markers imported into Resolve. |
| **Timeline starts at** | Timecode of the clip's first frame on your timeline. Resolve defaults to `01:00:00:00`; use `00:00:00:00` if your timeline starts at zero. |

The **Cuts** tab lists every detected cut with timecode, seconds and frame
number. The **Log** tab shows the detailed progress and output paths.

### Generated files

For a video named `interview.mp4`:

| File | Purpose |
|---|---|
| `interview_cuts.fcpxml` | **Cut timeline**: one clip per shot. Import with *File → Import → Timeline*. |
| `interview_markers.edl` | **Timeline markers**: one marker per cut. Import with *Timelines → Import → Timeline Markers from EDL*. |
| `interview_cuts.edl` | Classic CMX3600 cut timeline. |
| `interview_cuts.csv` | Shot and cut list (timecode, frames, seconds). |
| `interview_cuts.txt` | Human-readable report with statistics. |

---

## Importing into DaVinci Resolve

### Option A — Markers on your current timeline (recommended for review)

Use this when the video is already on a timeline and you just want to see where
the cuts are.

1. Put the clip on a timeline.
2. In the **Media Pool**, right-click the timeline and choose
   **Timelines → Import → Timeline Markers from EDL**.
3. Select `*_markers.edl`.

A marker appears at every cut. Navigate with **Shift+↓ / Shift+↑**, or review
them in **Index → Markers**.

> The marker EDL assumes the clip starts at **01:00:00:00** by default, which is
> how Resolve timelines normally start. If your timeline starts at zero, set
> **Timeline starts at** to `00:00:00:00` before detecting. If the clip starts
> later, enter its exact start timecode (for example `01:05:00:00`).

### Option B — A new, pre-cut timeline (FCPXML)

1. Choose **File → Import → Timeline…** (or drag the `.fcpxml` into the Media
   Pool).
2. Select `*_cuts.fcpxml`.

Resolve creates a new timeline with one clip per shot, cut exactly at every
detected cut. The FCPXML references the original video by absolute path, so no
relinking is needed while the file stays in place.

### Option C — A pre-cut timeline with EDL

Use **File → Import → Timeline…** with `*_cuts.edl`, then relink the original
video if Resolve asks. This uses the embedded timecode of the source file
(including drop-frame when applicable).

---

## Command line

The GUI is a layer over `scene_cut_detector.py`, which can also be used
directly:

```bash
# Default detection (all output formats)
.venv/bin/python scene_cut_detector.py video.mp4

# More cuts / fewer cuts
.venv/bin/python scene_cut_detector.py video.mp4 --preset sensitive
.venv/bin/python scene_cut_detector.py video.mp4 --preset strict

# Only a marker EDL, with a custom timeline start and color
.venv/bin/python scene_cut_detector.py video.mp4 \
    --formats markers --record-start 01:00:00:00 --marker-color Green

# FCPXML with markers instead of a cut timeline
.venv/bin/python scene_cut_detector.py video.mp4 --markers-only

# Analyze a fragment and open the output folder
.venv/bin/python scene_cut_detector.py video.mp4 --start 2:00 --end 5:00 \
    -o ~/Desktop/cuts --open
```

Run `.venv/bin/python scene_cut_detector.py --help` for every option.

### Tuning tips

| Symptom | Adjustment |
|---|---|
| Too many false cuts (camera movement, flashes) | `--preset strict`, or raise `--threshold` |
| Missing soft or fast cuts | `--preset sensitive`, or `--detector adaptive` |
| Very short shots you don't care about | `--min-scene-len 1.5` |
| Slow scan on 4K footage | `--downscale 4` (or `8`) |
| Container reports the wrong frame rate | `--fps 23.976` |

---

## Building a standalone app (optional)

To create `dist/Scene Cut Detector.app` (bundled Python, no installation
needed):

1. Run **`Install Dependencies.command`** once.
2. Double-click **`Build Mac App.command`**.

The app is built with PyInstaller and can be copied to `/Applications`. Because
it bundles PySide6 and OpenCV it is fairly large (several hundred MB); the
`.command` launcher is lighter if you only use it on this Mac.

---

## Project layout

```
scene-cut-detector/
├── gui.py                          # PySide6 interface
├── scene_cut_detector.py           # detection engine + CLI
├── requirements.txt
├── Install Dependencies.command
├── Launch Scene Cut Detector.command
├── Build Mac App.command
├── make_icon.py                    # generates the .icns from assets/icon.svg
├── assets/
│   └── icon.svg
├── README.md
└── LICENSE
```

## Troubleshooting

- **"PySceneDetect is not installed" banner**: run
  `Install Dependencies.command` again, or
  `.venv/bin/python -m pip install -r requirements.txt`.
- **The app does not open**: launch it from Terminal to see the error:

  ```bash
  cd /path/to/scene-cut-detector
  .venv/bin/python gui.py
  ```

- **macOS blocks a `.command` file**: right-click → **Open**.
- **No cuts detected**: try `Sensitive`, the `Adaptive` detector, a smaller
  minimum shot length, or check that the video actually contains cuts.
- **Markers are at the wrong time**: adjust **Timeline starts at** to match the
  timecode where the clip begins in your Resolve timeline.

## Notes

- Detection is offline and CPU-based; it does not compete with Resolve for the
  GPU.
- The FCPXML timeline starts at 0. Timecodes in the CSV/TXT include the source
  file's embedded timecode when available.
- Drop-frame timecode (29.97, 59.94) is supported in EDL and marker EDL
  exports.
- Tested with PySceneDetect 0.7.3, OpenCV 4.14 and PySide6 6.x on macOS.

## License

MIT. See [LICENSE](LICENSE).

Copyright © 2026 Rafael Olivares.

