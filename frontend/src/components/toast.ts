/**
 * Bottom-of-viewport, non-blocking success feedback -- shell furniture, not
 * palette-specific, even though plan 01-13 is its first real caller (the
 * recolour "Updated on {N} page{s}." toast, 01-UI-SPEC.md §6). Never used
 * for errors: those are persistent inline banners at the point of failure
 * (01-UI-SPEC.md §7), never a toast, never an `alert()`.
 */

export interface ToastOptions {
  /** Defaults to ~3s per 01-UI-SPEC.md §6/§7. */
  durationMs?: number;
}

export function showToast(message: string, options?: ToastOptions): void {
  const el = document.createElement("div");
  el.className = "toast";
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.textContent = message;
  document.body.append(el);

  const duration = options?.durationMs ?? 3000;
  window.setTimeout(() => el.remove(), duration);
}
