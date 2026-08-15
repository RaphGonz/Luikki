import { defineConfig } from "vitest/config";

// No jsdom, no happy-dom: every test this phase writes is pure maths or
// pure data mapping (RESEARCH.md Pattern 6), so a DOM environment buys
// nothing yet.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
});
