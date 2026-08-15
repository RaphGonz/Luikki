/**
 * The eight-segment pipeline stage strip (01-UI-SPEC.md §1): the visible
 * face of the stage registry built in plan 01-04. `segmentStates` is a pure
 * state-model function with its own DOM-free test suite; `renderStageStrip`
 * is the only place that builds DOM from it, in either the page grid's
 * compact 4px form or the page detail toolbar's 24px labelled form.
 *
 * 01-UI-SPEC.md §1 declares two distinct not-yet-reached situations: a
 * stage that is reachable in a future phase, and a stage whose runner
 * simply does not exist in this phase (only Import has one right now). The
 * spec requires both to render identically, because the artist should
 * never see an internal not-implemented distinction leak into the UI. The
 * per-stage runner-availability flag the registry endpoint truthfully
 * reports is therefore deliberately not consulted anywhere below -- do not
 * "fix" this into two different neutral treatments; that would violate the
 * exact contract this component exists to enforce.
 */

import type { StageDto } from "../api/types";
import "../styles/pages.css";

export type SegmentState = "complete" | "current" | "not-reached";

export interface SegmentModel {
  name: string;
  displayName: string;
  state: SegmentState;
  tooltip: string;
}

const NOT_REACHED_TOOLTIP = "Available in a later phase";

/**
 * Pure: no DOM, no fetch. `currentStage` is located by name inside
 * `stages`' own declaration order -- the eight stages always come from
 * `api.pipeline.stages()`, never a hardcoded list, so this function has no
 * knowledge of stage names or count beyond what it is handed.
 */
export function segmentStates(stages: StageDto[], currentStage: string): SegmentModel[] {
  const currentIndex = stages.findIndex((stage) => stage.name === currentStage);
  return stages.map((stage, index) => {
    const state: SegmentState =
      index < currentIndex ? "complete" : index === currentIndex ? "current" : "not-reached";
    return {
      name: stage.name,
      displayName: stage.display_name,
      state,
      tooltip: state === "not-reached" ? NOT_REACHED_TOOLTIP : "",
    };
  });
}

/**
 * Builds the strip DOM from an already-computed model. Segments carry no
 * click handlers and no focusable elements beyond the tooltip-bearing
 * `title` -- nothing past Import is reachable this phase, so nothing here
 * is interactive. `role="list"`/`role="listitem"` plus a per-segment
 * accessible name (`"{display name}: {state}"`) keep the state legible
 * without relying on colour alone.
 */
export function renderStageStrip(
  mount: HTMLElement,
  model: SegmentModel[],
  variant: "compact" | "full",
): void {
  mount.replaceChildren();

  const strip = document.createElement("div");
  strip.className =
    variant === "compact" ? "stage-strip stage-strip--compact" : "stage-strip stage-strip--full";
  strip.setAttribute("role", "list");
  strip.setAttribute("aria-label", "Pipeline stages");

  for (const segment of model) {
    const item = document.createElement("div");
    item.className = `stage-segment stage-segment--${segment.state}`;
    item.setAttribute("role", "listitem");
    item.setAttribute("aria-label", `${segment.displayName}: ${segment.state}`);
    if (segment.tooltip) {
      item.title = segment.tooltip;
    }

    const fill = document.createElement("div");
    fill.className = "stage-segment-fill";
    item.append(fill);

    if (variant === "full") {
      const label = document.createElement("div");
      label.className = "stage-segment-label";
      label.textContent = segment.displayName;
      item.append(label);
    }

    strip.append(item);
  }

  mount.append(strip);
}
