import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import * as api from "../../api/communications";
import {
  AuthenticationContext,
  type AuthenticationContextValue,
} from "../../auth/AuthenticationContext";
import { CommunicationsAdministrationRoute } from "./CommunicationsAdministrationRoute";

vi.mock("../../api/communications");

const auth = {
  status: "authenticated",
  activeCompany: null,
  user: null,
  permissionCodes: ["COMPANY_COMMUNICATIONS_READ"],
  signIn: vi.fn(),
  signOut: vi.fn(),
  refresh: vi.fn(),
  requireReauthentication: vi.fn(),
} as unknown as AuthenticationContextValue;

test("shows truthful provider gates and governed catalog", async () => {
  vi.mocked(api.getCommunicationsReadiness).mockResolvedValue({
    email: "EMAIL_PROVIDER_NOT_CONFIGURED",
    sms: "SMS_PROVIDER_NOT_CONFIGURED",
    webhook: "WEBHOOK_NOT_CONFIGURED",
    overall: "DEGRADED",
    synthetic_only: true,
    catalog_fingerprint: "a".repeat(64),
  });
  vi.mocked(api.listOperationalMessageCatalog).mockResolvedValue([
    {
      message_class: "technician_en_route",
      owner_domain: "dispatch",
      allowed_channels: ["email", "sms"],
      template_version: "technician-en-route-v1",
      policy_required: true,
    },
  ]);
  render(
    <AuthenticationContext.Provider value={auth}>
      <QueryClientProvider client={new QueryClient()}>
        <CommunicationsAdministrationRoute />
      </QueryClientProvider>
    </AuthenticationContext.Provider>,
  );
  expect(await screen.findByText("EMAIL PROVIDER NOT CONFIGURED")).toBeVisible();
  expect(screen.getByText("technician en route")).toBeVisible();
  expect(screen.getByText("Authority: dispatch")).toBeVisible();
  expect(screen.getByText(/Synthetic qualification never means real/)).toBeVisible();
});
