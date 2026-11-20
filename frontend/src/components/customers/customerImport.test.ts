import { describe, expect, it } from "vitest";

import { fileKind, validateCustomerCsv } from "./customerImport";

describe("customer import validation", () => {
  it("accepts common HCP headers and keeps source identities stable", () => {
    const preview = validateCustomerCsv(
      [
        "Customer ID,Customer Name,Email,Mobile Number,Service Address",
        "cus_1,Richard Ratliff,richard@example.com,555-0101,1 Main Street",
        "cus_2,All County Fixture,,555-0102,2 Main Street",
      ].join("\n"),
      "customers.csv",
      "company-all-county",
    );

    expect(preview.tenantId).toBe("company-all-county");
    expect(preview.sourceRows).toBe(2);
    expect(preview.readyRows).toBe(2);
    expect(preview.heldRows).toBe(0);
    expect(preview.rows[0]).toMatchObject({ sourceId: "cus_1", displayName: "Richard Ratliff", status: "ready" });
  });

  it("holds missing and duplicate source identities instead of guessing a merge", () => {
    const preview = validateCustomerCsv(
      [
        "id,name",
        "cus_1,First Customer",
        "cus_1,Duplicate Customer",
        ",Missing Identity",
      ].join("\n"),
      "customers.csv",
      "company-synthetic",
    );

    expect(preview.readyRows).toBe(0);
    expect(preview.heldRows).toBe(3);
    expect(preview.duplicateSourceIds).toBe(2);
    expect(preview.missingSourceIds).toBe(1);
    expect(preview.rows[1]?.status).toBe("held");
    expect(preview.rows[2]?.reasons).toContain("Add a source customer ID so retries cannot create duplicates.");
  });

  it("recognizes Excel files without pretending browser validation completed", () => {
    expect(fileKind("customers.xlsx")).toBe("excel");
    expect(fileKind("customers.xls")).toBeNull();
    expect(fileKind("customers.pdf")).toBeNull();
  });
});
