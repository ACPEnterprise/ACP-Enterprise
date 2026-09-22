import { describe, expect, it } from "vitest";

import { navigationCatalog, navigationGroups } from "./navigation";

describe("employee mobile navigation", () => {
  it("keeps My day permission-scoped without putting it in owner Operations", () => {
    const technician = navigationCatalog.find((item) => item.id === "technician");
    const myWork = navigationGroups.find((group) => group.id === "my-work");

    expect(technician).toMatchObject({
      label: "My day",
      path: "/technician",
      availability: "available",
      requiredPermission: "COMPANY_JOB_EXECUTE",
    });
    expect(myWork?.items).toContain(technician);
  });

  it("keeps the time clock in My work", () => {
    const workday = navigationCatalog.find((item) => item.id === "workday");
    const myWork = navigationGroups.find((group) => group.id === "my-work");

    expect(workday).toMatchObject({
      label: "My time clock",
      path: "/workday",
      availability: "available",
      requiredPermission: "COMPANY_TIMEKEEPING_OWN_READ",
    });
    expect(myWork?.items).toContain(workday);
  });

  it("keeps Purchasing discoverable in Office", () => {
    const purchasing = navigationCatalog.find((item) => item.id === "purchasing");
    const office = navigationGroups.find((group) => group.id === "office");

    expect(purchasing).toMatchObject({
      label: "Purchasing",
      path: "/purchasing",
      availability: "available",
      requiredPermission: "COMPANY_PURCHASING_READ",
    });
    expect(office?.items).toContain(purchasing);
  });
});
