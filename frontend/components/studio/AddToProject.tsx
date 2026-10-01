"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { TRACK_LABEL, mediaTone } from "@/lib/format";
import type { Media, ProjectSummary, TrackType } from "@/lib/types";

const NEW = "__new__";

/** Place this media (or the selected part of it) at the end of a project track. */
export function AddToProject({ media, selection }: { media: Media; selection: [number, number] | null }) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [projectId, setProjectId] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [trackType, setTrackType] = useState<TrackType>(() => {
    const tone = mediaTone(media);
    return tone === "other" ? "dialogue" : tone;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then((p) => {
        setProjects(p.items);
        setProjectId(p.items[0]?.id ?? NEW);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function add() {
    setBusy(true);
    setError(null);
    setAdded(null);
    try {
      let id = projectId;
      let name = projects?.find((p) => p.id === id)?.name ?? "";
      if (id === NEW) {
        const created = await api.createProject(newName.trim() || "Untitled remix");
        id = created.id;
        name = created.name;
        setProjects((prev) => [created, ...(prev ?? [])]);
        setProjectId(created.id);
      }
      const project = await api.getProject(id);
      let track = project.tracks.find((t) => t.track_type === trackType);
      if (!track) {
        track = await api.createTrack(id, { name: TRACK_LABEL[trackType], track_type: trackType });
      }
      const end = Math.max(0, ...track.clips.map((c) => c.timeline_start + c.source_end - c.source_start));
      await api.createClip(track.id, {
        media_id: media.id,
        timeline_start: Number(end.toFixed(3)),
        source_start: selection?.[0] ?? 0,
        source_end: selection?.[1] ?? media.duration,
      });
      setAdded({ id, name });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel p-4 flex flex-col gap-3">
      <div>
        <h2 className="font-bold">Add to a remix project</h2>
        <p className="text-xs text-muted mt-1">
          {selection ? "Adds just the selected part" : "Adds the whole file"} to the end of the matching track.
        </p>
      </div>
      <label className="text-sm">
        <span className="eyebrow block mb-1">Project</span>
        <select className="field" value={projectId} onChange={(e) => setProjectId(e.target.value)} disabled={!projects}>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
          <option value={NEW}>+ New project…</option>
        </select>
      </label>
      {projectId === NEW && (
        <input
          className="field"
          placeholder="Project name"
          aria-label="New project name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
      )}
      <label className="text-sm">
        <span className="eyebrow block mb-1">Track</span>
        <select className="field" value={trackType} onChange={(e) => setTrackType(e.target.value as TrackType)}>
          {(Object.keys(TRACK_LABEL) as TrackType[]).map((t) => (
            <option key={t} value={t}>
              {TRACK_LABEL[t]}
            </option>
          ))}
        </select>
      </label>
      {error && <p className="text-sm text-danger">{error}</p>}
      {added && (
        <p className="text-sm text-ok">
          Added to{" "}
          <Link className="underline font-bold" href={`/projects/${added.id}`}>
            {added.name}
          </Link>
          .
        </p>
      )}
      <button className="btn" disabled={busy || !projects} onClick={add}>
        {busy ? "Adding…" : "Add to project"}
      </button>
    </div>
  );
}
