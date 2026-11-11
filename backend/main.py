import asyncio
import json
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from analyzer import (
    compute_audio_energy_profile,
    download_audio_for_analysis,
    extract_youtube_id,
    fetch_transcript,
    fetch_video_info,
    select_top_viral_clips,
)
from renderer import JOBS_DIR, ensure_source_video, generate_srt, render_clip

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
VAR_TMP = Path("/var/tmp/viralclip_tmp")
VAR_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = str(VAR_TMP)
os.environ["TEMP"] = str(VAR_TMP)
os.environ["TMP"] = str(VAR_TMP)

app = FastAPI(title="ViralClip Studio API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


class AnalyzeRequest(BaseModel):
    url: str
    aspect_ratio: str = Field(default="9:16_crop")
    subtitle_style: str = Field(default="viral_pop")
    max_clips: int = Field(default=10, ge=1, le=10)


class RerenderRequest(BaseModel):
    aspect_ratio: Optional[str] = None
    subtitle_style: Optional[str] = None
    cues: Optional[List[Dict[str, Any]]] = None


def _safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return clean[:55] or "viral_clip"


def _prune_old_jobs(keep: int = 3) -> None:
    try:
        dirs = sorted(
            [d for d in JOBS_DIR.iterdir() if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in dirs[keep:]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        pass


def _public_job_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "step": job["step"],
        "step_message": job["step_message"],
        "progress": job["progress"],
        "error": job.get("error"),
        "video": job.get("video"),
        "heatmap": job.get("heatmap", []),
        "settings": job.get("settings"),
        "clips": [
            {
                k: v
                for k, v in c.items()
                if k not in ("_lock",)
            }
            for c in job.get("clips", [])
        ],
    }


def _update_job(job_id: str, **kwargs: Any) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)


def _ensure_clip_rendered(job: Dict[str, Any], clip: Dict[str, Any]) -> Path:
    lock: threading.Lock = clip["_lock"]
    with lock:
        if clip.get("render_status") == "ready" and clip.get("video_path") and Path(clip["video_path"]).exists():
            return Path(clip["video_path"])

        clip["render_status"] = "rendering"
        clip["render_error"] = None
        job_dir = Path(job["job_dir"])
        info = job["_info"]
        src_path = Path(job["_source_video"]) if job.get("_source_video") else None

        try:
            out_mp4 = render_clip(info, clip, job_dir, source_video=src_path)
            srt_path = job_dir / f"{clip['clip_id']}.srt"
            clip["video_path"] = str(out_mp4)
            clip["srt_path"] = str(srt_path)
            clip["render_status"] = "ready"
            clip["file_size_bytes"] = out_mp4.stat().st_size
            return out_mp4
        except Exception as exc:
            clip["render_status"] = "error"
            clip["render_error"] = str(exc)
            raise


def _run_pipeline(job_id: str) -> None:
    job = JOBS[job_id]
    url = job["url"]
    settings = job["settings"]
    job_dir = Path(job["job_dir"])

    try:
        _update_job(
            job_id,
            status="analyzing",
            step="fetching_info",
            step_message="Fetching YouTube metadata & audience replay heatmap...",
            progress=12,
        )
        info = fetch_video_info(url)
        job["_info"] = info

        # Extract compact heatmap for timeline visualization (60 buckets)
        raw_hm = info.get("heatmap") or []
        hm_points = [round(float(h.get("value", 0.0)), 3) for h in raw_hm]
        duration = float(info.get("duration") or 0)

        video_meta = {
            "id": info["_video_id"],
            "title": info.get("title") or "YouTube Video",
            "channel": info.get("channel") or info.get("uploader") or "Creator",
            "duration": duration,
            "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{info['_video_id']}/hqdefault.jpg",
            "view_count": info.get("view_count"),
            "has_heatmap": bool(raw_hm),
            "url": info["_canonical_url"],
        }
        _update_job(
            job_id,
            video=video_meta,
            heatmap=hm_points,
            step="extracting_transcript",
            step_message="Extracting timestamped speech & word-level subtitle timings...",
            progress=30,
        )

        # Download source media in parallel or ahead if <= 45 min so audio energy + clip rendering are super fast
        source_holder: Dict[str, Optional[Path]] = {"video": None}

        def _dl_source() -> None:
            source_holder["video"] = ensure_source_video(info)

        dl_thread = threading.Thread(target=_dl_source, daemon=True)
        dl_thread.start()

        def _prog_cb(msg: str) -> None:
            _update_job(job_id, step_message=msg)

        words, cues, lang = fetch_transcript(info, progress_cb=_prog_cb)

        _update_job(
            job_id,
            step="analyzing_virality",
            step_message="Preparing source stream & scanning vocal energy spikes...",
            progress=55,
        )
        dl_thread.join(timeout=240)
        src_video = source_holder["video"]
        if src_video:
            job["_source_video"] = str(src_video)

        energy_media = src_video
        if not energy_media:
            energy_media = download_audio_for_analysis(info)
        energy_curve = compute_audio_energy_profile(energy_media, duration)

        _update_job(
            job_id,
            step="scoring_clips",
            step_message="Ranking Top 10 viral moments (<60s), scoring & generating titles/tags...",
            progress=76,
        )

        plans = select_top_viral_clips(
            info=info,
            words=words,
            cues=cues,
            energy_curve=energy_curve,
            lang=lang,
            max_clips=settings["max_clips"],
            aspect_ratio=settings["aspect_ratio"],
            subtitle_style=settings["subtitle_style"],
        )

        clip_dicts: List[Dict[str, Any]] = []
        for p in plans:
            d = asdict(p)
            d["_lock"] = threading.Lock()
            # Pre-generate SRT right away
            srt_p = job_dir / f"{d['clip_id']}.srt"
            generate_srt(d["cues"], srt_p)
            d["srt_path"] = str(srt_p)
            clip_dicts.append(d)

        _update_job(
            job_id,
            clips=clip_dicts,
            status="rendering",
            step="rendering_clips",
            step_message=f"Top {len(clip_dicts)} viral clips found! Rendering burned-in subtitles (0/{len(clip_dicts)})...",
            progress=82,
        )

        total_c = max(1, len(clip_dicts))
        for idx, clip in enumerate(clip_dicts, start=1):
            try:
                _ensure_clip_rendered(job, clip)
            except Exception:
                pass
            ready_cnt = sum(1 for c in clip_dicts if c.get("render_status") == "ready")
            pct = 82 + int((idx / total_c) * 18)
            _update_job(
                job_id,
                step_message=f"Rendered {ready_cnt}/{total_c} subtitled clips ready for instant download",
                progress=min(99, pct),
            )

        _update_job(
            job_id,
            status="completed",
            step="done",
            step_message=f"All {len(clip_dicts)} viral clips ready!",
            progress=100,
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="error",
            step="error",
            step_message=str(exc),
            error=str(exc),
        )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
def start_analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    try:
        extract_youtube_id(req.url)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    _prune_old_jobs()
    job_id = uuid.uuid4().hex[:10]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    with JOBS_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "url": req.url.strip(),
            "job_dir": str(job_dir),
            "status": "queued",
            "step": "queued",
            "step_message": "Starting ViralClip analysis...",
            "progress": 5,
            "error": None,
            "video": None,
            "heatmap": [],
            "settings": {
                "aspect_ratio": req.aspect_ratio,
                "subtitle_style": req.subtitle_style,
                "max_clips": req.max_clips,
            },
            "clips": [],
            "created_at": time.time(),
        }

    t = threading.Thread(target=_run_pipeline, args=(job_id,), daemon=True)
    t.start()
    return {"job_id": job_id}


