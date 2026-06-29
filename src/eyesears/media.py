"""ffmpeg + Pillow plumbing: locate ffmpeg, probe duration, extract frames + audio,
and tile frames into labeled contact sheets for Claude's vision sub-agent.

We use the ffmpeg binary bundled by imageio-ffmpeg so the user needs no Homebrew /
system ffmpeg. This is codec + image plumbing, not a model -- no LLM runs locally.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


def ffmpeg_exe() -> str:
    """Absolute path to a working ffmpeg binary (bundled via imageio-ffmpeg)."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_exe(), *args], capture_output=True, text=True, check=False
    )


def probe_duration(video: Path) -> float | None:
    """Return duration in seconds by parsing ffmpeg's stderr, or None if unknown."""
    proc = _run(["-i", str(video)])
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        return None
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def extract_frames(
    video: Path,
    out_dir: Path,
    fps: float = 3.0,
    max_frames: int = 90,
    width: int = 360,
) -> list[dict]:
    """Extract downscaled JPEG frames; return [{path, timestamp_s}] in source time.
    Oversamples at `fps`, then evenly subsamples to `max_frames` if needed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f_*.jpg"):
        old.unlink()

    eff_fps = fps
    dur = probe_duration(video)
    if dur and dur * fps > 1.5 * max_frames:
        eff_fps = round((1.5 * max_frames) / dur, 3)  # keep temp frame count bounded

    vf = f"fps={eff_fps},scale={width}:-2"
    proc = _run([
        "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-vf", vf, "-q:v", "3",
        str(out_dir / "f_%05d.jpg"),
    ])
    frames = sorted(out_dir.glob("f_*.jpg"))
    if not frames:
        raise RuntimeError(
            f"ffmpeg produced no frames from {video}.\n{proc.stderr.strip()}"
        )

    items = [
        {"path": str(f.resolve()), "timestamp_s": round(i / eff_fps, 2)}
        for i, f in enumerate(frames)
    ]

    if len(items) > max_frames:
        step = (len(items) - 1) / (max_frames - 1)
        idxs = sorted({round(i * step) for i in range(max_frames)})
        keep = {items[i]["path"] for i in idxs}
        for it in items:
            if it["path"] not in keep:
                Path(it["path"]).unlink(missing_ok=True)
        items = [it for it in items if it["path"] in keep]

    return items


def extract_audio(video: Path, out_path: Path, sample_rate: int = 16000) -> Path:
    """Extract a mono WAV audio track suitable for ASR."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = _run([
        "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(out_path),
    ])
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(
            f"ffmpeg produced no audio from {video} (is there an audio track?).\n"
            f"{proc.stderr.strip()}"
        )
    return out_path


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                pass
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10
    except TypeError:
        return ImageFont.load_default()


def build_contact_sheets(
    frame_items: list[dict],
    out_dir: Path,
    cols: int = 3,
    rows: int = 3,
    label: bool = True,
) -> tuple[list[str], list[dict]]:
    """Tile frames into labeled grids. Returns (sheet_paths, manifest).

    manifest = [{sheet, grid, cells:[{cell,row,col,timestamp_s,frame}]}], so the
    vision sub-agent can map any grid cell back to an exact source timestamp."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("sheet_*.jpg"):
        old.unlink()
    if not frame_items:
        return [], []

    with Image.open(frame_items[0]["path"]) as im0:
        cw, ch = im0.size
    font = _load_font(max(14, cw // 18))
    per = cols * rows

    sheet_paths: list[str] = []
    manifest: list[dict] = []
    for s in range(0, len(frame_items), per):
        chunk = frame_items[s : s + per]
        sheet = Image.new("RGB", (cw * cols, ch * rows), (12, 12, 12))
        draw = ImageDraw.Draw(sheet)
        cells = []
        for idx, it in enumerate(chunk):
            r, c = divmod(idx, cols)
            x, y = c * cw, r * ch
            with Image.open(it["path"]) as im:
                im = im.convert("RGB")
                if im.size != (cw, ch):
                    im = im.resize((cw, ch))
                sheet.paste(im, (x, y))
            if label:
                txt = f"t={it['timestamp_s']:.2f}s"
                bbox = draw.textbbox((0, 0), txt, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.rectangle([x, y, x + tw + 10, y + th + 8], fill=(0, 0, 0))
                draw.text((x + 5, y + 3), txt, fill=(255, 255, 255), font=font)
            cells.append({
                "cell": idx, "row": r, "col": c,
                "timestamp_s": it["timestamp_s"], "frame": it["path"],
            })
        sheet_path = (out_dir / f"sheet_{s // per:03d}.jpg").resolve()
        sheet.save(sheet_path, quality=85)
        sheet_paths.append(str(sheet_path))
        manifest.append({"sheet": str(sheet_path), "grid": f"{cols}x{rows}", "cells": cells})

    return sheet_paths, manifest
