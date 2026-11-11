import React, { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Flame,
  Loader2,
  RefreshCw,
  Sparkles,
  Tag,
  Wand2,
} from "lucide-react";
import { ClipData, CueItem } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

interface Props {
  jobId: string;
  clip: ClipData;
  thumbnail: string;
  t: Record<string, string>;
  onClipUpdated: (updated: ClipData) => void;
}

function fmtSec(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export const ClipCard: React.FC<Props> = ({
  jobId,
  clip,
  thumbnail,
  t,
  onClipUpdated,
}) => {
  const [title, setTitle] = useState(clip.title);
  const [description, setDescription] = useState(clip.description);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showSubs, setShowSubs] = useState(false);
  const [editedCues, setEditedCues] = useState<CueItem[]>(clip.cues);
  const [styleChoice, setStyleChoice] = useState(clip.subtitle_style);
  const [aspectChoice, setAspectChoice] = useState(clip.aspect_ratio);
  const [rerendering, setRerendering] = useState(false);
  const [renderNonce, setRenderNonce] = useState(1);

  useEffect(() => {
    setTitle(clip.title);
    setDescription(clip.description);
    setEditedCues(clip.cues);
    setStyleChoice(clip.subtitle_style);
    setAspectChoice(clip.aspect_ratio);
  }, [clip.clip_id, clip.title, clip.description, clip.cues, clip.subtitle_style, clip.aspect_ratio]);

  const copyText = async (val: string, key: string) => {
    try {
      await navigator.clipboard.writeText(val);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  const safeTitle = title.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48) || clip.clip_id;
  const downloadFilename = `Top${String(clip.rank).padStart(2, "0")}_Score${clip.virality_score}_${safeTitle}.mp4`;
  const downloadUrl = `${API_BASE}/api/jobs/${jobId}/clips/${clip.clip_id}/download?v=${renderNonce}`;
  const srtUrl = `${API_BASE}/api/jobs/${jobId}/clips/${clip.clip_id}/srt`;
  const videoUrl = `${API_BASE}/api/jobs/${jobId}/clips/${clip.clip_id}/video?v=${renderNonce}`;

  const handleRerender = async (newAspect?: string, newStyle?: string) => {
    if (rerendering) return;
    setRerendering(true);
    const targetAspect = newAspect || aspectChoice;
    const targetStyle = newStyle || styleChoice;
    try {
      const resp = await fetch(`${API_BASE}/api/jobs/${jobId}/clips/${clip.clip_id}/rerender`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aspect_ratio: targetAspect,
          subtitle_style: targetStyle,
          cues: editedCues,
        }),
      });
      if (resp.ok) {
        const updated: ClipData = await resp.json();
        onClipUpdated(updated);
        setRenderNonce((n) => n + 1);
      }
    } finally {
      setRerendering(false);
    }
  };

  const scoreColor =
    clip.virality_score >= 85
      ? "text-emerald-400 border-emerald-500/40 bg-emerald-500/10"
      : clip.virality_score >= 72
      ? "text-amber-300 border-amber-500/40 bg-amber-500/10"
      : "text-violet-300 border-violet-500/40 bg-violet-500/10";

  const isLandscape = (clip.aspect_ratio || aspectChoice) === "16:9_original";
  const isReady = clip.render_status === "ready" && !rerendering;

  const copyAllPayload = `${title}\n\n${description}\n\nTags: ${clip.tags.join(", ")}`;

  return (
    <article
      id={clip.clip_id}
      className="rounded-2xl border border-slate-800/90 bg-[#10121C] overflow-hidden shadow-xl shadow-black/30 hover:border-slate-700/90 transition"
    >
      {/* Top Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-3 border-b border-slate-800/80 bg-[#141724]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-lg bg-violet-600/25 border border-violet-500/40 px-2.5 py-1 text-xs font-bold text-violet-200">
            <Flame className="w-3.5 h-3.5 text-amber-400" />
            #{clip.rank} VIRAL
          </span>
          <span className="rounded-lg bg-slate-800/80 px-2.5 py-1 text-xs font-mono text-slate-300">
            {fmtSec(clip.start)} – {fmtSec(clip.end)}
          </span>
          <span className="rounded-lg bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 text-[11px] font-semibold text-emerald-300 font-mono">
            {Math.round(clip.duration)}s ({t.under60s})
          </span>
        </div>

        <div className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1 ${scoreColor}`}>
          <span className="text-[11px] uppercase tracking-wider font-semibold opacity-85">
            {t.viralityScore}
          </span>
          <span className="text-base font-extrabold font-mono">{clip.virality_score}/100</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 p-4 sm:p-5">
        {/* Left: Video Player & Subtitle/Aspect Controls */}
        <div className="lg:col-span-4 flex flex-col items-center">
          <div
            className={`relative w-full ${
              isLandscape ? "aspect-video" : "max-w-[260px] aspect-[9/16]"
            } rounded-2xl overflow-hidden bg-black border border-slate-800 shadow-lg flex items-center justify-center`}
          >
            {isReady ? (
              <video
                key={`${clip.clip_id}-${renderNonce}`}
                controls
                playsInline
                preload="metadata"
                poster={thumbnail}
                src={videoUrl}
                className="w-full h-full object-contain bg-black"
              />
            ) : (
              <div className="relative w-full h-full flex flex-col items-center justify-center p-4 text-center">
                <img
                  src={thumbnail}
                  alt={title}
                  className="absolute inset-0 w-full h-full object-cover opacity-30 blur-sm"
                />
                <div className="relative z-10 flex flex-col items-center gap-2.5">
                  <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
                  <span className="text-xs font-medium text-slate-200">
                    {clip.render_status === "error"
                      ? `Error: ${clip.render_error || "Render failed"}`
                      : t.renderingWait}
                  </span>
                  {clip.cues[0] && (
                    <span className="mt-2 rounded-lg bg-black/75 px-2.5 py-1 text-[11px] font-bold text-amber-300 line-clamp-2">
                      "{clip.cues[0].text}"
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Quick Re-style Controls */}
          <div className="w-full max-w-[260px] mt-3 grid grid-cols-2 gap-2">
            <select
              value={aspectChoice}
              onChange={(e) => {
                setAspectChoice(e.target.value);
                handleRerender(e.target.value, styleChoice);
              }}
              className="rounded-lg bg-slate-900 border border-slate-700/80 px-2 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-violet-500"
            >
              <option value="9:16_crop">{t.aspectCrop}</option>
              <option value="9:16_blur">{t.aspectBlur}</option>
              <option value="16:9_original">{t.aspectOriginal}</option>
            </select>

            <select
              value={styleChoice}
              onChange={(e) => {
                setStyleChoice(e.target.value);
                handleRerender(aspectChoice, e.target.value);
              }}
              className="rounded-lg bg-slate-900 border border-slate-700/80 px-2 py-1.5 text-[11px] text-slate-200 focus:outline-none focus:border-violet-500"
            >
              <option value="viral_pop">{t.stylePop}</option>
              <option value="clean_minimal">{t.styleMinimal}</option>
              <option value="neon_cyber">{t.styleNeon}</option>
            </select>
          </div>
        </div>

        {/* Right: Metadata, Score Breakdown, Subtitles & 1-Click Download */}
        <div className="lg:col-span-8 flex flex-col gap-4">
          {/* Score Breakdown */}
          <div className="rounded-xl bg-[#0B0D14] border border-slate-800/80 p-3.5">
            <div className="flex items-center gap-2 text-xs font-medium text-violet-300 mb-2.5">
              <Sparkles className="w-3.5 h-3.5 text-violet-400 shrink-0" />
              <span>{clip.why_viral}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: t.hook, val: clip.score_breakdown.hook },
                { label: t.replayEnergy, val: clip.score_breakdown.replay_energy },
                { label: t.pacing, val: clip.score_breakdown.pacing },
                { label: t.shareability, val: clip.score_breakdown.shareability },
              ].map((m) => (
                <div key={m.label}>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                    <span>{m.label}</span>
                    <span className="font-mono font-semibold text-slate-200">{m.val}/25</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-violet-500 to-emerald-400"
                      style={{ width: `${Math.min(100, (m.val / 25) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Title */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                {t.titleLabel}
              </label>
              <button
                onClick={() => copyText(title, "title")}
                className="inline-flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200 cursor-pointer"
              >
                {copiedKey === "title" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedKey === "title" ? t.copied : "Copy"}
              </button>
            </div>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl bg-[#0B0D14] border border-slate-800 focus:border-violet-500 px-3 py-2 text-sm font-semibold text-white focus:outline-none"
            />
          </div>

          {/* Description */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                {t.descLabel}
              </label>
              <button
                onClick={() => copyText(description, "desc")}
                className="inline-flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200 cursor-pointer"
              >
                {copiedKey === "desc" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedKey === "desc" ? t.copied : "Copy"}
              </button>
            </div>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-xl bg-[#0B0D14] border border-slate-800 focus:border-violet-500 px-3 py-2 text-xs text-slate-300 leading-relaxed focus:outline-none resize-none"
            />
          </div>

          {/* Tags */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <Tag className="w-3 h-3" /> {t.tagsLabel}
              </span>
              <button
                onClick={() => copyText(clip.tags.join(", "), "tags")}
                className="inline-flex items-center gap-1 text-xs text-violet-300 hover:text-violet-200 cursor-pointer"
              >
                {copiedKey === "tags" ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedKey === "tags" ? t.copied : "Copy Tags"}
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {clip.tags.map((tg, i) => (
                <span
                  key={i}
                  className="rounded-lg bg-slate-900 border border-slate-800 px-2.5 py-0.5 text-[11px] text-slate-300"
                >
                  #{tg}
                </span>
              ))}
            </div>
          </div>

          {/* Expandable Auto-Subtitles Viewer / Editor */}
          <div className="rounded-xl border border-slate-800/80 bg-[#0B0D14]">
            <button
              onClick={() => setShowSubs((s) => !s)}
              className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs font-semibold text-slate-300 hover:text-white cursor-pointer"
            >
              <span className="inline-flex items-center gap-2">
                <Wand2 className="w-3.5 h-3.5 text-violet-400" />
                {t.subtitlesLabel} ({editedCues.length} lines • {t.editSubsHint})
              </span>
              {showSubs ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showSubs && (
              <div className="px-3.5 pb-3.5 pt-1 border-t border-slate-800/80 space-y-2">
                <div className="max-h-48 overflow-y-auto space-y-1.5 pr-1">
                  {editedCues.map((c, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="w-16 shrink-0 text-[10px] font-mono text-slate-500">
                        {c.start.toFixed(1)}s
                      </span>
                      <input
                        type="text"
                        value={c.text}
                        onChange={(e) => {
                          const next = [...editedCues];
                          next[idx] = { ...next[idx], text: e.target.value };
                          setEditedCues(next);
                        }}
                        className="flex-1 rounded-lg bg-slate-900 border border-slate-800 focus:border-violet-500 px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
                      />
                    </div>
                  ))}
                </div>
                <div className="flex justify-end pt-1">
                  <button
                    onClick={() => handleRerender()}
                    disabled={rerendering}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-60 px-3 py-1.5 text-xs font-semibold text-white cursor-pointer"
                  >
                    {rerendering ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    {t.reRenderBtn}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Primary One-Click Download & Secondary Actions */}
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <a
              href={downloadUrl}
              download={downloadFilename}
              className="flex-1 min-w-[200px] inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-violet-600/25 transition cursor-pointer"
            >
              {!isReady ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t.preparingMp4}
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  {t.downloadMp4}
                </>
              )}
            </a>

            <a
              href={downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              title="Direct Save in New Tab (fallback if preview iframe blocks direct download)"
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 px-3 py-2.5 text-xs font-semibold text-violet-300 transition"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Save ↗
            </a>

            <a
              href={srtUrl}
              download={`Top${String(clip.rank).padStart(2, "0")}_${safeTitle}.srt`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 px-3.5 py-2.5 text-xs font-semibold text-slate-200 transition"
            >
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              {t.downloadSrt}
            </a>

            <button
              onClick={() => copyText(copyAllPayload, "all")}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 px-3.5 py-2.5 text-xs font-semibold text-slate-200 transition cursor-pointer"
            >
              {copiedKey === "all" ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-slate-400" />
              )}
              {copiedKey === "all" ? t.copied : t.copyAll}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
};
