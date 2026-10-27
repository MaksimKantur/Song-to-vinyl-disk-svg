"""HTTP API. Run from the project root: uvicorn backend.app:app --reload"""

import shutil
import tempfile
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .audio import Analysis, AudioError, analyze, decode, read_title
from .render import Params, RenderError, render

MAX_CACHED = 4
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@dataclass
class Track:
    name: str
    title: str
    analysis: Analysis


_tracks: OrderedDict[str, Track] = OrderedDict()
_lock = threading.Lock()

app = FastAPI(title="song-to-svg")


@app.post("/api/upload")
def upload(file: UploadFile = File(...)):
    name = file.filename or "audio"
    with tempfile.NamedTemporaryFile(suffix=Path(name).suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp.flush()
        try:
            samples = decode(Path(tmp.name))
        except AudioError as e:
            raise HTTPException(400, f"Не удалось прочитать аудио: {e}")
        title = read_title(Path(tmp.name)) or Path(name).stem
    track = Track(name=name, title=title, analysis=analyze(samples))
    track_id = uuid.uuid4().hex
    with _lock:
        _tracks[track_id] = track
        while len(_tracks) > MAX_CACHED:
            _tracks.popitem(last=False)
    return {"id": track_id, "name": name, "title": title, "duration": track.analysis.duration}


class RenderRequest(BaseModel):
    id: str
    params: Params


@app.post("/api/render")
def render_svg(req: RenderRequest):
    with _lock:
        track = _tracks.get(req.id)
    if track is None:
        raise HTTPException(404, "Трек не найден, загрузи файл заново")
    try:
        svg = render(track.analysis, req.params)
    except RenderError as e:
        raise HTTPException(400, str(e))
    return Response(svg, media_type="image/svg+xml")


@app.get("/api/defaults")
def defaults():
    return Params().model_dump()


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
