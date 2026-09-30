"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { displayName, timecode } from "@/lib/format";
import type { Clip, Track } from "@/lib/types";

type Editable = Pick<Clip, "timeline_start" | "source_start" | "source_end" | "volume" | "fade_in" | "fade_out">;

/** Edit one clip. Changes save automatically shortly after you stop adjusting. */
export function ClipInspector({
  clip,
  tracks,
  onChange,
  onRemove,
  onClose,
}: {
  clip: Clip;
  tracks: Track[];
  onChange: (changes: Partial<Clip>) => void;
  onRemove: () => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Editable>(() => pick(clip));
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<Partial<Editable>>({});
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  });

  // Flush unsaved edits when the inspector closes or switches clips.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      if (Object.keys(pending.current).length) onChangeRef.current(pending.current);
    },
    [],
  );

  const set = (changes: Partial<Editable>) => {
    const next = { ...draft, ...changes };
    const length = next.source_end - next.source_start;
    if (length <= 0.05) return;
    setDraft(next);
    pending.current = { ...pending.current, ...changes };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const toSave = pending.current;
      pending.current = {};
      onChangeRef.current(toSave);
    }, 450);
  };

  const length = draft.source_end - draft.source_start;
  const duration = clip.media.duration;

  return (
    <section className="panel p-4 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="eyebrow">Selected clip</p>
          <h2 className="font-bold truncate">{displayName(clip.media)}</h2>
          <p className="text-xs text-muted font-mono">
            {timecode(draft.timeline_start)} → {timecode(draft.timeline_start + length)} · {timecode(length, 2)} long
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close clip settings">
          ✕
        </button>
      </div>

      <Slider label="Volume" value={draft.volume} min={0} max={2} step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => set({ volume: v })} />
      <div className="grid grid-cols-2 gap-4">
        <Slider label="Fade in" value={draft.fade_in} min={0} max={Math.min(10, length)} step={0.1} format={(v) => `${v.toFixed(1)} s`} onChange={(v) => set({ fade_in: v })} />
        <Slider label="Fade out" value={draft.fade_out} min={0} max={Math.min(10, length)} step={0.1} format={(v) => `${v.toFixed(1)} s`} onChange={(v) => set({ fade_out: v })} />
      </div>

      <fieldset className="grid grid-cols-3 gap-3">
        <legend className="eyebrow mb-2">Timing (seconds)</legend>
        <NumberField label="Starts at" value={draft.timeline_start} min={0} onChange={(v) => set({ timeline_start: v })} />
        <NumberField label="Trim start" value={draft.source_start} min={0} max={draft.source_end - 0.1} onChange={(v) => set({ source_start: v })} />
        <NumberField label="Trim end" value={draft.source_end} min={draft.source_start + 0.1} max={duration} onChange={(v) => set({ source_end: v })} />
      </fieldset>

      <label className="text-sm">
        <span className="eyebrow block mb-1">Track</span>
        <select className="field" value={clip.track_id} onChange={(e) => onChange({ track_id: e.target.value })}>
          {tracks.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-wrap gap-2">
        <Link className="btn btn-sm" href={`/media/${clip.media_id}`}>
          Open source
        </Link>
        <button className="btn btn-sm ml-auto text-danger" onClick={onRemove}>
          Remove from timeline
        </button>
      </div>
    </section>
  );
}

function pick(c: Clip): Editable {
  return {
    timeline_start: c.timeline_start,
    source_start: c.source_start,
    source_end: c.source_end,
    volume: c.volume,
    fade_in: c.fade_in,
    fade_out: c.fade_out,
  };
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="text-sm">
      <span className="flex justify-between mb-1">
        <span className="eyebrow">{label}</span>
        <span className="font-mono text-xs">{format(value)}</span>
      </span>
      <input type="range" className="w-full" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  const [text, setText] = useState(value.toFixed(2));
  const [focused, setFocused] = useState(false);
  return (
    <label className="text-sm">
      <span className="text-xs text-muted block mb-1">{label}</span>
      <input
        type="number"
        step={0.1}
        min={min}
        max={max}
        className="field font-mono px-2"
        value={focused ? text : value.toFixed(2)}
        onFocus={() => {
          setText(value.toFixed(2));
          setFocused(true);
        }}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          setFocused(false);
          let v = parseFloat(text);
          if (!Number.isFinite(v)) return;
          if (min !== undefined) v = Math.max(min, v);
          if (max !== undefined) v = Math.min(max, v);
          if (Math.abs(v - value) > 0.0005) onChange(Number(v.toFixed(3)));
        }}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
    </label>
  );
}
