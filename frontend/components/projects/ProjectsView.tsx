"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import type { ProjectSummary } from "@/lib/types";

export function ProjectsView() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .listProjects()
      .then((p) => setProjects(p.items))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const project = await api.createProject(name.trim() || "Untitled remix");
      // A fresh project starts with the two tracks almost every remix needs.
      await api.createTrack(project.id, { name: "Dialogue", track_type: "dialogue" });
      await api.createTrack(project.id, { name: "Music", track_type: "music", volume: 0.7 });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setCreating(false);
    }
  }

  async function remove(project: ProjectSummary) {
    if (!confirm(`Delete "${project.name}"? Its timeline is removed; your media stays in the library.`)) return;
    try {
      await api.deleteProject(project.id);
      setProjects((prev) => prev?.filter((p) => p.id !== project.id) ?? null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl">Remix projects</h1>
        <p className="text-muted mt-1">A project is a timeline: dialogue clips laid over music, saved as you edit.</p>
      </div>

      <form onSubmit={create} className="panel p-4 flex flex-col sm:flex-row gap-3">
        <label htmlFor="project-name" className="sr-only">
          Project name
        </label>
        <input
          id="project-name"
          className="field flex-1"
          placeholder="Name your remix, e.g. “Final battle speech × lo-fi”"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
        />
        <button className="btn btn-primary" disabled={creating}>
          {creating ? "Creating…" : "New project"}
        </button>
      </form>

      {error && (
        <p role="alert" className="text-danger">
          {error}
        </p>
      )}
      {projects === null && !error && <p className="text-muted">Loading projects…</p>}
      {projects?.length === 0 && (
        <div className="border-2 border-dashed border-line rounded-2xl p-10 text-center text-muted">
          No projects yet. Name one above to start a timeline.
        </div>
      )}

      <ul className="flex flex-col gap-3">
        {projects?.map((p) => (
          <li key={p.id} className="panel flex items-center gap-3 p-3 pl-4">
            <Link href={`/projects/${p.id}`} className="flex-1 min-w-0">
              <p className="font-bold truncate">{p.name}</p>
              <p className="text-xs text-muted">Edited {relativeTime(p.updated_at)}</p>
            </Link>
            <Link href={`/projects/${p.id}`} className="btn btn-sm">
              Open
            </Link>
            <button className="btn btn-sm btn-ghost" onClick={() => remove(p)} aria-label={`Delete ${p.name}`}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
