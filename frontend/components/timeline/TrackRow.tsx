"use client";

import { useRef, useState } from "react";
import { Waveform } from "@/components/Waveform";
import { displayName, TRACK_LABEL } from "@/lib/format";
import type { Clip, Track, TrackType } from "@/lib/types";

export const HEADER_W = 224;
const LANE_H = 76;

const FILL: Record<TrackType, string> = {
  dialogue: "bg-dialogue",
  music: "bg-music",
  sfx: "bg-sfx",
  other: "bg-other",
};

interface TrackRowProps {
  track: Track;
  pps: number;
  laneWidth: number;
  selected: boolean;
  selectedClipId: string | null;
  onSelectTrack: () => void;
  onSelectClip: (clip: Clip) => void;
  onMoveClip: (clip: Clip, timelineStart: number) => void;
  onSeek: (seconds: number) => void;
  onUpdate: (changes: Partial<Track>) => void;
  onDelete: () => void;
}

export function TrackRow(props: TrackRowProps) {
  const { track, pps, laneWidth, selected, onSelectTrack, onUpdate, onDelete } = props;

  return (
    <div className="flex border-b-2 border-line last:border-b-0" style={{ height: LANE_H }}>
      {/* Header (sticky so it stays visible while scrolling horizontally) */}
      <div
        style={{ width: HEADER_W }}
        className={`shrink-0 sticky left-0 z-10 border-r-2 border-line flex ${selected ? "bg-sunken" : "bg-surface"}`}
        onClick={onSelectTrack}
      >
        <div className={`w-2 shrink-0 ${FILL[track.track_type]} border-r-2 border-line`} aria-hidden="true" />
        <div className="flex-1 min-w-0 px-2 py-1.5 flex flex-col justify-between">
          <div className="flex items-center gap-1">
            <input
              key={track.name}
              defaultValue={track.name}
              aria-label="Track name"
              className="min-w-0 flex-1 bg-transparent font-bold text-sm truncate focus:outline-none focus:bg-surface rounded px-1"
              onBlur={(e) => e.target.value.trim() && e.target.value !== track.name && onUpdate({ name: e.target.value.trim() })}
              onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
            />
            <button
              className={`chip cursor-pointer ${track.muted ? "bg-ink text-paper" : "bg-surface"}`}
              onClick={(e) => {
                e.stopPropagation();
                onUpdate({ muted: !track.muted });
              }}
              aria-pressed={track.muted}
              title={track.muted ? "Unmute track" : "Mute track"}
            >
              M
            </button>
            <button
              className="text-muted hover:text-danger text-sm px-1"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              aria-label={`Remove ${track.name} track`}
              title="Remove track"
            >
              ✕
            </button>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={track.track_type}
              onChange={(e) => onUpdate({ track_type: e.target.value as TrackType })}
              aria-label="Track type"
              className="text-[11px] bg-transparent text-muted font-bold rounded focus:outline-none"
            >
              {(Object.keys(TRACK_LABEL) as TrackType[]).map((t) => (
                <option key={t} value={t}>
                  {TRACK_LABEL[t]}
                </option>
              ))}
            </select>
            <VolumeSlider value={track.volume} onCommit={(v) => onUpdate({ volume: v })} label={`${track.name} volume`} />
          </div>
        </div>
      </div>

      {/* Lane */}
      <div
        className={`relative ${track.muted ? "opacity-40" : ""}`}
        style={{ width: laneWidth }}
        onClick={(e) => {
          if (e.target !== e.currentTarget) return;
          onSelectTrack();
          const rect = e.currentTarget.getBoundingClientRect();
          props.onSeek(Math.max(0, (e.clientX - rect.left) / pps));
        }}
      >
        {track.clips.map((clip) => (
          <ClipBlock
            key={clip.id}
            clip={clip}
            tone={track.track_type}
            pps={pps}
            selected={props.selectedClipId === clip.id}
            onSelect={() => props.onSelectClip(clip)}
            onMove={(start) => props.onMoveClip(clip, start)}
          />
        ))}
      </div>
    </div>
  );
}

