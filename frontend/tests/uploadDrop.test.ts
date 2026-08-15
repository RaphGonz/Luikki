import { describe, expect, it } from "vitest";

import type { PageDto, PageUploadDto } from "../src/api/types";
import { partitionUploadResult } from "../src/components/uploadDrop";

function page(id: number): PageDto {
  return {
    id,
    volume_id: 1,
    index: id,
    original_name: `page-${id}.png`,
    width: 1000,
    height: 1400,
    stage: "panels",
    image_url: `/api/pages/${id}/image`,
  };
}

describe("partitionUploadResult", () => {
  it("all-accepted yields empty failures and an empty summary", () => {
    const result: PageUploadDto = { accepted: [page(1), page(2)], rejected: [] };
    const outcome = partitionUploadResult(result);
    expect(outcome.added).toHaveLength(2);
    expect(outcome.failures).toHaveLength(0);
    expect(outcome.summary).toBe("");
  });

  it("a mixed result keeps every accepted page and every failure with its detail", () => {
    const result: PageUploadDto = {
      accepted: [page(1)],
      rejected: [
        {
          filename: "bad.txt",
          detail: "Upload failed: the file isn't a readable image — try a PNG, JPG or TIFF.",
        },
      ],
    };
    const outcome = partitionUploadResult(result);
    expect(outcome.added).toEqual([page(1)]);
    expect(outcome.failures).toEqual([
      {
        filename: "bad.txt",
        detail: "Upload failed: the file isn't a readable image — try a PNG, JPG or TIFF.",
      },
    ]);
    expect(outcome.summary.length).toBeGreaterThan(0);
  });

  it("an all-rejected result yields an empty added and a non-empty summary", () => {
    const result: PageUploadDto = {
      accepted: [],
      rejected: [{ filename: "bad.txt", detail: "unreadable file" }],
    };
    const outcome = partitionUploadResult(result);
    expect(outcome.added).toHaveLength(0);
    expect(outcome.summary.length).toBeGreaterThan(0);
  });

  it("the summary never equals a generic 'Something went wrong' sentence", () => {
    const result: PageUploadDto = {
      accepted: [],
      rejected: [{ filename: "bad.txt", detail: "unreadable file" }],
    };
    const outcome = partitionUploadResult(result);
    expect(outcome.summary.toLowerCase()).not.toBe("something went wrong");
  });
});
