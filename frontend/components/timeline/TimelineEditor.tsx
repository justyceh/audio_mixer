"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useJobs, useJobSettled } from "@/components/jobs/JobsProvider";
import { api, downloadUrl, errorMessage } from "@/lib/api";
import { audioContext, playTimeline, type PreviewClip } from "@/lib/audio";
import { TRACK_LABEL, timecode } from "@/lib/format";
import type { AudioFormat, Clip, Job, Project, Track, TrackType } from "@/lib/types";
import { ClipInspector } from "./ClipInspector";
import { MediaBin } from "./MediaBin";
import { TrackRow, HEADER_W } from "./TrackRow";

const MIN_PPS = 10;
const MAX_PPS = 200;

export function TimelineEditor({ projectId }: { projectId: string }) {
  const { track: trackJob, jobs } = useJobs();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [selectedTrackId, setSelectedTrackId] = useState<string | null>(null);
  const [pps, setPps] = useState(40); // pixels per second
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [exportFormat, setExportFormat] = useState<AudioFormat>("mp3");
  const [lastExport, setLastExport] = useState<Job | null>(null);
  const playback = useRef<{ stop: () => void; raf: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await api.getProject(projectId);
      setProject(p);
      setSelectedTrackId((cur) => cur ?? p.tracks[0]?.id ?? null);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(load);
  }, [load]);

  useJobSettled((job) => {
    if (job.job_type === "export" && job.project_id === projectId) setLastExport(job);
  });

  const exportJob = jobs.find((j) => j.job.job_type === "export" && j.job.project_id === projectId)?.job;
  const exporting = exportJob && (exportJob.status === "pending" || exportJob.status === "processing");

  // --- Local state helpers ---------------------------------------------------
  const replaceClip = (clip: Clip) =>
    setProject((p) =>
      p && {
        ...p,
        tracks: p.tracks.map((t) => ({
          ...t,
          clips: t.id === clip.track_id ? [...t.clips.filter((c) => c.id !== clip.id), clip] : t.clips.filter((c) => c.id !== clip.id),
        })),
      },
    );

  const replaceTrack = (track: Partial<Track> & { id: string }) =>
    setProject((p) => p && { ...p, tracks: p.tracks.map((t) => (t.id === track.id ? { ...t, ...track, clips: t.clips } : t)) });

  const report = (e: unknown) => {
    setNotice(errorMessage(e));
    load();
  };

  // --- Mutations -----------------------------------------------------------------
  async function saveClip(clip: Clip, changes: Partial<Clip>) {
    replaceClip({ ...clip, ...changes });
    try {
      replaceClip(await api.updateClip(clip.id, changes));
    } catch (e) {
      report(e);
    }
  }

  async function removeClip(clip: Clip) {
    setSelectedClipId(null);
    setProject((p) => p && { ...p, tracks: p.tracks.map((t) => ({ ...t, clips: t.clips.filter((c) => c.id !== clip.id) })) });
    try {
      await api.deleteClip(clip.id);
    } catch (e) {
      report(e);
    }
  }

  async function saveTrack(track: Track, changes: Partial<Track>) {
    replaceTrack({ id: track.id, ...changes });
    try {
      replaceTrack(await api.updateTrack(track.id, changes));
    } catch (e) {
      report(e);
    }
  }

  async function removeTrack(track: Track) {
    if (track.clips.length && !confirm(`Remove the "${track.name}" track and its ${track.clips.length} clip(s)?`)) return;
    try {
      await api.deleteTrack(track.id);
      if (selectedTrackId === track.id) setSelectedTrackId(null);
      load();
    } catch (e) {
      report(e);
    }
  }

  async function addTrack(type: TrackType) {
    try {
      const t = await api.createTrack(projectId, { name: TRACK_LABEL[type], track_type: type });
      setSelectedTrackId(t.id);
      load();
    } catch (e) {
      report(e);
    }
  }

  async function rename(name: string) {
    if (!project || !name.trim() || name === project.name) return;
    try {
      const p = await api.renameProject(project.id, name.trim());
      setProject((cur) => cur && { ...cur, name: p.name, updated_at: p.updated_at });
    } catch (e) {
      report(e);
    }
  }

  async function startExport() {
    try {
      const job = await api.exportProject(projectId, exportFormat);
      trackJob(job, `Exporting ${project?.name ?? "project"} (${exportFormat.toUpperCase()})`);
      setLastExport(null);
    } catch (e) {
      setNotice(errorMessage(e));
    }
  }

  // --- Preview playback ------------------------------------------------------------
  const stop = useCallback(() => {
    if (playback.current) {
      playback.current.stop();
      cancelAnimationFrame(playback.current.raf);
      playback.current = null;
    }
    setPlaying(false);
  }, []);

  useEffect(() => stop, [stop]);

  const previewClips = useMemo<PreviewClip[]>(
    () =>
      project?.tracks
        .filter((t) => !t.muted)
        .flatMap((t) =>
          t.clips.map((c) => ({
            media: c.media,
            timelineStart: c.timeline_start,
            sourceStart: c.source_start,
            sourceEnd: c.source_end,
            gain: Math.min(4, t.volume * c.volume),
            fadeIn: c.fade_in,
            fadeOut: c.fade_out,
          })),
        ) ?? [],
    [project],
  );

  async function play() {
    if (!project) return;
    stop();
    const from = playhead >= project.duration ? 0 : playhead;
    setPlaying(true);
    try {
      const { stop: stopAudio, startedAt } = await playTimeline(previewClips, from);
      const ac = audioContext();
      const tick = () => {
        const t = from + Math.max(0, ac.currentTime - startedAt);
        setPlayhead(t);
        if (t >= project.duration) {
          stop();
          return;
        }
        if (playback.current) playback.current.raf = requestAnimationFrame(tick);
      };
      playback.current = { stop: stopAudio, raf: requestAnimationFrame(tick) };
    } catch (e) {
      setPlaying(false);
      setNotice(`Preview failed: ${errorMessage(e)}`);
    }
  }

  // Space toggles playback (outside of form fields).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.code !== "Space" || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;
      e.preventDefault();
      if (playback.current) stop();
      else document.getElementById("play-toggle")?.click();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stop]);

  if (error) {
    return (
      <div className="panel p-6 max-w-xl">
        <p className="text-danger font-bold">{error}</p>
        <Link href="/projects" className="btn mt-4">
          Back to projects
        </Link>
      </div>
    );
  }
  if (!project) return <p className="text-muted">Loading project…</p>;

  const selectedClip = project.tracks.flatMap((t) => t.clips).find((c) => c.id === selectedClipId) ?? null;
  const selectedClipTrack = selectedClip ? project.tracks.find((t) => t.id === selectedClip.track_id) ?? null : null;
  const lanesSeconds = Math.max(30, project.duration + 15);
  const laneWidth = lanesSeconds * pps;
  const hasClips = project.tracks.some((t) => t.clips.length);
  const doneExport = lastExport?.status === "completed" ? lastExport : null;

  return (
    <div className="flex flex-col gap-5">
      {/* Title + transport */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link href="/projects" className="text-sm text-muted hover:text-ink font-bold">
            ← Projects
          </Link>
          <input
            key={project.name}
            defaultValue={project.name}
            aria-label="Project name"
            className="block font-display text-2xl sm:text-3xl bg-transparent border-b-2 border-transparent hover:border-line focus:border-line focus:outline-none w-full max-w-xl mt-1"
            onBlur={(e) => rename(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="field w-24" value={exportFormat} onChange={(e) => setExportFormat(e.target.value as AudioFormat)} aria-label="Export format">
            <option value="mp3">MP3</option>
            <option value="wav">WAV</option>
          </select>
          <button className="btn btn-primary" disabled={!hasClips || !!exporting} onClick={startExport}>
            {exporting ? `Exporting… ${exportJob?.progress ?? 0}%` : "Export remix"}
          </button>
          {doneExport && (
            <a className="btn btn-blue" href={downloadUrl(doneExport)}>
              Download export
            </a>
          )}
        </div>
      </div>

      {notice && (
        <div role="alert" className="panel p-3 flex items-start justify-between gap-3 text-sm">
          <span className="text-danger">{notice}</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setNotice(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      {/* Timeline */}
      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b-2 border-line px-3 py-2 bg-sunken">
          <button id="play-toggle" className="btn btn-sm w-24" disabled={!hasClips} onClick={playing ? stop : play}>
            {playing ? "■ Stop" : "▶ Play"}
          </button>
          <button className="btn btn-sm btn-ghost" onClick={() => (stop(), setPlayhead(0))} aria-label="Back to start">
            ⏮
          </button>
          <span className="font-mono text-sm tabular-nums">
            {timecode(playhead)} / {timecode(project.duration)}
          </span>
          <label className="flex items-center gap-2 text-xs text-muted ml-auto">
            Zoom
            <input type="range" min={MIN_PPS} max={MAX_PPS} value={pps} onChange={(e) => setPps(Number(e.target.value))} className="w-28" />
          </label>
        </div>

        <div className="overflow-x-auto">
          <div style={{ width: HEADER_W + laneWidth }} className="relative">
            <Ruler seconds={lanesSeconds} pps={pps} onSeek={(t) => (stop(), setPlayhead(t))} />
            {project.tracks.length === 0 && (
              <p className="p-6 text-sm text-muted" style={{ marginLeft: HEADER_W }}>
                Add a track below to start building your remix.
              </p>
            )}
            {project.tracks.map((t) => (
              <TrackRow
                key={t.id}
                track={t}
                pps={pps}
                laneWidth={laneWidth}
                selected={selectedTrackId === t.id}
                selectedClipId={selectedClipId}
                onSelectTrack={() => setSelectedTrackId(t.id)}
                onSelectClip={(c) => {
                  setSelectedClipId(c.id);
                  setSelectedTrackId(t.id);
                }}
                onMoveClip={(c, start) => saveClip(c, { timeline_start: start })}
                onSeek={(s) => (stop(), setPlayhead(s))}
                onUpdate={(changes) => saveTrack(t, changes)}
                onDelete={() => removeTrack(t)}
              />
            ))}
            {/* Playhead */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-dialogue pointer-events-none z-20"
              style={{ left: HEADER_W + playhead * pps }}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t-2 border-line px-3 py-2">
          <span className="text-xs text-muted mr-1">Add track:</span>
          {(Object.keys(TRACK_LABEL) as TrackType[]).map((type) => (
            <button key={type} className="btn btn-sm" onClick={() => addTrack(type)}>
              + {TRACK_LABEL[type]}
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr] items-start">
        {selectedClip && selectedClipTrack ? (
          <ClipInspector
            key={`${selectedClip.id}-${selectedClip.timeline_start}-${selectedClip.track_id}`}
            clip={selectedClip}
            tracks={project.tracks}
            onChange={(changes) => saveClip(selectedClip, changes)}
            onRemove={() => removeClip(selectedClip)}
            onClose={() => setSelectedClipId(null)}
          />
        ) : (
          <div className="border-2 border-dashed border-line rounded-2xl p-6 text-sm text-muted">
            <p className="font-bold text-ink mb-1">How to edit</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>Drag a clip left or right to move it in time.</li>
              <li>Click a clip to change its volume, fades or trim.</li>
              <li>Click the ruler to move the playhead, then press Space to preview.</li>
              <li>Pick a track, then add media from the list to drop it at the playhead.</li>
            </ul>
          </div>
        )}
        <MediaBin
          targetTrack={project.tracks.find((t) => t.id === selectedTrackId) ?? null}
          playhead={playhead}
          onAdded={(clip) => {
            replaceClip(clip);
            setSelectedClipId(clip.id);
            load();
          }}
          onError={(e) => setNotice(errorMessage(e))}
        />
      </div>
    </div>
  );
}

function Ruler({ seconds, pps, onSeek }: { seconds: number; pps: number; onSeek: (t: number) => void }) {
  const step = pps >= 80 ? 1 : pps >= 30 ? 5 : 10;
  const marks = Array.from({ length: Math.floor(seconds / step) + 1 }, (_, i) => i * step);
  return (
    <div className="flex h-7 border-b-2 border-line bg-surface sticky top-0 z-10">
      <div style={{ width: HEADER_W }} className="shrink-0 border-r-2 border-line sticky left-0 bg-surface z-10" />
      <div
        className="relative flex-1 cursor-pointer"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          onSeek(Math.max(0, (e.clientX - rect.left) / pps));
        }}
      >
        {marks.map((m) => (
          <div key={m} className="absolute top-0 bottom-0 border-l border-line/40" style={{ left: m * pps }}>
            <span className="font-mono text-[10px] text-muted pl-1">{timecode(m, 0)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
