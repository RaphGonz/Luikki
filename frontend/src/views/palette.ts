/**
 * Stub. Filled by plan 01-13 (PAL-01, PAL-02, PAL-03, PAL-04) -- the
 * palette grid: the swatch grid at full 120x120 is the screen's visual
 * anchor, doubling as the character-sheet proposal review surface
 * (01-UI-SPEC.md §8, Phase-Specific Interaction Contracts §4/§5).
 * Registered in `shell/router.ts` now so plan 01-13 never needs to touch
 * the router.
 */

export function renderPalette(mount: HTMLElement): () => void {
  const el = document.createElement("div");
  el.className = "view-stub";
  el.textContent = "Coming in plan 01-13";
  mount.append(el);
  return () => el.remove();
}
