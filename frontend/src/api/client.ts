/**
 * The typed fetch layer every view uses -- the whole phase's endpoint
 * surface in one module. 01-11-SUMMARY.md records the full signature list
 * plans 01-12 and 01-13 build directly against.
 *
 * Every request is a same-origin relative `/api/...` URL: `vite dev`
 * proxies `/api` to the FastAPI dev server (`frontend/vite.config.ts`) and
 * production serves this SPA from the same FastAPI process
 * (01-06-SUMMARY.md's `app.frontend()` mount). A configurable base URL
 * would be dead weight and a way to accidentally point the app at another
 * machine (T-01-ORIGIN) -- grep-asserted that no `http(s)://` literal
 * appears anywhere below.
 */

import type {
  BrowseDto,
  PageDto,
  PageUploadDto,
  PaletteEntryDto,
  PaletteUpdateDto,
  ProjectDto,
  RecentProjectDto,
  RGBTuple,
  SheetAcceptDto,
  SheetAcceptItemDto,
  SheetProposalDto,
  StageDto,
  SwatchExtractDto,
  VolumeDto,
} from "./types";

/**
 * Builds a relative `/api/...` URL with encoded query parameters, skipping
 * undefined values.
 */
export const apiUrl = (
  path: string,
  query?: Record<string, string | number | undefined>,
): string => {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const base = `/api${normalized}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
};

/**
 * A FastAPI error response, carrying the backend's own UI-SPEC-shaped copy
 * in `detail` verbatim. The backend already ships Copywriting-Contract
 * wording in `detail` for every deliberate error (plans 01-07 through
 * 01-10 define the constants), so views render `error.detail` directly
 * rather than inventing their own wording -- that is how the contract
 * stays in one place instead of drifting across five views.
 */
export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /**
   * Reads FastAPI's `{"detail": ...}` body, handles the 422
   * validation-error array shape, and falls back to a status-derived
   * sentence that still names what failed if the body isn't JSON.
   */
  static async fromResponse(res: Response): Promise<ApiError> {
    let detail = `Request failed with status ${res.status}.`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body?.detail)) {
        const messages = body.detail
          .map((item: { loc?: unknown[]; msg?: string }) => {
            const field = Array.isArray(item.loc) ? item.loc.at(-1) : undefined;
            return field !== undefined ? `${field}: ${item.msg}` : item.msg;
          })
          .filter((m: unknown): m is string => typeof m === "string" && m.length > 0);
        if (messages.length > 0) {
          detail = messages.join("; ");
        }
      }
    } catch {
      // Body wasn't JSON -- keep the status-derived sentence above.
    }
    return new ApiError(res.status, detail);
  }
}

function jsonRequest(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/**
 * `fetch`, throw `ApiError` on a non-ok response, return `undefined` for
 * 204, otherwise parse JSON.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    throw await ApiError.fromResponse(res);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

/**
 * `api` groups typed functions for every route the phase exposes:
 * `projects.create/open/current/close/recent/browse`,
 * `volumes.list/create/rename/remove`,
 * `pages.upload/list/get/remove/imageUrl`,
 * `pipeline.stages`,
 * `palette.list/create/update/remove/swatch`,
 * `references.uploadSheet/accept/discard/sheetImageUrl`.
 *
 * Uploads use `FormData`; none of those call sites set a `Content-Type`
 * header manually, since the browser must set the multipart boundary
 * itself.
 */
export const api = {
  projects: {
    create: (name: string, parentDir?: string): Promise<ProjectDto> =>
      request(apiUrl("/projects"), jsonRequest("POST", { name, parent_dir: parentDir })),
    open: (path: string): Promise<ProjectDto> =>
      request(apiUrl("/projects/open"), jsonRequest("POST", { path })),
    current: (): Promise<ProjectDto> => request(apiUrl("/projects/current")),
    close: (): Promise<void> => request(apiUrl("/projects/close"), { method: "POST" }),
    recent: (): Promise<RecentProjectDto[]> => request(apiUrl("/projects/recent")),
    browse: (): Promise<BrowseDto | undefined> =>
      request(apiUrl("/projects/browse"), { method: "POST" }),
  },
  volumes: {
    list: (): Promise<VolumeDto[]> => request(apiUrl("/volumes/")),
    create: (name: string): Promise<VolumeDto> =>
      request(apiUrl("/volumes/"), jsonRequest("POST", { name })),
    rename: (volumeId: number, name: string): Promise<VolumeDto> =>
      request(apiUrl(`/volumes/${volumeId}`), jsonRequest("PATCH", { name })),
    remove: (volumeId: number): Promise<void> =>
      request(apiUrl(`/volumes/${volumeId}`), { method: "DELETE" }),
  },
  pages: {
    upload: (volumeId: number, files: File[]): Promise<PageUploadDto> => {
      const form = new FormData();
      for (const file of files) form.append("files", file);
      return request(apiUrl("/pages/", { volume_id: volumeId }), {
        method: "POST",
        body: form,
      });
    },
    list: (volumeId: number): Promise<PageDto[]> =>
      request(apiUrl("/pages/", { volume_id: volumeId })),
    get: (pageId: number): Promise<PageDto> => request(apiUrl(`/pages/${pageId}`)),
    remove: (pageId: number): Promise<void> =>
      request(apiUrl(`/pages/${pageId}`), { method: "DELETE" }),
    imageUrl: (pageId: number): string => apiUrl(`/pages/${pageId}/image`),
  },
  pipeline: {
    stages: (): Promise<StageDto[]> => request(apiUrl("/pipeline/stages")),
  },
  palette: {
    list: (): Promise<PaletteEntryDto[]> => request(apiUrl("/palette")),
    create: (rgb: RGBTuple, label: string): Promise<PaletteEntryDto> =>
      request(apiUrl("/palette"), jsonRequest("POST", { rgb, label })),
    update: (
      entryId: number,
      body: { label?: string; rgb?: RGBTuple },
    ): Promise<PaletteUpdateDto> =>
      request(apiUrl(`/palette/${entryId}`), jsonRequest("PATCH", body)),
    remove: (entryId: number): Promise<void> =>
      request(apiUrl(`/palette/${entryId}`), { method: "DELETE" }),
    swatch: (file: File): Promise<SwatchExtractDto> => {
      const form = new FormData();
      form.append("file", file);
      return request(apiUrl("/palette/swatch"), { method: "POST", body: form });
    },
  },
  references: {
    uploadSheet: (file: File): Promise<SheetProposalDto> => {
      const form = new FormData();
      form.append("file", file);
      return request(apiUrl("/references/sheets"), { method: "POST", body: form });
    },
    accept: (
      sheetId: string,
      characterName: string,
      items: SheetAcceptItemDto[],
    ): Promise<SheetAcceptDto> =>
      request(
        apiUrl(`/references/sheets/${sheetId}/accept`),
        jsonRequest("POST", { character_name: characterName, items }),
      ),
    discard: (sheetId: string): Promise<void> =>
      request(apiUrl(`/references/sheets/${sheetId}`), { method: "DELETE" }),
    sheetImageUrl: (sheetId: string): string =>
      apiUrl(`/references/sheets/${sheetId}/image`),
  },
} as const;
