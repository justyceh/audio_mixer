"use client";

import Link from "next/link";
import { downloadUrl } from "@/lib/api";
import { useJobs } from "./JobsProvider";

const STATUS_TEXT = {
  pending: "Waiting for the worker",
  processing: "Working",
  completed: "Done",
  failed: "Failed",
} as const;

export function JobTray() {
  const { jobs, dismiss } = useJobs();
  const visible = jobs.slice(0, 4);
  if (!visible.length) return null;

  return (
    <aside
      aria-label="Background jobs"
      aria-live="polite"
      className="fixed bottom-4 right-4 left-4 sm:left-auto sm:w-80 z-40 flex flex-col gap-3"
    >
      {visible.map(({ job, label, href: explicitHref }) => {
        const href =
          explicitHref ??
          (job.job_type === "export" && job.project_id
            ? `/projects/${job.project_id}`
            : job.output_media_id
              ? `/media/${job.output_media_id}`
              : undefined);
        const done = job.status === "completed";
        const failed = job.status === "failed";
        return (
          <div key={job.id} className="panel p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-bold truncate">{label}</p>
                <p className={failed ? "text-danger" : done ? "text-ok" : "text-muted"}>
                  {STATUS_TEXT[job.status]}
                  {job.status === "processing" && ` · ${job.progress}%`}
                </p>
              </div>
              <button
                className="btn btn-ghost btn-sm -mr-1 -mt-1"
                aria-label={`Dismiss ${label}`}
                onClick={() => dismiss(job.id)}
              >
                ✕
              </button>
            </div>

            {!done && !failed && (
              <div className="mt-2 h-2.5 rounded-full border-2 border-line bg-sunken overflow-hidden">
                <div
                  className="h-full bg-dialogue transition-[width] duration-500"
                  style={{ width: `${job.status === "pending" ? 3 : Math.max(job.progress, 5)}%` }}
                />
              </div>
            )}
            {job.status === "pending" && (
              <p className="mt-2 text-xs text-muted">
                Nothing happening? Start the worker: <code className="font-mono">python -m api.worker</code>
              </p>
            )}
            {failed && job.error_message && (
              <p className="mt-2 text-xs text-danger whitespace-pre-wrap line-clamp-4">{job.error_message}</p>
            )}
            {done && (
              <div className="mt-2 flex gap-2">
                {href && (
                  <Link href={href} className="btn btn-sm" onClick={() => dismiss(job.id)}>
                    Open
                  </Link>
                )}
                {job.download_url && (
                  <a href={downloadUrl(job)} className="btn btn-sm btn-blue">
                    Download
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
