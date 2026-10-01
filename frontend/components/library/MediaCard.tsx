import Link from "next/link";
import { Waveform } from "@/components/Waveform";
import { displayName, mediaTone, relativeTime, SOURCE_LABEL, timecode } from "@/lib/format";
import type { Media } from "@/lib/types";

// Card thumbnails decode the whole file in the browser, so skip big ones.
const WAVEFORM_MAX_BYTES = 40 * 1024 * 1024;

export function MediaCard({ media }: { media: Media }) {
  const tone = mediaTone(media);
  return (
    <Link
      href={`/media/${media.id}`}
      className="panel group flex flex-col overflow-hidden hover:-translate-x-px hover:-translate-y-px transition-transform"
    >
      <div className="h-20 bg-sunken border-b-2 border-line px-3 py-2">
        {media.size_bytes <= WAVEFORM_MAX_BYTES ? (
          <Waveform media={media} tone={tone === "other" ? "ink" : tone} className="h-full" />
        ) : (
          <div className="h-full flex items-center justify-center text-xs text-muted">Open to see the waveform</div>
        )}
      </div>
      <div className="p-3 flex flex-col gap-2 min-w-0">
        <p className="font-bold leading-snug line-clamp-2 break-words" title={media.original_filename}>
          {displayName(media)}
        </p>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="chip">{media.media_type === "video" ? "Video" : "Audio"}</span>
          <span className="chip">{SOURCE_LABEL[media.source]}</span>
          <span className="font-mono text-muted ml-auto">{timecode(media.duration, 0)}</span>
        </div>
        <p className="text-xs text-muted">{relativeTime(media.created_at)}</p>
      </div>
    </Link>
  );
}
