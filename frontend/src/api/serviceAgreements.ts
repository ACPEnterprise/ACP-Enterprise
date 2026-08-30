import { apiClient } from "./client";
import type {
  AgreementPlan,
  AgreementWorkspace,
  ServiceAgreement,
  ServiceEntitlement,
} from "../types/serviceAgreements";
const root = "/api/v1/service-agreements";
export const getAgreementWorkspace = async () =>
  (await apiClient.get<AgreementWorkspace>(`${root}/workspace`)).data;
export const listAgreementPlans = async () =>
  (await apiClient.get<AgreementPlan[]>(`${root}/plans`)).data;
export const createAgreementPlan = async (input: Record<string, unknown>) =>
  (await apiClient.post<AgreementPlan>(`${root}/plans`, input)).data;
export const activateAgreementPlan = async (id: string) =>
  (await apiClient.post<AgreementPlan>(`${root}/plans/${id}/activate`)).data;
export const enrollAgreement = async (input: Record<string, unknown>) =>
  (await apiClient.post<ServiceAgreement>(root, input)).data;
export const transitionAgreement = async (
  id: string,
  action: string,
  input: Record<string, unknown>,
) =>
  (await apiClient.post<ServiceAgreement>(`${root}/${id}/${action}`, input))
    .data;
export const generateEntitlements = async (id: string) =>
  (await apiClient.post<ServiceEntitlement[]>(`${root}/${id}/entitlements`))
    .data;
