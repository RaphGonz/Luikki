/**
 * The upload drop zone shared by the page grid (01-UI-SPEC.md §7, §8): a
 * click-to-browse target that also accepts a real drag-and-drop, with
 * empty-state Copywriting Contract copy when the volume has no pages yet
 * and an "Upload Pages" CTA once it does. `partitionUploadResult` is kept
 * pure and DOM-free so the mixed-batch behaviour (T-01-PARTIAL) is
 * testable without a browser; `renderUploadDrop`/`uploadWithProgress` are
 * the only parts that touch the DOM or the network.
 */

import type { PageDto, PageUploadDto, RejectedUploadDto } from "../api/types";
import "../styles/pages.css";

export interface UploadFailure {
  filename: string;
  detail: string;
}

export interface UploadOutcome {
  added: PageDto[];
  failures: UploadFailure[];
  summary: string;
}

/**
 * Pure: splits a `PageUploadResponse` into what was added and what wasn't,
 * and writes the Copywriting Contract's error-shape summary sentence. Every
 * failure keeps the backend's own `detail` verbatim -- this function never
 * invents its own per-file wording, only the batch-level summary.
 */
export function partitionUploadResult(result: PageUploadDto): UploadOutcome {
  const failures: UploadFailure[] = result.rejected.map((rejected: RejectedUploadDto) => ({
    filename: rejected.filename,
    detail: rejected.detail,
  }));
  const summary =
    failures.length === 0
      ? ""
      : `${failures.length} file${failures.length === 1 ? "" : "s"} failed to upload — the rest were added below; fix and re-drop the failed ones.`;
  return { added: result.accepted, failures, summary };
}

export interface UploadDropOptions {
  /** Toggles the empty-state prompt vs. the "Upload Pages" CTA (§8). */
  hasPages: boolean;
  onFiles: (files: File[]) => void | Promise<void>;
}

export interface UploadDropHandle {
  /** Determinate 0..100 progress, or `null` to hide the bar (§7). */
  setProgress(percent: number | null): void;
  /** Persistent inline failure banner -- never auto-dismisses (§7). */
  showFailures(summary: string, failures: UploadFailure[]): void;
  clearFailures(): void;
  /** Called after a volume gains its first page, to swap the empty-state prompt for the CTA without a full re-mount. */
  setHasPages(hasPages: boolean): void;
}

export function renderUploadDrop(mount: HTMLElement, options: UploadDropOptions): UploadDropHandle {
  const state = { hasPages: options.hasPages };

  const root = document.createElement("div");
  root.className = "upload-drop";

  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = "image/*";
  input.className = "upload-drop-input";

  const prompt = document.createElement("div");
  prompt.className = "upload-drop-prompt";

  const progress = document.createElement("div");
  progress.className = "upload-drop-progress";
  progress.hidden = true;
  const progressFill = document.createElement("div");
  progressFill.className = "upload-drop-progress-fill";
  const progressLabel = document.createElement("span");
  progressLabel.className = "upload-drop-progress-label";
  progress.append(progressFill, progressLabel);

  const failureBanner = document.createElement("div");
  failureBanner.className = "upload-drop-error";
  failureBanner.hidden = true;

  root.append(prompt, input, progress, failureBanner);
  mount.append(root);

  function renderPrompt(): void {
    prompt.replaceChildren();
    if (state.hasPages) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "upload-drop-cta accent";
      button.textContent = "Upload Pages";
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        input.click();
      });
      prompt.append(button);
    } else {
      const heading = document.createElement("div");
      heading.className = "upload-drop-heading";
      heading.textContent = "No pages yet";
      const body = document.createElement("div");
      body.className = "upload-drop-body";
      body.textContent =
        "Drop line art pages here, or click to upload. You can add more anytime.";
      prompt.append(heading, body);
    }
  }
  renderPrompt();

  root.addEventListener("click", (event) => {
    if (event.target === input) return;
    input.click();
  });

  root.addEventListener("dragover", (event) => {
    event.preventDefault();
    root.classList.add("is-dragover");
  });
  root.addEventListener("dragleave", () => {
    root.classList.remove("is-dragover");
  });
  root.addEventListener("drop", (event) => {
    event.preventDefault();
    root.classList.remove("is-dragover");
    const files = event.dataTransfer ? Array.from(event.dataTransfer.files) : [];
    if (files.length > 0) void options.onFiles(files);
  });

  input.addEventListener("change", () => {
    const files = input.files ? Array.from(input.files) : [];
    input.value = "";
    if (files.length > 0) void options.onFiles(files);
  });

  return {
    setProgress(percent) {
      if (percent === null) {
        progress.hidden = true;
        return;
      }
      progress.hidden = false;
      const clamped = Math.max(0, Math.min(100, percent));
      progressFill.style.width = `${clamped}%`;
      progressLabel.textContent = `${Math.round(clamped)}%`;
    },
    showFailures(summary, failures) {
      failureBanner.hidden = false;
      failureBanner.replaceChildren();
      const summaryEl = document.createElement("div");
      summaryEl.className = "upload-drop-error-summary";
      summaryEl.textContent = summary;
      failureBanner.append(summaryEl);
      if (failures.length > 0) {
        const list = document.createElement("ul");
        for (const failure of failures) {
          const item = document.createElement("li");
          item.textContent = `${failure.filename}: ${failure.detail}`;
          list.append(item);
        }
        failureBanner.append(list);
      }
    },
    clearFailures() {
      failureBanner.hidden = true;
      failureBanner.replaceChildren();
    },
    setHasPages(hasPages) {
      state.hasPages = hasPages;
      renderPrompt();
    },
  };
}

/**
 * Uploads via `XMLHttpRequest`, not `fetch`, specifically because
 * `xhr.upload.onprogress` is what drives a real determinate percentage
 * (01-UI-SPEC.md §7) -- `fetch` has no equivalent upload-progress event.
 *
 * The route returns 201 (some/all accepted, `accepted` + `rejected` both
 * present) or 400 (all rejected, `rejected` only) -- both carry a JSON body
 * this function normalises into the same `PageUploadDto` shape, since it is
 * `partitionUploadResult`, not the HTTP status, that decides success vs.
 * failure per file. Only a genuine transport failure (no body at all)
 * rejects the returned promise.
 */
export function uploadWithProgress(
  url: string,
  files: File[],
  onProgress: (percent: number) => void,
): Promise<PageUploadDto> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress((event.loaded / event.total) * 100);
      }
    };
    xhr.onload = () => {
      if (xhr.status === 201 || xhr.status === 400) {
        try {
          const body = JSON.parse(xhr.responseText) as Partial<PageUploadDto>;
          resolve({ accepted: body.accepted ?? [], rejected: body.rejected ?? [] });
          return;
        } catch {
          // fall through to the generic failure below
        }
      }
      reject(new Error(`Upload failed: the server returned status ${xhr.status} — try again.`));
    };
    xhr.onerror = () => {
      reject(new Error("Upload failed: the connection was lost — try again."));
    };
    xhr.send(form);
  });
}
