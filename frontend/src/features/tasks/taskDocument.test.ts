import { describe, expect, it } from "vitest";

import {
  buildTaskDocumentFromEditors,
  createEmptyTaskDocument,
  serializeTaskBodyForEditor,
  serializeTaskDocument,
} from "@/features/tasks/taskDocument";

describe("taskDocument", () => {
  it("does not serialize empty document sections", () => {
    expect(
      buildTaskDocumentFromEditors(
        "## Описание\nApproved workflow body\n\n## Acceptance criteria\nFilter preset is restored after refresh.",
        "",
      ),
    ).toBe(
      "## Описание\nApproved workflow body\n\n## Acceptance criteria\nFilter preset is restored after refresh.",
    );
  });

  it("keeps plain description content unwrapped when it is the only section", () => {
    expect(
      serializeTaskDocument({
        ...createEmptyTaskDocument(),
        description: "Approved workflow body",
      }),
    ).toBe("Approved workflow body");
  });

  it("does not show empty structured sections in the editor body", () => {
    expect(
      serializeTaskBodyForEditor({
        ...createEmptyTaskDocument(),
        description: "Approved workflow body",
        acceptanceCriteria: "Filter preset is restored after refresh.",
      }),
    ).toBe(
      "## Описание\nApproved workflow body\n\n## Acceptance criteria\nFilter preset is restored after refresh.",
    );
  });
});
