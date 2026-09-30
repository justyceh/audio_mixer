"use client";

import { streamUrl } from "./api";
import type { Media } from "./types";

// Browser-side audio helpers: decoding for waveforms and timeline preview playback.

let ctx: AudioContext | null = null;

export function audioContext(): AudioContext {
  if (!ctx) ctx = new AudioContext();
  return ctx;
}

const buffers = new Map<string, Promise<AudioBuffer>>();

/** Fetch + decode a media file once; results are cached per media id. */
export function loadBuffer(media: Pick<Media, "id" | "url">): Promise<AudioBuffer> {
  let pending = buffers.get(media.id);
  if (!pending) {
    pending = fetch(streamUrl(media))
      .then((r) => {
        if (!r.ok) throw new Error(`Could not load audio (${r.status})`);
        return r.arrayBuffer();
      })
      .then((data) => audioContext().decodeAudioData(data));
    pending.catch(() => buffers.delete(media.id));
    buffers.set(media.id, pending);
  }
  return pending;
}

/** Peak amplitude (0..1) per bucket across all channels for [start, end) seconds. */
export function computePeaks(buffer: AudioBuffer, buckets: number, start = 0, end = buffer.duration): Float32Array {
  const peaks = new Float32Array(Math.max(1, buckets));
  const from = Math.max(0, Math.floor(start * buffer.sampleRate));
  const to = Math.min(buffer.length, Math.ceil(end * buffer.sampleRate));
  const span = Math.max(1, to - from);
  const channels = Array.from({ length: buffer.numberOfChannels }, (_, i) => buffer.getChannelData(i));
  const step = span / peaks.length;
  // Sample at most ~200 points per bucket so long files stay fast.
  const stride = Math.max(1, Math.floor(step / 200));
  let max = 0;
  for (let b = 0; b < peaks.length; b++) {
    const s0 = from + Math.floor(b * step);
    const s1 = Math.min(to, from + Math.floor((b + 1) * step));
    let peak = 0;
    for (const data of channels) {
      for (let i = s0; i < s1; i += stride) {
        const v = Math.abs(data[i]);
        if (v > peak) peak = v;
      }
    }
    peaks[b] = peak;
    if (peak > max) max = peak;
  }
  if (max > 0) for (let b = 0; b < peaks.length; b++) peaks[b] /= max;
  return peaks;
}

export interface PreviewClip {
  media: Media;
  timelineStart: number;
  sourceStart: number;
  sourceEnd: number;
  gain: number;
  fadeIn: number;
  fadeOut: number;
}

/**
 * Schedule a timeline for playback starting at `from` seconds.
 * Returns a stop function. Mirrors the backend mixer: trim, gain, fades, offsets.
 */
export async function playTimeline(clips: PreviewClip[], from: number): Promise<{ stop: () => void; startedAt: number }> {
  const ac = audioContext();
  if (ac.state === "suspended") await ac.resume();
  const loaded = await Promise.all(clips.map(async (c) => ({ clip: c, buffer: await loadBuffer(c.media) })));
  const master = ac.createGain();
  master.connect(ac.destination);
  const t0 = ac.currentTime + 0.08;
  const sources: AudioBufferSourceNode[] = [];

  for (const { clip, buffer } of loaded) {
    const length = clip.sourceEnd - clip.sourceStart;
    const clipEnd = clip.timelineStart + length;
    if (clipEnd <= from) continue;
    const skip = Math.max(0, from - clip.timelineStart);
    const when = t0 + Math.max(0, clip.timelineStart - from);

    const source = ac.createBufferSource();
    source.buffer = buffer;
    const gain = ac.createGain();
    source.connect(gain).connect(master);

    // Gain envelope in absolute context time.
    const clipZero = when - skip; // context time where the clip's local t=0 would be
    const g = gain.gain;
    const fi = Math.min(clip.fadeIn, length);
    const fo = Math.min(clip.fadeOut, length);
    g.setValueAtTime(fi > 0 && skip < fi ? clip.gain * (skip / fi) : clip.gain, when);
    if (fi > 0 && skip < fi) g.linearRampToValueAtTime(clip.gain, clipZero + fi);
    if (fo > 0) {
      const foStart = Math.max(clipZero + length - fo, when);
      g.setValueAtTime(clip.gain, foStart);
      g.linearRampToValueAtTime(0, clipZero + length);
    }
    source.start(when, clip.sourceStart + skip, length - skip);
    sources.push(source);
  }

  return {
    startedAt: t0,
    stop: () => {
      for (const s of sources) {
        try {
          s.stop();
        } catch {
          // already stopped
        }
      }
      master.disconnect();
    },
  };
}
