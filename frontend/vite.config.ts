import { defineConfig } from "vite";

// Two-process dev setup (RESEARCH.md Pattern 2): `vite dev` proxies `/api`
// to the FastAPI dev server (`uvicorn --reload` on 127.0.0.1:8000). In
// production, FastAPI serves this project's `dist/` directly from the same
// process (plan 01-06's `app.frontend("/", directory="frontend/dist")`),
// so `build.outDir` must stay the default `dist`.
export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
