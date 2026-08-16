/**
 * The standing destructive-confirmation dialog `01-UI-SPEC.md` §3 specified
 * in Phase 1 and left unreachable there ("Phase 1 does not need a working
 * instance of this dialog... the component and copy contract above is what
 * Phase 2 onward must implement without re-deriving it"). `02-UI-SPEC.md`
 * §8 supplies the first two computable instances (Protected -> Panels,
 * Panels -> Import); Phases 3 to 7 reuse this exact component for their own
 * destructive Go-Backs rather than writing their own.
 *
 * The rule that makes this component correct: every visible string --
 * heading, body, confirm label, cancel label -- comes from the server's
 * `GoBackTargetDto` and is set with `.textContent`. This component holds no
 * template string, no pluralisation logic and no default copy of its own.
 * `01-UI-SPEC.md` §3 forbids a vague sentence with no numbers in it, and the
 * only reliable way to honour that from the client is for the client to
 * have no ability to produce one -- if the server cannot yet compute a
 * target's affected-count, it simply omits that target from the list this
 * component is given, and a dialog opened with an empty list renders
 * nothing at all.
 *
 * T-01-XSS: every string is set via `.textContent`; raw-markup insertion is
 * never used.
 */

import type { GoBackTargetDto, PipelineStageName } from "../api/types";

const NOOP: () => void = () => {};

export function openGoBackDialog(
  mount: HTMLElement,
  targets: GoBackTargetDto[],
  onConfirm: (stage: PipelineStageName) => Promise<void>,
): () => void {
  // "A Go-Back with no number in it is never shown" -- extended here to
  // "a Go-Back with nothing to go back to is simply not offered": an empty
  // target list renders nothing and returns a no-op teardown.
  if (targets.length === 0) {
    return NOOP;
  }

  let selectedIndex = 0;
  let confirmInFlight = false;
  let disposed = false;

  const overlay = document.createElement("div");
  overlay.className = "go-back-dialog-overlay";

  const panel = document.createElement("div");
  panel.className = "go-back-dialog";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");

  const heading = document.createElement("h2");
  heading.className = "go-back-dialog-heading";

  const targetList = document.createElement("div");
  targetList.className = "go-back-dialog-targets";
  targetList.setAttribute("role", "radiogroup");

  const targetButtons: HTMLButtonElement[] = targets.map((target, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "go-back-dialog-target";
    button.setAttribute("role", "radio");
    button.textContent = target.display_name;
    button.addEventListener("click", () => selectTarget(index));
    targetList.append(button);
    return button;
  });

  const body = document.createElement("p");
  body.className = "go-back-dialog-body";

  const actions = document.createElement("div");
  actions.className = "go-back-dialog-actions";

  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "go-back-dialog-cancel";

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "go-back-dialog-confirm destructive";

  actions.append(cancelButton, confirmButton);
  // Only rendered as a selectable list when there is a real choice to make
  // -- a single target has nothing to select and Task 1's acceptance
  // criteria require no list markup in that case.
  panel.append(heading, ...(targets.length > 1 ? [targetList] : []), body, actions);
  overlay.append(panel);
  mount.append(overlay);

  function syncSelectedTarget(): void {
    const target = targets[selectedIndex];
    heading.textContent = target.heading;
    body.textContent = target.body;
    confirmButton.textContent = target.confirm_label;
    cancelButton.textContent = target.cancel_label;
    for (const [index, button] of targetButtons.entries()) {
      const isSelected = index === selectedIndex;
      button.classList.toggle("is-selected", isSelected);
      button.setAttribute("aria-checked", String(isSelected));
    }
  }

  function selectTarget(index: number): void {
    if (confirmInFlight) return;
    selectedIndex = index;
    syncSelectedTarget();
  }

  function teardown(): void {
    if (disposed) return;
    disposed = true;
    document.removeEventListener("keydown", onKeyDown);
    overlay.remove();
  }

  function onKeyDown(event: KeyboardEvent): void {
    if (event.key === "Escape") teardown();
  }

  cancelButton.addEventListener("click", () => teardown());

  confirmButton.addEventListener("click", () => {
    // The confirm button disables while `onConfirm` is in flight so a
    // double-click (T-2-42) cannot issue two go-back transitions -- the
    // guard below is checked synchronously, before the first `await`, so
    // the second click of a double-click always loses the race.
    if (confirmInFlight) return;
    confirmInFlight = true;
    confirmButton.disabled = true;

    const stage = targets[selectedIndex].stage;
    onConfirm(stage)
      .then(() => {
        if (!disposed) teardown();
      })
      .catch(() => {
        // The caller (pageEditor.ts) reports the error via a toast; this
        // dialog's only responsibility on failure is to stay open and let
        // the artist retry rather than silently discarding their intent.
        confirmInFlight = false;
        if (!disposed) confirmButton.disabled = false;
      });
  });

  document.addEventListener("keydown", onKeyDown);

  syncSelectedTarget();
  // Focus lands on cancel, not confirm, so the destructive action is never
  // the default (T-2-44) -- the artist must deliberately reach for it.
  cancelButton.focus();

  return teardown;
}
