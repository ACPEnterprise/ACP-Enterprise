import { describe, expect, it } from "vitest";

import { employeeDetailPath } from "./paths";

describe("employee operations paths", () => {
  it("uses the canonical Employee route and safely encodes identity", () => {
    expect(employeeDetailPath("employee-1")).toBe(
      "/employees?employee=employee-1",
    );
    expect(employeeDetailPath("employee/foreign?scope=other")).toBe(
      "/employees?employee=employee%2Fforeign%3Fscope%3Dother",
    );
  });
});
