import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { brandConfig } from "../branding/brandConfig";
import { ThemeProvider } from "../theme/ThemeProvider";
import { ApplicationHeader } from "./ApplicationHeader";

describe("ApplicationHeader", () => {
  it("renders route metadata and accessible breadcrumbs", () => {
    render(
      <MemoryRouter>
        <ThemeProvider preference="dark">
          <ApplicationHeader brand={brandConfig} metadata={{ pageTitle: "Customer Detail", breadcrumbs: [{ label: "Customers", path: "/customers" }, { label: "Customer Detail" }] }} onOpenNavigation={() => undefined} navigationTriggerRef={createRef()} />
        </ThemeProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Customer Detail" })).toBeInTheDocument();
    const breadcrumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(breadcrumbs).toBeInTheDocument();
    expect(within(breadcrumbs).getByText("Customer Detail")).toHaveAttribute("aria-current", "page");
  });

  it("changes the active theme preference", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><ThemeProvider preference="dark"><ApplicationHeader brand={brandConfig} metadata={{ pageTitle: "Mission Control", breadcrumbs: [] }} onOpenNavigation={() => undefined} navigationTriggerRef={createRef()} /></ThemeProvider></MemoryRouter>);
    await user.selectOptions(screen.getByRole("combobox", { name: "Theme preference" }), "light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });
});
