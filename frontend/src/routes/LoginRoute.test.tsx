import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../auth/AuthenticationContext";
import { ThemeProvider } from "../theme/ThemeProvider";
import { LoginRoute } from "./LoginRoute";

function renderLogin(signIn: AuthenticationContextValue["signIn"]) {
  const context: AuthenticationContextValue = {
    status: "unauthenticated",
    activeCompany: null,
    user: null,
    signIn,
    signOut: vi.fn(),
    signOutAll: vi.fn(),
  };
  const router = createMemoryRouter([{ path: "/login", Component: LoginRoute }, { path: "/mission-control", element: <p>Mission Control loaded</p> }], { initialEntries: ["/login"] });
  render(<ThemeProvider preference="dark"><AuthenticationContext.Provider value={context}><RouterProvider router={router} /></AuthenticationContext.Provider></ThemeProvider>);
}

describe("LoginRoute", () => {
  it("uses the dynamic viewport and safe-area login foundation", () => {
    renderLogin(vi.fn());
    expect(screen.getByRole("main")).toHaveClass(
      "safe-area-login",
      "min-h-dvh",
    );
  });

  it("submits credentials and enters Mission Control", async () => {
    const signIn = vi.fn().mockResolvedValue(undefined);
    renderLogin(signIn);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.com");
    await userEvent.type(screen.getByLabelText(/^password/i), "valid-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(signIn).toHaveBeenCalledWith({ email: "admin@example.com", password: "valid-password" });
    expect(await screen.findByText("Mission Control loaded")).toBeInTheDocument();
  });

  it("shows a generic invalid-credentials message and supports password visibility", async () => {
    renderLogin(vi.fn().mockRejectedValue(new Error("specific backend detail")));
    const password = screen.getByLabelText(/^password/i);
    await userEvent.type(screen.getByLabelText(/email address/i), "admin@example.com");
    await userEvent.type(password, "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect");
    expect(screen.queryByText("specific backend detail")).not.toBeInTheDocument();
  });
});
