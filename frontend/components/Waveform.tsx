"use client";

import { useEffect, useRef, useState } from "react";
import { computePeaks, loadBuffer } from "@/lib/audio";
import type { Media, TrackType } from "@/lib/types";

interface WaveformProps {
  media: Pick<Media, "id" | "url">;
  tone?: TrackType | "ink";
  /** Visible source window in seconds (defaults to the whole file). */
  start?: number;
  end?: number;
  className?: string;
  /** Selected region in source seconds, drawn as a highlight. */
  selection?: [number, number] | null;
  playhead?: number | null;
  /** Enables click-to-seek and drag-to-select. */
  interactive?: boolean;
  onSeek?: (seconds: number) => void;
  onSelect?: (range: [number, number]) => void;
}

const COLORS: Record<string, string> = {
  dialogue: "--dialogue",
  music: "--music",
  sfx: "--sfx",
  other: "--other",
  ink: "--ink",
};

export function Waveform({
  media,
  tone = "other",
  start = 0,
  end,
  className = "",
  selection,
  playhead,
  interactive = false,
  onSeek,
  onSelect,
}: WaveformProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [buffer, setBuffer] = useState<AudioBuffer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const drag = useRef<{ from: number; moved: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadBuffer(media)
      .then((b) => !cancelled && setBuffer(b))
      .catch(() => !cancelled && setError("Waveform unavailable"));
    return () => {
      cancelled = true;
    };
  }, [media]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const windowEnd = end ?? buffer?.duration ?? 0;
  const span = Math.max(0.001, windowEnd - start);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !buffer || size.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    const g = canvas.getContext("2d");
    if (!g) return;
    g.scale(dpr, dpr);
    g.clearRect(0, 0, size.w, size.h);

    const styles = getComputedStyle(canvas);
    const color = styles.getPropertyValue(COLORS[tone] ?? "--other").trim() || "#888";
    const barW = 2;
    const gap = 1;
    const count = Math.max(1, Math.floor(size.w / (barW + gap)));
    const peaks = computePeaks(buffer, count, start, windowEnd);
    const mid = size.h / 2;

    if (selection) {
      const x0 = ((selection[0] - start) / span) * size.w;
      const x1 = ((selection[1] - start) / span) * size.w;
      g.fillStyle = color;
      g.globalAlpha = 0.16;
      g.fillRect(x0, 0, x1 - x0, size.h);
      g.globalAlpha = 1;
    }

    for (let i = 0; i < peaks.length; i++) {
      const x = i * (barW + gap);
      const t = start + ((x + barW / 2) / size.w) * span;
      const inSel = !selection || (t >= selection[0] && t <= selection[1]);
      const h = Math.max(1.5, peaks[i] * (size.h - 4));
      g.fillStyle = color;
      g.globalAlpha = inSel ? 1 : 0.3;
      g.fillRect(x, mid - h / 2, barW, h);
    }
    g.globalAlpha = 1;

    if (selection) {
      g.fillStyle = styles.getPropertyValue("--ink").trim();
      for (const s of selection) {
        const x = ((s - start) / span) * size.w;
        g.fillRect(x - 1, 0, 2, size.h);
      }
    }
  }, [buffer, size, tone, start, windowEnd, span, selection]);

  const timeAt = (clientX: number) => {
    const rect = wrapRef.current!.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    return start + f * span;
  };

  const handlers = interactive
    ? {
        onPointerDown: (e: React.PointerEvent) => {
          (e.target as Element).setPointerCapture(e.pointerId);
          drag.current = { from: timeAt(e.clientX), moved: false };
        },
        onPointerMove: (e: React.PointerEvent) => {
          if (!drag.current) return;
          const now = timeAt(e.clientX);
          if (Math.abs(now - drag.current.from) > span * 0.005) {
            drag.current.moved = true;
            onSelect?.([Math.min(drag.current.from, now), Math.max(drag.current.from, now)]);
          }
        },
        onPointerUp: (e: React.PointerEvent) => {
          if (drag.current && !drag.current.moved) onSeek?.(timeAt(e.clientX));
          drag.current = null;
        },
      }
    : {};

  return (
    <div
      ref={wrapRef}
      className={`relative select-none ${interactive ? "cursor-crosshair touch-none" : ""} ${className}`}
      {...handlers}
    >
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      {!buffer && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">
          {error ?? "Drawing waveform…"}
        </div>
      )}
      {playhead != null && playhead >= start && playhead <= windowEnd && (
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-ink pointer-events-none"
          style={{ left: `${((playhead - start) / span) * 100}%` }}
        />
      )}
    </div>
  );
}
