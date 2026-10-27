"""Spectrogram -> printable SVG.

Everything is laid out on "tracks": a polar disc is one circular track per
frequency band, a spiral is a single track winding inwards. A track is cut
into cells along its angle, each cell carries a 0..1 darkness value, and an
encoding turns those values into marks (fills, strokes or dots).
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator, Literal
from xml.sax.saxutils import escape

import numpy as np
from pydantic import BaseModel, Field

from .audio import Analysis, SR, band_grid, to_levels

TAU = 2 * math.pi
PAPER_MM = {"A3": (297.0, 420.0), "A2": (420.0, 594.0)}
SPIRAL_STEP = math.radians(1.0)  # max angle between polyline points on a spiral


class Params(BaseModel):
    mode: Literal["polar", "spiral"] = "polar"
    encoding: Literal["gray", "width", "threshold", "dots", "hatch", "wiggle"] = "threshold"
    # fragment, seconds
    start: float = Field(0, ge=0)
    end: float | None = Field(None, ge=0)
    # polar
    rings: int = Field(96, ge=4, le=400)
    segments: int = Field(480, ge=16, le=2000)
    gap_deg: float = Field(4, ge=0, le=90)
    bass_center: bool = True
    # spiral
    turns: int = Field(40, ge=1, le=300)
    cell_mm: float = Field(1.5, ge=0.2, le=20)  # length of one time cell along the groove
    # spectrum -> darkness
    fmin: float = Field(40, ge=10, le=4000)
    fmax: float = Field(12000, ge=200, le=SR / 2)
    range_db: float = Field(45, ge=6, le=120)
    gamma: float = Field(1.0, ge=0.2, le=5)
    tilt_db_oct: float = Field(3, ge=-6, le=12)
    invert: bool = False
    # marks
    fill: float = Field(0.85, ge=0.05, le=1)  # share of the track pitch a mark may use
    threshold: float = Field(0.5, ge=0, le=1)
    levels: int = Field(12, ge=2, le=64)
    lines: int = Field(4, ge=1, le=12)
    pen_mm: float = Field(0.3, ge=0.02, le=3)
    # sheet
    paper: Literal["A3", "A2"] = "A2"
    landscape: bool = False
    margin_mm: float = Field(25, ge=0, le=150)
    hole_mm: float = Field(8, ge=0, le=100)  # radius of the empty centre
    outline: bool = True
    mirror: bool = False
    title: str = ""
    title_size_mm: float = Field(6, ge=1, le=40)


class RenderError(ValueError):
    pass


@dataclass
class Track:
    r0: float  # centre-line radius at angle 0
    dr: float  # radius change per radian (0 for circular rings)
    pitch: float
    bounds: np.ndarray  # (cells + 1,) cell boundary angles
    values: np.ndarray  # (cells,)

    def r(self, theta):
        return self.r0 + self.dr * theta

    def theta(self, cell):
        """Angle at a (fractional) cell index."""
        return np.interp(cell, np.arange(len(self.bounds)), self.bounds)


class Canvas:
    """Path-data helpers. Angles run clockwise from 12 o'clock."""

    def __init__(self, cx: float, cy: float):
        self.cx, self.cy = cx, cy

    def xy(self, r: float, theta: float) -> str:
        return f"{self.cx + r * math.sin(theta):.2f},{self.cy - r * math.cos(theta):.2f}"

    def _edge(self, t: Track, a: float, b: float, off: float) -> str:
        """Curve from angle a to b at `off` from the centre line; pen already at its start."""
        if t.dr == 0:
            r = max(t.r0 + off, 0.0)
            n = max(1, math.ceil(abs(b - a) / (math.pi / 2)))
            sweep = 1 if b > a else 0
            return "".join(
                f"A{r:.2f},{r:.2f} 0 0 {sweep} {self.xy(r, a + (b - a) * k / n)}" for k in range(1, n + 1)
            )
        n = max(1, math.ceil(abs(b - a) / SPIRAL_STEP))
        return "".join(
            "L" + self.xy(t.r(a + (b - a) * k / n) + off, a + (b - a) * k / n) for k in range(1, n + 1)
        )

    def band(self, t: Track, a: float, b: float, lo: float, hi: float) -> str:
        return (
            f"M{self.xy(t.r(a) + hi, a)}{self._edge(t, a, b, hi)}"
            f"L{self.xy(t.r(b) + lo, b)}{self._edge(t, b, a, lo)}Z"
        )

    def line(self, t: Track, a: float, b: float, off: float) -> str:
        return f"M{self.xy(t.r(a) + off, a)}{self._edge(t, a, b, off)}"

    def polyline(self, t: Track, thetas: np.ndarray, offs: np.ndarray) -> str:
        pts = [self.xy(t.r(th) + o, th) for th, o in zip(thetas, offs)]
        return "M" + "L".join(pts)

    def ribbon(self, t: Track, thetas: np.ndarray, half: np.ndarray) -> str:
        outer = [self.xy(t.r(th) + h, th) for th, h in zip(thetas, half)]
        inner = [self.xy(t.r(th) - h, th) for th, h in zip(thetas[::-1], half[::-1])]
        return "M" + "L".join(outer + inner) + "Z"

    def dot(self, t: Track, theta: float, rad: float) -> str:
        r = t.r(theta)
        x, y = self.cx + r * math.sin(theta), self.cy - r * math.cos(theta)
        return f"M{x - rad:.2f},{y:.2f}a{rad:.2f},{rad:.2f} 0 1 0 {2 * rad:.2f},0a{rad:.2f},{rad:.2f} 0 1 0 {-2 * rad:.2f},0Z"


