"""Audio decoding and spectral analysis."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SR = 32000
N_FFT = 4096
HOP = 1024


class AudioError(Exception):
    pass


@dataclass
class Analysis:
    power: np.ndarray  # (frames, bins) power spectrum
    freqs: np.ndarray  # (bins,) Hz
    frame_times: np.ndarray  # (frames,) seconds, frame centres
    duration: float


def decode(path: Path) -> np.ndarray:
    """Decode any ffmpeg-readable file to mono float32 at SR."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise AudioError(proc.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    if samples.size < N_FFT:
        raise AudioError("Audio is too short or empty")
    return samples


def read_title(path: Path) -> str | None:
    """'Artist — Title' from file tags, if present."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format_tags=title,artist", "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        return None
    tags = {k.lower(): v for k, v in json.loads(proc.stdout or "{}").get("format", {}).get("tags", {}).items()}
    title, artist = tags.get("title"), tags.get("artist")
    if title and artist:
        return f"{artist} — {title}"
    return title


def analyze(samples: np.ndarray) -> Analysis:
    window = np.hanning(N_FFT).astype(np.float32)
    padded = np.pad(samples, (N_FFT // 2, N_FFT // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP]
    power = np.empty((len(frames), N_FFT // 2 + 1), dtype=np.float32)
    chunk = 256
    for start in range(0, len(frames), chunk):
        spec = np.fft.rfft(frames[start:start + chunk] * window, axis=1)
        power[start:start + chunk] = spec.real ** 2 + spec.imag ** 2
    return Analysis(
        power=power,
        freqs=np.fft.rfftfreq(N_FFT, 1 / SR),
        frame_times=np.arange(len(frames)) * HOP / SR,
        duration=samples.size / SR,
    )


def _filterbank(freqs: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """(bins, bands) weights averaging the power inside each band.

    Bands narrower than one FFT bin (low end of a log scale) interpolate
    between the two nearest bins instead of coming out empty.
    """
    n_bands = len(edges) - 1
    weights = np.zeros((len(freqs), n_bands), dtype=np.float32)
    bin_hz = freqs[1] - freqs[0]
    for b in range(n_bands):
        lo, hi = edges[b], edges[b + 1]
        inside = (freqs >= lo) & (freqs < hi)
        if inside.any():
            weights[inside, b] = 1.0 / inside.sum()
        else:
            pos = np.sqrt(lo * hi) / bin_hz
            i = min(int(pos), len(freqs) - 2)
            frac = pos - i
            weights[i, b] = 1 - frac
            weights[i + 1, b] = frac
    return weights


def band_grid(
    a: Analysis, t0: float, t1: float, n_time: int, edges: np.ndarray
) -> np.ndarray:
    """Mean band power on a (n_time, n_bands) grid over [t0, t1)."""
    band_power = a.power @ _filterbank(a.freqs, edges)  # (frames, bands)
    cum = np.vstack([np.zeros((1, band_power.shape[1])), np.cumsum(band_power, axis=0, dtype=np.float64)])
    bounds = np.linspace(t0, t1, n_time + 1)
    start = np.searchsorted(a.frame_times, bounds[:-1])
    end = np.searchsorted(a.frame_times, bounds[1:])
    # Cells shorter than a hop still get the nearest frame.
    start = np.clip(start, 0, len(a.frame_times) - 1)
    end = np.maximum(end, start + 1)
    return (cum[end] - cum[start]) / (end - start)[:, None]


def to_levels(
    power: np.ndarray, centres: np.ndarray, range_db: float, gamma: float, tilt_db_oct: float
) -> np.ndarray:
    """Map band power to 0..1 darkness.

    tilt_db_oct boosts highs relative to 1 kHz so the outer rings are not
    empty (music energy falls off with frequency).
    """
    db = 10 * np.log10(power + 1e-12) + tilt_db_oct * np.log2(centres / 1000.0)
    top = np.percentile(db, 99.5)
    # A compressed signal (e.g. overall loudness) spans far less than range_db;
    # don't waste the scale on levels that never occur.
    floor = max(top - range_db, np.percentile(db, 2))
    return np.clip((db - floor) / max(top - floor, 1e-6), 0, 1) ** gamma
