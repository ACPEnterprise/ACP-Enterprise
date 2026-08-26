import { describe, expect, it } from "vitest";

import { navigationCatalog, navigationGroups } from "./navigation";

describe("technician navigation", () => {
  it("registers My day as a permission-scoped operations destination", () => {
    const technician = navigationCatalog.find((item) => item.id === "technician");
    const operations = navigationGroups.find((group) => group.id === "operations");

    expect(technician).toMatchObject({
      label: "My day",
      path: "/technician",
      availability: "available",
      requiredPermission: "COMPANY_JOB_EXECUTE",
    });
    expect(operations?.items).toContain(technician);
  });
});
