export interface WordItem {
  text: string;
  start: number;
  end: number;
}

export interface CueItem {
  start: number;
  end: number;
  text: string;
  words?: WordItem[];
}

export interface ScoreBreakdown {
  hook: number;
  replay_energy: number;
  pacing: number;
  shareability: number;
}

export interface ClipData {
  clip_id: string;
  rank: number;
  start: number;
  end: number;
  duration: number;
  virality_score: number;
  score_breakdown: ScoreBreakdown;
  why_viral: string;
  title: string;
  description: string;
  tags: string[];
  transcript_text: string;
  cues: CueItem[];
  language: string;
  render_status: "pending" | "rendering" | "ready" | "error";
  render_error?: string | null;
  aspect_ratio: string;
  subtitle_style: string;
  file_size_bytes?: number;
}

export interface VideoMeta {
  id: string;
  title: string;
  channel: string;
  duration: number;
  thumbnail: string;
  view_count?: number;
  has_heatmap: boolean;
  url: string;
}

export interface JobState {
  job_id: string;
  status: "queued" | "analyzing" | "rendering" | "completed" | "error";
  step: string;
  step_message: string;
  progress: number;
  error?: string | null;
  video?: VideoMeta | null;
  heatmap: number[];
  settings: {
    aspect_ratio: string;
    subtitle_style: string;
    max_clips: number;
  };
  clips: ClipData[];
}
