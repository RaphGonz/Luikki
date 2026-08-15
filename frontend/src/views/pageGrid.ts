/**
 * Stub. Filled by plan 01-12 (PROJ-02, PROJ-04) -- the volume/page grid:
 * the page thumbnail grid as the screen's visual anchor, with the compact
 * 8-stage strip under each page (01-UI-SPEC.md §8, Phase-Specific
 * Interaction Contracts §1). Registered in `shell/router.ts` now so plan
 * 01-12 never needs to touch the router.
 */

export function renderPageGrid(
  mount: HTMLElement,
  params: { volumeId: number },
): () => void {
  const el = document.createElement("div");
  el.className = "view-stub";
  el.textContent = `Coming in plan 01-12 (volume ${params.volumeId})`;
  mount.append(el);
  return () => el.remove();
}
