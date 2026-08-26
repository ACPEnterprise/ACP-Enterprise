import { describe, expect, it } from "vitest";

import { technicianHandle } from "./routeMetadata";

describe("technician route metadata", () => {
  it("provides accessible workspace context", () => {
    expect(technicianHandle.workspace).toEqual({
      pageTitle: "My day",
      breadcrumbs: [{ label: "My day" }],
      helpTopic: "technician-itinerary",
      aiContext: "technician-itinerary",
    });
  });
});
