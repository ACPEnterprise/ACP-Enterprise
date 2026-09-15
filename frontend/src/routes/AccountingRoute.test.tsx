import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccountingRoute } from "./AccountingRoute";

let permissions = new Set<string>();

vi.mock("../auth/usePermissions", () => ({
  useEffectivePermissions: () => permissions,
}));

describe("AccountingRoute", () => {
  beforeEach(() => {
    permissions = new Set();
  });

  it("links only to existing surfaces allowed by current permissions", () => {
    permissions = new Set(["COMPANY_ACCOUNTING_REPORT_READ", "COMPANY_INVOICE_READ"]);
    render(<MemoryRouter><AccountingRoute /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "Open Financial Reports" })).toHaveAttribute("href", "/financial-reports");
    expect(screen.getByRole("link", { name: "Open Accounts Receivable" })).toHaveAttribute("href", "/invoices");
    expect(screen.queryByRole("link", { name: "Open Payroll Accounting" })).not.toBeInTheDocument();
    expect(screen.queryByText("Chart of Accounts")).not.toBeInTheDocument();
  });

  it("accepts AP reporting authority without exposing other accounting areas", () => {
    permissions = new Set(["COMPANY_ACCOUNTS_PAYABLE_REPORT_READ"]);
    render(<MemoryRouter><AccountingRoute /></MemoryRouter>);

    expect(screen.getByRole("link", { name: "Open Accounts Payable" })).toHaveAttribute("href", "/accounts-payable");
    expect(screen.queryByRole("link", { name: "Open Payments & Receipts" })).not.toBeInTheDocument();
  });

  it("fails closed when no supported accounting read permission exists", () => {
    render(<MemoryRouter><AccountingRoute /></MemoryRouter>);
    expect(screen.getByText("You do not have permission to open an Accounting workspace.")).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "Accounting tasks" })).not.toBeInTheDocument();
  });

  it("preserves browser back and forward behavior across existing routes", async () => {
    permissions = new Set(["COMPANY_ACCOUNTING_REPORT_READ"]);
    const router = createMemoryRouter([
      { path: "/accounting", Component: AccountingRoute },
      { path: "/financial-reports", element: <h1>Existing Financial Reports</h1> },
    ], { initialEntries: ["/accounting"] });
    render(<RouterProvider router={router} />);

    await userEvent.click(screen.getByRole("link", { name: "Open Financial Reports" }));
    expect(await screen.findByRole("heading", { name: "Existing Financial Reports" })).toBeVisible();
    await router.navigate(-1);
    expect(await screen.findByRole("heading", { name: "Accounting workspace" })).toBeVisible();
    await router.navigate(1);
    expect(await screen.findByRole("heading", { name: "Existing Financial Reports" })).toBeVisible();
  });
});
