"""YAMNet audio-event tagging — semantic labels (Music, Speech, instruments, genres,
SFX) on top of the numpy signal profile. Free + local; ~15MB model on TensorFlow Hub.

TensorFlow is imported lazily and the model is cached for the process, so importing
this module is cheap and only the first classify() call pays the TF + download cost.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np

_MODEL = None
_CLASSES: list[str] | None = None

# Coarse buckets for ad-relevant rollups + timeline.
_SPEECH = ("speech", "narration", "conversation", "monologue", "whispering")
_MUSIC = ("music", "singing", "instrument", "guitar", "drum", "bass", "piano",
          "synthesizer", "violin", "trumpet", "saxophone", "melody", "song",
          "rapping", "choir", "orchestra", "beat")
_SFX = ("whoosh", "swoosh", "beep", "click", "ding", "whip", "boing", "sound effect",
        "ringtone", "alarm", "notification", "camera", "whistle", "explosion",
        "gunshot", "sweep", "zip", "thump")


def _coarse(label: str) -> str:
    l = label.lower()
    if any(k in l for k in _SPEECH):
        return "Speech"
    if any(k in l for k in _MUSIC):
        return "Music"
    if any(k in l for k in _SFX):
        return "SFX"
    return "Other"


def _load():
    global _MODEL, _CLASSES
    if _MODEL is not None:
        return _MODEL, _CLASSES
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    import tensorflow as tf  # noqa: F401
    import tensorflow_hub as hub

    model = hub.load("https://tfhub.dev/google/yamnet/1")
    names: list[str] = []
    with open(model.class_map_path().numpy().decode(), newline="") as fh:
        for row in csv.DictReader(fh):
            names.append(row["display_name"])
    _MODEL, _CLASSES = model, names
    return _MODEL, _CLASSES


def _read_16k_mono(path: str | Path) -> np.ndarray:
    from .audio_features import _read_wav_mono

    x, sr = _read_wav_mono(Path(path))
    if sr != 16000 and x.size:
        n = int(round(x.size * 16000 / sr))
        x = np.interp(np.linspace(0, x.size, n, endpoint=False), np.arange(x.size), x)
    return x.astype(np.float32)


def classify(path: str | Path, top_k: int = 12) -> dict:
    """Return {top:[{label,score}], rollup:{Music,Speech,SFX,...}, timeline:[{start,end,label}]}."""
    model, names = _load()
    wav = _read_16k_mono(path)
    if wav.size == 0:
        return {"error": "empty audio"}

    scores, _embeddings, _spec = model(wav)
    scores = scores.numpy()  # [T, 521]
    mean = scores.mean(axis=0)

    order = [i for i in mean.argsort()[::-1] if mean[i] >= 0.05][:top_k]
    top = [{"label": names[i], "score": round(float(mean[i]), 3)} for i in order]

    def grp(keys: tuple[str, ...]) -> float:
        idxs = [i for i, n in enumerate(names) if any(k in n.lower() for k in keys)]
        return round(float(mean[idxs].max()), 3) if idxs else 0.0

    rollup = {"Music": grp(_MUSIC), "Speech": grp(_SPEECH), "SFX": grp(_SFX)}

    # coarse timeline (YAMNet hop ~0.48s); merge runs, drop <0.5s blips
    hop = 0.48
    frame_labels = [_coarse(names[int(r.argmax())]) for r in scores]
    timeline: list[dict] = []
    for i, lab in enumerate(frame_labels):
        t = round(i * hop, 2)
        if timeline and timeline[-1]["label"] == lab:
            timeline[-1]["end"] = round(t + hop, 2)
        else:
            timeline.append({"start": t, "end": round(t + hop, 2), "label": lab})
    timeline = [s for s in timeline if (s["end"] - s["start"]) >= 0.5] or timeline

    return {"top": top, "rollup": rollup, "timeline": timeline}
