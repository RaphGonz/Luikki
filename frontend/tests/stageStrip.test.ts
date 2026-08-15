import { describe, expect, it } from "vitest";

import type { PipelineStageName, StageDto } from "../src/api/types";
import { segmentStates } from "../src/components/stageStrip";

const STAGE_NAMES: PipelineStageName[] = [
  "import",
  "panels",
  "protected",
  "zones",
  "propose",
  "snap",
  "review",
  "export",
];

/**
 * Builds an eight-stage registry response with a configurable subset of
 * runner-having stages -- the identical-model test below proves
 * `segmentStates` ignores this flag entirely (01-UI-SPEC.md §1).
 */
function stages(withRunner: PipelineStageName[] = ["import"]): StageDto[] {
  return STAGE_NAMES.map((name, index) => ({
    name,
    display_name: name.charAt(0).toUpperCase() + name.slice(1),
    upstream: index === 0 ? null : STAGE_NAMES[index - 1],
    produces: `${name} output`,
    has_runner: withRunner.includes(name),
  }));
}

describe("segmentStates", () => {
  it("marks exactly one complete, one current, six not-reached for currentStage='panels'", () => {
    const model = segmentStates(stages(), "panels");
    expect(model.filter((segment) => segment.state === "complete")).toHaveLength(1);
    expect(model.filter((segment) => segment.state === "current")).toHaveLength(1);
    expect(model.filter((segment) => segment.state === "not-reached")).toHaveLength(6);
    expect(model[0]?.state).toBe("complete");
    expect(model[1]?.state).toBe("current");
  });

  it("produces identical models for two stage lists differing only in runner availability", () => {
    const withExtraRunner = segmentStates(stages(["import", "panels"]), "panels");
    const withoutExtraRunner = segmentStates(stages(["import"]), "panels");
    expect(withExtraRunner).toEqual(withoutExtraRunner);
  });

  it("every not-reached segment carries the exact Copywriting Contract tooltip", () => {
    const model = segmentStates(stages(), "panels");
    for (const segment of model.filter((s) => s.state === "not-reached")) {
      expect(segment.tooltip).toBe("Available in a later phase");
    }
  });

  it("returns segments in the input's declaration order", () => {
    const model = segmentStates(stages(), "panels");
    expect(model.map((segment) => segment.name)).toEqual(STAGE_NAMES);
  });

  it("an unknown currentStage yields all not-reached and throws nothing", () => {
    expect(() => segmentStates(stages(), "nonexistent")).not.toThrow();
    const model = segmentStates(stages(), "nonexistent");
    expect(model.every((segment) => segment.state === "not-reached")).toBe(true);
  });
});
