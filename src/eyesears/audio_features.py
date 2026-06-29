"""Free, local audio analysis (numpy only) — the 'hears music' layer.

Reads the extracted mono WAV and returns signal-based structure: tempo, energy curve,
onset 'hits', loudness dynamics, brightness, and a rough music-vs-speech estimate.
Reliable for energy/onsets/tempo; music-likelihood and genre/mood are approximate
(genre/mood/song-ID would need a small audio model — not done here).
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"unsupported sample width: {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def profile(path: str | Path, n_buckets: int = 12, max_onsets: int = 40) -> dict:
    try:
        x, sr = _read_wav_mono(Path(path))
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not read audio: {e}"}
    if x.size == 0:
        return {"error": "empty audio"}

    hop = max(1, int(0.05 * sr))  # 50 ms frames
    n = x.size // hop
    if n < 4:
        return {"error": "audio too short to profile"}
    frames = x[: n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    times = np.arange(n) * hop / sr
    dur = x.size / sr
    fps = sr / hop  # analysis frames per second

    db = 20 * np.log10(rms + 1e-6)
    rms_max = float(rms.max()) or 1.0

    # energy curve (normalised 0-1 buckets)
    edges = np.linspace(0, n, n_buckets + 1).astype(int)
    curve = []
    for i in range(n_buckets):
        a, b = edges[i], max(edges[i] + 1, edges[i + 1])
        seg = rms[a:b]
        curve.append({"t": round(float(times[a]), 2),
                      "level": round(float(seg.mean() / rms_max), 2) if seg.size else 0.0})

    # smoothed peak / trough / trend
    k = max(1, n // 50)
    sm = np.convolve(rms, np.ones(k) / k, mode="same")
    third = max(1, n // 3)
    rel = float(sm[-third:].mean() - sm[:third].mean()) / (rms_max + 1e-9)
    trend = "builds" if rel > 0.08 else "fades" if rel < -0.08 else "steady"
    dyn_db = round(float(db.max() - np.percentile(db, 5)), 1)

    # onsets: positive jumps in the energy envelope
    denv = np.diff(rms, prepend=rms[0])
    denv[denv < 0] = 0
    if denv.max() > 0:
        denv = denv / denv.max()
    thr = float(denv.mean() + 1.5 * denv.std())
    min_gap = max(1, int(0.12 * fps))
    onsets, last = [], -(10**9)
    for i in range(1, n - 1):
        if denv[i] > thr and denv[i] >= denv[i - 1] and denv[i] >= denv[i + 1] and i - last >= min_gap:
            onsets.append(i)
            last = i
    onset_times = [round(float(times[i]), 2) for i in onsets]

    # tempo via autocorrelation of the onset envelope (60-200 BPM window)
    bpm = None
    if denv.std() > 0 and n > int(fps):
        env = denv - denv.mean()
        ac = np.correlate(env, env, mode="full")[n - 1:]
        lo, hi = int(fps * 60 / 200), int(fps * 60 / 60)
        if 0 < lo < hi < len(ac):
            lag = lo + int(np.argmax(ac[lo:hi]))
            if lag > 0:
                bpm = int(round(60 * fps / lag))

    # brightness via spectral centroid (voiced frames only)
    win = np.hanning(hop)
    freqs = np.fft.rfftfreq(hop, d=1.0 / sr)
    voiced = rms > (0.1 * np.median(rms) + 1e-9)
    cents = []
    for i in np.nonzero(voiced)[0]:
        mag = np.abs(np.fft.rfft(frames[i] * win))
        s = float(mag.sum())
        if s > 0:
            cents.append(float((freqs * mag).sum() / s))
    centroid = round(float(np.mean(cents))) if cents else 0
    brightness = "bright" if centroid > 3000 else "mellow" if 0 < centroid < 1200 else "neutral"

    # music vs speech proxy: speech has frequent pauses; a music bed is continuous
    silence_ratio = round(float((rms < (0.15 * np.median(rms) + 1e-9)).mean()), 2)
    continuous = silence_ratio < 0.18
    if continuous and onset_times and bpm:
        music = "high"
    elif continuous:
        music = "medium"
    else:
        music = "low"

    return {
        "duration_s": round(dur, 2),
        "tempo_bpm_estimate": bpm,
        "energy_trend": trend,
        "energy_peak_s": round(float(times[int(np.argmax(sm))]), 2),
        "energy_trough_s": round(float(times[int(np.argmin(sm))]), 2),
        "loudness_dynamic_range_db": dyn_db,
        "energy_curve": curve,
        "onset_count": len(onset_times),
        "onset_times_s": onset_times[:max_onsets],
        "brightness": brightness,
        "spectral_centroid_hz": centroid,
        "silence_ratio": silence_ratio,
        "continuous_audio_bed": continuous,
        "music_likelihood": music,
        "note": ("signal-based heuristics (free, local). energy/onsets/tempo reliable; "
                 "music-vs-speech approximate; no genre/mood/song-ID."),
    }
