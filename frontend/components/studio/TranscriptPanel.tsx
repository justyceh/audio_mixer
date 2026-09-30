"use client";

import { timecode } from "@/lib/format";
import type { TranscriptSegment, Transcription } from "@/lib/types";

export function TranscriptPanel({
  transcripts,
  currentTime,
  onPick,
}: {
  transcripts: Transcription[];
  currentTime: number;
  onPick: (segment: TranscriptSegment) => void;
}) {
  const latest = transcripts[0];
  if (!latest) return null;

  return (
    <section className="panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h2 className="font-bold">Dialogue</h2>
        <span className="text-xs text-muted">
          {latest.segments.length} lines{latest.language ? ` · ${latest.language.toUpperCase()}` : ""} · click a line to select it
        </span>
      </div>
      {latest.segments.length === 0 ? (
        <p className="text-sm text-muted">No speech was detected in this file.</p>
      ) : (
        <ol className="flex flex-col max-h-80 overflow-y-auto -mx-1">
          {latest.segments.map((seg, i) => {
            const active = currentTime >= seg.start && currentTime < seg.end;
            return (
              <li key={i}>
                <button
                  onClick={() => onPick(seg)}
                  className={`w-full text-left flex gap-3 rounded-lg px-2 py-1.5 border-2 ${
                    active ? "border-line bg-dialogue/15" : "border-transparent hover:bg-sunken"
                  }`}
                >
                  <span className="font-mono text-xs text-muted pt-0.5 shrink-0 w-24">
                    {timecode(seg.start)}–{timecode(seg.end)}
                  </span>
                  <span className="text-sm">{seg.text}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
