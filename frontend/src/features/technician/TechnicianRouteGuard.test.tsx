import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { AuthenticationContext, type AuthenticationContextValue } from "../../auth/AuthenticationContext";
import { TechnicianRouteGuard } from "./TechnicianRouteGuard";

const context: AuthenticationContextValue = {
  status: "authenticated",
  user: null,
  activeCompany: null,
  signIn: async () => undefined,
  signOut: async () => undefined,
  signOutAll: async () => undefined,
  requireReauthentication: () => undefined,
};

function renderGuard(permissionCodes: readonly string[]) {
  render(
    <AuthenticationContext.Provider value={{ ...context, permissionCodes }}>
      <MemoryRouter initialEntries={["/technician"]}>
        <Routes>
          <Route path="/" element={<div>Command Center</div>} />
          <Route element={<TechnicianRouteGuard />}>
            <Route path="/technician" element={<div>Technician shell</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthenticationContext.Provider>,
  );
}

describe("TechnicianRouteGuard", () => {
  it("allows users with field execution permission", () => {
    renderGuard(["COMPANY_JOB_EXECUTE"]);
    expect(screen.getByText("Technician shell")).toBeInTheDocument();
  });

  it("redirects users without field execution permission", () => {
    renderGuard(["COMPANY_JOB_READ"]);
    expect(screen.getByText("Command Center")).toBeInTheDocument();
    expect(screen.queryByText("Technician shell")).not.toBeInTheDocument();
  });
});
