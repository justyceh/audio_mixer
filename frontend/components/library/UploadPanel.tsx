"use client";

import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Media } from "@/lib/types";
import { useJobs } from "@/components/jobs/JobsProvider";

const ACCEPT = ".mp3,.wav,.mp4,.mov,.m4a,.webm";

interface Upload {
  name: string;
  progress: number;
  error?: string;
}

export function UploadPanel({ onUploaded }: { onUploaded: (media: Media) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [url, setUrl] = useState("");
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const { track } = useJobs();

  const update = (name: string, patch: Partial<Upload>) =>
    setUploads((prev) => prev.map((u) => (u.name === name ? { ...u, ...patch } : u)));

  async function uploadFiles(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      setUploads((prev) => [...prev.filter((u) => u.name !== file.name), { name: file.name, progress: 0 }]);
      try {
        const media = await api.uploadMedia(file, (p) => update(file.name, { progress: p }));
        setUploads((prev) => prev.filter((u) => u.name !== file.name));
        onUploaded(media);
      } catch (e) {
        update(file.name, { error: errorMessage(e) });
      }
    }
  }

  async function importFromUrl(e: React.FormEvent) {
    e.preventDefault();
    setImportError(null);
    setImporting(true);
    try {
      const job = await api.importUrl(url.trim());
      track(job, `Importing ${new URL(url.trim()).hostname}`);
      setUrl("");
    } catch (err) {
      setImportError(errorMessage(err));
    } finally {
      setImporting(false);
    }
  }

  return (
    <section className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
      <div
        className={`panel relative p-6 sm:p-8 flex flex-col items-center justify-center text-center gap-3 min-h-52 transition-colors ${
          dragOver ? "bg-dialogue/10" : ""
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
        }}
      >
        <p className="font-display text-2xl sm:text-3xl leading-tight">Drop an episode clip here</p>
        <p className="text-muted max-w-md">
          Video or audio: MP4, MOV, WebM, MP3, WAV or M4A. You&apos;ll separate the voices from the music next.
        </p>
        <button className="btn btn-primary mt-1" onClick={() => inputRef.current?.click()}>
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          onChange={(e) => {
            if (e.target.files?.length) uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
        {uploads.length > 0 && (
          <ul className="w-full max-w-md mt-2 flex flex-col gap-2 text-left text-sm">
            {uploads.map((u) => (
              <li key={u.name}>
                <div className="flex justify-between gap-2">
                  <span className="truncate font-bold">{u.name}</span>
                  {!u.error && <span className="font-mono text-muted">{Math.round(u.progress * 100)}%</span>}
                </div>
                {u.error ? (
                  <p className="text-danger">{u.error}</p>
                ) : (
                  <div className="mt-1 h-2 rounded-full border-2 border-line bg-sunken overflow-hidden">
                    <div className="h-full bg-dialogue" style={{ width: `${u.progress * 100}%` }} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <form onSubmit={importFromUrl} className="panel p-6 flex flex-col gap-3">
        <h2 className="font-bold text-lg">Import from a link</h2>
        <p className="text-sm text-muted">
          For media you&apos;re allowed to download from YouTube, SoundCloud, Vimeo or Bandcamp. Private, paid and
          DRM-protected videos can&apos;t be imported.
        </p>
        <label className="sr-only" htmlFor="import-url">
          Media URL
        </label>
        <input
          id="import-url"
          className="field"
          type="url"
          required
          placeholder="https://www.youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        {importError && <p className="text-sm text-danger">{importError}</p>}
        <button className="btn self-start" disabled={importing || !url.trim()}>
          {importing ? "Checking link…" : "Import"}
        </button>
      </form>
    </section>
  );
}
