/**
 * A dashed-border 120x120 proposal card (01-UI-SPEC.md §5): visually
 * distinct from a confirmed swatch card by a dashed `--color-border`, so
 * it reads as provisional at a glance. Carries a multi-select checkbox
 * plus per-card Accept (accent) and Reject (destructive) controls.
 *
 * Rejecting a proposal removes the card immediately, with no confirmation
 * step and no server call -- a proposal was never persisted (D-05,
 * 01-10-SUMMARY.md), so discarding one costs nothing and re-uploading the
 * sheet reproduces it exactly. This deliberately does NOT use the §3
 * "Go back" destructive-confirmation pattern, which is reserved for
 * actions with real cost.
 *
 * T-01-XSS: every string is set via `.textContent`/`.value`, never via
 * raw-markup injection.
 */

import type { ProposalDto, RGBTuple, SheetAcceptItemDto } from "../api/types";

export interface ProposalCardHandlers {
  onToggleSelect: (index: number, selected: boolean) => void;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
}

function toHex([r, g, b]: RGBTuple): string {
  const channel = (n: number) => n.toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

/**
 * Builds one dashed proposal card and appends it to `mount`. Returns the
 * card element so a caller can remove it directly on reject.
 */
export function renderProposalCard(
  mount: HTMLElement,
  proposal: ProposalDto,
  selected: boolean,
  handlers: ProposalCardHandlers,
): HTMLElement {
  const card = document.createElement("div");
  card.className = "proposal-card";
  if (selected) card.classList.add("proposal-card--selected");

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "proposal-card__select";
  checkbox.checked = selected;
  checkbox.setAttribute("aria-label", `Select proposal ${proposal.index + 1}`);
  checkbox.addEventListener("change", () => {
    card.classList.toggle("proposal-card--selected", checkbox.checked);
    handlers.onToggleSelect(proposal.index, checkbox.checked);
  });

  const colour = document.createElement("div");
  colour.className = "proposal-card__colour";
  colour.style.background = toHex(proposal.rgb);

  const controls = document.createElement("div");
  controls.className = "proposal-card__controls";

  // Icon-only accent control: aria-label="Accept proposal".
  const acceptButton = document.createElement("button");
  acceptButton.type = "button";
  acceptButton.className = "proposal-card__accept accent";
  acceptButton.setAttribute("aria-label", "Accept proposal");
  acceptButton.textContent = "✓";
  acceptButton.addEventListener("click", () => handlers.onAccept(proposal.index));

  // Icon-only destructive control, no confirmation step: aria-label="Reject proposal".
  const rejectButton = document.createElement("button");
  rejectButton.type = "button";
  rejectButton.className = "proposal-card__reject destructive";
  rejectButton.setAttribute("aria-label", "Reject proposal");
  rejectButton.textContent = "×";
  rejectButton.addEventListener("click", () => handlers.onReject(proposal.index));

  controls.append(acceptButton, rejectButton);
  card.append(checkbox, colour, controls);
  mount.append(card);
  return card;
}

/**
 * Pure. Mirrors the server's own `_entry_label` (plan 01-10,
 * `web/routers/reference.py`) for optimistic display only -- the entries
 * actually returned by `POST .../accept` are authoritative, this is not
 * where the two could silently diverge in a way that matters.
 */
export function entryLabel(character: string, part: string): string {
  return `${character.trim()} / ${part.trim()}`;
}

/** Thrown by `acceptPayload` so callers can render an inline message
 * instead of sending a request the server would reject. */
export class ProposalValidationError extends Error {}

export interface ProposalSelectionEntry {
  index: number;
  selected: boolean;
  part: string;
}

export interface ProposalSelection {
  characterName: string;
  entries: ProposalSelectionEntry[];
}

/** The exact `SheetAcceptRequest` shape `POST .../accept` expects
 * (01-10-SUMMARY.md), so `acceptPayload`'s result can be sent verbatim. */
export interface SheetAcceptRequest {
  character_name: string;
  items: SheetAcceptItemDto[];
}

/**
 * Pure. Maps a selection into the exact accept-request shape: drops every
 * unselected proposal (that is what rejection *is* when nothing was ever
 * persisted -- T-01-EPHEM), trims both the character name and every part,
 * and throws a typed `ProposalValidationError` before anything invalid
 * would leave the browser.
 */
export function acceptPayload(selection: ProposalSelection): SheetAcceptRequest {
  const characterName = selection.characterName.trim();
  if (!characterName) {
    throw new ProposalValidationError(
      "Name the character before accepting proposals.",
    );
  }

  const items: SheetAcceptItemDto[] = [];
  for (const entry of selection.entries) {
    if (!entry.selected) continue;
    const part = entry.part.trim();
    if (!part) {
      throw new ProposalValidationError(
        "Every accepted entry needs a part before it can be added.",
      );
    }
    items.push({ index: entry.index, part });
  }

  return { character_name: characterName, items };
}
