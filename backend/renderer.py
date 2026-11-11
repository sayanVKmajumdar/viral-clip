import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from analyzer import resolve_cookies_file, ytdlp_base_args

CACHE_DIR = Path("/var/tmp/viralclip_cache")
JOBS_DIR = Path("/var/tmp/viralclip_jobs")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _prune_cache(max_bytes: int = 1_200_000_000) -> None:
    # Remove any leftover incomplete .part files first
    for part in CACHE_DIR.glob("*.part"):
        try:
            part.unlink()
        except OSError:
            pass
    files = [p for p in CACHE_DIR.glob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    if total <= max_bytes:
        return
    files.sort(key=lambda p: p.stat().st_mtime)
    for p in files:
        if total <= max_bytes * 0.65:
            break
        sz = p.stat().st_size
        try:
            p.unlink()
            total -= sz
        except OSError:
            pass


def ensure_source_video(info: Dict[str, Any]) -> Optional[Path]:
    """Download lightweight H.264 MP4 once for videos <= 45 min. For longer videos, use section downloads."""
    duration = float(info.get("duration") or 0)
    if duration > 2700:
        return None
    vid = info["_video_id"]
    out_path = CACHE_DIR / f"{vid}_720p.mp4"
    if out_path.exists() and out_path.stat().st_size > 10_000:
        os.utime(out_path, None)
        return out_path

    _prune_cache()
    tmp_tmpl = str(CACHE_DIR / f"{vid}_720p.%(ext)s")
    if duration > 900:
        # For 15-45 min videos, avoid huge 60fps 750MB+ files; prefer 720p<=30fps or 480p30
        fmt = (
            "bv*[vcodec^=avc1][height<=720][fps<=30][filesize<350M]+ba[acodec^=mp4a]/"
            "bv*[vcodec^=avc1][height<=480][fps<=30]+ba[acodec^=mp4a]/"
            "bv*[vcodec^=avc1][height<=720][fps<=30]+ba[acodec^=mp4a]/"
            "b[height<=480][ext=mp4]/b[height<=720][ext=mp4]/b[ext=mp4]/b"
        )
    else:
        fmt = (
            "bv*[vcodec^=avc1][height<=720]+ba[acodec^=mp4a]/"
            "bv*[height<=720]+ba/b[height<=720][ext=mp4]/b[height<=720]/b[ext=mp4]/b"
        )

    has_cookies = resolve_cookies_file() is not None
    tried: List[Optional[str]] = [info.get("_player_client")]
    for fb in ("android_vr", "android"):
        if fb not in tried:
            tried.append(fb)

    for client in tried:
        use_cookies = has_cookies and client not in ("android_vr", "android", "ios")
        cmd = [
            *ytdlp_base_args(player_client=client, allow_cookies=use_cookies),
            "-f", fmt,
            "--merge-output-format", "mp4",
            "-o", tmp_tmpl,
            "--no-playlist",
            "--no-warnings",
            info["_canonical_url"],
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        # Clean any partial files if download failed
        for part in CACHE_DIR.glob(f"{vid}*.part"):
            try:
                part.unlink()
            except OSError:
                pass
        if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 10_000:
            return out_path
    return None


def _detect_font(text: str) -> str:
    if re.search(r"[\u0980-\u09FF]", text):
        return "Noto Sans Bengali"
    if re.search(r"[\u0900-\u097F]", text):
        return "Noto Sans Devanagari"
    if re.search(r"[\u0600-\u06FF]", text):
        return "Noto Sans Arabic"
    return "Noto Sans"


def _fmt_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _fmt_srt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _esc_ass(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def generate_srt(cues: List[Dict[str, Any]], out_path: Path) -> Path:
    lines: List[str] = []
    for idx, cue in enumerate(cues, start=1):
        st = _fmt_srt_time(float(cue["start"]))
        et = _fmt_srt_time(float(cue["end"]))
        txt = str(cue["text"]).strip()
        if not txt:
            continue
        lines.append(f"{idx}\n{st} --> {et}\n{txt}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def generate_ass_subtitles(
    cues: List[Dict[str, Any]],
    out_path: Path,
    style: str = "viral_pop",
    aspect_ratio: str = "9:16_crop",
    full_text: str = "",
) -> Path:
    is_landscape = aspect_ratio == "16:9_original"
    play_x = 1280 if is_landscape else 720
    play_y = 720 if is_landscape else 1280
    font_name = _detect_font(full_text or " ".join(str(c.get("text", "")) for c in cues))

    if style == "clean_minimal":
        font_size = 40 if is_landscape else 44
        margin_v = 48 if is_landscape else 190
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H00FFFFFF,&HBA11131B,&HBA11131B,-1,0,0,0,100,100,0,0,3,10,0,2,48,48,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for cue in cues:
            st = _fmt_ass_time(float(cue["start"]))
            et = _fmt_ass_time(float(cue["end"]))
            txt = _esc_ass(str(cue["text"]).strip())
            if txt:
                events.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{txt}")
        out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
        return out_path

    # viral_pop or neon_cyber -> active word-by-word highlight!
    is_neon = style == "neon_cyber"
    font_size = 46 if is_landscape else 52
    margin_v = 54 if is_landscape else 205
    highlight_bgr = "&H00FFF000&" if is_neon else "&H0000EAFF&"   # Neon Cyan vs Viral Gold-Yellow
    outline_bgr = "&H002A082A&" if is_neon else "&H00000000&"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_x}
PlayResY: {play_y}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000EAFF,{outline_bgr},&H96000000,-1,0,0,0,100,100,0,0,1,4,2,2,42,42,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    for cue in cues:
        cue_words = cue.get("words") or []
        if not cue_words:
            st = _fmt_ass_time(float(cue["start"]))
            et = _fmt_ass_time(float(cue["end"]))
            txt = _esc_ass(str(cue["text"]).strip())
            if is_neon:
                txt = txt.upper()
            if txt:
                events.append(f"Dialogue: 0,{st},{et},Default,,0,0,0,,{txt}")
            continue

        cue_end = float(cue["end"])
        for wi, w in enumerate(cue_words):
            ws = float(w["start"])
            we = float(cue_words[wi + 1]["start"]) if wi + 1 < len(cue_words) else max(float(w["end"]), cue_end)
            if we <= ws:
                we = ws + 0.1
            parts: List[str] = []
            for idx2, w2 in enumerate(cue_words):
                wt = _esc_ass(str(w2["text"]))
                if is_neon:
                    wt = wt.upper()
                if idx2 == wi:
                    parts.append(f"{{\\c{highlight_bgr}\\fscx108\\fscy108}}{wt}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                else:
                    parts.append(wt)
            line = " ".join(parts)
            events.append(f"Dialogue: 0,{_fmt_ass_time(ws)},{_fmt_ass_time(we)},Default,,0,0,0,,{line}")

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def render_clip(
    info: Dict[str, Any],
    clip: Dict[str, Any],
    job_dir: Path,
    source_video: Optional[Path] = None,
) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    cid = clip["clip_id"]
    style = clip.get("subtitle_style", "viral_pop")
    aspect = clip.get("aspect_ratio", "9:16_crop")

    ass_path = job_dir / f"{cid}.ass"
    srt_path = job_dir / f"{cid}.srt"
    out_mp4 = job_dir / f"{cid}.mp4"
    raw_seg = job_dir / f"{cid}_raw.mp4"

    generate_srt(clip["cues"], srt_path)
    generate_ass_subtitles(
        clip["cues"],
        ass_path,
        style=style,
        aspect_ratio=aspect,
        full_text=clip.get("transcript_text", ""),
    )

    start = float(clip["start"])
    duration = float(clip["duration"])
    end = start + duration

    use_local = source_video is not None and source_video.exists()
    input_path = source_video

    if not use_local:
        # Download just this <60s section for huge >45min videos
        has_cookies = resolve_cookies_file() is not None
        tried: List[Optional[str]] = [info.get("_player_client")]
        for fb in ("android_vr", "android"):
            if fb not in tried:
                tried.append(fb)
        last_sec_err = ""
        for client in tried:
            use_cookies = has_cookies and client not in ("android_vr", "android", "ios")
            sec_cmd = [
                *ytdlp_base_args(player_client=client, allow_cookies=use_cookies),
                "-f", "bv*[vcodec^=avc1][height<=720]+ba[acodec^=mp4a]/b[height<=720][ext=mp4]/b[height<=720]/b[ext=mp4]/b",
                "--download-sections", f"*{start:.2f}-{end:.2f}",
                "-o", str(raw_seg),
                "--no-playlist",
                "--no-warnings",
                info["_canonical_url"],
            ]
            p_dl = subprocess.run(sec_cmd, capture_output=True, text=True, timeout=120)
            if p_dl.returncode == 0 and raw_seg.exists():
                break
            last_sec_err = p_dl.stderr
        if not raw_seg.exists():
            raise RuntimeError(f"Failed downloading clip segment: {last_sec_err[:240]}")
        input_path = raw_seg
        seek_args: List[str] = []
    else:
        seek_args = ["-ss", f"{start:.3f}"]

    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    if aspect == "9:16_blur":
        vf = (
            f"split[bg][fg];"
            f"[bg]scale=180:320:force_original_aspect_ratio=increase,crop=180:320,boxblur=4:2,scale=720:1280:flags=bilinear,eq=brightness=-0.12[bg2];"
            f"[fg]scale=720:1280:force_original_aspect_ratio=decrease[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1,ass='{ass_escaped}'"
        )
    elif aspect == "16:9_original":
        vf = (
            f"scale='min(1280,iw)':-2:flags=bilinear,"
            f"pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1,ass='{ass_escaped}'"
        )
    else:
        # 9:16_crop default
        vf = (
            f"scale='if(gt(iw/ih,720/1280),-2,720)':'if(gt(iw/ih,720/1280),1280,-2)':flags=bilinear,"
            f"crop=720:1280:(iw-720)/2:(ih-1280)/2,setsar=1,ass='{ass_escaped}'"
        )

    ff_cmd = [
        "ffmpeg", "-y", "-v", "error",
        *seek_args,
        "-i", str(input_path),
        "-t", f"{duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "superfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-threads", "2",
        str(out_mp4),
    ]
    proc = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=180)
    if raw_seg.exists():
        try:
            raw_seg.unlink()
        except OSError:
            pass
    if proc.returncode != 0 or not out_mp4.exists():
        raise RuntimeError(f"FFmpeg render error: {proc.stderr[:300]}")
    return out_mp4
