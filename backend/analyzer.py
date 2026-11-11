import array
import base64
import html
import json
import math
import os
import re
import subprocess
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

CACHE_DIR = Path("/var/tmp/viralclip_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_PATH = CACHE_DIR / "_yt_cookies.txt"


def resolve_cookies_file() -> Optional[Path]:
    """Return path to YouTube Netscape cookies file from env vars if configured."""
    env_file = os.environ.get("YT_COOKIES_FILE", "").strip()
    if env_file and Path(env_file).is_file():
        return Path(env_file)

    raw_b64 = os.environ.get("YT_COOKIES_B64", "").strip()
    raw_txt = os.environ.get("YT_COOKIES_TXT", "").strip()

    content = ""
    if raw_b64:
        try:
            content = base64.b64decode(raw_b64).decode("utf-8", errors="ignore").strip()
        except Exception:
            content = ""
    elif raw_txt:
        if "\n" not in raw_txt and "\\n" in raw_txt:
            raw_txt = raw_txt.replace("\\n", "\n")
        content = raw_txt.strip()

    if content:
        if not content.startswith("#"):
            content = "# Netscape HTTP Cookie File\n" + content
        COOKIES_PATH.write_text(content + "\n", encoding="utf-8")
        try:
            os.chmod(COOKIES_PATH, 0o600)
        except OSError:
            pass
        return COOKIES_PATH

    if COOKIES_PATH.is_file() and COOKIES_PATH.stat().st_size > 20:
        return COOKIES_PATH
    return None


def ytdlp_base_args(player_client: Optional[str] = None, allow_cookies: bool = True) -> List[str]:
    args: List[str] = ["yt-dlp", "--js-runtimes", "node:/usr/bin/node"]
    cookies_file = resolve_cookies_file() if allow_cookies else None
    if cookies_file:
        args.extend(["--cookies", str(cookies_file)])
    if player_client:
        args.extend(["--extractor-args", f"youtube:player_client={player_client}"])
    return args


def _is_bot_or_client_error(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(
        k in low
        for k in (
            "sign in to confirm",
            "not a bot",
            "page needs to be reloaded",
            "http error 403",
            "requested format is not available",
        )
    )

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "when", "where",
    "why", "how", "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should", "can", "could", "may",
    "might", "must", "to", "of", "in", "on", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after", "above",
    "below", "from", "up", "down", "out", "off", "over", "under", "again", "further",
    "once", "here", "there", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "don", "now", "i", "me", "my", "myself", "we", "our",
    "ours", "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "it",
    "its", "they", "them", "their", "theirs", "im", "ive", "youre", "youve", "dont",
    "didnt", "doesnt", "cant", "wont", "isnt", "arent", "wasnt", "werent", "thats",
    "theres", "heres", "whats", "hes", "shes", "theyre", "well", "like", "know",
    "really", "actually", "literally", "basically", "right", "yeah", "okay", "ok",
    "um", "uh", "ah", "oh", "going", "gonna", "wanna", "gotta", "got", "get",
    "make", "made", "say", "said", "think", "thought", "see", "saw", "want",
    "thing", "things", "something", "anything", "everything", "nothing", "one",
    "two", "even", "also", "much", "many", "way", "lot", "kind", "sort", "back",
    "still", "come", "came", "go", "went", "take", "took", "look", "give", "gave",
    "because", "as", "until", "while", "since", "though", "although", "yet",
    "i'll", "i've", "i'm", "i'd", "you'll", "you've", "you're", "you'd",
    "we'll", "we've", "we're", "they'll", "they've", "they're", "it's",
    "that's", "there's", "here's", "what's", "who's", "he's", "she's",
    "don't", "didn't", "doesn't", "can't", "won't", "isn't", "aren't",
    "wasn't", "weren't", "couldn't", "wouldn't", "shouldn't", "haven't", "hasn't",
}

HOOK_STARTERS = [
    "how to", "why ", "what if", "never ", "always ", "stop ", "don't ", "do not ",
    "the secret", "the truth", "the biggest", "the real reason", "nobody tells",
    "most people", "everyone thinks", "here's why", "here is why", "listen ",
    "watch ", "imagine ", "remember ", "the mistake", "worst thing", "best way",
    "one thing", "three things", "five ", "10 ", "first ", "turns out",
    "কেন", "কিভাবে", "কীভাবে", "সবচেয়ে", "আসল", "সত্যি", "কখনো",
    "क्यों", "कैसे", "सबसे", "असली", "कभी", "सच",
]

CONTRAST_MARKERS = [
    "but ", "however", "actually", "turns out", "instead", "because", "therefore",
    "the problem is", "the reality is", "what happened", "suddenly", "until ",
    "except", "in fact", "surprisingly", "crazy part", "twist", "realize",
]

EMOTION_WORDS = {
    "love", "hate", "fear", "afraid", "fail", "failure", "success", "successful",
    "dream", "dreams", "money", "rich", "poor", "life", "death", "die", "live",
    "future", "change", "power", "powerful", "build", "learn", "warning", "lesson",
    "happy", "freedom", "believe", "insane", "crazy", "shocking", "amazing",
    "brilliant", "terrible", "mistake", "secret", "truth", "struggle", "pain",
    "win", "lose", "million", "billion", "breakthrough", "viral", "transform",
    "destroy", "create", "genius", "mind", "brain", "heart", "soul", "hope",
    "danger", "risk", "opportunity", "unbelievable", "incredible", "impossible",
}


@dataclass
class WordItem:
    text: str
    start: float
    end: float


@dataclass
class CueItem:
    text: str
    start: float
    end: float
    words: List[WordItem] = field(default_factory=list)


@dataclass
class ClipPlan:
    clip_id: str
    rank: int
    start: float
    end: float
    duration: float
    virality_score: int
    score_breakdown: Dict[str, int]
    why_viral: str
    title: str
    description: str
    tags: List[str]
    transcript_text: str
    cues: List[Dict[str, Any]]
    words: List[Dict[str, Any]]
    language: str = "en"
    render_status: str = "pending"
    render_error: Optional[str] = None
    video_path: Optional[str] = None
    srt_path: Optional[str] = None
    aspect_ratio: str = "9:16_crop"
    subtitle_style: str = "viral_pop"


def extract_youtube_id(url: str) -> str:
    url = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    patterns = [
        r"(?:youtube\.com/watch\?.*?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/v/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "v" in qs and re.fullmatch(r"[A-Za-z0-9_-]{11}", qs["v"][0]):
        return qs["v"][0]
    raise ValueError("Invalid YouTube URL. Please paste a valid youtube.com or youtu.be link.")


def fetch_video_info(url: str) -> Dict[str, Any]:
    vid = extract_youtube_id(url)
    canonical_url = f"https://www.youtube.com/watch?v={vid}"

    has_cookies = resolve_cookies_file() is not None
    # Try default client first (preserves heatmap & 720p+), then fall back to mobile/VR clients on datacenter bot checks
    clients: List[Optional[str]] = (
        [None, "web", "tv", "android_vr", "android"]
        if has_cookies
        else [None, "android_vr", "android", "tv_simply", "ios"]
    )

    last_err = "Failed to fetch YouTube video info"
    for client in clients:
        use_cookies = has_cookies and client not in ("android_vr", "android", "ios")
        cmd = [
            *ytdlp_base_args(player_client=client, allow_cookies=use_cookies),
            "--dump-single-json",
            "--no-download",
            "--no-playlist",
            "--no-warnings",
            canonical_url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            data["_canonical_url"] = canonical_url
            data["_video_id"] = vid
            data["_player_client"] = client
            return data
        last_err = (proc.stderr or last_err).strip()
        if not _is_bot_or_client_error(last_err):
            break

    if "sign in to confirm" in last_err.lower() or "not a bot" in last_err.lower():
        raise RuntimeError(
            "YouTube blocked this cloud server IP ('Sign in to confirm you're not a bot'). "
            "Fix: Add YT_COOKIES_TXT (or YT_COOKIES_B64) to your Render Environment Variables and redeploy, "
            "or run locally / on Hugging Face."
        )
    raise RuntimeError(f"Could not access YouTube video: {last_err[:280]}")


def _clean_text(t: str) -> str:
    t = html.unescape(t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("\n", " ").replace("\r", " ")
    t = re.sub(r"\[[^\]]{1,28}\]", "", t)
    t = re.sub(r"\((?:Music|Applause|Laughter|Cheering|Silence|Sound|Sighs|Chuckles)[^)]{0,24}\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _pick_caption_track(info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], str]:
    """Return (json3_url, source_kind, lang_code) matching the video's true spoken language."""
    subtitles = info.get("subtitles") or {}
    auto_caps = info.get("automatic_captions") or {}
    title = info.get("title") or ""

    raw_lang = info.get("language")
    if not raw_lang:
        if re.search(r"[\u0980-\u09FF]", title):
            raw_lang = "bn"
        elif re.search(r"[\u0900-\u097F]", title):
            raw_lang = "hi"
        else:
            raw_lang = "en"
    base_lang = raw_lang.split("-")[0].lower()

    def find_json3(track_list: List[Dict[str, Any]], allow_translated: bool = False) -> Optional[str]:
        for item in track_list:
            u = item.get("url") or ""
            if item.get("ext") == "json3" and u:
                if not allow_translated and "tlang=" in u:
                    continue
                return u
        return None

    def pick_from_dict(tracks: Dict[str, Any], target_base: str, allow_translated: bool = False) -> Tuple[Optional[str], Optional[str]]:
        # Exact or -orig match first
        priority_keys = [
            k for k in tracks.keys()
            if not k.startswith("live_chat") and k.lower() in (target_base, f"{target_base}-orig", f"{target_base}-us", f"{target_base}-gb", f"{target_base}-in")
        ]
        # Prefix match next (e.g. en-eEY6OEpapPo)
        prefix_keys = [
            k for k in tracks.keys()
            if not k.startswith("live_chat") and k not in priority_keys and k.split("-")[0].lower() == target_base
        ]
        for k in priority_keys + prefix_keys:
            u = find_json3(tracks[k], allow_translated=allow_translated)
            if u:
                return u, k
        return None, None

    manual_url, manual_lang = pick_from_dict(subtitles, base_lang, allow_translated=True)
    auto_url, auto_lang = pick_from_dict(auto_caps, base_lang, allow_translated=False)

    # Try fallback to English if video language wasn't found in tracks
    if not manual_url and not auto_url and base_lang != "en":
        manual_url, manual_lang = pick_from_dict(subtitles, "en", allow_translated=True)
        auto_url, auto_lang = pick_from_dict(auto_caps, "en", allow_translated=False)

    # Last resort: pick first available non-translated track
    if not manual_url and not auto_url:
        for k, tl in auto_caps.items():
            if not k.startswith("live_chat"):
                u = find_json3(tl, allow_translated=False)
                if u:
                    auto_url, auto_lang = u, k
                    break
        if not auto_url:
            for k, tl in subtitles.items():
                if not k.startswith("live_chat"):
                    u = find_json3(tl, allow_translated=True)
                    if u:
                        manual_url, manual_lang = u, k
                        break

    if auto_url and manual_url and auto_lang and manual_lang:
        if auto_lang.split("-")[0].lower() == manual_lang.split("-")[0].lower():
            return json.dumps({"manual": manual_url, "auto": auto_url}), "both", manual_lang.split("-")[0].lower()
    if manual_url and manual_lang:
        return manual_url, "manual", manual_lang.split("-")[0].lower()
    if auto_url and auto_lang:
        return auto_url, "auto", auto_lang.split("-")[0].lower()
    return None, None, base_lang


def _parse_json3_words_and_cues(raw_json: Dict[str, Any]) -> Tuple[List[WordItem], List[CueItem]]:
    events = raw_json.get("events") or []
    words: List[WordItem] = []
    cues: List[CueItem] = []

    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        t_start = float(ev.get("tStartMs", 0)) / 1000.0
        d_dur = float(ev.get("dDurationMs", 2500)) / 1000.0
        ev_end = t_start + max(0.2, d_dur)

        # Build clean text and check if per-word tOffsetMs exists
        has_offsets = any("tOffsetMs" in s for s in segs)
        ev_words: List[WordItem] = []

        if has_offsets and len(segs) > 1:
            raw_tokens: List[Tuple[str, float]] = []
            for s in segs:
                txt = _clean_text(s.get("utf8", ""))
                if not txt:
                    continue
                off = float(s.get("tOffsetMs", 0)) / 1000.0
                w_start = t_start + off
                # Split if a seg contains multiple words
                parts = txt.split()
                if len(parts) == 1:
                    raw_tokens.append((parts[0], w_start))
                else:
                    for k, p in enumerate(parts):
                        raw_tokens.append((p, w_start + k * 0.18))

            for idx, (tok, ws) in enumerate(raw_tokens):
                if idx + 1 < len(raw_tokens):
                    we = max(ws + 0.08, min(ev_end, raw_tokens[idx + 1][1]))
                else:
                    we = max(ws + 0.16, min(ws + 0.65, ev_end))
                ev_words.append(WordItem(text=tok, start=round(ws, 3), end=round(we, 3)))
        else:
            full_txt = _clean_text("".join(s.get("utf8", "") for s in segs))
            if not full_txt:
                continue
            tokens = full_txt.split()
            total_chars = sum(max(1, len(tk)) for tk in tokens)
            cur = t_start
            usable_dur = max(0.3, min(d_dur, max(0.8, len(tokens) * 0.55)))
            for tk in tokens:
                frac = max(1, len(tk)) / total_chars
                w_dur = max(0.08, usable_dur * frac)
                ev_words.append(WordItem(text=tk, start=round(cur, 3), end=round(cur + w_dur, 3)))
                cur += w_dur

        if not ev_words:
            continue

        cue_text = " ".join(w.text for w in ev_words).strip()
        if not cue_text:
            continue
        c_start = ev_words[0].start
        c_end = max(c_start + 0.25, ev_words[-1].end)
        words.extend(ev_words)
        cues.append(CueItem(text=cue_text, start=round(c_start, 3), end=round(c_end, 3), words=ev_words))

    # Fix monotonic order and remove duplicate overlapping auto-cap roll-up lines
    dedup_words: List[WordItem] = []
    for w in sorted(words, key=lambda x: x.start):
        if dedup_words and abs(w.start - dedup_words[-1].start) < 0.08 and w.text.lower() == dedup_words[-1].text.lower():
            continue
        if dedup_words and w.start < dedup_words[-1].end:
            dedup_words[-1].end = round(max(dedup_words[-1].start + 0.06, w.start), 3)
        dedup_words.append(w)

    # Rebuild clean sentence/phrase cues from dedup_words if cues were overlapping/messy
    clean_cues = _regroup_words_into_cues(dedup_words)
    return dedup_words, clean_cues


def _regroup_words_into_cues(words: List[WordItem], max_words: int = 12, max_dur: float = 5.5) -> List[CueItem]:
    if not words:
        return []
    cues: List[CueItem] = []
    buf: List[WordItem] = []

    for i, w in enumerate(words):
        buf.append(w)
        next_gap = (words[i + 1].start - w.end) if i + 1 < len(words) else 999.0
        ends_sentence = bool(re.search(r"[.!?।]$", w.text))
        ends_clause = bool(re.search(r"[,;:]$", w.text)) and len(buf) >= 5
        dur = w.end - buf[0].start

        if ends_sentence or next_gap >= 0.55 or len(buf) >= max_words or dur >= max_dur or (ends_clause and dur >= 2.2):
            cues.append(CueItem(
                text=" ".join(x.text for x in buf),
                start=round(buf[0].start, 3),
                end=round(max(buf[0].start + 0.2, buf[-1].end), 3),
                words=list(buf),
            ))
            buf = []

    if buf:
        cues.append(CueItem(
            text=" ".join(x.text for x in buf),
            start=round(buf[0].start, 3),
            end=round(max(buf[0].start + 0.2, buf[-1].end), 3),
            words=list(buf),
        ))
    return cues


def _apply_punctuation_from_manual(auto_words: List[WordItem], manual_cues: List[CueItem]) -> List[WordItem]:
    """When both punctuated manual captions and word-timed auto captions exist,
    prefer manual words aligned smoothly to timestamps when lengths roughly match,
    otherwise return manual words interpolated or auto words."""
    if not manual_cues:
        return auto_words
    manual_words: List[WordItem] = []
    for c in manual_cues:
        manual_words.extend(c.words)
    if not auto_words:
        return manual_words
    # If word counts are within 18%, match punctuation/casing from manual onto auto timing
    if abs(len(manual_words) - len(auto_words)) / max(1, len(manual_words)) <= 0.18:
        # Simple sliding alignment by nearest normalized index + fuzzy match
        aligned: List[WordItem] = []
        j = 0
        for mw in manual_words:
            norm_m = re.sub(r"\W+", "", mw.text.lower())
            best_j = None
            for k in range(max(0, j - 3), min(len(auto_words), j + 6)):
                norm_a = re.sub(r"\W+", "", auto_words[k].text.lower())
                if norm_m and norm_m == norm_a:
                    best_j = k
                    break
            if best_j is not None:
                aw = auto_words[best_j]
                aligned.append(WordItem(text=mw.text, start=aw.start, end=aw.end))
                j = best_j + 1
            else:
                aligned.append(mw)
        # Ensure monotonic timestamps
        for idx in range(1, len(aligned)):
            if aligned[idx].start < aligned[idx - 1].start:
                aligned[idx].start = aligned[idx - 1].end
                aligned[idx].end = max(aligned[idx].start + 0.1, aligned[idx].end)
        return aligned
    # Manual captions already have clean punctuation & tight 3-6s cue timestamps!
    return manual_words


def fetch_transcript(
    info: Dict[str, Any],
    audio_path: Optional[Path] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[List[WordItem], List[CueItem], str]:
    track_spec, kind, lang = _pick_caption_track(info)

    if track_spec:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"}
            with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
                if kind == "both":
                    urls = json.loads(track_spec)
                    r_man = client.get(urls["manual"]).json()
                    r_aut = client.get(urls["auto"]).json()
                    _, man_cues = _parse_json3_words_and_cues(r_man)
                    aut_words, _ = _parse_json3_words_and_cues(r_aut)
                    merged_words = _apply_punctuation_from_manual(aut_words, man_cues)
                    cues = _regroup_words_into_cues(merged_words)
                    if cues:
                        return merged_words, cues, lang
                else:
                    r_sub = client.get(track_spec).json()
                    words, cues = _parse_json3_words_and_cues(r_sub)
                    if cues:
                        return words, cues, lang
        except Exception:
            pass

    # Fallback 1: youtube_transcript_api
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt = YouTubeTranscriptApi()
        vid = info["_video_id"]
        fetched = ytt.fetch(vid, languages=[lang, "en", "bn", "hi"])
        words: List[WordItem] = []
        for snip in fetched:
            txt = _clean_text(snip.text)
            if not txt:
                continue
            tokens = txt.split()
            total_c = sum(max(1, len(t)) for t in tokens)
            cur = float(snip.start)
            dur = max(0.3, float(snip.duration))
            for tk in tokens:
                wd = max(0.08, dur * (max(1, len(tk)) / total_c))
                words.append(WordItem(text=tk, start=round(cur, 3), end=round(cur + wd, 3)))
                cur += wd
        if words:
            return words, _regroup_words_into_cues(words), lang
    except Exception:
        pass

    # Fallback 2: faster-whisper tiny int8 on downloaded audio
    if audio_path is None or not audio_path.exists():
        if progress_cb:
            progress_cb("No YouTube captions found — downloading audio for AI speech recognition...")
        audio_path = download_audio_for_analysis(info)

    if audio_path and audio_path.exists():
        if progress_cb:
            progress_cb("Transcribing audio locally with Whisper AI...")
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=2)
        segments, seg_info = model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
        detected_lang = getattr(seg_info, "language", lang) or lang
        words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    wt = w.word.strip()
                    if wt:
                        words.append(WordItem(text=wt, start=round(w.start, 3), end=round(max(w.start + 0.08, w.end), 3)))
            else:
                txt = seg.text.strip()
                if txt:
                    tokens = txt.split()
                    dur = max(0.3, seg.end - seg.start)
                    step = dur / len(tokens)
                    for idx, tk in enumerate(tokens):
                        words.append(WordItem(
                            text=tk,
                            start=round(seg.start + idx * step, 3),
                            end=round(seg.start + (idx + 1) * step, 3),
                        ))
        if words:
            return words, _regroup_words_into_cues(words), detected_lang

    raise RuntimeError("Could not extract speech/subtitles from this video.")


def download_audio_for_analysis(info: Dict[str, Any]) -> Optional[Path]:
    vid = info["_video_id"]
    audio_file = CACHE_DIR / f"{vid}_audio.m4a"
    if audio_file.exists() and audio_file.stat().st_size > 1024:
        return audio_file

    has_cookies = resolve_cookies_file() is not None
    tried: List[Optional[str]] = [info.get("_player_client")]
    for fb in ("android_vr", "android"):
        if fb not in tried:
            tried.append(fb)

    for client in tried:
        use_cookies = has_cookies and client not in ("android_vr", "android", "ios")
        cmd = [
            *ytdlp_base_args(player_client=client, allow_cookies=use_cookies),
            "-f", "ba[acodec^=mp4a]/ba[ext=m4a]/ba/b[ext=mp4]/b",
            "-o", str(audio_file),
            "--no-playlist",
            "--no-warnings",
            info["_canonical_url"],
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if proc.returncode == 0 and audio_file.exists() and audio_file.stat().st_size > 1024:
            return audio_file
    return None


def compute_audio_energy_profile(media_path: Optional[Path], duration: float) -> List[float]:
    """Compute normalized per-second RMS audio energy [0.0..1.0] in <0.5s using ffmpeg PCM pipe."""
    n_secs = max(1, int(math.ceil(duration)))
    if not media_path or not media_path.exists():
        return [0.5] * n_secs

    try:
        cmd = [
            "ffmpeg", "-v", "error",
            "-i", str(media_path),
            "-vn", "-ac", "1", "-ar", "4000",
            "-f", "s16le", "pipe:1",
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if proc.returncode != 0 or not proc.stdout:
            return [0.5] * n_secs

        samples = array.array("h")
        # Ensure even byte length
        raw = proc.stdout[: len(proc.stdout) - (len(proc.stdout) % 2)]
        samples.frombytes(raw)

        sr = 4000
        buckets: List[float] = []
        for s in range(0, len(samples), sr):
            chunk = samples[s:s + sr]
            if not chunk:
                break
            rms = math.sqrt(sum(x * x for x in chunk) / len(chunk))
            buckets.append(rms)

        if not buckets:
            return [0.5] * n_secs

        sorted_b = sorted(buckets)
        p95 = sorted_b[min(len(sorted_b) - 1, int(0.95 * len(sorted_b)))] or 1.0
        norm = [min(1.0, b / p95) for b in buckets]
        while len(norm) < n_secs:
            norm.append(norm[-1] if norm else 0.5)
        return norm[:n_secs]
    except Exception:
        return [0.5] * n_secs


def _heatmap_curve(info: Dict[str, Any], duration: float) -> List[float]:
    n_secs = max(1, int(math.ceil(duration)))
    hm = info.get("heatmap")
    if not hm:
        return []
    curve = [0.0] * n_secs
    for seg in hm:
        s = max(0, int(math.floor(float(seg.get("start_time", 0)))))
        e = min(n_secs, int(math.ceil(float(seg.get("end_time", s + 1)))))
        val = float(seg.get("value", 0.0))
        for sec in range(s, e):
            curve[sec] = max(curve[sec], val)
    return curve


def _score_window(
    window_cues: List[CueItem],
    full_text: str,
    start: float,
    end: float,
    video_title: str,
    heatmap_curve: List[float],
    energy_curve: List[float],
    chapter_starts: List[float],
) -> Tuple[int, Dict[str, int], str]:
    dur = end - start
    words = full_text.split()
    n_words = len(words)
    lower = full_text.lower()

    # 1. Hook Power (0..25)
    opening_cues = [c for c in window_cues if c.start <= start + 6.0]
    opening = " ".join(c.text for c in opening_cues) if opening_cues else window_cues[0].text
    op_lower = opening.lower()

    hook = 10.0
    if "?" in opening:
        hook += 4.5
    if any(hs in op_lower for hs in HOOK_STARTERS):
        hook += 4.5
    if re.search(r"\b\d+(?:%|x|k|m|b|\+)?\b", op_lower):
        hook += 3.0
    if re.search(r"\b(you|your|you're|you've)\b", op_lower):
        hook += 2.2
    if any(abs(start - ch) <= 4.0 for ch in chapter_starts):
        hook += 2.0
    if any(w in op_lower for w in EMOTION_WORDS):
        hook += 2.0
    # Penalize weak filler starts ("and so", "but anyway", "uh")
    if re.match(r"^(?:and|so|but|uh|um|well|yeah)\b", op_lower.strip()):
        hook -= 2.5
    hook_score = int(max(6, min(25, round(hook))))

    # 2. Replay & Audio Energy (0..25)
    s_idx = max(0, int(start))
    e_idx = max(s_idx + 1, int(math.ceil(end)))
    replay = 12.0
    why_bits: List[str] = []

    if heatmap_curve:
        slice_hm = heatmap_curve[s_idx:min(len(heatmap_curve), e_idx)]
        if slice_hm:
            hm_peak = max(slice_hm)
            hm_avg = sum(slice_hm) / len(slice_hm)
            replay = 9.0 + (hm_peak * 10.0) + (hm_avg * 6.0)
            if hm_peak >= 0.72:
                why_bits.append("High YouTube Most-Replayed viewer spike")
    if energy_curve:
        slice_en = energy_curve[s_idx:min(len(energy_curve), e_idx)]
        if slice_en:
            en_peak = max(slice_en)
            en_avg = sum(slice_en) / len(slice_en)
            en_dyn = en_peak - min(slice_en)
            en_pts = 9.0 + (en_avg * 7.5) + (en_peak * 5.0) + (en_dyn * 3.5)
            replay = (replay * 0.65 + en_pts * 0.35) if heatmap_curve else en_pts
            if en_peak >= 0.82 and "Most-Replayed" not in " ".join(why_bits):
                why_bits.append("Strong vocal emphasis & dynamic audio peak")
    replay_score = int(max(7, min(25, round(replay))))

    # 3. Pacing & Information Density (0..25)
    wpm = (n_words / max(1.0, dur)) * 60.0
    pacing = 12.0
    if 125 <= wpm <= 200:
        pacing += 6.0
    elif 100 <= wpm <= 230:
        pacing += 3.5
    else:
        pacing -= 2.0

    # Sweet spot duration 28..53s under 60s
    if 28.0 <= dur <= 53.0:
        pacing += 3.5
    elif 22.0 <= dur < 58.0:
        pacing += 2.0

    # Narrative turns / payoff density
    contrast_hits = sum(1 for m in CONTRAST_MARKERS if m in lower)
    pacing += min(4.0, contrast_hits * 1.4)

    # Dead-air penalty
    speech_time = sum(max(0.1, c.end - c.start) for c in window_cues)
    silence_ratio = max(0.0, 1.0 - (speech_time / max(1.0, dur)))
    if silence_ratio > 0.35:
        pacing -= 4.0
    pacing_score = int(max(7, min(25, round(pacing))))

    # 4. Shareability & Payoff (0..25)
    share = 10.5
    emo_hits = len({w for w in re.findall(r"[a-zA-Z]+", lower) if w in EMOTION_WORDS})
    share += min(6.5, emo_hits * 1.6)
    q_count = full_text.count("?") + full_text.count("!")
    share += min(3.0, q_count * 1.2)

    # Topic overlap with main video title
    title_kw = {w for w in re.findall(r"[a-zA-Z]{4,}", video_title.lower()) if w not in STOPWORDS}
    clip_kw = set(re.findall(r"[a-zA-Z]{4,}", lower))
    if title_kw & clip_kw:
        share += min(3.0, len(title_kw & clip_kw) * 1.2)

    # Clean ending payoff
    last_txt = window_cues[-1].text.strip()
    if re.search(r"[.!?।]$", last_txt):
        share += 2.2
    elif re.search(r"\b(and|but|so|or|the|a|to|of|that|which)$", last_txt.lower()):
        share -= 2.5

    share_score = int(max(7, min(25, round(share))))
    total = int(max(55, min(99, hook_score + replay_score + pacing_score + share_score)))

    # Build human-readable reason
    if hook_score >= 20:
        why_bits.insert(0, "Scroll-stopping opening hook")
    if pacing_score >= 20:
        why_bits.append(f"Crisp {int(wpm)} WPM narrative pacing")
    if share_score >= 20:
        why_bits.append("High emotional & shareable takeaway")
    if not why_bits:
        why_bits.append("Strong self-contained insight with clean finish")

    breakdown = {
        "hook": hook_score,
        "replay_energy": replay_score,
        "pacing": pacing_score,
        "shareability": share_score,
    }
    return total, breakdown, " • ".join(why_bits[:3])


def _extract_keywords(text: str, video_title: str, limit: int = 12) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)
    if len(words) < 5:
        words = [w for w in re.findall(r"[^\s.,!?;:\"'()\[\]{}|।/\\0-9]{3,}", text, flags=re.UNICODE)]
    freq: Dict[str, int] = {}
    proper: Dict[str, int] = {}
    for w in words:
        lw = w.lower().strip("'-")
        lw_base = re.sub(r"(?:'s|'ll|'ve|'re|'m|'d|n't)$", "", lw)
        if len(lw_base) < 3 or lw in STOPWORDS or lw_base in STOPWORDS or lw_base.isdigit():
            continue
        freq[lw_base] = freq.get(lw_base, 0) + 1
        if w[0].isupper() and len(lw_base) > 2:
            proper[lw_base] = proper.get(lw_base, 0) + 1

    # Add meaningful words from video title
    title_words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", video_title)
    if len(title_words) < 2:
        title_words = [w for w in re.findall(r"[^\s.,!?;:\"'()\[\]{}|।/\\0-9]{3,}", video_title, flags=re.UNICODE)]
    for tw in title_words:
        ltw = tw.lower().strip("'-")
        if len(ltw) >= 3 and ltw not in STOPWORDS:
            freq[ltw] = freq.get(ltw, 0) + 2

    ranked = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
    tags: List[str] = []
    seen = set()
    for p, _ in sorted(proper.items(), key=lambda x: -x[1]):
        lp = p.lower()
        if lp not in seen and lp not in STOPWORDS:
            tags.append(lp)
            seen.add(lp)
            if len(tags) >= 5:
                break
    for k, _ in ranked:
        if k not in seen:
            tags.append(k)
            seen.add(k)
        if len(tags) >= limit - 4:
            break

    for base_tag in ["shorts", "viralshorts", "reels", "fyp", "trending"]:
        if base_tag not in seen and len(tags) < limit:
            tags.append(base_tag)
            seen.add(base_tag)
    return tags[:limit]


def _generate_metadata(
    clip_cues: List[CueItem],
    full_text: str,
    video_info: Dict[str, Any],
    rank: int,
    why_viral: str,
) -> Tuple[str, str, List[str]]:
    video_title = video_info.get("title") or "YouTube Video"
    channel = video_info.get("channel") or video_info.get("uploader") or ""

    # Pick the punchiest sentence/clause inside the clip for the Title
    sentences = [s.strip() for s in re.split(r"(?<=[.!?।])\s+", full_text) if len(s.strip()) >= 14]
    if not sentences:
        sentences = [c.text.strip() for c in clip_cues if len(c.text.strip()) >= 12]

    best_sent = sentences[0] if sentences else video_title
    best_s_score = -99.0
    for idx, s in enumerate(sentences[:6]):
        sl = s.lower()
        sc = 0.0
        if idx == 0:
            sc += 1.5
        if "?" in s:
            sc += 3.2
        if any(hs in sl for hs in HOOK_STARTERS):
            sc += 3.0
        if any(ew in sl for ew in EMOTION_WORDS):
            sc += 2.5
        if 22 <= len(s) <= 68:
            sc += 3.5
        # Penalize awkward quote fragments or trailing/mid-sentence fragments
        if s.count('"') % 2 == 1:
            sc -= 3.5
        if s and s[0].islower():
            sc -= 3.0
        if sc > best_s_score:
            best_s_score = sc
            best_sent = s

    # Clean leading fillers & stray unmatched quotes
    title = re.sub(r"^(?:And|So|But|Because|Well|Yeah|Okay|Actually|You know|I mean),?\s+", "", best_sent, flags=re.IGNORECASE).strip()
    if title.count('"') % 2 == 1:
        title = title.replace('"', "")
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > 64:
        # Trim cleanly at word boundary
        cut = title[:61].rsplit(" ", 1)[0].rstrip(",;:-")
        title = cut + "..."
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    if not title or len(title) < 10:
        short_base = video_title[:45].strip()
        title = f"{short_base} — Viral Moment #{rank}"

    tags = _extract_keywords(full_text, video_title, limit=12)
    hashtags = " ".join(f"#{re.sub(r'[^A-Za-z0-9]', '', t)}" for t in tags[:6] if re.sub(r'[^A-Za-z0-9]', '', t))

    # Craft clean summary description
    snippet = full_text.strip()
    if len(snippet) > 190:
        snippet = snippet[:187].rsplit(" ", 1)[0].rstrip(",;:-") + "..."
    credit = f"From: {video_title}" + (f" ({channel})" if channel else "")
    description = (
        f"{snippet}\n\n"
        f"🔥 {why_viral}\n"
        f"📺 {credit}\n"
        f"💬 What do you think? Drop your thoughts below!\n\n"
        f"{hashtags} #shorts"
    )
    return title, description, tags


def _slice_clip_subtitles(
    all_words: List[WordItem],
    clip_start: float,
    clip_end: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return clip-relative (0.0 .. dur) words and 2-5 word visual subtitle chunks."""
    dur = clip_end - clip_start
    rel_words: List[WordItem] = []
    for w in all_words:
        if w.end <= clip_start + 0.02:
            continue
        if w.start >= clip_end - 0.02:
            break
        rs = max(0.0, w.start - clip_start)
        re_t = min(dur, max(rs + 0.06, w.end - clip_start))
        rel_words.append(WordItem(text=w.text, start=round(rs, 3), end=round(re_t, 3)))

    # Group into dynamic Shorts-friendly 2-4 word chunks (never exceeding 28 chars per line)
    chunks: List[Dict[str, Any]] = []
    buf: List[WordItem] = []
    for i, w in enumerate(rel_words):
        buf.append(w)
        char_len = sum(len(x.text) for x in buf) + max(0, len(buf) - 1)
        next_gap = (rel_words[i + 1].start - w.end) if i + 1 < len(rel_words) else 999.0
        ends_sent = bool(re.search(r"[.!?।,;:]$", w.text))
        if len(buf) >= 4 or char_len >= 22 or next_gap >= 0.45 or (ends_sent and len(buf) >= 2):
            chunks.append({
                "start": round(buf[0].start, 3),
                "end": round(max(buf[0].start + 0.18, buf[-1].end), 3),
                "text": " ".join(x.text for x in buf),
                "words": [{"text": x.text, "start": x.start, "end": x.end} for x in buf],
            })
            buf = []
    if buf:
        chunks.append({
            "start": round(buf[0].start, 3),
            "end": round(max(buf[0].start + 0.18, buf[-1].end), 3),
            "text": " ".join(x.text for x in buf),
            "words": [{"text": x.text, "start": x.start, "end": x.end} for x in buf],
        })

    return chunks, [asdict(w) for w in rel_words]


def select_top_viral_clips(
    info: Dict[str, Any],
    words: List[WordItem],
    cues: List[CueItem],
    energy_curve: List[float],
    lang: str = "en",
    max_clips: int = 10,
    aspect_ratio: str = "9:16_crop",
    subtitle_style: str = "viral_pop",
) -> List[ClipPlan]:
    duration = float(info.get("duration") or (cues[-1].end if cues else 60.0))
    video_title = info.get("title") or "YouTube Video"
    heatmap_curve = _heatmap_curve(info, duration)
    chapter_starts = [float(ch.get("start_time", 0.0)) for ch in (info.get("chapters") or [])]

    # Very short video (< 62s): return single whole/trimmed clip under 60s
    if duration <= 62.0:
        end_t = min(58.5, duration)
        sub_cues, sub_words = _slice_clip_subtitles(words, 0.0, end_t)
        txt = " ".join(c.text for c in cues)
        score, breakdown, why = _score_window(
            cues, txt, 0.0, end_t, video_title, heatmap_curve, energy_curve, chapter_starts
        )
        title, desc, tags = _generate_metadata(cues, txt, info, 1, why)
        return [ClipPlan(
            clip_id="clip-01",
            rank=1,
            start=0.0,
            end=round(end_t, 2),
            duration=round(end_t, 2),
            virality_score=score,
            score_breakdown=breakdown,
            why_viral=why,
            title=title,
            description=desc,
            tags=tags,
            transcript_text=txt,
            cues=sub_cues,
            words=sub_words,
            language=lang,
            aspect_ratio=aspect_ratio,
            subtitle_style=subtitle_style,
        )]

    # Build candidate windows [start, end] strictly 18s <= dur <= 58s
    candidates: List[Dict[str, Any]] = []
    n = len(cues)

    for i in range(n):
        c_start = cues[i].start
        # Slight padding before cue start if gap allows
        prev_end = cues[i - 1].end if i > 0 else 0.0
        pad_start = max(0.0, max(prev_end + 0.05, c_start - 0.25))

        for j in range(i, n):
            c_end = cues[j].end
            dur = c_end - pad_start
            if dur < 20.0:
                continue
            if dur > 57.5:
                break

            # Prefer starting at sentence start or pause, and ending on punctuation or pause
            next_start = cues[j + 1].start if j + 1 < n else duration
            pad_end = min(duration, min(next_start - 0.05, c_end + 0.3))
            final_dur = pad_end - pad_start
            if final_dur > 58.5:
                pad_end = pad_start + 58.0
                final_dur = 58.0

            win_cues = cues[i:j + 1]
            txt = " ".join(c.text for c in win_cues)
            if len(txt.split()) < 18:
                continue

            score, breakdown, why = _score_window(
                win_cues, txt, pad_start, pad_end, video_title, heatmap_curve, energy_curve, chapter_starts
            )

            # Bonus for starting cleanly on sentence boundary
            if i == 0 or (c_start - cues[i - 1].end) >= 0.45 or re.search(r"[.!?।]$", cues[i - 1].text):
                score = min(99, score + 2)

            candidates.append({
                "start": round(pad_start, 2),
                "end": round(pad_end, 2),
                "duration": round(final_dur, 2),
                "score": score,
                "breakdown": breakdown,
                "why": why,
                "cues": win_cues,
                "text": txt,
            })

    # Fallback if cues were sparse or didn't satisfy 20..57.5s rules
    if not candidates:
        step = max(25.0, min(48.0, (duration - 5.0) / max(1, max_clips)))
        t = 0.0
        while t + 18.0 < duration and len(candidates) < max_clips * 2:
            e = min(duration, t + 45.0)
            win_cues = [c for c in cues if c.end > t and c.start < e] or cues[:1]
            txt = " ".join(c.text for c in win_cues)
            score, breakdown, why = _score_window(
                win_cues, txt, t, e, video_title, heatmap_curve, energy_curve, chapter_starts
            )
            candidates.append({
                "start": round(t, 2),
                "end": round(e, 2),
                "duration": round(e - t, 2),
                "score": score,
                "breakdown": breakdown,
                "why": why,
                "cues": win_cues,
                "text": txt,
            })
            t += step

    candidates.sort(key=lambda x: (-x["score"], -abs(x["duration"] - 40.0)))

    def overlap_ratio(a: Dict[str, Any], b: Dict[str, Any]) -> float:
        inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
        min_d = max(1.0, min(a["duration"], b["duration"]))
        return inter / min_d

    selected: List[Dict[str, Any]] = []
    # Pass 1: strictly non-overlapping (or <12% overlap)
    for cand in candidates:
        if any(overlap_ratio(cand, s) > 0.12 or abs(cand["start"] - s["start"]) < 20.0 for s in selected):
            continue
        selected.append(cand)
        if len(selected) >= max_clips:
            break

    # Pass 2 (for medium videos 3-6 min that can't fit 10 totally disjoint 45s clips):
    # allow controlled distinct angles (different hook starts >= 12s apart, <45% overlap)
    if len(selected) < max_clips and duration >= 140.0:
        for cand in candidates:
            if any(overlap_ratio(cand, s) > 0.45 or abs(cand["start"] - s["start"]) < 12.0 for s in selected):
                continue
            selected.append(cand)
            if len(selected) >= max_clips:
                break

    # Sort selected by score descending
    selected.sort(key=lambda x: -x["score"])

    plans: List[ClipPlan] = []
    for idx, sel in enumerate(selected[:max_clips], start=1):
        sub_cues, sub_words = _slice_clip_subtitles(words, sel["start"], sel["end"])
        title, desc, tags = _generate_metadata(sel["cues"], sel["text"], info, idx, sel["why"])
        plans.append(ClipPlan(
            clip_id=f"clip-{idx:02d}",
            rank=idx,
            start=sel["start"],
            end=sel["end"],
            duration=sel["duration"],
            virality_score=sel["score"],
            score_breakdown=sel["breakdown"],
            why_viral=sel["why"],
            title=title,
            description=desc,
            tags=tags,
            transcript_text=sel["text"],
            cues=sub_cues,
            words=sub_words,
            language=lang,
            aspect_ratio=aspect_ratio,
            subtitle_style=subtitle_style,
        ))
    return plans
