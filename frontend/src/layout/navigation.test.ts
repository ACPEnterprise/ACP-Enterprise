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

  it("keeps the available Purchasing workspace discoverable in Operations", () => {
    const purchasing = navigationCatalog.find((item) => item.id === "purchasing");
    const operations = navigationGroups.find((group) => group.id === "operations");

    expect(purchasing).toMatchObject({
      label: "Purchasing",
      path: "/purchasing",
      availability: "available",
      requiredPermission: "COMPANY_PURCHASING_READ",
    });
    expect(operations?.items).toContain(purchasing);
  });

  it("groups real financial routes under Accounting without duplicating operational entries", () => {
    const accounting = navigationGroups.find((group) => group.id === "accounting");
    const operations = navigationGroups.find((group) => group.id === "operations");

    expect(accounting?.items.map((entry) => [entry.label, entry.path])).toEqual([
      ["Overview", "/accounting"],
      ["Financial Reports", "/financial-reports"],
      ["Accounts Receivable", "/invoices"],
      ["Accounts Payable", "/accounts-payable"],
      ["Payments & Receipts", "/payments"],
      ["Payroll Accounting", "/payroll"],
    ]);
    expect(operations?.items.map((entry) => entry.id)).toEqual(
      expect.arrayContaining(["revenue-cycle", "purchasing"]),
    );
    expect(operations?.items.map((entry) => entry.id)).not.toEqual(
      expect.arrayContaining(["invoices", "payments", "payroll", "accounts-payable", "financial-reports"]),
    );
  });
});
