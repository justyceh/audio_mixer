// Mirrors the backend's Pydantic response models (backend/api/schemas).

export type MediaType = "audio" | "video";
export type MediaSource = "upload" | "import" | "extracted" | "trimmed" | "isolated" | "mixed" | "export";
export type TrackType = "dialogue" | "music" | "sfx" | "other";
export type JobType = "isolate" | "mix" | "transcribe" | "export" | "import";
export type JobStatus = "pending" | "processing" | "completed" | "failed";
export type AudioFormat = "wav" | "mp3";

export interface Media {
  id: string;
  original_filename: string;
  filename: string;
  media_type: MediaType;
  source: MediaSource;
  format: string;
  mime_type: string;
  duration: number;
  size_bytes: number;
  audio_codec: string | null;
  sample_rate: number | null;
  channels: number | null;
  parent_media_id: string | null;
  source_url: string | null;
  created_at: string;
  url: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Job {
  id: string;
  job_type: JobType;
  status: JobStatus;
  progress: number;
  result: Record<string, unknown> | null;
  input_media_id: string | null;
  project_id: string | null;
  output_media_id: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  updated_at: string;
  completed_at: string | null;
  status_url: string;
  download_url: string | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

export interface Transcription {
  id: string;
  media_id: string;
  job_id: string | null;
  model: string;
  language: string | null;
  text: string;
  segments: TranscriptSegment[];
  created_at: string;
}

export interface Clip {
  id: string;
  track_id: string;
  media_id: string;
  timeline_start: number;
  source_start: number;
  source_end: number;
  volume: number;
  fade_in: number;
  fade_out: number;
  media: Media;
}

export interface Track {
  id: string;
  project_id: string;
  name: string;
  track_type: TrackType;
  volume: number;
  muted: boolean;
  order_index: number;
  clips: Clip[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface Project extends ProjectSummary {
  tracks: Track[];
  duration: number;
}

export interface Health {
  status: string;
  database: boolean;
  ffmpeg: boolean;
  demucs: boolean;
  faster_whisper: boolean;
  yt_dlp: boolean;
}
