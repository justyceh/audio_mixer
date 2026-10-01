"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Media, MediaSource } from "@/lib/types";
import { useJobSettled } from "@/components/jobs/JobsProvider";
import { MediaCard } from "./MediaCard";
import { UploadPanel } from "./UploadPanel";

type Filter = "all" | "originals" | "voices" | "clips" | "mixes";

const FILTERS: { id: Filter; label: string; sources: MediaSource[] | null }[] = [
  { id: "all", label: "Everything", sources: null },
  { id: "originals", label: "Originals", sources: ["upload", "import"] },
  { id: "voices", label: "Separated tracks", sources: ["isolated", "extracted"] },
  { id: "clips", label: "Clips", sources: ["trimmed"] },
  { id: "mixes", label: "Mixes & exports", sources: ["mixed", "export"] },
];

export function LibraryView() {
  const [media, setMedia] = useState<Media[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const refresh = useCallback(async () => {
    try {
      const page = await api.listMedia();
      setMedia(page.items);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    queueMicrotask(refresh);
  }, [refresh]);

  useJobSettled(() => refresh());

  const sources = FILTERS.find((f) => f.id === filter)!.sources;
  const visible = media?.filter((m) => !sources || sources.includes(m.source)) ?? [];

  return (
    <div className="flex flex-col gap-8">
      <UploadPanel onUploaded={(m) => setMedia((prev) => [m, ...(prev ?? [])])} />

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="font-display text-2xl">Library</h1>
          <div role="tablist" aria-label="Filter media" className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                role="tab"
                aria-selected={filter === f.id}
                onClick={() => setFilter(f.id)}
                className={`chip px-3 py-1 text-sm cursor-pointer ${
                  filter === f.id ? "bg-ink text-paper" : "bg-surface hover:bg-sunken"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="panel p-4 text-danger" role="alert">
            {error}{" "}
            <button className="btn btn-sm ml-2" onClick={refresh}>
              Try again
            </button>
          </div>
        )}

        {media === null && !error && <p className="text-muted">Loading your library…</p>}

        {media !== null && visible.length === 0 && (
          <div className="border-2 border-dashed border-line rounded-2xl p-10 text-center text-muted">
            {media.length === 0
              ? "Your library is empty. Upload a clip above to get started."
              : "Nothing in this group yet."}
          </div>
        )}

        {visible.length > 0 && (
          <div className="grid gap-5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visible.map((m) => (
              <MediaCard key={m.id} media={m} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
