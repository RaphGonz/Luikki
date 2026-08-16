import { defineConfig } from "vitest/config";

// Phase 2 opens a jsdom path for the canvas editor's DOM/ARIA assertions
// (D-26 — jsdom only, the native `canvas` package is rejected). The
// project default STAYS "node": most tests here are still pure maths or
// pure data mapping (RESEARCH.md Pattern 6), and a global jsdom would
// silently change their semantics. jsdom is opted into per file via a
// `// @vitest-environment jsdom` docblock as each file's first line
// (see frontend/tests/editor/domEnvironment.test.ts) — never globally.
// `tests/**/*.test.ts` already matches `tests/editor/**/*.test.ts`;
// no separate include entry is needed.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
