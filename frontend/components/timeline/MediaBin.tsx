"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { displayName, mediaTone, SOURCE_LABEL, timecode } from "@/lib/format";
import type { Clip, Media, Track } from "@/lib/types";

/** Library picker: drops the chosen media onto the selected track at the playhead. */
export function MediaBin({
  targetTrack,
  playhead,
  onAdded,
  onError,
}: {
  targetTrack: Track | null;
  playhead: number;
  onAdded: (clip: Clip) => void;
  onError: (e: unknown) => void;
}) {
  const [media, setMedia] = useState<Media[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState<string | null>(null);

  useEffect(() => {
    api
      .listMedia()
      .then((p) => setMedia(p.items))
      .catch((e) => setLoadError(errorMessage(e)));
  }, []);

  const q = search.trim().toLowerCase();
  const visible = (media ?? []).filter((m) => !q || m.original_filename.toLowerCase().includes(q));

  async function add(m: Media) {
    if (!targetTrack) return;
    setAdding(m.id);
    try {
      onAdded(await api.createClip(targetTrack.id, { media_id: m.id, timeline_start: Number(playhead.toFixed(3)) }));
    } catch (e) {
      onError(e);
    } finally {
      setAdding(null);
    }
  }

  return (
    <section className="panel p-4 flex flex-col gap-3">
      <div>
        <h2 className="font-bold">Add from library</h2>
        <p className="text-xs text-muted mt-1">
          {targetTrack ? (
            <>
              Goes on <b className="text-ink">{targetTrack.name}</b> at {timecode(playhead)}.
            </>
          ) : (
            "Click a track first to choose where clips go."
          )}
        </p>
      </div>
      <input className="field" placeholder="Search your media" aria-label="Search media" value={search} onChange={(e) => setSearch(e.target.value)} />
      {loadError && <p className="text-sm text-danger">{loadError}</p>}
      {media === null && !loadError && <p className="text-sm text-muted">Loading…</p>}
      {media?.length === 0 && <p className="text-sm text-muted">Your library is empty. Upload clips from the Library page.</p>}
      <ul className="flex flex-col gap-1 max-h-72 overflow-y-auto -mx-1">
        {visible.map((m) => {
          const tone = mediaTone(m);
          return (
            <li key={m.id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-sunken">
              <span
                className={`w-2.5 h-2.5 rounded-full border-[1.5px] border-line shrink-0 ${
                  { dialogue: "bg-dialogue", music: "bg-music", sfx: "bg-sfx", other: "bg-other" }[tone]
                }`}
                aria-hidden="true"
              />
              <span className="flex-1 min-w-0">
                <span className="block truncate text-sm font-bold">{displayName(m)}</span>
                <span className="text-xs text-muted">
                  {SOURCE_LABEL[m.source]} · <span className="font-mono">{timecode(m.duration, 0)}</span>
                </span>
              </span>
              <button className="btn btn-sm" disabled={!targetTrack || adding !== null} onClick={() => add(m)}>
                {adding === m.id ? "Adding…" : "Add"}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
