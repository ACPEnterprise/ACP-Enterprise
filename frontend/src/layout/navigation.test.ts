import { describe, expect, it } from "vitest";

import { navigationCatalog, navigationGroups } from "./navigation";

describe("employee mobile navigation", () => {
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

  it("registers the time clock as an own-read-scoped operations destination", () => {
    const workday = navigationCatalog.find((item) => item.id === "workday");
    const operations = navigationGroups.find((group) => group.id === "operations");

    expect(workday).toMatchObject({
      label: "My time clock",
      path: "/workday",
      availability: "available",
      requiredPermission: "COMPANY_TIMEKEEPING_OWN_READ",
    });
    expect(operations?.items).toContain(workday);
  });
});
