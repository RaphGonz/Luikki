/**
 * The volume's page thumbnail grid (01-UI-SPEC.md §8): the artwork itself
 * is the screen's visual anchor -- each card is the thumbnail at full card
 * scale with the compact stage strip and page name beneath it, subordinate
 * and never competing with the art for scale or accent. Filled in from
 * plan 01-11's stub; the view-function signature and router registration
 * are unchanged.
 *
 * There is no Save button and no confirm step here: a drop is the commit
 * (PROJ-05, UI-SPEC §7).
 */

import { api, apiUrl } from "../api/client";
import type { PageDto, StageDto } from "../api/types";
import { renderStageStrip, segmentStates } from "../components/stageStrip";
import { partitionUploadResult, renderUploadDrop, uploadWithProgress } from "../components/uploadDrop";
import type { UploadDropHandle } from "../components/uploadDrop";
import { navigate } from "../shell/router";
import "../styles/pages.css";

export function renderPageGrid(mount: HTMLElement, params: { volumeId: number }): () => void {
  const root = document.createElement("div");
  root.className = "page-grid-view";
  mount.append(root);

  const dropMount = document.createElement("div");
  root.append(dropMount);

  const grid = document.createElement("div");
  grid.className = "page-grid";
  root.append(grid);

  let disposed = false;
  let stages: StageDto[] = [];
  let pages: PageDto[] = [];

  const uploadHandle: UploadDropHandle = renderUploadDrop(dropMount, {
    hasPages: false,
    onFiles: (files) => void handleFiles(files),
  });

  void boot();

  async function boot(): Promise<void> {
    const [stagesResult, pagesResult] = await Promise.all([
      api.pipeline.stages(),
      api.pages.list(params.volumeId),
    ]);
    if (disposed) return;
    stages = stagesResult;
    pages = pagesResult;
    uploadHandle.setHasPages(pages.length > 0);
    renderGrid();
  }

  function renderGrid(): void {
    grid.replaceChildren();
    for (const page of pages) {
      grid.append(renderCard(page));
    }
  }

  function renderCard(page: PageDto): HTMLElement {
    const card = document.createElement("div");
    card.className = "page-card";
    card.addEventListener("click", () => navigate({ kind: "page", pageId: page.id }));

    const thumb = document.createElement("img");
    thumb.src = page.image_url;
    thumb.loading = "lazy";
    thumb.alt = page.original_name;
    thumb.className = "page-card-thumb";
    card.append(thumb);

    const stripMount = document.createElement("div");
    stripMount.className = "page-card-strip";
    card.append(stripMount);
    renderStageStrip(stripMount, segmentStates(stages, page.stage), "compact");

    const name = document.createElement("div");
    name.className = "page-card-name";
    name.textContent = page.original_name;
    card.append(name);

    return card;
  }

  async function handleFiles(files: File[]): Promise<void> {
    uploadHandle.setProgress(0);
    try {
      const result = await uploadWithProgress(
        apiUrl("/pages/", { volume_id: params.volumeId }),
        files,
        (percent) => uploadHandle.setProgress(percent),
      );
      const outcome = partitionUploadResult(result);
      if (outcome.added.length > 0) {
        // A partial failure never discards the successful uploads
        // (T-01-PARTIAL): accepted pages are appended before the failure
        // banner is even considered.
        pages = [...pages, ...outcome.added];
        renderGrid();
      }
      if (outcome.failures.length > 0) {
        uploadHandle.showFailures(outcome.summary, outcome.failures);
      } else {
        uploadHandle.clearFailures();
      }
    } catch (err) {
      uploadHandle.showFailures(
        err instanceof Error ? err.message : "Upload failed — try again.",
        [],
      );
    } finally {
      uploadHandle.setProgress(null);
      uploadHandle.setHasPages(pages.length > 0);
    }
  }

  return () => {
    disposed = true;
    root.remove();
  };
}
