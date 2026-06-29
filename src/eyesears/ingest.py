"""Resolve an input (local file path or platform URL) to a local video file."""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .media import ffmpeg_exe

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(s: str) -> bool:
    return bool(_URL_RE.match(s.strip()))


def slugify(name: str, seed: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "video"
    digest = hashlib.sha1(seed.encode()).hexdigest()[:6]
    return f"{base}-{digest}"


def resolve(input_str: str, downloads_dir: Path) -> tuple[Path, str]:
    """Return (local_video_path, slug). Downloads URLs via yt-dlp if needed."""
    if is_url(input_str):
        return _download(input_str, downloads_dir)

    path = Path(input_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    return path, slugify(path.stem, str(path))


def _download(url: str, downloads_dir: Path) -> tuple[Path, str]:
    downloads_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify("dl", url)
    out_tmpl = str(downloads_dir / f"{slug}.%(ext)s")

    # Use yt-dlp's CLI (installed as a dependency) and point it at the bundled ffmpeg
    # so it can merge/remux without a system ffmpeg.
    cmd = [
        "yt-dlp",
        "-f", "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "--ffmpeg-location", ffmpeg_exe(),
        "--no-playlist",
        "-o", out_tmpl,
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {url}:\n{proc.stderr.strip()}")

    candidates = sorted(downloads_dir.glob(f"{slug}.*"))
    videos = [c for c in candidates if c.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if not videos:
        raise RuntimeError(f"yt-dlp downloaded nothing usable for {url}")
    return videos[0].resolve(), slug
