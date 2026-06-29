"""Health check: deps, ffmpeg, config, Groq key, and (optionally) a live Groq ping."""
from __future__ import annotations

import importlib
import subprocess

from .config import Config
from .media import ffmpeg_exe


def check(cfg: Config, ping: bool = False) -> list[tuple[str, bool, str]]:
    """Return a list of (label, ok, detail) rows."""
    rows: list[tuple[str, bool, str]] = []

    for mod in ("yt_dlp", "imageio_ffmpeg", "PIL", "groq", "mcp", "dotenv", "typer", "rich"):
        try:
            m = importlib.import_module(mod)
            rows.append((f"import {mod}", True, getattr(m, "__version__", "ok")))
        except Exception as e:  # noqa: BLE001
            rows.append((f"import {mod}", False, str(e)))

    try:
        exe = ffmpeg_exe()
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, check=False)
        first = out.stdout.splitlines()[0] if out.stdout else "no output"
        rows.append(("ffmpeg", out.returncode == 0, first))
    except Exception as e:  # noqa: BLE001
        rows.append(("ffmpeg", False, str(e)))

    try:
        out = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, check=False)
        rows.append(("yt-dlp cli", out.returncode == 0, out.stdout.strip() or out.stderr.strip()))
    except Exception as e:  # noqa: BLE001
        rows.append(("yt-dlp cli", False, str(e)))

    rows.append(("frames", True, f"{cfg.fps} fps, cap {cfg.max_frames}, {cfg.sheet_cols}x{cfg.sheet_rows} sheets"))
    rows.append(("ears model", True, f"{cfg.ears_model} (lang={cfg.language})"))
    rows.append(("GROQ_API_KEY", cfg.has_key,
                 "set" if cfg.has_key else "MISSING (cp .env.example .env)"))

    if ping:
        if not cfg.has_key:
            rows.append(("groq ping", False, "skipped: no API key"))
        else:
            try:
                from groq import Groq
                models = Groq(api_key=cfg.groq_api_key).models.list()
                ids = [m.id for m in models.data] if hasattr(models, "data") else []
                has = cfg.ears_model in ids
                rows.append(("groq ping", True,
                             f"key ok; {cfg.ears_model} {'available' if has else 'NOT in model list'}"))
            except Exception as e:  # noqa: BLE001
                rows.append(("groq ping", False, str(e)))

    return rows
