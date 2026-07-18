import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "../theme/ThemeProvider";
import { appRoutes } from "./router";

vi.mock("../routes/MissionControlRoute", () => ({ MissionControlRoute: () => <div>Mission route content</div> }));
vi.mock("../routes/CustomersRoute", () => ({ CustomersRoute: () => <div>Customer route content</div> }));

function renderRoute(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<ThemeProvider preference="dark"><QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider></ThemeProvider>);
  return router;
}

describe("application routing", () => {
  it("redirects the root to Mission Control", async () => {
    const router = renderRoute("/");
    expect(await screen.findByText("Mission route content")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/mission-control");
  });

  it("renders Customers directly and marks its navigation link active", async () => {
    renderRoute("/customers");
    expect(await screen.findByText("Customer route content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute("aria-current", "page");
  });

  it("preserves browser-style back and forward navigation", async () => {
    const router = renderRoute("/mission-control");
    await screen.findByText("Mission route content");
    await router.navigate("/customers");
    expect(await screen.findByText("Customer route content")).toBeInTheDocument();
    await router.navigate(-1);
    expect(await screen.findByText("Mission route content")).toBeInTheDocument();
    await router.navigate(1);
    expect(await screen.findByText("Customer route content")).toBeInTheDocument();
  });

  it("renders a constrained not-found route inside the workspace", async () => {
    renderRoute("/unknown");
    expect(await screen.findByRole("heading", { name: "Page not found", level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-workspace");
  });

  it("provides skip navigation and keeps the AI workspace absent", async () => {
    renderRoute("/mission-control");
    await screen.findByText("Mission route content");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-workspace");
    expect(screen.queryByRole("complementary", { name: "AI workspace" })).not.toBeInTheDocument();
  });

  it("closes mobile navigation with Escape and restores trigger focus", async () => {
    const user = userEvent.setup();
    renderRoute("/mission-control");
    const trigger = await screen.findByRole("button", { name: "Open navigation" });
    await user.click(trigger);
    expect(screen.getByRole("complementary", { name: "Mobile application navigation" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Mobile application navigation" })).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
