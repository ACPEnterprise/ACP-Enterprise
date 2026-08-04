import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { ThemeProvider } from "../theme/ThemeProvider";
import { appRoutes } from "./router";

vi.mock("../routes/MissionControlRoute", () => ({ MissionControlRoute: () => <div>Mission route content</div> }));
vi.mock("../routes/CommandCenterRoute", () => ({ CommandCenterRoute: () => <div>Command Center route content</div> }));
vi.mock("../routes/CustomersRoute", () => ({ CustomersRoute: () => <div>Customer route content</div> }));
vi.mock("../routes/CustomerDetailRoute", () => ({ CustomerDetailRoute: () => <div>Customer detail route content</div> }));
vi.mock("../routes/JobsRoute", () => ({ JobsRoute: () => <div>Jobs route content</div> }));
vi.mock("../routes/JobDetailRoute", () => ({ JobDetailRoute: () => <div>Job detail route content</div> }));
vi.mock("../routes/AppointmentDetailRoute", () => ({ AppointmentDetailRoute: () => <div>Appointment detail route content</div> }));
vi.mock("../routes/DispatchRoute", () => ({ DispatchRoute: () => <div>Dispatch route content</div> }));
vi.mock("../features/engineering-mobile/MobileEngineeringListPage", () => ({ MobileEngineeringListPage: () => <div>Engineering route content</div> }));
vi.mock("../features/engineering-mobile/MobileEngineeringDetailPage", () => ({ MobileEngineeringDetailPage: () => <div>Engineering detail route content</div> }));

const authenticatedContext: AuthenticationContextValue = {
  status: "authenticated",
  activeCompany: null,
  user: {
    id: "user-1",
    normalized_email: "admin@example.com",
    first_name: "Preview",
    last_name: "Administrator",
    display_name: "Preview Administrator",
    email_verified_at: null,
  },
  signIn: vi.fn(),
  signOut: vi.fn(),
  signOutAll: vi.fn(),
  requireReauthentication: vi.fn(),
};

function renderRoute(path: string, context: AuthenticationContextValue = authenticatedContext) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<ThemeProvider preference="dark"><AuthenticationContext.Provider value={context}><QueryClientProvider client={queryClient}><RouterProvider router={router} /></QueryClientProvider></AuthenticationContext.Provider></ThemeProvider>);
  return router;
}

describe("application routing", () => {
  it("redirects an unauthenticated user to login without looping", async () => {
    const router = renderRoute("/customers", { ...authenticatedContext, status: "unauthenticated", user: null });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("uses Command Center as the authenticated landing route", async () => {
    const router = renderRoute("/");
    expect(await screen.findByText("Command Center route content")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(screen.getByRole("link", { name: "Command Center" })).toHaveAttribute("aria-current", "page");
  });

  it("renders Customers directly and marks its navigation link active", async () => {
    renderRoute("/customers");
    expect(await screen.findByText("Customer route content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute("aria-current", "page");
  });

  it("supports direct Customer detail navigation through the protected shell", async () => {
    renderRoute("/customers/customer-1");
    expect(await screen.findByText("Customer detail route content")).toBeInTheDocument();
    expect(
      screen
        .getAllByRole("link", { name: "Customers" })
        .find((link) => link.getAttribute("aria-current") === "page"),
    ).toBeDefined();
  });

  it("routes Jobs list and detail through the application shell", async () => {
    const router = renderRoute("/jobs");
    expect(await screen.findByText("Jobs route content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
    await router.navigate("/jobs/job-1");
    expect(await screen.findByText("Job detail route content")).toBeInTheDocument();
  });

  it("supports direct Appointment detail navigation through the protected shell", async () => {
    const router = renderRoute("/appointments/appointment-1");
    expect(await screen.findByText("Appointment detail route content")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/appointments/appointment-1");
  });

  it("loads Dispatch directly through the protected application shell", async () => {
    renderRoute("/dispatch");
    expect(await screen.findByText("Dispatch route content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dispatch" })).toHaveAttribute("aria-current", "page");
  });

  it("routes Engineering list and detail through the protected shell", async () => {
    const router = renderRoute("/engineering");
    expect(await screen.findByText("Engineering route content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Engineering Factory" })).toHaveAttribute("aria-current", "page");
    await router.navigate("/engineering/command-1");
    expect(await screen.findByText("Engineering detail route content")).toBeInTheDocument();
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
    expect(screen.getAllByRole("link", { name: "Customers" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Jobs" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Dispatch" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Engineering Factory" })).toHaveLength(2);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Mobile application navigation" })).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
