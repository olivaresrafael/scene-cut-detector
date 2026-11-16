#!/usr/bin/env python3
"""
scene_cut_detector.py — Detect scene cuts in a video and export files ready for
DaVinci Resolve.

Outputs:
  - .fcpxml  -> cut timeline (or a single clip with markers)
  - .edl     -> cut timeline in CMX3600 format (classic method)
  - .csv     -> shot/cut list for review or processing
  - .txt     -> human-readable summary
  - markers  -> Resolve marker EDL (one marker per cut)

Quick start:
    python scene_cut_detector.py video.mp4
    python scene_cut_detector.py video.mp4 --markers-only
    python scene_cut_detector.py video.mp4 --preset sensitive

Requirements: PySceneDetect >= 0.7, OpenCV, ffmpeg/ffprobe (recommended).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

VERSION = "2.0.0-beta.1"

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mxf", ".mts", ".m2ts",
    ".webm", ".wmv", ".flv", ".mpg", ".mpeg", ".ts",
}

# Default detector thresholds for each sensitivity preset.
PRESETS = {
    "normal":    {"content": 27.0, "adaptive": 3.0, "hash": 0.35, "histogram": 0.20},
    "sensitive": {"content": 18.0, "adaptive": 2.0, "hash": 0.24, "histogram": 0.13},
    "strict":    {"content": 36.0, "adaptive": 5.0, "hash": 0.46, "histogram": 0.30},
}

RESOLVE_COLORS = [
    "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
    "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream",
    "White", "Black",
]


# --------------------------------------------------------------------------- #
# Time, fps and timecode helpers
# --------------------------------------------------------------------------- #

def fps_fraction(value) -> Fraction:
    """Turn 23.976 / '24000/1001' / 29.97 into an exact fraction."""
    if isinstance(value, Fraction):
        return value
    text = str(value).strip()
    if "/" in text:
        try:
            f = Fraction(text)
            if f > 0:
                return f
        except (ValueError, ZeroDivisionError):
            pass
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"Invalid FPS: {value!r}")
    if number <= 0:
        raise ValueError(f"Invalid FPS: {value!r}")
    for target, num, den in (
        (23.976, 24000, 1001),
        (29.97, 30000, 1001),
        (47.952, 48000, 1001),
        (59.94, 60000, 1001),
        (119.88, 120000, 1001),
    ):
        if abs(number - target) < 0.01:
            return Fraction(num, den)
    return Fraction(number).limit_denominator(1_000_000)


def nominal_fps(fps: Fraction) -> int:
    return max(1, int(round(float(fps))))


def tc_to_frames(tc: str, fps: Fraction, drop_frame: bool) -> int:
    """Convert HH:MM:SS:FF (or HH:MM:SS;FF) to a frame number."""
    parts = re.split(r"[:;]", tc.strip())
    if len(parts) != 4:
        raise ValueError(f"Invalid timecode: {tc!r}")
    h, m, s, f = (int(p) for p in parts)
    fps_i = nominal_fps(fps)
    total = (h * 3600 + m * 60 + s) * fps_i + f
    if drop_frame:
        drop = 2 if fps_i == 30 else 4 if fps_i == 60 else 0
        if drop:
            total_minutes = h * 60 + m
            total -= drop * (total_minutes - total_minutes // 10)
    return total


def frames_to_tc(frames: int, fps: Fraction, drop_frame: bool = False,
                 separator: str = ":") -> str:
    """Convert a frame number to HH:MM:SS:FF (drop-frame aware)."""
    frames = int(round(frames))
    fps_i = nominal_fps(fps)
    if frames < 0:
        frames = 0
    frames %= fps_i * 60 * 60 * 24  # 24 hours

    adjusted = frames
    if drop_frame:
        drop = 2 if fps_i == 30 else 4 if fps_i == 60 else 0
        if drop:
            # Every minute except every tenth minute, "drop" labels are skipped.
            minutes = frames // (fps_i * 60)
            adjusted = frames + drop * (minutes - minutes // 10)

    ff = adjusted % fps_i
    ss = (adjusted // fps_i) % 60
    mm = (adjusted // (fps_i * 60)) % 60
    hh = (adjusted // (fps_i * 3600)) % 24
    return f"{hh:02d}{separator}{mm:02d}{separator}{ss:02d}{separator}{ff:02d}"


def seconds_to_tc(seconds: float, fps: Fraction, drop_frame: bool = False) -> str:
    return frames_to_tc(int(round(seconds * float(fps))), fps, drop_frame)


def format_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    ms = int(round((seconds - whole) * 1000))
    if ms == 1000:
        whole += 1
        ms = 0
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_time(value: str) -> float:
    """Accept '83.5', '83.5s', 'MM:SS', 'HH:MM:SS.mmm' or 'HH:MM:SS'."""
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    if re.fullmatch(r"\d+(?:\.\d+)?s", text, re.IGNORECASE):
        return float(text[:-1])
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,3}):(\d{1,2}(?:\.\d+)?)", text)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    raise argparse.ArgumentTypeError(
        f"Invalid time: {value!r}. Use seconds (83.5) or HH:MM:SS(.mmm)."
    )


# --------------------------------------------------------------------------- #
# Video information
# --------------------------------------------------------------------------- #

@dataclass
class MediaInfo:
    path: Path
    fps: Fraction
    width: int
    height: int
    duration: float
    total_frames: int
    start_tc_frames: int
    drop_frame: bool
    has_audio: bool
    audio_channels: int
    audio_rate: int
    codec: str
    bit_depth: str = ""
    bitrate: str = ""

    @property
    def fps_label(self) -> str:
        return f"{float(self.fps):.3f}".rstrip("0").rstrip(".")

    @property
    def end_tc(self) -> str:
        return frames_to_tc(
            self.start_tc_frames + self.total_frames, self.fps, self.drop_frame
        )


@dataclass
class Shot:
    index: int
    start_frame: int
    end_frame: int

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    def start_seconds(self, fps: Fraction) -> float:
        return self.start_frame / float(fps)

    def end_seconds(self, fps: Fraction) -> float:
        return self.end_frame / float(fps)

    def duration_seconds(self, fps: Fraction) -> float:
        return self.duration_frames / float(fps)


@dataclass
class DetectionResult:
    info: MediaInfo
    shots: list[Shot]
    cuts: list[dict]
    outputs: list[Path]
    out_dir: Path

    @property
    def durations(self) -> list[float]:
        return [shot.duration_seconds(self.info.fps) for shot in self.shots]


class DetectionCancelled(Exception):
    """Raised when the caller cancels a running detection."""


def _first_tag(tags: dict, key: str) -> Optional[str]:
    for k, v in (tags or {}).items():
        if k.lower() == key.lower() and v:
            return str(v)
    return None


def probe_with_ffprobe(path: Path) -> MediaInfo:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffprobe failed")

    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next(
        (s for s in streams if s.get("codec_type") == "video"
         and not s.get("disposition", {}).get("attached_pic")),
        None,
    )
    if video is None:
        raise RuntimeError("The file does not contain a video track.")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    fps = None
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = video.get(key)
        if raw and raw not in ("0/0", "0"):
            try:
                candidate = Fraction(raw)
                if candidate > 0:
                    fps = candidate
                    break
            except (ValueError, ZeroDivisionError):
                pass
    if fps is None:
        raise RuntimeError("Could not determine the video FPS.")

    duration = 0.0
    for raw in (video.get("duration"), data.get("format", {}).get("duration")):
        try:
            if raw is not None:
                duration = float(raw)
                if duration > 0:
                    break
        except (TypeError, ValueError):
            pass

    total_frames = 0
    try:
        total_frames = int(video.get("nb_frames") or 0)
    except (TypeError, ValueError):
        total_frames = 0
    if total_frames <= 0 and duration > 0:
        total_frames = int(round(duration * float(fps)))

    tc = _first_tag(video.get("tags", {}), "timecode")
    if not tc:
        tc = _first_tag(data.get("format", {}).get("tags", {}), "timecode")
    drop_frame = bool(tc and ";" in tc)
    start_tc_frames = 0
    if tc:
        try:
            start_tc_frames = tc_to_frames(tc, fps, drop_frame)
        except ValueError:
            start_tc_frames = 0
            drop_frame = False

    return MediaInfo(
        path=path,
        fps=fps,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        duration=duration,
        total_frames=total_frames,
        start_tc_frames=start_tc_frames,
        drop_frame=drop_frame,
        has_audio=audio is not None,
        audio_channels=int((audio or {}).get("channels") or 2),
        audio_rate=int((audio or {}).get("sample_rate") or 48000),
        codec=str(video.get("codec_name") or ""),
        bit_depth=str(video.get("bits_per_raw_sample") or ""),
        bitrate=str(data.get("format", {}).get("bit_rate") or ""),
    )


def probe_with_scenedetect(path: Path) -> MediaInfo:
    from scenedetect import open_video

    video = open_video(str(path))
    fps_raw = video.frame_rate
    if isinstance(fps_raw, Fraction):
        fps = fps_raw
    else:
        fps = Fraction(getattr(fps_raw, "numerator", fps_raw)) / Fraction(
            getattr(fps_raw, "denominator", 1)
        )
    if fps <= 0:
        fps = Fraction(25, 1)
    width, height = video.frame_size
    duration = video.duration.get_seconds() if video.duration else 0.0
    return MediaInfo(
        path=path,
        fps=fps,
        width=int(width),
        height=int(height),
        duration=float(duration),
        total_frames=int(round(float(duration) * float(fps))) if duration else 0,
        start_tc_frames=0,
        drop_frame=False,
        has_audio=True,
        audio_channels=2,
        audio_rate=48000,
        codec="",
    )


def probe_media(path: Path, fps_override: Optional[str] = None, warn=None) -> MediaInfo:
    if warn is None:
        def warn(message: str) -> None:
            print(message, file=sys.stderr)

    if shutil.which("ffprobe"):
        try:
            info = probe_with_ffprobe(path)
        except Exception as exc:
            warn(f"Warning: ffprobe could not read the file ({exc}). "
                 f"Falling back to PySceneDetect...")
            info = probe_with_scenedetect(path)
    else:
        warn("Warning: ffprobe is not installed; using PySceneDetect "
             "(embedded timecode will not be read).")
        info = probe_with_scenedetect(path)

    if fps_override:
        info.fps = fps_fraction(fps_override)
        if info.duration > 0:
            info.total_frames = int(round(info.duration * float(info.fps)))

    if info.total_frames <= 0:
        raise RuntimeError("Could not determine the video duration.")
    return info


# --------------------------------------------------------------------------- #
# Scene detection
# --------------------------------------------------------------------------- #

def make_detector(name: str, threshold: float, min_scene_len: float,
                  min_content_val: Optional[float]):
    from scenedetect import AdaptiveDetector, ContentDetector, HashDetector, HistogramDetector

    if name == "adaptive":
        kwargs = {
            "adaptive_threshold": threshold,
            "min_scene_len": min_scene_len,
        }
        if min_content_val is not None:
            kwargs["min_content_val"] = min_content_val
        return AdaptiveDetector(**kwargs)
    if name == "hash":
        return HashDetector(threshold=threshold, min_scene_len=min_scene_len)
    if name == "histogram":
        return HistogramDetector(threshold=threshold, min_scene_len=min_scene_len)
    return ContentDetector(threshold=threshold, min_scene_len=min_scene_len)


def detect_shots(path: Path, info: MediaInfo, args, progress=None,
                 cancelled=None) -> list[Shot]:
    from scenedetect import FrameTimecode, SceneManager, open_video

    start_sec = args.start or 0.0
    end_sec = args.end
    if end_sec is not None and end_sec <= start_sec:
        raise ValueError("--end must be greater than --start.")

    start_frame = int(round(start_sec * float(info.fps)))
    end_frame = (
        int(round(end_sec * float(info.fps))) if end_sec is not None
        else info.total_frames
    )

    video = open_video(str(path), frame_rate=info.fps)
    video.seek(FrameTimecode(start_frame, info.fps))

    manager = SceneManager()
    if args.downscale == "auto":
        manager.auto_downscale = True
    else:
        manager.auto_downscale = False
        manager.downscale = max(1, int(args.downscale))

    manager.add_detector(
        make_detector(args.detector, args.threshold, args.min_scene_len,
                      args.min_content)
    )

    total_frames = max(1, end_frame - start_frame)

    def on_frame(_image, timecode) -> None:
        if cancelled is not None and cancelled():
            raise DetectionCancelled("Detection cancelled by the user.")
        if progress is not None:
            done = int(timecode.frame_num) - start_frame
            progress(min(1.0, max(0.0, done / total_frames)))

    end_tc = FrameTimecode(end_frame, info.fps) if args.end is not None else None
    manager.detect_scenes(
        video=video,
        end_time=end_tc,
        show_progress=not getattr(args, "quiet", True) and sys.stderr.isatty(),
        callback=on_frame,
    )
    raw_scenes = manager.get_scene_list(start_in_scene=True)

    if not raw_scenes:
        raw_scenes = [
            (FrameTimecode(start_frame, info.fps),
             FrameTimecode(end_frame, info.fps)),
        ]

    shots: list[Shot] = []
    for i, (start, end) in enumerate(raw_scenes, start=1):
        s = max(start_frame, int(start.frame_num))
        e = min(end_frame, int(end.frame_num))
        if e > s:
            shots.append(Shot(index=i, start_frame=s, end_frame=e))

    if not shots:
        raise RuntimeError("Could not build the shot list.")
    return shots


# --------------------------------------------------------------------------- #
# Format writers
# --------------------------------------------------------------------------- #

def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^\w\-. ]+", "_", path.stem, flags=re.UNICODE).strip()
    return stem or "video"


def sanitize_reel(name: str) -> str:
    reel = re.sub(r"[^A-Za-z0-9]", "", name.upper())
    return (reel[:8] or "AX").ljust(8)


def shot_timecodes(shots: Iterable[Shot], info: MediaInfo):
    for shot in shots:
        s = info.start_tc_frames + shot.start_frame
        e = info.start_tc_frames + shot.end_frame
        yield (
            shot,
            frames_to_tc(s, info.fps, info.drop_frame),
            frames_to_tc(e, info.fps, info.drop_frame),
        )


def build_edl(shots: list[Shot], info: MediaInfo, title: str) -> str:
    fcm = "DROP FRAME" if info.drop_frame else "NON-DROP FRAME"
    reel = sanitize_reel(info.path.stem)
    record = 0
    number_width = max(3, len(str(len(shots))))
    lines = [f"TITLE: {title}", f"FCM: {fcm}", ""]
    for index, (shot, src_in, src_out) in enumerate(shot_timecodes(shots, info), 1):
        rec_in = frames_to_tc(record, info.fps, info.drop_frame)
        record += shot.duration_frames
        rec_out = frames_to_tc(record, info.fps, info.drop_frame)
        lines.append(
            f"{index:0{number_width}d}  {reel} V     C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )
        lines.append(f"* FROM CLIP NAME: {info.path.name}")
        lines.append("")
    return "\n".join(lines)


def build_marker_edl(shots: list[Shot], info: MediaInfo, title: str,
                     offset_frames: int = 0, color: str = "Blue") -> str:
    """
    Marker EDL for DaVinci Resolve.

    Import with: right-click the timeline in the Media Pool →
    Timelines → Import → Timeline Markers from EDL.

    Format validated against Resolve/EditingTools output:
      <event> 001 V C <in> <out> <in> <out>
      <comment> |C:ResolveColorBlue |M:<name> |D:1
    """
    fcm = "DROP FRAME" if info.drop_frame else "NON-DROP FRAME"
    color_token = f"ResolveColor{color}"
    cuts = shots[1:]
    number_width = max(3, len(str(len(cuts))))
    lines = [f"TITLE: {title}", f"FCM: {fcm}", ""]

    for number, shot in enumerate(cuts, 1):
        frame = offset_frames + shot.start_frame
        tc_in = frames_to_tc(frame, info.fps, info.drop_frame)
        tc_out = frames_to_tc(frame + 1, info.fps, info.drop_frame)
        previous = shots[number - 1]
        note = (
            f"Cut {number:0{number_width}d} - previous shot "
            f"{previous.duration_seconds(info.fps):.2f}s"
        )
        lines.append(
            f"{number:0{number_width}d}  001      V     C        "
            f"{tc_in} {tc_out} {tc_in} {tc_out}"
        )
        lines.append(
            f"{note} |C:{color_token} |M:Cut {number:0{number_width}d} |D:1"
        )
        lines.append("")

    return "\n".join(lines)


def parse_record_start(value: str, info: MediaInfo) -> int:
    text = str(value).strip()
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}[:;]\d{1,2}", text):
        return tc_to_frames(text, info.fps, info.drop_frame)
    return int(round(parse_time(text) * float(info.fps)))


def _frame_time(frames: int, frame_duration: Fraction) -> str:
    value = Fraction(frames) * frame_duration
    return f"{value.numerator}/{value.denominator}s"


def format_name(width: int, height: int, fps: Fraction) -> str:
    rate = float(fps)
    codes = {
        23.976: "2398", 24: "24", 25: "25", 29.97: "2997",
        30: "30", 47.952: "4795", 48: "48", 50: "50",
        59.94: "5994", 60: "60", 119.88: "11988", 120: "120",
    }
    code = next((v for k, v in codes.items() if abs(rate - k) < 0.01), None)
    standard = {
        (1920, 1080): "1080", (3840, 2160): "2160", (1280, 720): "720",
        (2560, 1440): "1440", (4096, 2160): "2160", (2048, 1080): "1080",
    }.get((width, height))
    if standard and code:
        return f"FFVideoFormat{standard}p{code}"
    return f"FFVideoFormat{width}x{height}"


def build_fcpxml(shots: list[Shot], info: MediaInfo, title: str,
                 markers_only: bool = False) -> str:
    frame_duration = Fraction(1, 1) / info.fps
    first = shots[0].start_frame
    last = shots[-1].end_frame
    timeline_frames = last - first
    total_frames = max(info.total_frames, last)

    fmt = ET.Element("format", {
        "id": "r1",
        "name": format_name(info.width, info.height, info.fps),
        "frameDuration": _frame_time(1, frame_duration),
        "width": str(info.width),
        "height": str(info.height),
    })

    asset_attrs = {
        "id": "r2",
        "name": info.path.name,
        "start": _frame_time(0, frame_duration),
        "duration": _frame_time(total_frames, frame_duration),
        "hasVideo": "1",
        "videoSources": "1",
        "format": "r1",
    }
    if info.has_audio:
        asset_attrs.update({
            "hasAudio": "1",
            "audioSources": "1",
            "audioChannels": str(info.audio_channels or 2),
            "audioRate": str(info.audio_rate or 48000),
        })
    asset = ET.Element("asset", asset_attrs)
    ET.SubElement(asset, "media-rep", {
        "kind": "original-media",
        "src": info.path.as_uri(),
    })

    resources = ET.Element("resources")
    resources.append(fmt)
    resources.append(asset)

    root = ET.Element("fcpxml", {"version": "1.9"})
    root.append(resources)

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": title})
    project = ET.SubElement(event, "project", {"name": title})
    sequence = ET.SubElement(project, "sequence", {
        "format": "r1",
        "duration": _frame_time(timeline_frames, frame_duration),
        "tcStart": _frame_time(0, frame_duration),
        "tcFormat": "DF" if info.drop_frame else "NDF",
        "audioLayout": "stereo",
        "audioRate": "48k",
    })
    spine = ET.SubElement(sequence, "spine")

    if markers_only:
        clip = ET.SubElement(spine, "asset-clip", {
            "ref": "r2",
            "offset": _frame_time(0, frame_duration),
            "start": _frame_time(first, frame_duration),
            "duration": _frame_time(timeline_frames, frame_duration),
            "name": info.path.stem,
            "format": "r1",
        })
        # One marker per cut (the start of the video is not a cut).
        for number, shot in enumerate(shots[1:], start=1):
            local = shot.start_frame - first
            if local <= 0:
                continue
            tc = frames_to_tc(
                info.start_tc_frames + shot.start_frame,
                info.fps, info.drop_frame,
            )
            ET.SubElement(clip, "marker", {
                "start": _frame_time(local, frame_duration),
                "duration": _frame_time(1, frame_duration),
                "value": f"Cut {number:04d}",
                "note": f"{tc} - previous shot "
                        f"{shots[number - 1].duration_seconds(info.fps):.2f}s",
            })
    else:
        for number, shot in enumerate(shots, 1):
            offset = shot.start_frame - first
            ET.SubElement(spine, "asset-clip", {
                "ref": "r2",
                "offset": _frame_time(offset, frame_duration),
                "start": _frame_time(shot.start_frame, frame_duration),
                "duration": _frame_time(shot.duration_frames, frame_duration),
                "name": f"{info.path.stem}_C{number:04d}",
                "format": "r1",
            })

    ET.indent(root, space="    ")
    body = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!DOCTYPE fcpxml>\n"
        f"{body}\n"
    )


def build_csv(shots: list[Shot], info: MediaInfo) -> str:
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([
        "shot", "cut_at_start", "start_tc", "end_tc",
        "start_frame", "end_frame", "duration_s", "start_s", "end_s",
    ])
    for number, (shot, tc_in, tc_out) in enumerate(shot_timecodes(shots, info), 1):
        writer.writerow([
            number,
            "yes" if number > 1 else "no",
            tc_in,
            tc_out,
            shot.start_frame,
            shot.end_frame,
            f"{shot.duration_seconds(info.fps):.3f}",
            f"{shot.start_seconds(info.fps):.3f}",
            f"{shot.end_seconds(info.fps):.3f}",
        ])
    return buffer.getvalue()


def cut_list(shots: list[Shot], info: MediaInfo) -> list[dict]:
    """Return cut points (boundaries between shots), not shot starts."""
    cuts = []
    for number, shot in enumerate(shots[1:], start=2):
        frame = shot.start_frame
        cuts.append({
            "number": number - 1,
            "frame": frame,
            "seconds": frame / float(info.fps),
            "timecode": frames_to_tc(
                info.start_tc_frames + frame, info.fps, info.drop_frame
            ),
        })
    return cuts


def build_txt(shots: list[Shot], info: MediaInfo, args) -> str:
    durations = [s.duration_seconds(info.fps) for s in shots]
    cuts = cut_list(shots, info)
    lines = [
        "SCENE CUT DETECTION",
        "=" * 60,
        f"File          : {info.path}",
        f"Duration      : {format_duration(info.duration)}",
        f"Resolution    : {info.width}x{info.height}",
        f"FPS           : {info.fps_label} ({info.fps.numerator}/{info.fps.denominator})",
        f"Start TC      : {frames_to_tc(info.start_tc_frames, info.fps, info.drop_frame)}"
        + ("  (drop frame)" if info.drop_frame else ""),
        f"Detector      : {args.detector}  "
        f"(threshold {args.threshold}, min shot {args.min_scene_len}s)",
        "",
        f"Cuts          : {len(cuts)}",
        f"Shots         : {len(shots)}",
        f"Average shot  : {sum(durations) / len(durations):.2f}s",
        f"Shortest shot : {min(durations):.2f}s",
        f"Longest shot  : {max(durations):.2f}s",
        "",
        "CUTS",
        "-" * 60,
        f"{'#':>5}  {'TIMECODE':<14} {'SECONDS':>10}  {'FRAME':>8}",
    ]
    for cut in cuts:
        lines.append(
            f"{cut['number']:>5}  {cut['timecode']:<14} "
            f"{cut['seconds']:>10.3f}  {cut['frame']:>8}"
        )
    lines += [
        "",
        "SHOTS",
        "-" * 60,
        f"{'#':>5}  {'START':<14} {'END':<14} {'DUR(s)':>8}",
    ]
    for number, (shot, tc_in, tc_out) in enumerate(shot_timecodes(shots, info), 1):
        lines.append(
            f"{number:>5}  {tc_in:<14} {tc_out:<14} "
            f"{shot.duration_seconds(info.fps):>8.2f}"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# End-to-end processing (shared by the CLI and the GUI)
# --------------------------------------------------------------------------- #

def process_video(video: Path, out_dir: Path, args, log=print, progress=None,
                  cancelled=None) -> DetectionResult:
    """Probe, detect and write every requested output. Returns a result object."""
    if getattr(args, "threshold", None) is None:
        args.threshold = PRESETS[args.preset][args.detector]

    if args.downscale != "auto":
        try:
            args.downscale = int(args.downscale)
            if args.downscale < 1:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("downscale must be 'auto' or an integer >= 1")

    log(f"Analyzing: {video.name}")
    info = probe_media(video, getattr(args, "fps", None), warn=log)
    log(
        f"  {info.width}x{info.height} · {info.fps_label} fps · "
        f"{format_duration(info.duration)} · TC "
        f"{frames_to_tc(info.start_tc_frames, info.fps, info.drop_frame)}"
    )
    log(f"  Detector: {args.detector} (preset {args.preset}, "
        f"threshold {args.threshold})")

    marker_offset = 0
    if "markers" in args.formats:
        marker_offset = parse_record_start(args.record_start, info)
        if marker_offset < 0:
            raise ValueError("record start timecode cannot be negative")

    shots = detect_shots(video, info, args, progress=progress,
                         cancelled=cancelled)
    cuts = cut_list(shots, info)
    durations = [shot.duration_seconds(info.fps) for shot in shots]

    path_stem = safe_stem(video)
    title = f"{path_stem}_cuts"
    outputs: list[Path] = []
    out_dir.mkdir(parents=True, exist_ok=True)

    if "fcpxml" in args.formats:
        target = out_dir / f"{path_stem}_cuts.fcpxml"
        target.write_text(
            build_fcpxml(shots, info, title, markers_only=args.markers_only),
            encoding="utf-8",
        )
        outputs.append(target)

    if "edl" in args.formats:
        target = out_dir / f"{path_stem}_cuts.edl"
        target.write_text(build_edl(shots, info, title), encoding="utf-8")
        outputs.append(target)

    if "markers" in args.formats:
        target = out_dir / f"{path_stem}_markers.edl"
        target.write_text(
            build_marker_edl(
                shots, info, f"{path_stem}_markers",
                offset_frames=marker_offset, color=args.marker_color,
            ),
            encoding="utf-8",
        )
        outputs.append(target)

    if "csv" in args.formats:
        target = out_dir / f"{path_stem}_cuts.csv"
        target.write_text("\ufeff" + build_csv(shots, info), encoding="utf-8")
        outputs.append(target)

    if "txt" in args.formats:
        target = out_dir / f"{path_stem}_cuts.txt"
        target.write_text(build_txt(shots, info, args), encoding="utf-8")
        outputs.append(target)

    log("")
    log(f"  Cuts detected : {len(cuts)}")
    log(f"  Shots         : {len(shots)}")
    if durations:
        log(f"  Average shot  : {sum(durations) / len(durations):.2f} s")
        log(f"  Shortest shot : {min(durations):.2f} s")
        log(f"  Longest shot  : {max(durations):.2f} s")
    log("")
    for output in outputs:
        log(f"  → {output}")

    return DetectionResult(
        info=info, shots=shots, cuts=cuts, outputs=outputs, out_dir=out_dir
    )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def open_in_file_manager(path: Path) -> None:
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scene-cut-detector",
        description=(
            "Detect scene cuts and generate FCPXML/EDL/CSV files ready for "
            "DaVinci Resolve."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scene_cut_detector.py video.mp4\n"
            "  python scene_cut_detector.py video.mp4 --markers-only\n"
            "  python scene_cut_detector.py video.mp4 --preset sensitive --detector adaptive\n"
            "  python scene_cut_detector.py video.mp4 -o ~/Desktop/cuts --open\n"
        ),
    )
    parser.add_argument("video", type=Path, help="Video file to analyze.")
    parser.add_argument("-o", "--out", type=Path, default=None,
                        help="Output folder (default: <video>_cuts).")
    parser.add_argument("--detector", default="content",
                        choices=["content", "adaptive", "hash", "histogram"],
                        help="Detection algorithm (default: content).")
    parser.add_argument("--preset", default="normal",
                        choices=list(PRESETS),
                        help="Sensitivity: normal, sensitive (more cuts) or "
                             "strict (fewer cuts).")
    parser.add_argument("-t", "--threshold", type=float, default=None,
                        help="Detector threshold. Uses the preset value if omitted.")
    parser.add_argument("--min-scene-len", type=float, default=0.5,
                        metavar="SEC",
                        help="Minimum shot length in seconds (default: 0.5).")
    parser.add_argument("--min-content", type=float, default=None,
                        help="AdaptiveDetector only: minimum content value "
                             "(default: 15).")
    parser.add_argument("--downscale", default="auto",
                        help="Downscale factor for speed: auto (default), 1, 2, 4...")
    parser.add_argument("--start", type=parse_time, default=None,
                        metavar="TIME", help="Start analysis at this point.")
    parser.add_argument("--end", type=parse_time, default=None,
                        metavar="TIME", help="Stop analysis at this point.")
    parser.add_argument("--fps", default=None,
                        help="Force FPS (if the container reports it incorrectly).")
    parser.add_argument("--formats", nargs="+",
                        choices=["fcpxml", "edl", "markers", "csv", "txt"],
                        default=["fcpxml", "markers", "edl", "csv", "txt"],
                        help="Output formats (default: all).")
    parser.add_argument("--record-start", default="01:00:00:00",
                        metavar="TC",
                        help="Timeline timecode where the first frame of the clip "
                             "sits. Resolve defaults to 01:00:00:00; use "
                             "00:00:00:00 if your timeline starts at zero.")
    parser.add_argument("--marker-color", default="Blue",
                        choices=RESOLVE_COLORS,
                        help="Resolve marker color (default: Blue).")
    parser.add_argument("--markers-only", action="store_true",
                        help="FCPXML with a single clip and a marker at every cut "
                             "(instead of a pre-cut timeline).")
    parser.add_argument("--open", action="store_true",
                        help="Open the output folder when finished.")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Do not show the progress bar.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {VERSION}")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        import scenedetect  # noqa: F401
    except ImportError:
        print(
            "ERROR: PySceneDetect is not installed.\n\n"
            "Install the dependencies with:\n"
            "  ./Install Dependencies.command\n"
            "or manually:\n"
            "  python3 -m pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        return 2

    video = args.video.expanduser().resolve()
    if not video.is_file():
        print(f"ERROR: file not found: {video}", file=sys.stderr)
        return 2
    if video.suffix.lower() not in VIDEO_EXTENSIONS:
        print(f"Warning: unknown extension ({video.suffix}); trying anyway.",
              file=sys.stderr)

    if args.threshold is None:
        args.threshold = PRESETS[args.preset][args.detector]

    if args.markers_only and "fcpxml" not in args.formats:
        print("Warning: --markers-only only affects the FCPXML format, "
              "which is not in --formats.", file=sys.stderr)

    out_dir = (args.out.expanduser().resolve() if args.out
               else video.parent / f"{video.stem}_cuts")

    if args.downscale != "auto":
        try:
            args.downscale = int(args.downscale)
            if args.downscale < 1:
                raise ValueError
        except (TypeError, ValueError):
            parser.error("--downscale must be 'auto' or an integer >= 1.")

    try:
        result = process_video(video, out_dir, args, log=print)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR while processing the video: {exc}", file=sys.stderr)
        return 1

    print()
    if not result.cuts:
        print("  No cuts detected. Try:")
        print("    --preset sensitive")
        print("    --detector adaptive --preset sensitive")
        print("    --min-scene-len 0.2")
        print()

    if args.open:
        open_in_file_manager(out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
