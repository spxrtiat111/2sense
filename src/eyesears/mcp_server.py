"""2Sense MCP server: full eyes + ears for short-form video ads.

Tools (callable from Claude Code CLI and the Claude Desktop app):
  - analyze_ad(source)  -> labeled contact-sheet IMAGES (eyes) + transcript (ears)
  - transcribe(path)    -> transcript only (Groq Whisper)

`analyze_ad` returns the frames as image content so Claude can SEE the ad directly —
this is how the Desktop app (which has no Claude Code sub-agents) gets eyes.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from . import audio_features, media, prep, yamnet
from .config import Config, load_config

mcp = FastMCP("2Sense")

_PASSTHROUGH_AUDIO = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


# --------------------------------------------------------------------------- ears


def _transcribe(path: str, language: str, cfg: Config) -> dict:
    if not cfg.has_key:
        return {"error": "GROQ_API_KEY is not set. Add it to the project .env file."}
    src = Path(path).expanduser().resolve()
    if not src.exists():
        return {"error": f"No such file: {src}"}

    lang = None if (language or "auto").lower() == "auto" else language
    tmp_audio: Path | None = None
    try:
        if src.suffix.lower() not in _PASSTHROUGH_AUDIO:
            tmp_audio = Path(tempfile.mkstemp(suffix=".wav")[1])
            audio_path = media.extract_audio(src, tmp_audio, sample_rate=cfg.audio_sr)
        else:
            audio_path = src

        from groq import Groq

        client = Groq(api_key=cfg.groq_api_key)
        with open(audio_path, "rb") as fh:
            kwargs = dict(
                file=(audio_path.name, fh.read()),
                model=cfg.ears_model,
                response_format="verbose_json",
            )
            if lang:
                kwargs["language"] = lang
            resp = client.audio.transcriptions.create(**kwargs)

        data = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        segments = [
            {"start": s.get("start"), "end": s.get("end"), "text": (s.get("text") or "").strip()}
            for s in (data.get("segments") or [])
        ]
        return {
            "text": (data.get("text") or "").strip(),
            "language": data.get("language"),
            "duration": data.get("duration"),
            "segments": segments,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"transcription failed: {e}"}
    finally:
        if tmp_audio and tmp_audio.exists():
            tmp_audio.unlink(missing_ok=True)


@mcp.tool()
def transcribe(path: str, language: str = "auto") -> dict:
    """Transcribe speech from a local audio OR video file using Groq Whisper.

    Args:
        path: Absolute path to an audio or video file (video audio is auto-extracted).
        language: "auto" to detect, or an ISO code like "fr" / "en" to force.

    Returns: {text, language, duration, segments:[{start,end,text}]}.
    """
    return _transcribe(path, language, load_config())


@mcp.tool()
def audio_profile(path: str) -> dict:
    """Analyze music/energy/rhythm of an audio OR video file (free, local, numpy-based).

    Returns tempo (BPM), energy curve, onset 'hits' (useful vs. visual cuts), loudness
    dynamics, brightness, and a music-vs-speech estimate. No genre/mood/song-ID.
    """
    cfg = load_config()
    src = Path(path).expanduser().resolve()
    if not src.exists():
        return {"error": f"No such file: {src}"}
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        wavp = media.extract_audio(src, tmp, sample_rate=cfg.audio_sr)
        return audio_features.profile(wavp)
    except Exception as e:  # noqa: BLE001
        return {"error": f"audio profile failed: {e}"}
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


@mcp.tool()
def audio_events(path: str, top_k: int = 12) -> dict:
    """Tag audio events with YAMNet (free, local): Music, Speech, instruments, genres,
    SFX (whoosh/beep/...). Works on an audio OR video file.

    Returns {top:[{label,score}], rollup:{Music,Speech,SFX}, timeline:[{start,end,label}]}.
    No mood (happy/sad) — YAMNet covers events/instruments/genres, not affect.
    """
    cfg = load_config()
    src = Path(path).expanduser().resolve()
    if not src.exists():
        return {"error": f"No such file: {src}"}
    tmp = Path(tempfile.mkstemp(suffix=".wav")[1])
    try:
        wavp = media.extract_audio(src, tmp, sample_rate=cfg.audio_sr)
        return yamnet.classify(wavp, top_k=top_k)
    except Exception as e:  # noqa: BLE001
        return {"error": f"audio events failed: {e}"}
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------- eyes + ears


def _legend(prep_out: dict) -> str:
    """Compact per-sheet timestamp map so the model can anchor each grid cell."""
    lines = []
    manifest = json.loads(Path(prep_out["manifest_path"]).read_text())
    for i, sheet in enumerate(manifest):
        ts = ", ".join(f"{c['timestamp_s']}s" for c in sheet["cells"])
        name = Path(sheet["sheet"]).name
        lines.append(f"  Sheet {i + 1} ({name}, {sheet['grid']} row-major): {ts}")
    return "\n".join(lines)


@mcp.tool()
def analyze_ad(source: str, language: str = "auto", with_audio: bool = True) -> list:
    """Give Claude EYES + EARS on a short-form video ad.

    Runs the local prep pipeline (download if a URL, sample frames at the configured
    fps, tile them into labeled contact sheets, extract audio), transcribes the audio,
    and returns: a text block (timestamp legend + transcript) followed by the contact
    sheet IMAGES. Look at the images and read the transcript to analyze the ad.

    Args:
        source: A local video path OR a TikTok / Reels / YouTube / Meta URL.
        language: "auto", or an ISO code like "fr" / "en" to force transcription language.
        with_audio: set false to skip transcription (eyes only).

    Returns: [text, image, image, ...] — contact sheets each have per-cell timestamps
    burned into the top-left as `t=SECONDS`, matching the legend in the text block.
    """
    cfg = load_config()
    try:
        out = prep.run(source, cfg)
    except Exception as e:  # noqa: BLE001
        return [f"prep failed for {source!r}: {e}"]

    parts = [
        f"# Ad perception: {out['slug']}",
        f"source: {out['source']}",
        f"duration: {out.get('duration_s')}s | frames: {out['frame_count']} @ {out['fps']}fps "
        f"| sheets: {out['sheet_count']}",
        "",
        "## Contact-sheet timestamp legend (each cell is a frame; times also burned into the image)",
        _legend(out),
        "",
        "## Transcript (ears)",
    ]

    if with_audio:
        tr = _transcribe(out["audio_path"], language, cfg)
        if tr.get("error"):
            parts.append(f"(transcription error: {tr['error']})")
        else:
            parts.append(f"language: {tr.get('language')} | duration: {tr.get('duration')}s")
            parts.append(f"\n{tr.get('text') or '(no speech detected)'}\n")
            if tr.get("segments"):
                parts.append("segments:")
                for s in tr["segments"]:
                    parts.append(f"  [{s['start']}-{s['end']}s] {s['text']}")
            # persist alongside the prep artifacts
            (Path(out["workdir"]) / "ears.json").write_text(
                json.dumps(tr, ensure_ascii=False, indent=2)
            )
    else:
        parts.append("(skipped)")

    if cfg.audio_profile:
        parts.append("\n## Audio energy & rhythm (music/SFX — free signal analysis)")
        prof = audio_features.profile(out["audio_path"])
        if prof.get("error"):
            parts.append(f"(audio profile unavailable: {prof['error']})")
        else:
            parts.append(
                f"tempo ~{prof['tempo_bpm_estimate']} BPM | energy {prof['energy_trend']} "
                f"(peak {prof['energy_peak_s']}s, trough {prof['energy_trough_s']}s) | "
                f"dynamic range {prof['loudness_dynamic_range_db']}dB | "
                f"brightness {prof['brightness']} | music likelihood {prof['music_likelihood']} "
                f"(continuous bed: {prof['continuous_audio_bed']})"
            )
            parts.append("energy curve: " + ", ".join(f"{b['t']}s:{b['level']}" for b in prof["energy_curve"]))
            if prof["onset_times_s"]:
                parts.append(
                    f"audio hits ({prof['onset_count']}; compare with visual cuts): "
                    + ", ".join(f"{t}s" for t in prof["onset_times_s"])
                )
            (Path(out["workdir"]) / "audio.json").write_text(
                json.dumps(prof, ensure_ascii=False, indent=2)
            )

    if cfg.yamnet:
        parts.append("\n## Audio events (YAMNet — music/speech/instruments/genre/SFX)")
        try:
            ev = yamnet.classify(out["audio_path"])
            if ev.get("error"):
                parts.append(f"(audio events unavailable: {ev['error']})")
            else:
                parts.append("top tags: " + ", ".join(f"{t['label']} {t['score']}" for t in ev["top"]))
                r = ev["rollup"]
                parts.append(f"presence — Music {r['Music']} | Speech {r['Speech']} | SFX {r['SFX']}")
                if ev.get("timeline"):
                    parts.append("timeline: " + ", ".join(
                        f"{s['start']}-{s['end']}s {s['label']}" for s in ev["timeline"]))
                (Path(out["workdir"]) / "audio_events.json").write_text(
                    json.dumps(ev, ensure_ascii=False, indent=2))
        except Exception as e:  # noqa: BLE001
            parts.append(f"(audio events unavailable: {e})")

    parts.append(
        "\n---\nLook at the contact sheets below (eyes), the transcript + audio energy/rhythm "
        "+ audio events above (ears), then analyze the ad: hook, pacing, message/awareness, "
        "clarity, brand, CTA — and give advice to improve future content and/or design an "
        "incrementality test. Note where audio hits/energy peaks/music changes align (or not) "
        "with cuts and the hook."
    )

    blocks: list = ["\n".join(parts)]
    blocks.extend(Image(path=s) for s in out["sheets"])
    return blocks


def main():
    mcp.run()


if __name__ == "__main__":
    main()
