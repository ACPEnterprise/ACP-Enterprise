import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { PriceBookRoute } from "./PriceBookRoute";

const authState = vi.hoisted(() => ({
  permissionCodes: ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE", "COMPANY_PRICE_BOOK_ACTIVATE"],
}));

vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      id: "company-1",
      branches: [{ id: "branch-1", name: "Main", code: "MAIN" }],
    },
    permissionCodes: authState.permissionCodes,
  }),
  useHasPermission: (code: string) => authState.permissionCodes.includes(code),
}));
vi.mock("../hooks/usePriceBook", () => ({
  usePriceBook: () => ({
    isPending: false,
    isError: false,
    data: {
      categories: [{ id: "category-1", name: "Drain", code: "DRAIN" }],
      tax_classifications: [{ id: "tax-1", name: "Taxable", code: "TAXABLE" }],
      service_items: [{ id: "item-1", name: "Drain clearing", code: "DRAIN-CLEAR", status: "draft", customer_description: "Clear a drain." }],
      versions: [{ id: "version-1", service_item_id: "item-1", revision: 1, currency: "USD", unit_price: "149.95", status: "draft", version: 1 }],
      option_groups: [{ id: "group-1", name: "Service level", code: "SERVICE-LEVEL" }],
      options: [],
    },
  }),
  usePriceBookMutations: () => ({
    category: { isPending: false, mutateAsync: vi.fn() }, tax: { isPending: false, mutateAsync: vi.fn() }, item: { isPending: false, mutateAsync: vi.fn() }, version: { isPending: false, mutateAsync: vi.fn() }, activate: { mutateAsync: vi.fn() }, optionGroup: { isPending: false, mutateAsync: vi.fn() }, option: { isPending: false, mutateAsync: vi.fn() },
  }),
}));

describe("PriceBookRoute", () => {
  it("fails closed without Price Book read authority", () => {
    authState.permissionCodes = [];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByText("You are not authorized to view Price Book.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
  });

  it("lets read-only users browse without mutation controls", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ"];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByText("Drain clearing")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate version" })).not.toBeInTheDocument();
  });

  it("gates manage and activate controls independently", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE"];
    const { unmount } = render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "Create category" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Activate version" })).not.toBeInTheDocument();
    unmount();
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_ACTIVATE"];
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "Create category" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate version" })).toBeVisible();
  });

  it("renders complete management workflows on a narrow viewport", () => {
    authState.permissionCodes = ["COMPANY_PRICE_BOOK_READ", "COMPANY_PRICE_BOOK_MANAGE", "COMPANY_PRICE_BOOK_ACTIVATE"];
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    render(<MemoryRouter><PriceBookRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Price Book" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create service item" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create tax classification" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Create option group" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Activate version" })).toBeVisible();
  });
});
