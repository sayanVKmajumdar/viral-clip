import React from "react";
import { Clock, Eye, Flame, PlayCircle } from "lucide-react";
import { ClipData, VideoMeta } from "../types";

interface Props {
  video: VideoMeta;
  heatmap: number[];
  clips: ClipData[];
  onSelectClip: (clipId: string) => void;
  t: Record<string, string>;
}

function fmtDur(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export const HeatmapTimeline: React.FC<Props> = ({
  video,
  heatmap,
  clips,
  onSelectClip,
  t,
}) => {
  const dur = Math.max(1, video.duration || 1);
  const w = 1000;
  const h = 84;

  // Build SVG polyline from heatmap points (or gentle fallback wave)
  const pts = heatmap.length > 2 ? heatmap : [0.3, 0.45, 0.52, 0.4, 0.65, 0.55, 0.72, 0.5, 0.6, 0.42];
  const coords = pts.map((v, i) => {
    const x = (i / Math.max(1, pts.length - 1)) * w;
    const y = h - 8 - Math.min(1, Math.max(0, v)) * (h - 20);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const areaPath = `M 0,${h} L ${coords.join(" L ")} L ${w},${h} Z`;
  const linePath = `M ${coords.join(" L ")}`;

  return (
    <div className="rounded-2xl border border-slate-800/90 bg-[#10121C] p-4 sm:p-5 shadow-xl shadow-black/30">
      <div className="flex flex-col md:flex-row gap-4 md:items-center justify-between">
        <div className="flex items-start sm:items-center gap-3.5 min-w-0">
          <div className="relative shrink-0 w-28 h-16 rounded-xl overflow-hidden border border-slate-700/70 bg-slate-900">
            <img
              src={video.thumbnail}
              alt={video.title}
              className="w-full h-full object-cover"
            />
            <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-white">
              {fmtDur(dur)}
            </span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-xs text-slate-400 mb-1">
              <PlayCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
              <span className="truncate font-medium text-slate-300">{video.channel}</span>
              {video.view_count ? (
                <span className="inline-flex items-center gap-1 text-slate-400 shrink-0">
                  • <Eye className="w-3 h-3" /> {video.view_count.toLocaleString()}
                </span>
              ) : null}
              <span className="inline-flex items-center gap-1 text-slate-400 shrink-0">
                • <Clock className="w-3 h-3" /> {fmtDur(dur)}
              </span>
            </div>
            <h2 className="text-sm sm:text-base font-semibold text-white line-clamp-2 leading-snug">
              {video.title}
            </h2>
          </div>
        </div>

        {video.has_heatmap && (
          <div className="shrink-0 inline-flex items-center gap-1.5 self-start md:self-center rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-medium text-emerald-300">
            <Flame className="w-3.5 h-3.5 text-emerald-400" />
            YouTube Replay Heatmap Active
          </div>
        )}
      </div>

      {clips.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-800/80">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <span className="text-xs font-medium text-slate-300">{t.timelineTitle}</span>
            <span className="text-[11px] text-slate-400">{t.clickMarker}</span>
          </div>

          <div className="relative rounded-xl bg-[#090B11] border border-slate-800/80 p-2 overflow-hidden">
            <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16 overflow-visible">
              <defs>
                <linearGradient id="hmGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.45" />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.02" />
                </linearGradient>
              </defs>
              <path d={areaPath} fill="url(#hmGrad)" />
              <path d={linePath} fill="none" stroke="#8b5cf6" strokeWidth="2.2" strokeOpacity="0.85" />

              {clips.map((c) => {
                const x1 = (c.start / dur) * w;
                const bw = Math.max(8, ((c.end - c.start) / dur) * w);
                const col =
                  c.virality_score >= 85
                    ? "#10b981"
                    : c.virality_score >= 72
                    ? "#f59e0b"
                    : "#a855f7";
                return (
                  <g
                    key={c.clip_id}
                    className="cursor-pointer group"
                    onClick={() => onSelectClip(c.clip_id)}
                  >
                    <rect
                      x={x1}
                      y={6}
                      width={bw}
                      height={h - 10}
                      rx={4}
                      fill={col}
                      fillOpacity={0.22}
                      stroke={col}
                      strokeWidth={1.5}
                    />
                  </g>
                );
              })}
            </svg>

            <div className="mt-2 flex flex-wrap gap-1.5">
              {clips.map((c) => (
                <button
                  key={c.clip_id}
                  onClick={() => onSelectClip(c.clip_id)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900/90 hover:bg-violet-600/25 border border-slate-700/70 hover:border-violet-500/60 px-2 py-1 text-[11px] font-medium text-slate-200 transition cursor-pointer"
                >
                  <span className="font-mono font-bold text-violet-400">#{c.rank}</span>
                  <span className="text-slate-400 font-mono">{fmtDur(c.start)}</span>
                  <span
                    className={`font-mono font-bold ${
                      c.virality_score >= 85
                        ? "text-emerald-400"
                        : c.virality_score >= 72
                        ? "text-amber-400"
                        : "text-violet-300"
                    }`}
                  >
                    {c.virality_score}/100
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