function VolumeSlider({ value, onCommit, label }: { value: number; onCommit: (v: number) => void; label: string }) {
  const [local, setLocal] = useState<number | null>(null);
  const shown = local ?? value;
  return (
    <span className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.stopPropagation()}>
      <input
        type="range"
        min={0}
        max={2}
        step={0.05}
        value={shown}
        aria-label={label}
        className="flex-1 min-w-0"
        onChange={(e) => setLocal(Number(e.target.value))}
        onPointerUp={() => local !== null && (onCommit(local), setLocal(null))}
        onKeyUp={() => local !== null && (onCommit(local), setLocal(null))}
      />
      <span className="font-mono text-[10px] text-muted w-8 text-right">{Math.round(shown * 100)}%</span>
    </span>
  );
}

function ClipBlock({
  clip,
  tone,
  pps,
  selected,
  onSelect,
  onMove,
}: {
  clip: Clip;
  tone: TrackType;
  pps: number;
  selected: boolean;
  onSelect: () => void;
  onMove: (timelineStart: number) => void;
}) {
  const [dragX, setDragX] = useState<number | null>(null);
  const origin = useRef<{ x: number; moved: boolean } | null>(null);
  const length = clip.source_end - clip.source_start;
  const offset = dragX ?? 0;
  const left = Math.max(0, clip.timeline_start * pps + offset);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${displayName(clip.media)}, starts at ${clip.timeline_start.toFixed(1)} seconds`}
      aria-pressed={selected}
      className={`absolute top-1.5 bottom-1.5 rounded-lg border-2 border-line overflow-hidden cursor-grab active:cursor-grabbing touch-none ${FILL[tone]} ${
        selected ? "shadow-[3px_3px_0_var(--shadow)] ring-2 ring-offset-1 ring-ink z-10" : ""
      }`}
      style={{ left, width: Math.max(8, length * pps) }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        origin.current = { x: e.clientX, moved: false };
        onSelect();
      }}
      onPointerMove={(e) => {
        if (!origin.current) return;
        const dx = e.clientX - origin.current.x;
        if (Math.abs(dx) > 3) origin.current.moved = true;
        if (origin.current.moved) setDragX(dx);
      }}
      onPointerUp={() => {
        if (origin.current?.moved && dragX !== null) {
          onMove(Number(Math.max(0, clip.timeline_start + dragX / pps).toFixed(3)));
        }
        origin.current = null;
        setDragX(null);
      }}
      onKeyDown={(e) => {
        // Arrow keys nudge the clip by 0.1 s (1 s with Shift).
        const step = e.shiftKey ? 1 : 0.1;
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
          e.preventDefault();
          const next = clip.timeline_start + (e.key === "ArrowLeft" ? -step : step);
          onMove(Number(Math.max(0, next).toFixed(3)));
        }
      }}
    >
      <div className="absolute inset-0 bg-surface/80 mix-blend-normal" style={{ top: 20 }} />
      <p className="relative px-1.5 text-[11px] font-bold text-white truncate leading-5 [text-shadow:0_1px_0_rgba(0,0,0,.35)]">
        {displayName(clip.media)}
      </p>
      <Waveform
        media={clip.media}
        tone={tone}
        start={clip.source_start}
        end={clip.source_end}
        className="absolute left-0 right-0 bottom-0.5 top-[22px] px-0.5 pointer-events-none"
      />
      {clip.fade_in > 0 && <FadeMark side="left" width={Math.min(clip.fade_in, length) * pps} />}
      {clip.fade_out > 0 && <FadeMark side="right" width={Math.min(clip.fade_out, length) * pps} />}
    </div>
  );
}

function FadeMark({ side, width }: { side: "left" | "right"; width: number }) {
  return (
    <svg
      className="absolute top-[20px] bottom-0 pointer-events-none"
      style={{ [side]: 0, width, height: "calc(100% - 20px)" }}
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path d={side === "left" ? "M0 100 L100 0 L0 0 Z" : "M0 0 L100 100 L100 0 Z"} fill="var(--ink)" opacity="0.18" />
    </svg>
  );
}
