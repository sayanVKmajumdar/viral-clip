import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  Archive,
  CheckCircle2,
  Film,
  Flame,
  Globe,
  Link2,
  Loader2,
  Play,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Zap,
} from "lucide-react";
import { ClipCard } from "./components/ClipCard";
import { HeatmapTimeline } from "./components/HeatmapTimeline";
import { Lang, TEXT } from "./i18n";
import { ClipData, JobState } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

const SAMPLE_VIDEOS = [
  {
    label: "Steve Jobs Stanford Speech (15m)",
    url: "https://www.youtube.com/watch?v=UF8uR6Z6KLc",
  },
  {
    label: "Master Procrastinator — TED (14m)",
    url: "https://www.youtube.com/watch?v=arj7oStGLkU",
  },
  {
    label: "How to Speak — Julian Treasure TED (10m)",
    url: "https://www.youtube.com/watch?v=eIho2S0ZahI",
  },
];

export function App() {
  const [lang, setLang] = useState<Lang>("en");
  const t = TEXT[lang];

  const [url, setUrl] = useState("");
  const [aspectRatio, setAspectRatio] = useState("9:16_crop");
  const [subtitleStyle, setSubtitleStyle] = useState("viral_pop");
  const [sortBy, setSortBy] = useState<"score" | "timeline">("score");

  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [job, setJob] = useState<JobState | null>(null);

  const pollTimerRef = useRef<number | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const stopListeners = () => {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopListeners();
  }, []);

  const startTrackingJob = (jobId: string) => {
    stopListeners();

    const fetchLatest = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        if (!res.ok) return;
        const data: JobState = await res.json();
        setJob(data);
        if (data.status === "completed" || data.status === "error") {
          stopListeners();
        }
      } catch {
        // ignore transient errors
      }
    };

    try {
      const es = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
      esRef.current = es;
      es.onmessage = (ev) => {
        try {
          const data: JobState = JSON.parse(ev.data);
          setJob(data);
          if (data.status === "completed" || data.status === "error") {
            stopListeners();
          }
        } catch {
          // ignore
        }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
      };
    } catch {
      // SSE unsupported fallback
    }

    fetchLatest();
    pollTimerRef.current = window.setInterval(fetchLatest, 1500);
  };

  const handleAnalyze = async (customUrl?: string) => {
    const targetUrl = (customUrl ?? url).trim();
    if (!targetUrl) {
      setErrorMsg("Please paste a YouTube video link first.");
      return;
    }
    if (customUrl) setUrl(customUrl);
    setErrorMsg(null);
    setSubmitting(true);
    setJob(null);

    try {
      const resp = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: targetUrl,
          aspect_ratio: aspectRatio,
          subtitle_style: subtitleStyle,
          max_clips: 10,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Could not start analysis.");
      }
      startTrackingJob(data.job_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to analyze video";
      setErrorMsg(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleClipUpdated = (updated: ClipData) => {
    setJob((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        clips: prev.clips.map((c) => (c.clip_id === updated.clip_id ? updated : c)),
      };
    });
  };

  const sortedClips = useMemo(() => {
    if (!job?.clips) return [];
    const copy = [...job.clips];
    if (sortBy === "timeline") {
      copy.sort((a, b) => a.start - b.start);
    } else {
      copy.sort((a, b) => a.rank - b.rank);
    }
    return copy;
  }, [job?.clips, sortBy]);

  const scrollToClip = (clipId: string) => {
    const el = document.getElementById(clipId);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  const isWorking =
    submitting ||
    (job !== null && (job.status === "queued" || job.status === "analyzing"));

  const readyCount = job?.clips?.filter((c) => c.render_status === "ready").length || 0;

  return (
    <div className="min-h-screen bg-[#08090E] text-slate-100 flex flex-col">
      {/* Subtle Ambient Background Glow */}
      <div className="pointer-events-none fixed inset-x-0 top-0 h-96 bg-gradient-to-b from-violet-600/12 via-indigo-600/5 to-transparent" />

      {/* Top Navigation */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-[#08090E]/80 border-b border-slate-800/80">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-violet-600/30">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-base tracking-tight text-white">
                {t.brand}
              </span>
              <span className="hidden sm:inline-block ml-2 rounded-md bg-violet-500/15 border border-violet-500/30 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-violet-300">
                AI Shorts Lab
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <span className="hidden md:inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-medium text-emerald-300">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              {t.noLoginBadge}
            </span>

            <button
              onClick={() => setLang((l) => (l === "en" ? "bn" : "en"))}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 px-3 py-1.5 text-xs font-semibold text-slate-200 transition cursor-pointer"
              title="Switch Language"
            >
              <Globe className="w-3.5 h-3.5 text-violet-400" />
              <span>{lang === "en" ? "EN | বাংলা" : "বাংলা | EN"}</span>
            </button>
          </div>
        </div>
      </header>

      <main className="relative z-10 flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8 space-y-7">
        {/* Hero Input Card */}
        <section className="rounded-3xl border border-slate-800/90 bg-gradient-to-b from-[#121523] to-[#0D0F18] p-5 sm:p-8 shadow-2xl shadow-black/40">
          <div className="max-w-3xl mx-auto text-center space-y-3 mb-6">
            <div className="inline-flex items-center gap-2 rounded-full bg-violet-500/10 border border-violet-500/30 px-3.5 py-1 text-xs font-medium text-violet-300">
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              Top 10 Viral Clips • Under 60s • Auto Subtitles • Virality Score /100
            </div>
            <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
              {t.heroTitle}
            </h1>
            <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
              {t.heroSub}
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAnalyze();
            }}
            className="max-w-4xl mx-auto space-y-4"
          >
            <div className="flex flex-col sm:flex-row gap-2.5">
              <div className="relative flex-1">
                <Link2 className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder={t.urlPlaceholder}
                  className="w-full rounded-2xl bg-[#080A10] border border-slate-700/90 focus:border-violet-500 pl-11 pr-4 py-3.5 text-sm text-white placeholder:text-slate-500 focus:outline-none shadow-inner"
                />
              </div>

              <button
                type="submit"
                disabled={isWorking}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-60 px-6 py-3.5 text-sm font-bold text-white shadow-lg shadow-violet-600/30 transition cursor-pointer shrink-0"
              >
                {isWorking ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t.analyzingBtn}
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    {t.analyzeBtn}
                  </>
                )}
              </button>
            </div>

            {/* Format & Subtitle Style Options */}
            <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
              <div className="flex items-center gap-2 rounded-xl bg-[#080A10] border border-slate-800 px-3 py-1.5">
                <Film className="w-3.5 h-3.5 text-violet-400" />
                <span className="text-xs text-slate-400">{t.aspectLabel}:</span>
                <select
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  className="bg-transparent text-xs font-semibold text-slate-200 focus:outline-none cursor-pointer"
                >
                  <option value="9:16_crop" className="bg-slate-900">{t.aspectCrop}</option>
                  <option value="9:16_blur" className="bg-slate-900">{t.aspectBlur}</option>
                  <option value="16:9_original" className="bg-slate-900">{t.aspectOriginal}</option>
                </select>
              </div>

              <div className="flex items-center gap-2 rounded-xl bg-[#080A10] border border-slate-800 px-3 py-1.5">
                <Subtitles className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs text-slate-400">{t.subStyleLabel}:</span>
                <select
                  value={subtitleStyle}
                  onChange={(e) => setSubtitleStyle(e.target.value)}
                  className="bg-transparent text-xs font-semibold text-slate-200 focus:outline-none cursor-pointer"
                >
                  <option value="viral_pop" className="bg-slate-900">{t.stylePop}</option>
                  <option value="clean_minimal" className="bg-slate-900">{t.styleMinimal}</option>
                  <option value="neon_cyber" className="bg-slate-900">{t.styleNeon}</option>
                </select>
              </div>
            </div>

            {/* Quick Try Examples */}
            <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
              <span className="text-xs text-slate-500">{t.trySamples}</span>
              {SAMPLE_VIDEOS.map((s) => (
                <button
                  key={s.url}
                  type="button"
                  disabled={isWorking}
                  onClick={() => handleAnalyze(s.url)}
                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-900/90 hover:bg-violet-600/20 border border-slate-800 hover:border-violet-500/50 px-3 py-1 text-[11px] font-medium text-slate-300 transition cursor-pointer disabled:opacity-50"
                >
                  <Play className="w-3 h-3 text-violet-400" />
                  {s.label}
                </button>
              ))}
            </div>
          </form>

          {errorMsg && (
            <div className="max-w-3xl mx-auto mt-4 rounded-xl bg-rose-500/10 border border-rose-500/30 px-4 py-3 flex items-center gap-2.5 text-sm text-rose-200">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
        </section>

        {/* Live Analysis & Rendering Progress */}
        {job && (
          <section className="rounded-2xl border border-slate-800/90 bg-[#10121C] p-4 sm:p-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2.5">
              <div className="flex items-center gap-2.5">
                {job.status === "completed" ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : job.status === "error" ? (
                  <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
                ) : (
                  <Loader2 className="w-5 h-5 text-violet-400 animate-spin shrink-0" />
                )}
                <span className="text-sm font-semibold text-white">
                  {job.step_message}
                </span>
              </div>
              <span className="text-xs font-mono font-bold text-violet-300">
                {job.progress}%
              </span>
            </div>

            <div className="h-2 rounded-full bg-slate-900 overflow-hidden">
              <div
                className={`h-full transition-all duration-500 rounded-full ${
                  job.status === "error"
                    ? "bg-rose-500"
                    : job.status === "completed"
                    ? "bg-emerald-500"
                    : "bg-gradient-to-r from-violet-500 via-indigo-500 to-emerald-400"
                }`}
                style={{ width: `${Math.max(4, job.progress)}%` }}
              />
            </div>

            {job.status === "error" && job.error && (
              <p className="mt-2 text-xs text-rose-300">{job.error}</p>
            )}
          </section>
        )}

        {/* Source Video Overview & Heatmap */}
        {job?.video && (
          <HeatmapTimeline
            video={job.video}
            heatmap={job.heatmap || []}
            clips={job.clips || []}
            onSelectClip={scrollToClip}
            t={t}
          />
        )}

        {/* Top 10 Clips Results */}
        {sortedClips.length > 0 && job && (
          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <h2 className="text-lg sm:text-xl font-bold text-white">
                  {t.topClipsHeading}
                </h2>
                <span className="rounded-full bg-violet-500/15 border border-violet-500/30 px-2.5 py-0.5 text-xs font-mono font-semibold text-violet-300">
                  {readyCount}/{sortedClips.length} MP4 Ready
                </span>
              </div>

              <div className="flex flex-wrap items-center gap-2.5">
                <div className="inline-flex rounded-xl bg-[#10121C] border border-slate-800 p-1">
                  <button
                    onClick={() => setSortBy("score")}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                      sortBy === "score"
                        ? "bg-violet-600 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {t.sortScore}
                  </button>
                  <button
                    onClick={() => setSortBy("timeline")}
                    className={`rounded-lg px-3 py-1 text-xs font-semibold transition cursor-pointer ${
                      sortBy === "timeline"
                        ? "bg-violet-600 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {t.sortTimeline}
                  </button>
                </div>

                <a
                  href={`${API_BASE}/api/jobs/${job.job_id}/download-all`}
                  download={`Top10_ViralClips_${job.video?.id || job.job_id}.zip`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 px-4 py-2 text-xs font-bold text-white shadow-lg shadow-emerald-600/20 transition cursor-pointer"
                >
                  <Archive className="w-3.5 h-3.5" />
                  {t.downloadAllZip}
                </a>
              </div>
            </div>

            <div className="space-y-5">
              {sortedClips.map((clip) => (
                <ClipCard
                  key={clip.clip_id}
                  jobId={job.job_id}
                  clip={clip}
                  thumbnail={job.video?.thumbnail || ""}
                  t={t}
                  onClipUpdated={handleClipUpdated}
                />
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
