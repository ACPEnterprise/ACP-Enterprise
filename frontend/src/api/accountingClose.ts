import { apiClient } from "./client";

export interface AccountingPeriod {
  id: string;
  company_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: "open" | "closing" | "closed" | "reopened";
  version: number;
}

export async function getAccountingPeriods(): Promise<AccountingPeriod[]> {
  return (await apiClient.get<AccountingPeriod[]>("/api/v1/accounting/periods"))
    .data;
}
