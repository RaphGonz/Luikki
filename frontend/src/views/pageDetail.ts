/**
 * Stub. Filled by plan 01-12 (PROJ-04) -- the page detail screen: the full
 * 8-stage strip in the toolbar is the visual anchor, since until an editor
 * exists (Phase 2+) the entire purpose of this screen is answering "where
 * is this page in the pipeline and what can I do next" (01-UI-SPEC.md §8).
 * Registered in `shell/router.ts` now so plan 01-12 never needs to touch
 * the router.
 */

export function renderPageDetail(
  mount: HTMLElement,
  params: { pageId: number },
): () => void {
  const el = document.createElement("div");
  el.className = "view-stub";
  el.textContent = `Coming in plan 01-12 (page ${params.pageId})`;
  mount.append(el);
  return () => el.remove();
}