MAX_RUN_CELLS = 3000
MAX_RUN_ANGLE = 10 * TAU  # spiral edges are sampled every SPIRAL_STEP


def _runs(mask: np.ndarray, t: Track) -> Iterator[tuple[int, int]]:
    """(start, end) of each stretch of True, cut so no single subpath gets huge."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    for s, e in zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()):
        while s < e:
            stop = min(e, s + MAX_RUN_CELLS, int(np.searchsorted(t.bounds, t.bounds[s] + MAX_RUN_ANGLE)) - 1)
            stop = max(stop, s + 1)
            yield s, stop
            s = stop


FILL = "fill:#000"
STROKE = "stroke"  # placeholder key; resolved with the pen width


def _encode(enc: str, c: Canvas, tracks: list[Track], p: Params) -> dict[str, list[str]]:
    """Path data grouped by style key."""
    out: dict[str, list[str]] = defaultdict(list)
    for t in tracks:
        v, half = t.values, p.fill * t.pitch / 2
        if enc == "gray":
            q = np.round(v * p.levels).astype(int)
            for level in range(1, p.levels + 1):
                g = round(255 * (1 - level / p.levels))
                for s, e in _runs(q == level):
                    out[f"fill:#{g:02x}{g:02x}{g:02x}"].append(c.band(t, t.theta(s), t.theta(e), -half, half))
        elif enc == "threshold":
            for s, e in _runs(v > p.threshold):
                out[FILL].append(c.band(t, t.theta(s), t.theta(e), -half, half))
        elif enc == "width":
            for s, e in _runs(v > 0.02):
                thetas = np.concatenate([[t.theta(s)], t.theta(np.arange(s, e) + 0.5), [t.theta(e)]])
                vals = np.concatenate([[v[s]], v[s:e], [v[e - 1]]])
                out[FILL].append(c.ribbon(t, thetas, half * vals))
        elif enc == "dots":
            for i in np.flatnonzero(v > 0.01):
                th = t.theta(i + 0.5)
                cell = min(t.pitch, t.r(th) * (t.bounds[i + 1] - t.bounds[i]))
                rad = 0.5 * cell * p.fill * math.sqrt(v[i])
                if rad >= 0.02:
                    out[FILL].append(c.dot(t, th, rad))
        elif enc == "hatch":
            # Lines fill the track from its centre line outwards as the value grows.
            offs = -half + (np.arange(p.lines) + 0.5) * 2 * half / p.lines
            count = np.round(v * p.lines)
            for rank, li in enumerate(np.argsort(np.abs(offs), kind="stable")):
                for s, e in _runs(count > rank):
                    out[STROKE].append(c.line(t, t.theta(s), t.theta(e), offs[li]))
        elif enc == "wiggle":
            n = len(v)
            thetas = np.concatenate([[t.theta(0)], t.theta(np.arange(n) + 0.5), [t.theta(n)]])
            sign = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
            offs = np.concatenate([[0.0], half * v * sign, [0.0]])
            out[STROKE].append(c.polyline(t, thetas, offs))
    return out


def _tracks(a: Analysis, p: Params, r_in: float, r_out: float) -> list[Track]:
    t0 = p.start
    t1 = a.duration if p.end is None else min(p.end, a.duration)
    if t1 - t0 < 0.5:
        raise RenderError("Фрагмент слишком короткий (меньше 0.5 с)")
    if p.fmax <= p.fmin:
        raise RenderError("fmax должна быть больше fmin")

    if p.mode == "polar":
        edges = np.geomspace(p.fmin, p.fmax, p.rings + 1)
        centres = np.sqrt(edges[:-1] * edges[1:])
        v = to_levels(band_grid(a, t0, t1, p.segments, edges), centres, p.range_db, p.gamma, p.tilt_db_oct)
        if p.invert:
            v = 1 - v
        pitch = (r_out - r_in) / p.rings
        gap = math.radians(p.gap_deg)
        bounds = np.linspace(gap / 2, TAU - gap / 2, p.segments + 1)
        return [
            Track(
                r0=r_in + pitch * (i + 0.5), dr=0.0, pitch=pitch, bounds=bounds,
                values=v[:, i if p.bass_center else p.rings - 1 - i],
            )
            for i in range(p.rings)
        ]

    # Spiral: overall loudness along one groove from the rim inwards, like a
    # record. Cells have equal length along the groove so inner turns don't
    # get denser than outer ones.
    pitch = (r_out - r_in) / p.turns
    r0, dr = r_out - pitch / 2, -pitch / TAU
    fine = np.linspace(0, TAU * p.turns, p.turns * 720 + 1)
    length = r0 * fine + dr * fine ** 2 / 2
    n = min(max(16, round(length[-1] / p.cell_mm)), 200_000)
    bounds = np.interp(np.linspace(0, length[-1], n + 1), length, fine)

    edges = np.array([p.fmin, p.fmax])
    v = to_levels(band_grid(a, t0, t1, n, edges), np.array([1000.0]), p.range_db, p.gamma, 0.0)[:, 0]
    if p.invert:
        v = 1 - v
    return [Track(r0=r0, dr=dr, pitch=pitch, bounds=bounds, values=v)]


def render(a: Analysis, p: Params) -> str:
    w, h = PAPER_MM[p.paper]
    if p.landscape:
        w, h = h, w
    title = p.title.strip()
    title_zone = p.title_size_mm * 3 if title else 0.0
    avail_h = h - 2 * p.margin_mm - title_zone
    r_out = min(w - 2 * p.margin_mm, avail_h) / 2
    if r_out <= p.hole_mm + 5:
        raise RenderError("Диск не помещается: уменьши поля, отверстие или подпись")
    cx, cy = w / 2, p.margin_mm + avail_h / 2
    canvas = Canvas(cx, cy)

    groups = _encode(p.encoding, canvas, _tracks(a, p, p.hole_mm, r_out), p)
    stroke = (
        f'fill="none" stroke="#000" stroke-width="{p.pen_mm:g}" stroke-linecap="round" stroke-linejoin="round"'
    )
    art = []
    for key, paths in groups.items():
        style = stroke if key == STROKE else f'fill="{key.removeprefix("fill:")}" stroke="none"'
        art.extend(f'<path {style} d="{d}"/>' for d in _split(paths))

    layers = [_layer("art", "\n".join(art))]
    if p.outline:
        circles = [f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r_out:.2f}"/>']
        if p.hole_mm > 0:
            circles.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{p.hole_mm:.2f}"/>')
        layers.append(_layer("outline", f'<g {stroke}>{"".join(circles)}</g>'))
    if title:
        ty = cy + r_out + p.title_size_mm * 1.8
        layers.append(_layer(
            "title",
            f'<text x="{cx:.2f}" y="{ty:.2f}" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="{p.title_size_mm:g}" text-anchor="middle" fill="#000">{escape(title)}</text>',
        ))

    body = "\n".join(layers)
    if p.mirror:
        body = f'<g transform="translate({w:g},0) scale(-1,1)">\n{body}\n</g>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{w:g}mm" height="{h:g}mm" viewBox="0 0 {w:g} {h:g}">\n{body}\n</svg>\n'
    )


MAX_PATH_ELEMENTS = 8000


def _split(paths: list[str]) -> Iterator[str]:
    """Join subpaths into <path> data, several paths if needed.

    Qt SVG (Gwenview, Okular, KDE previews) silently drops a whole path with
    more than ~32k elements; an arc counts as a few cubic curves there.
    """
    chunk, size = [], 0
    for d in paths:
        cost = d.count("M") + d.count("L") + d.count("Z") + 3 * (d.count("A") + 2 * d.count("a"))
        if chunk and size + cost > MAX_PATH_ELEMENTS:
            yield "".join(chunk)
            chunk, size = [], 0
        chunk.append(d)
        size += cost
    if chunk:
        yield "".join(chunk)


def _layer(name: str, content: str) -> str:
    return f'<g id="{name}" inkscape:groupmode="layer" inkscape:label="{name}">\n{content}\n</g>'
