/**
 * Minimal DOM mount/reset helpers for jsdom-environment test files only.
 *
 * Import this module ONLY from a test file whose first line is the
 * `// @vitest-environment jsdom` docblock (vitest.config.ts keeps the
 * project default at `environment: "node"` — this module assumes a real
 * `document` exists, which is true only under that per-file opt-in).
 * Importing it from a node-environment test will throw at import time
 * because `document` is undefined there.
 *
 * Uses `textContent` and `append` only — never the HTML-string-parsing DOM
 * setter Phase 1's T-01-XSS control forbids.
 */

export function mountTestRoot(): HTMLElement {
  const root = document.createElement("div");
  document.body.append(root);
  return root;
}

export function resetTestRoot(): void {
  document.body.textContent = "";
}
