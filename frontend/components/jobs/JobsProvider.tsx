"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { Job } from "@/lib/types";

// Tracks background jobs (isolation, transcription, export, import) across pages,
// polls them until they finish, and lets components react when one settles.

export interface TrackedJob {
  job: Job;
  label: string;
  /** Where the "open" link in the tray should go once complete. */
  href?: string;
}

type Listener = (job: Job) => void;

interface JobsContextValue {
  jobs: TrackedJob[];
  track: (job: Job, label: string, href?: string) => void;
  dismiss: (id: string) => void;
  /** Subscribe to job completion/failure. Returns an unsubscribe function. */
  onSettled: (listener: Listener) => () => void;
}

const JobsContext = createContext<JobsContextValue | null>(null);
const STORAGE_KEY = "ars.jobs";
const POLL_MS = 1500;

const isActive = (job: Job) => job.status === "pending" || job.status === "processing";

function readStored(): TrackedJob[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TrackedJob[]) : [];
  } catch {
    return [];
  }
}

export function JobsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<TrackedJob[]>([]);
  const listeners = useRef(new Set<Listener>());
  const loaded = useRef(false);

  // Restore jobs from a previous visit (so a refresh doesn't lose a running export).
  useEffect(() => {
    const stored = readStored();
    loaded.current = true;
    if (stored.length) queueMicrotask(() => setJobs(stored));
  }, []);

  useEffect(() => {
    if (!loaded.current) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs.slice(0, 20)));
    } catch {
      // storage unavailable: tracking still works for this tab
    }
  }, [jobs]);

  const activeIds = jobs.filter((t) => isActive(t.job)).map((t) => t.job.id).join(",");

  useEffect(() => {
    if (!activeIds) return;
    const ids = activeIds.split(",");
    const timer = setInterval(async () => {
      const results = await Promise.allSettled(ids.map((id) => api.getJob(id)));
      const fresh = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
      if (!fresh.length) return;
      setJobs((prev) =>
        prev.map((t) => {
          const next = fresh.find((j) => j.id === t.job.id);
          if (!next) return t;
          if (isActive(t.job) && !isActive(next)) {
            queueMicrotask(() => listeners.current.forEach((l) => l(next)));
          }
          return { ...t, job: next };
        }),
      );
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [activeIds]);

  const track = useCallback((job: Job, label: string, href?: string) => {
    setJobs((prev) => [{ job, label, href }, ...prev.filter((t) => t.job.id !== job.id)]);
  }, []);

  const dismiss = useCallback((id: string) => {
    setJobs((prev) => prev.filter((t) => t.job.id !== id));
  }, []);

  const onSettled = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  return <JobsContext.Provider value={{ jobs, track, dismiss, onSettled }}>{children}</JobsContext.Provider>;
}

export function useJobs(): JobsContextValue {
  const value = useContext(JobsContext);
  if (!value) throw new Error("useJobs must be used inside <JobsProvider>");
  return value;
}

/** Run `callback` whenever a tracked job finishes (either way). */
export function useJobSettled(callback: Listener) {
  const { onSettled } = useJobs();
  const ref = useRef(callback);
  useEffect(() => {
    ref.current = callback;
  });
  useEffect(() => onSettled((job) => ref.current(job)), [onSettled]);
}
