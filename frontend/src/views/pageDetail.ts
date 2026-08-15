/**
 * The page detail screen (01-UI-SPEC.md §8): the full stage strip in the
 * top toolbar is the visual anchor -- until an editor exists (Phase 2+),
 * this screen's entire purpose is answering "where is this page in the
 * pipeline and what can I do next". Filled in from plan 01-11's stub; the
 * view-function signature and router registration are unchanged.
 *
 * The content region stays full-bleed and unpadded -- Phase 2 mounts the
 * Konva panel editor into exactly this space (UI-SPEC §8), so no bordered
 * viewer frame, max-width or centred card is added here.
 *
 * Renders no Go-Back entry point and no "Confirm & Continue" control.
 * D-08 and UI-SPEC §3 both describe why: Phase 1 has no stage past Import
 * to go back from or confirm into, and §3 is explicit that a destructive
 * dialog whose affected-count cannot yet be computed from real data must
 * not ship in place of a computed one. The contract and the `upstream`
 * links needed to compute that sentence already exist (`pipeline/stages`);
 * Phase 2 implements it from there rather than re-deriving either.
 */

import { api } from "../api/client";
import type { PageDto } from "../api/types";
import { renderStageStrip, segmentStates } from "../components/stageStrip";
import { navigate } from "../shell/router";
import { getToolbarHandle } from "../shell/toolbar";
import "../styles/pages.css";

export function renderPageDetail(mount: HTMLElement, params: { pageId: number }): () => void {
  const root = document.createElement("div");
  root.className = "page-detail";
  mount.append(root);

  const meta = document.createElement("div");
  meta.className = "page-detail-meta";
  root.append(meta);

  const content = document.createElement("div");
  content.className = "page-detail-content";
  root.append(content);

  const toolbar = getToolbarHandle();
  toolbar.setTitle("");
  toolbar.slot.replaceChildren();

  const toolbarRow = document.createElement("div");
  toolbarRow.className = "page-detail-toolbar-row";

  const backButton = document.createElement("button");
  backButton.type = "button";
  backButton.className = "page-detail-back";
  backButton.setAttribute("aria-label", "Back to pages");
  backButton.textContent = "←";

  const stripMount = document.createElement("div");
  stripMount.className = "page-detail-strip";

  toolbarRow.append(backButton, stripMount);
  toolbar.slot.append(toolbarRow);

  let disposed = false;
  let volumeId: number | null = null;

  backButton.addEventListener("click", () => {
    if (volumeId !== null) navigate({ kind: "volume", volumeId });
  });

  void boot();

  async function boot(): Promise<void> {
    const [stages, page] = await Promise.all([api.pipeline.stages(), api.pages.get(params.pageId)]);
    if (disposed) return;
    volumeId = page.volume_id;
    toolbar.setTitle(page.original_name);
    meta.textContent = `Page ${page.index + 1}`;
    renderStageStrip(stripMount, segmentStates(stages, page.stage), "full");
    renderImage(page);
  }

  function renderImage(page: PageDto): void {
    content.replaceChildren();
    const img = document.createElement("img");
    img.src = page.image_url;
    img.alt = page.original_name;
    img.className = "page-detail-image";
    content.append(img);
  }

  return () => {
    disposed = true;
    root.remove();
    toolbar.setTitle("");
    toolbar.slot.replaceChildren();
  };
}
