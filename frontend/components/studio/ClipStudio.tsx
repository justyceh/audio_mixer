"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Waveform } from "@/components/Waveform";
import { useJobs, useJobSettled } from "@/components/jobs/JobsProvider";
import { api, errorMessage, streamUrl } from "@/lib/api";
import { bytes, displayName, mediaTone, SOURCE_LABEL, timecode } from "@/lib/format";
import type { AudioFormat, Media, Transcription } from "@/lib/types";
import { AddToProject } from "./AddToProject";
import { TranscriptPanel } from "./TranscriptPanel";

const SEPARATION_NOTE =
  "Separation uses Demucs, a model built for music. Voices come out well over a soundtrack, but sound effects and background noise can stay mixed in with the dialogue.";

export function ClipStudio({ mediaId }: { mediaId: string }) {
  const router = useRouter();
  const { track } = useJobs();
  const playerRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const stopAt = useRef<number | null>(null);

  const [media, setMedia] = useState<Media | null>(null);
  const [related, setRelated] = useState<Media[]>([]);
  const [transcripts, setTranscripts] = useState<Transcription[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [time, setTime] = useState(0);
  const [selection, setSelection] = useState<[number, number] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [format, setFormat] = useState<AudioFormat>("wav");
  const [language, setLanguage] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, all, tr] = await Promise.all([
        api.getMedia(mediaId),
        api.listMedia(),
        api.listTranscriptions(mediaId),
      ]);
      setMedia(m);
      setRelated(all.items.filter((x) => x.parent_media_id === mediaId || x.id === m.parent_media_id));
      setTranscripts(tr);
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, [mediaId]);

  useEffect(() => {
    queueMicrotask(load);
  }, [load]);

  useJobSettled((job) => {
    if (job.input_media_id === mediaId) load();
  });

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setActionError(null);
    try {
      await action();
    } catch (e) {
      setActionError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const seek = (t: number) => {
    const el = playerRef.current;
    if (el) el.currentTime = t;
    setTime(t);
  };

  const playRange = (range: [number, number]) => {
    const el = playerRef.current;
    if (!el) return;
    el.currentTime = range[0];
    stopAt.current = range[1];
    el.play();
  };

  if (loadError) {
    return (
      <div className="panel p-6 max-w-xl">
        <p className="text-danger font-bold">{loadError}</p>
        <Link href="/" className="btn mt-4">
          Back to library
        </Link>
      </div>
    );
  }
  if (!media) return <p className="text-muted">Loading…</p>;

  const tone = mediaTone(media);
  const sel = selection;
  const selLength = sel ? sel[1] - sel[0] : 0;
  const parent = related.find((r) => r.id === media.parent_media_id);
  const children = related.filter((r) => r.parent_media_id === media.id);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/" className="text-sm text-muted hover:text-ink font-bold">
            ← Library
          </Link>
          <h1 className="font-display text-2xl sm:text-3xl mt-1 break-words">{displayName(media)}</h1>
          <div className="flex flex-wrap gap-1.5 mt-2 text-xs">
            <span className="chip">{media.media_type === "video" ? "Video" : "Audio"}</span>
            <span className="chip">{SOURCE_LABEL[media.source]}</span>
            <span className="chip font-mono">{timecode(media.duration)}</span>
            <span className="chip">{media.format.toUpperCase()}</span>
            <span className="chip">{bytes(media.size_bytes)}</span>
            {parent && (
              <Link href={`/media/${parent.id}`} className="chip hover:bg-sunken">
                From: {displayName(parent)}
              </Link>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <a className="btn btn-sm" href={streamUrl(media)} download={media.original_filename}>
            Download
          </a>
          <button
            className="btn btn-sm"
            onClick={() =>
              confirm(`Delete "${displayName(media)}"? This can't be undone.`) &&
              run("delete", async () => {
                await api.deleteMedia(media.id);
                router.push("/");
              })
            }
          >
            Delete
          </button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px] items-start">
        {/* Player + waveform */}
        <section className="flex flex-col gap-4 min-w-0">
          <div className="panel overflow-hidden">
            {media.media_type === "video" ? (
              <video
                ref={playerRef}
                src={streamUrl(media)}
                controls
                className="w-full max-h-[420px] bg-black"
                onTimeUpdate={(e) => onTime(e.currentTarget)}
              />
            ) : (
              <div className="p-4">
                <audio
                  ref={playerRef}
                  src={streamUrl(media)}
                  controls
                  className="w-full"
                  onTimeUpdate={(e) => onTime(e.currentTarget)}
                />
              </div>
            )}
            <div className="border-t-2 border-line bg-sunken p-3">
              <Waveform
                media={media}
                tone={tone === "other" ? "dialogue" : tone}
                className="h-28"
                interactive
                selection={sel}
                playhead={time}
                onSeek={(t) => {
                  seek(t);
                  setSelection(null);
                }}
                onSelect={setSelection}
              />
              <p className="mt-2 text-xs text-muted">
                Drag across the waveform to select a line of dialogue. Click to jump to a moment.
              </p>
            </div>
          </div>

          {/* Selection bar */}
          <div className="panel p-4 flex flex-wrap items-end gap-3">
            <TimeField label="Start" value={sel?.[0]} max={media.duration} onChange={(v) => setSelection([v, Math.max(v + 0.1, sel?.[1] ?? media.duration)])} />
            <TimeField label="End" value={sel?.[1]} max={media.duration} onChange={(v) => setSelection([Math.min(sel?.[0] ?? 0, v - 0.1), v])} />
            <div className="text-sm pb-2">
              <span className="eyebrow block">Length</span>
              <span className="font-mono">{sel ? timecode(selLength, 2) : "—"}</span>
            </div>
            <div className="flex flex-wrap gap-2 ml-auto">
              <button className="btn btn-sm" disabled={!sel} onClick={() => sel && playRange(sel)}>
                ▶ Play selection
              </button>
              <button className="btn btn-sm btn-ghost" disabled={!sel} onClick={() => setSelection(null)}>
                Clear
              </button>
            </div>
          </div>

          {actionError && (
            <p role="alert" className="panel p-3 text-danger text-sm">
              {actionError}
            </p>
          )}

          <TranscriptPanel
            transcripts={transcripts}
            currentTime={time}
            onPick={(seg) => {
              setSelection([seg.start, Math.min(seg.end, media.duration)]);
              playRange([seg.start, Math.min(seg.end, media.duration)]);
            }}
          />
        </section>

        {/* Tools */}
        <aside className="flex flex-col gap-4">
          <ToolCard title="Save selection as a clip" hint={sel ? `${timecode(sel[0], 2)} → ${timecode(sel[1], 2)}` : "Select a region on the waveform first."}>
            <div className="flex gap-2">
              <select className="field w-24" value={format} onChange={(e) => setFormat(e.target.value as AudioFormat)} aria-label="Clip format">
                <option value="wav">WAV</option>
                <option value="mp3">MP3</option>
              </select>
              <button
                className="btn btn-primary flex-1"
                disabled={!sel || busy !== null}
                onClick={() =>
                  sel &&
                  run("trim", async () => {
                    const clip = await api.trim(media.id, sel[0], sel[1], format);
                    router.push(`/media/${clip.id}`);
                  })
                }
              >
                {busy === "trim" ? "Cutting…" : "Save clip"}
              </button>
            </div>
          </ToolCard>

          <ToolCard title="Separate voices from music" hint={SEPARATION_NOTE}>
            <button
              className="btn btn-blue w-full"
              disabled={busy !== null}
              onClick={() =>
                run("isolate", async () => {
                  const job = await api.isolate(media.id, "vocals");
                  track(job, `Separating voices · ${displayName(media)}`);
                })
              }
            >
              Separate voices
            </button>
            <p className="text-xs text-muted">Creates two new tracks: voices, and music + effects. Takes about a minute per 15 seconds of audio.</p>
          </ToolCard>

          <ToolCard title="Find the dialogue" hint="Transcribes speech with timestamps so you can jump straight to a line.">
            <div className="flex gap-2">
              <select className="field w-32" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Spoken language">
                <option value="">Auto-detect</option>
                <option value="ja">Japanese</option>
                <option value="en">English</option>
                <option value="ko">Korean</option>
                <option value="zh">Chinese</option>
                <option value="es">Spanish</option>
              </select>
              <button
                className="btn flex-1"
                disabled={busy !== null}
                onClick={() =>
                  run("transcribe", async () => {
                    const job = await api.transcribe(media.id, language);
                    track(job, `Transcribing · ${displayName(media)}`, `/media/${media.id}`);
                  })
                }
              >
                Transcribe
              </button>
            </div>
          </ToolCard>

          {media.media_type === "video" && (
            <ToolCard title="Extract audio" hint="Saves the soundtrack of this video as its own audio file.">
              <button
                className="btn w-full"
                disabled={busy !== null}
                onClick={() =>
                  run("extract", async () => {
                    const audio = await api.extract(media.id, "wav");
                    router.push(`/media/${audio.id}`);
                  })
                }
              >
                {busy === "extract" ? "Extracting…" : "Extract audio"}
              </button>
            </ToolCard>
          )}

          <AddToProject media={media} selection={sel} />

          {children.length > 0 && (
            <ToolCard title="Made from this">
              <ul className="flex flex-col gap-1.5">
                {children.map((c) => (
                  <li key={c.id}>
                    <Link href={`/media/${c.id}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-sunken">
                      <span className="flex items-center gap-2 min-w-0">
                        <ToneDot tone={mediaTone(c)} />
                        <span className="truncate text-sm font-bold">{displayName(c)}</span>
                      </span>
                      <span className="font-mono text-xs text-muted">{timecode(c.duration, 0)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </ToolCard>
          )}
        </aside>
      </div>
    </div>
  );

  function onTime(el: HTMLMediaElement) {
    setTime(el.currentTime);
    if (stopAt.current != null && el.currentTime >= stopAt.current) {
      el.pause();
      stopAt.current = null;
    }
  }
}

function ToolCard({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="panel p-4 flex flex-col gap-3">
      <div>
        <h2 className="font-bold">{title}</h2>
        {hint && <p className="text-xs text-muted mt-1">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function ToneDot({ tone }: { tone: string }) {
  const bg = { dialogue: "bg-dialogue", music: "bg-music", sfx: "bg-sfx", other: "bg-other" }[tone] ?? "bg-other";
  return <span className={`w-2.5 h-2.5 rounded-full border-[1.5px] border-line shrink-0 ${bg}`} aria-hidden="true" />;
}

function TimeField({ label, value, max, onChange }: { label: string; value?: number; max: number; onChange: (v: number) => void }) {
  return (
    <label className="text-sm">
      <span className="eyebrow block mb-1">{label} (s)</span>
      <input
        type="number"
        className="field w-28 font-mono"
        step={0.1}
        min={0}
        max={max}
        value={value !== undefined ? Number(value.toFixed(2)) : ""}
        placeholder="—"
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onChange(Math.min(max, Math.max(0, v)));
        }}
      />
    </label>
  );
}
