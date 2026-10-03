import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  OpeningControlProjectionReview,
  type OpeningControlProjection,
} from "./OpeningControlProjectionReview";

const projection = (
  changes: Partial<OpeningControlProjection> = {},
): OpeningControlProjection => ({
  package_id: "opening-package-1",
  cutoff: "2026-09-30",
  source_as_of: "2026-09-30T23:59:59Z",
  currency: "USD",
  status: "READY_FOR_REVIEW",
  trial_balance: {
    lines: [
      {
        identity: "cash",
        account: "1000 · Cash",
        account_type: "Bank",
        debit: "100.00",
        credit: "0.00",
        source_label: "QuickBooks opening package",
        status: "READY_FOR_REVIEW",
      },
      {
        identity: "equity",
        account: "3000 · Retained Earnings",
        account_type: "Equity",
        debit: "0.00",
        credit: "100.00",
        source_label: "QuickBooks opening package",
        status: "READY_FOR_REVIEW",
      },
    ],
    total_debits: "100.00",
    total_credits: "100.00",
    difference: "0.00",
    balanced: true,
  },
  equity: {
    retained_earnings: "100.00",
    owner_equity: "0.00",
    opening_balance_equity: null,
    unexplained_difference: null,
    status: "READY_FOR_REVIEW",
  },
  ar: {
    control_balance: "25.00",
    subledger_total: "25.00",
    difference: "0.00",
    status: "RECONCILED",
  },
  ap: {
    control_balance: "10.00",
    subledger_total: "10.00",
    difference: "0.00",
    status: "RECONCILED",
  },
  exceptions: [],
  ...changes,
});

describe("OpeningControlProjectionReview", () => {
  it("renders a balanced sanitized package without calculating its accounting values", () => {
    render(<OpeningControlProjectionReview value={projection()} />);
    expect(
      screen.getByRole("heading", { name: "Opening Trial Balance" }),
    ).toBeVisible();
    expect(screen.getByText("1000 · Cash")).toBeVisible();
    expect(screen.getAllByText("$100.00").length).toBeGreaterThan(1);
    expect(screen.getAllByText("$0.00").length).toBeGreaterThan(1);
  });

  it("keeps an unbalanced package and unexplained equity visibly in review", () => {
    render(
      <OpeningControlProjectionReview
        value={projection({
          status: "INCOMPLETE",
          trial_balance: {
            ...projection().trial_balance,
            total_debits: "101.00",
            difference: "1.00",
            balanced: false,
          },
          equity: {
            ...projection().equity,
            opening_balance_equity: "1.00",
            unexplained_difference: "1.00",
            status: "INCOMPLETE",
          },
          exceptions: [
            {
              id: "equity-1",
              family: "EQUITY",
              disposition: "REVIEW_REQUIRED",
              subject: "Opening balance equity",
              explanation: "The difference requires accountant classification.",
              status: "OPEN",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText(/Trial Balance is not balanced/i)).toBeVisible();
    expect(
      screen.getByText("The difference requires accountant classification."),
    ).toBeVisible();
    expect(screen.getAllByText("$1.00").length).toBeGreaterThan(1);
  });

  it("renders source-only and ACP-only A/R and A/P exceptions", () => {
    render(
      <OpeningControlProjectionReview
        value={projection({
          exceptions: [
            {
              id: "ar-source",
              family: "AR",
              disposition: "SOURCE_ONLY",
              subject: "Invoice 101",
              explanation: "No native successor is linked.",
              status: "OPEN",
            },
            {
              id: "ap-native",
              family: "AP",
              disposition: "ACP_ONLY",
              subject: "Bill 202",
              explanation: "No source cutoff item is linked.",
              status: "READY_FOR_REVIEW",
            },
          ],
        })}
      />,
    );
    expect(screen.getByText("SOURCE ONLY")).toBeVisible();
    expect(screen.getByText("ACP ONLY")).toBeVisible();
    expect(screen.getByText("Invoice 101")).toBeVisible();
    expect(screen.getByText("Bill 202")).toBeVisible();
  });
});
