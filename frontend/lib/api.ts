import type {
  AudioFormat,
  Clip,
  Health,
  Job,
  JobStatus,
  Media,
  MediaSource,
  MediaType,
  Paged,
  Project,
  ProjectSummary,
  Track,
  TrackType,
  Transcription,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const OFFLINE_MESSAGE = `Can't reach the backend at ${API_URL}. Start it with "uvicorn api.server:app --reload" in the backend folder.`;

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    const err = body?.error;
    if (err?.message) {
      let message: string = err.message;
      // Pydantic validation errors: surface the first field problem.
      if (err.code === "validation_error" && Array.isArray(err.details) && err.details[0]?.msg) {
        const first = err.details[0];
        const field = Array.isArray(first.loc) ? first.loc.filter((p: unknown) => p !== "body").join(".") : "";
        message = field ? `${field}: ${first.msg}` : first.msg;
      }
      return new ApiError(message, response.status, err.code ?? "error", err.details);
    }
  } catch {
    // fall through
  }
  return new ApiError(`Request failed (${response.status})`, response.status, "http_error");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: init.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...init.headers }
        : init.headers,
    });
  } catch {
    throw new ApiError(OFFLINE_MESSAGE, 0, "offline");
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) });
const post = <T>(path: string, body: unknown) => request<T>(path, { method: "POST", ...json(body) });
const patch = <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", ...json(body) });
const del = (path: string) => request<void>(path, { method: "DELETE" });

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Upload with progress reporting (fetch can't report upload progress). */
function uploadMedia(file: File, onProgress?: (fraction: number) => void): Promise<Media> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/media/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(OFFLINE_MESSAGE, 0, "offline"));
    xhr.onload = async () => {
      const response = new Response(xhr.responseText, { status: xhr.status });
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else reject(await toApiError(response));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const api = {
  health: () => request<Health>("/api/health"),

  // Media
  listMedia: (p: { limit?: number; offset?: number; media_type?: MediaType; source?: MediaSource } = {}) =>
    request<Paged<Media>>(`/api/media${query({ limit: 200, ...p })}`),
  getMedia: (id: string) => request<Media>(`/api/media/${id}`),
  deleteMedia: (id: string) => del(`/api/media/${id}`),
  uploadMedia,
  importUrl: (url: string) => post<Job>("/api/media/import", { url }),
  listTranscriptions: (mediaId: string) => request<Transcription[]>(`/api/media/${mediaId}/transcriptions`),

  // Audio tools
  extract: (media_id: string, format: AudioFormat = "wav") => post<Media>("/api/audio/extract", { media_id, format }),
  trim: (media_id: string, start_time: number, end_time: number, format: AudioFormat = "wav") =>
    post<Media>("/api/audio/trim", { media_id, start_time, end_time, format }),
  isolate: (media_id: string, mode: "vocals" | "instrumental" = "vocals") =>
    post<Job>("/api/audio/isolate", { media_id, mode }),
  transcribe: (media_id: string, language?: string) =>
    post<Job>("/api/audio/transcribe", { media_id, language: language || null }),

  // Projects
  listProjects: () => request<Paged<ProjectSummary>>("/api/projects?limit=200"),
  createProject: (name: string) => post<Project>("/api/projects", { name }),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  renameProject: (id: string, name: string) => patch<Project>(`/api/projects/${id}`, { name }),
  deleteProject: (id: string) => del(`/api/projects/${id}`),

  createTrack: (projectId: string, body: { name: string; track_type: TrackType; volume?: number }) =>
    post<Track>(`/api/projects/${projectId}/tracks`, body),
  updateTrack: (id: string, body: Partial<Pick<Track, "name" | "track_type" | "volume" | "muted" | "order_index">>) =>
    patch<Track>(`/api/tracks/${id}`, body),
  deleteTrack: (id: string) => del(`/api/tracks/${id}`),

  createClip: (
    trackId: string,
    body: { media_id: string; timeline_start?: number; source_start?: number; source_end?: number },
  ) => post<Clip>(`/api/tracks/${trackId}/clips`, body),
  updateClip: (
    id: string,
    body: Partial<Pick<Clip, "track_id" | "timeline_start" | "source_start" | "source_end" | "volume" | "fade_in" | "fade_out">>,
  ) => patch<Clip>(`/api/clips/${id}`, body),
  deleteClip: (id: string) => del(`/api/clips/${id}`),

  // Jobs & export
  exportProject: (project_id: string, format: AudioFormat) => post<Job>("/api/exports", { project_id, format }),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  listJobs: (status?: JobStatus) => request<Job[]>(`/api/jobs${query({ status })}`),
};

export const streamUrl = (media: Pick<Media, "url">) => `${API_URL}${media.url}`;
export const downloadUrl = (job: Pick<Job, "id">) => `${API_URL}/api/jobs/${job.id}/download`;

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
