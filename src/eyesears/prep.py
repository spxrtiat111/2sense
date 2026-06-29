"""Prep step (no LLM calls): ingest -> frames -> contact sheets + manifest -> audio.

The eyes (Claude vision sub-agent) and ears (Groq Whisper MCP) consume these artifacts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import ingest, media
from .config import Config


def run(input_str: str, cfg: Config) -> dict:
    """Produce perception inputs for one video. Returns the prep dict; writes to disk."""
    video, slug = ingest.resolve(input_str, cfg.downloads_dir)
    workdir = cfg.out_dir / slug
    workdir.mkdir(parents=True, exist_ok=True)

    duration = media.probe_duration(video)

    frame_items = media.extract_frames(
        video, workdir / "frames",
        fps=cfg.fps, max_frames=cfg.max_frames, width=cfg.cell_width,
    )
    sheets, manifest = media.build_contact_sheets(
        frame_items, workdir / "sheets",
        cols=cfg.sheet_cols, rows=cfg.sheet_rows, label=cfg.sheet_label,
    )
    (workdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    audio = media.extract_audio(video, workdir / "audio.wav", sample_rate=cfg.audio_sr)

    prep = {
        "slug": slug,
        "source": input_str,
        "video_path": str(video),
        "duration_s": duration,
        "fps": cfg.fps,
        "frame_count": len(frame_items),
        "sheet_count": len(sheets),
        "sheets_dir": str((workdir / "sheets").resolve()),
        "sheets": sheets,
        "manifest_path": str((workdir / "manifest.json").resolve()),
        "audio_path": str(audio.resolve()),
        "workdir": str(workdir.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (workdir / "prep.json").write_text(json.dumps(prep, ensure_ascii=False, indent=2))
    return prep
