---
status: testing
phase: 01-foundation-project-palette-pipeline-backbone
source: [01-VERIFICATION.md]
started: 2026-08-16T00:00:00Z
updated: 2026-08-16T00:00:00Z
---

## Current Test

number: 1
name: Create a named project via the picker, add a volume and pages, close the app (POST /close or quit the server), reopen it and navigate back in.
expected: |
  The same project opens with its volumes, pages, thumbnails and palette all present;
  nothing looks reset or partially loaded.
awaiting: user response

## Tests

### 1. Create a named project via the picker, add a volume and pages, close the app (POST /close or quit the server), reopen it and navigate back in.
expected: The same project opens with its volumes, pages, thumbnails and palette all present; nothing looks reset or partially loaded.
result: [pending]

### 2. Drag-and-drop a batch of line art pages onto a volume, including one corrupt/non-image file, then add more pages to the same volume in a later session.
expected: Good pages appear with thumbnails and a stage indicator at "Panels"; the bad file is reported inline without losing the others; later uploads append rather than replace.
result: [pending]

### 3. Upload a swatch image with a few flat colour chips; separately upload a character sheet, then accept some proposals and reject/discard others individually, naming the character.
expected: Swatch upload creates named "Colour N" entries matching the chip colours; sheet proposals render as dashed cards the artist can accept one-by-one into "{character} / {part}" entries, and the sheet stays actionable after a partial accept (CR-04 fix).
result: [pending]

### 4. Rename, recolour and delete a palette entry by hand; then recolour an entry that came from a swatch or sheet and watch for a toast, not a confirmation dialog.
expected: Recolour applies immediately with an "Updated on N pages." toast and no confirmation step (D-09); rename and delete work with no stage-chain interaction.
result: [pending]

### 5. Open a page from the grid and confirm the stage strip shows "Import"/"Panels" complete and every later stage visually neutral, identically, regardless of whether a runner exists.
expected: The strip renders 8 segments with the current position highlighted and all not-yet-reached segments looking the same (01-UI-SPEC.md contract).
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