def _get_job_or_404(job_id: str) -> Dict[str, Any]:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")
    return job


def _get_clip_or_404(job: Dict[str, Any], clip_id: str) -> Dict[str, Any]:
    for c in job.get("clips", []):
        if c["clip_id"] == clip_id:
            return c
    raise HTTPException(status_code=404, detail="Clip not found.")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = _get_job_or_404(job_id)
    return _public_job_snapshot(job)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    _get_job_or_404(job_id)

    async def event_stream():
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            job = JOBS.get(job_id)
            if not job:
                break
            snap = json.dumps(_public_job_snapshot(job))
            if snap != last_payload:
                yield f"data: {snap}\n\n"
                last_payload = snap
            if job["status"] in ("completed", "error"):
                break
            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/clips/{clip_id}/video")
def stream_clip_video(job_id: str, clip_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    clip = _get_clip_or_404(job, clip_id)
    mp4_path = _ensure_clip_rendered(job, clip)
    return FileResponse(mp4_path, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/clips/{clip_id}/download")
def download_clip_mp4(job_id: str, clip_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    clip = _get_clip_or_404(job, clip_id)
    mp4_path = _ensure_clip_rendered(job, clip)
    fname = f"Top{clip['rank']:02d}_Score{clip['virality_score']}_{_safe_filename(clip['title'])}.mp4"
    return FileResponse(
        mp4_path,
        media_type="video/mp4",
        filename=fname,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.get("/api/jobs/{job_id}/clips/{clip_id}/srt")
def download_clip_srt(job_id: str, clip_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    clip = _get_clip_or_404(job, clip_id)
    srt_path = Path(job["job_dir"]) / f"{clip_id}.srt"
    if not srt_path.exists():
        generate_srt(clip["cues"], srt_path)
    fname = f"Top{clip['rank']:02d}_{_safe_filename(clip['title'])}.srt"
    return FileResponse(
        srt_path,
        media_type="application/x-subrip",
        filename=fname,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.post("/api/jobs/{job_id}/clips/{clip_id}/rerender")
def rerender_clip(job_id: str, clip_id: str, req: RerenderRequest) -> Dict[str, Any]:
    job = _get_job_or_404(job_id)
    clip = _get_clip_or_404(job, clip_id)

    lock: threading.Lock = clip["_lock"]
    with lock:
        if req.aspect_ratio:
            clip["aspect_ratio"] = req.aspect_ratio
        if req.subtitle_style:
            clip["subtitle_style"] = req.subtitle_style
        if req.cues is not None:
            # Update edited cues cleanly while preserving word timing proportionally if text changed
            updated_cues = []
            for c in req.cues:
                txt = str(c.get("text", "")).strip()
                st = float(c.get("start", 0))
                et = float(c.get("end", st + 1.0))
                if not txt:
                    continue
                tokens = txt.split()
                dur = max(0.2, et - st)
                total_ch = sum(max(1, len(tk)) for tk in tokens)
                cur = st
                w_list = []
                for tk in tokens:
                    wd = max(0.06, dur * (max(1, len(tk)) / total_ch))
                    w_list.append({"text": tk, "start": round(cur, 3), "end": round(cur + wd, 3)})
                    cur += wd
                updated_cues.append({"start": st, "end": et, "text": txt, "words": w_list})
            clip["cues"] = updated_cues
            clip["transcript_text"] = " ".join(c["text"] for c in updated_cues)
        clip["render_status"] = "pending"

    _ensure_clip_rendered(job, clip)
    return {k: v for k, v in clip.items() if k != "_lock"}


@app.get("/api/jobs/{job_id}/download-all")
def download_all_zip(job_id: str) -> FileResponse:
    job = _get_job_or_404(job_id)
    clips = job.get("clips") or []
    if not clips:
        raise HTTPException(status_code=400, detail="No clips available yet.")

    job_dir = Path(job["job_dir"])
    zip_path = job_dir / f"ViralClips_{job_id}.zip"
    meta_lines = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for clip in clips:
            try:
                mp4_path = _ensure_clip_rendered(job, clip)
                mp4_name = f"Top{clip['rank']:02d}_Score{clip['virality_score']}_{_safe_filename(clip['title'])}.mp4"
                zf.write(mp4_path, arcname=mp4_name)
                srt_path = Path(clip["srt_path"])
                if srt_path.exists():
                    zf.write(srt_path, arcname=mp4_name.replace(".mp4", ".srt"))
            except Exception:
                pass
            meta_lines.append(
                f"=== #{clip['rank']} | Score: {clip['virality_score']}/100 | Duration: {clip['duration']}s ({clip['start']}s - {clip['end']}s) ===\n"
                f"Title: {clip['title']}\n"
                f"Tags: {', '.join(clip['tags'])}\n"
                f"Description:\n{clip['description']}\n"
                f"Why Viral: {clip['why_viral']}\n"
            )
        zf.writestr("ALL_TITLES_TAGS_DESCRIPTIONS.txt", "\n\n".join(meta_lines))

    vid_title = _safe_filename((job.get("video") or {}).get("title") or "YouTube_Clips")
    out_name = f"Top10_ViralClips_{vid_title}.zip"
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=out_name,
        headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
    )


if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")


@app.get("/{full_path:path}")
def serve_spa(full_path: str) -> Any:
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    candidate = STATIC_DIR / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    index_file = STATIC_DIR / "index.html"
    if index_file.is_file():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>ViralClip Studio backend running — build frontend to populate UI.</h1>")
