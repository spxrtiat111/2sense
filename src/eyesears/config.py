"""Load configuration from config.toml + .env."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = two levels up from this file (src/eyesears/config.py -> root).
ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    groq_api_key: str | None
    # frames
    fps: float
    max_frames: int
    cell_width: int
    # sheets
    sheet_cols: int
    sheet_rows: int
    sheet_label: bool
    # audio
    audio_sr: int
    audio_profile: bool
    yamnet: bool
    # ears (groq whisper)
    ears_model: str
    language: str
    # io
    out_dir: Path
    downloads_dir: Path

    @property
    def has_key(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.strip())


def load_config(config_path: Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")  # populates GROQ_API_KEY if present
    path = config_path or (ROOT / "config.toml")
    raw: dict = {}
    if path.exists():
        with path.open("rb") as fh:
            raw = tomllib.load(fh)

    frames = raw.get("frames", {})
    sheets = raw.get("sheets", {})
    audio = raw.get("audio", {})
    ears = raw.get("ears", {})
    io = raw.get("io", {})

    return Config(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        fps=float(frames.get("fps", 3)),
        max_frames=int(frames.get("max_frames", 90)),
        cell_width=int(frames.get("cell_width", 360)),
        sheet_cols=int(sheets.get("cols", 3)),
        sheet_rows=int(sheets.get("rows", 3)),
        sheet_label=bool(sheets.get("label", True)),
        audio_sr=int(audio.get("sample_rate", 16000)),
        audio_profile=bool(audio.get("profile", True)),
        yamnet=bool(audio.get("yamnet", True)),
        ears_model=ears.get("model", "whisper-large-v3"),
        language=ears.get("language", "auto"),
        out_dir=_resolve(io.get("out_dir", "data/out")),
        downloads_dir=_resolve(io.get("downloads_dir", "data/downloads")),
    )


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)
