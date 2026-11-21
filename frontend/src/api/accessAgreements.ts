import { apiClient } from "./client";

export interface CurrentAccessAgreement {
  required: boolean;
  configured: boolean;
  accepted: boolean;
  agreement_id: string | null;
  code: string | null;
  title: string | null;
  version: number | null;
  effective_at: string | null;
  content: string | null;
  content_sha256: string | null;
  receipt_id: string | null;
  accepted_at: string | null;
}

export interface AccessAgreementReceipt {
  receipt_id: string;
  agreement_id: string;
  agreement_version: number;
  agreement_sha256: string;
  recipient_name: string;
  recipient_email: string;
  company_id: string;
  accepted_at: string;
  action: string;
  electronic_signature_consent: boolean;
}

export async function getCurrentAccessAgreement(): Promise<CurrentAccessAgreement> {
  return (await apiClient.get<CurrentAccessAgreement>("/api/v1/access-agreements/current")).data;
}

export async function acceptAccessAgreement(input: {
  agreement_id: string;
  version: number;
  acknowledge_reviewed: boolean;
  electronic_signature_consent: boolean;
}): Promise<AccessAgreementReceipt> {
  return (await apiClient.post<AccessAgreementReceipt>("/api/v1/access-agreements/accept", input)).data;
}
