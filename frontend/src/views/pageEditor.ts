/**
 * Placeholder for the Phase 2 page-editor screen.
 *
 * 02-12-PLAN.md Task 2 creates only this minimal stub because this plan
 * owns routing and the API client, not UI: `#/page/{id}/edit` needs
 * somewhere real to dispatch to before plan 02-13 exists. Plan 02-13
 * replaces this module wholesale with the Konva panel/protected-mask
 * editor (02-UI-SPEC.md) -- do not build any UI here.
 */

export function renderPageEditor(mount: HTMLElement, _params: { pageId: number }): () => void {
  const root = document.createElement("div");
  root.className = "page-editor-placeholder";
  mount.append(root);

  return () => {
    root.remove();
  };
}
