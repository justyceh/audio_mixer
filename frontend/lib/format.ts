import type { Media, MediaSource, TrackType } from "./types";

/** 83.456 -> "1:23.4" */
export function timecode(seconds: number, precision = 1): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  const width = precision > 0 ? 3 + precision : 2;
  return `${m}:${s.toFixed(precision).padStart(width, "0")}`;
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return new Date(iso).toLocaleDateString();
}

export const SOURCE_LABEL: Record<MediaSource, string> = {
  upload: "Uploaded",
  import: "Imported",
  extracted: "Extracted audio",
  trimmed: "Trimmed clip",
  isolated: "Separated",
  mixed: "Mix",
  export: "Export",
};

export const TRACK_LABEL: Record<TrackType, string> = {
  dialogue: "Dialogue",
  music: "Music",
  sfx: "Sound effects",
  other: "Other",
};

/** Name without the extension, for compact display. */
export function displayName(media: Pick<Media, "original_filename">): string {
  return media.original_filename.replace(/\.[a-z0-9]+$/i, "");
}

/** Colour role for a media item, used for waveform tints. */
export function mediaTone(media: Pick<Media, "original_filename" | "source">): TrackType {
  const name = media.original_filename.toLowerCase();
  if (media.source === "isolated" && name.includes("(vocals)")) return "dialogue";
  if (media.source === "isolated" && name.includes("(instrumental)")) return "music";
  if (media.source === "mixed" || media.source === "export") return "music";
  return "other";
}
