import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/shell.css";

import { renderSidebar } from "./shell/sidebar";
import { renderToolbar } from "./shell/toolbar";
import { startRouter } from "./shell/router";

// The three shell regions (01-UI-SPEC.md §8): sidebar, toolbar, and a
// full-bleed content region the router mounts each view into. All three
// are direct children of `.app-shell` so the CSS grid's `grid-area`
// assignment in shell.css applies to each one directly.
const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("#app root element is missing from index.html");
}
app.className = "app-shell";

renderSidebar(app);
renderToolbar(app);

const content = document.createElement("div");
content.className = "app-content";
app.append(content);

startRouter(content);
