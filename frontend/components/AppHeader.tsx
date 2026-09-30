"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Health } from "@/lib/types";

const NAV = [
  { href: "/", label: "Library" },
  { href: "/projects", label: "Projects" },
];

export function AppHeader() {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => !cancelled && (setHealth(h), setOffline(null)))
      .catch((e) => !cancelled && setOffline(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const missing = health
    ? [
        !health.database && "database",
        !health.ffmpeg && "FFmpeg",
        !health.demucs && "Demucs (voice separation)",
        !health.faster_whisper && "faster-whisper (transcription)",
      ].filter(Boolean)
    : [];

  return (
    <header className="border-b-2 border-line bg-surface">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2.5 shrink-0" aria-label="Anime Remix Studio home">
          <Logo />
          <span className="font-display text-lg leading-none hidden sm:block">Anime Remix Studio</span>
        </Link>
        <nav className="flex gap-1" aria-label="Main">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" || pathname.startsWith("/media") : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`px-3 py-1.5 rounded-lg font-bold text-sm border-2 ${
                  active ? "border-line bg-sunken" : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {(offline || missing.length > 0) && (
        <div role="alert" className="border-t-2 border-line bg-sfx/25 px-4 py-2 text-sm text-center">
          {offline ?? `The backend is running but missing: ${missing.join(", ")}. Some tools won't work.`}
        </div>
      )}
    </header>
  );
}

/** Three stacked bars: dialogue over music over effects, the studio's whole idea in one mark. */
function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
      <rect x="1" y="1" width="28" height="28" rx="7" fill="var(--surface)" stroke="var(--line)" strokeWidth="2" />
      <rect x="6" y="7" width="12" height="4" rx="2" fill="var(--dialogue)" />
      <rect x="9" y="13" width="15" height="4" rx="2" fill="var(--music)" />
      <rect x="6" y="19" width="8" height="4" rx="2" fill="var(--sfx)" />
    </svg>
  );
}
