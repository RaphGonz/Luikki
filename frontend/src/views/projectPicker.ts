/**
 * Stub. Filled out fully by this same plan's Task 3 (the recent-projects
 * list, create-project form and browse fallback). Registered in
 * `shell/router.ts` here in Task 2 because the router must register all
 * four views in one place -- this file is created now as a placeholder
 * purely so `router.ts` has something real to import; Task 3 replaces this
 * body without touching the router.
 */

export function renderProjectPicker(mount: HTMLElement): () => void {
  const el = document.createElement("div");
  el.className = "view-stub";
  el.textContent = "Loading…";
  mount.append(el);
  return () => el.remove();
}
