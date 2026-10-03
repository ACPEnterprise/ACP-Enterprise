import { apiClient } from "./client";
import type { BankSummary, BankTransaction, CashFlow, Drilldown, ImportConfirm, ImportPreview, ImportRequest, MatchReview, Reconciliation, ReconciliationPrepare, ReconciliationPreview } from "../types/banking";

const root = "/api/v1/accounting/banking";
export const getBankingSummary = async () => (await apiClient.get<BankSummary[]>(`${root}/summary`)).data;
export const getBankTransactions = async (accountId: string) => (await apiClient.get<BankTransaction[]>(`${root}/accounts/${accountId}/transactions`)).data;
export const previewBankImport = async (accountId: string, request: ImportRequest) => (await apiClient.post<ImportPreview>(`${root}/accounts/${accountId}/imports/preview`, request)).data;
export const confirmBankImport = async (accountId: string, request: ImportRequest, previewDigest: string) => (await apiClient.post<ImportConfirm>(`${root}/accounts/${accountId}/imports/confirm`, { ...request, preview_digest: previewDigest })).data;
export const getMatchReview = async (accountId?: string) => (await apiClient.get<MatchReview[]>(`${root}/match-review`, { params: accountId ? { bank_account_id: accountId } : {} })).data;
export const matchBankTransaction = async (accountId: string, transactionId: string) => (await apiClient.post(`${root}/accounts/${accountId}/transactions/${transactionId}/match`)).data;
export const getBankDrilldown = async (transactionId: string) => (await apiClient.get<Drilldown>(`${root}/transactions/${transactionId}/drilldown`)).data;
export const previewReconciliation = async (accountId: string, request: { statement_identity: string; period_start: string; period_end: string; ending_balance: string; cleared_transaction_ids: string[] }) => (await apiClient.post<ReconciliationPreview>(`${root}/accounts/${accountId}/reconciliations/preview`, request)).data;
export const getReconciliationHistory = async (accountId: string) => (await apiClient.get<Reconciliation[]>(`${root}/accounts/${accountId}/reconciliations/history`)).data;
export const getReconciliations = async (accountId: string) => (await apiClient.get<Reconciliation[]>(`${root}/accounts/${accountId}/reconciliations`)).data;
export const prepareReconciliation = async (accountId: string, request: ReconciliationPrepare) => (await apiClient.post<Reconciliation>(`${root}/accounts/${accountId}/reconciliations/prepare`, request)).data;
export const submitReconciliation = async (accountId: string, reconciliationId: string, expectedVersion: number) => (await apiClient.post<Reconciliation>(`${root}/accounts/${accountId}/reconciliations/${reconciliationId}/submit`, { expected_version: expectedVersion })).data;
export const closeReconciliation = async (accountId: string, reconciliationId: string, expectedVersion: number) => (await apiClient.post<Reconciliation>(`${root}/accounts/${accountId}/reconciliations/${reconciliationId}/close`, { expected_version: expectedVersion })).data;
export const getCashFlow = async (periodStart: string, periodEnd: string) => (await apiClient.get<CashFlow>(`${root}/cash-flow`, { params: { period_start: periodStart, period_end: periodEnd, basis: "posted_cash_movement" } })).data;
