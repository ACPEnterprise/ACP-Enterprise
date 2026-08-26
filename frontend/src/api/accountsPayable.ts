import { apiClient } from "./client";
import type { APAgingItem, AccountingVendor, CreateVendorInput } from "../types/accountsPayable";
const root = "/api/v1/accounts-payable";
export const getAPAging = async (asOf: string): Promise<APAgingItem[]> => (await apiClient.get<APAgingItem[]>(`${root}/aging`, { params: { as_of: asOf } })).data;
export const createAccountingVendor = async (input: CreateVendorInput): Promise<AccountingVendor> => (await apiClient.post<AccountingVendor>(`${root}/vendors`, input)).data;
