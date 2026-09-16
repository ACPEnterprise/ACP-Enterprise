import { apiClient } from "./client";
import type {
  PriceBookCatalog,
  PriceBookCandidateReviewPage,
  PriceBookAdjustmentProposal,
  PriceBookBulkMaterialization,
  PriceBookCategory,
  PriceBookOption,
  PriceBookOptionGroup,
  PriceBookReviewBatch,
  PriceBookServiceItem,
  PriceBookSnapshot,
  PriceBookVersion,
  TaxClassification,
} from "../types/priceBook";

const path = "/api/v1/price-book";
export async function getPriceBook(
  branchId?: string,
): Promise<PriceBookCatalog> {
  return (
    await apiClient.get<PriceBookCatalog>(path, {
      params: { ...(branchId ? { branch_id: branchId } : {}), limit: 500 },
    })
  ).data;
}
export async function getCandidateReview(params: {
  search?: string;
  category?: string;
  admission_status?: "admitted" | "held";
  review_flag?: string;
  limit?: number;
  offset?: number;
}): Promise<PriceBookCandidateReviewPage> {
  return (
    await apiClient.get<PriceBookCandidateReviewPage>(`${path}/candidate-review`, {
      params,
    })
  ).data;
}
export async function createCommercialSnapshot(
  itemId: string,
  data: {
    branch_id: string;
    quantity: string;
    currency: string;
    effective_at: string;
    idempotency_key: string;
    option_group_id?: string;
    option_id?: string;
  },
): Promise<PriceBookSnapshot> {
  return (
    await apiClient.post<PriceBookSnapshot>(
      `${path}/service-items/${itemId}/snapshots`,
      data,
    )
  ).data;
}
export async function createCategory(data: {
  code: string;
  name: string;
}): Promise<PriceBookCategory> {
  return (await apiClient.post<PriceBookCategory>(`${path}/categories`, data))
    .data;
}
export async function createTax(data: {
  code: string;
  name: string;
  taxable: boolean;
}): Promise<TaxClassification> {
  return (
    await apiClient.post<TaxClassification>(`${path}/tax-classifications`, data)
  ).data;
}
export async function createServiceItem(data: {
  branch_id?: string;
  category_id: string;
  code: string;
  name: string;
  customer_description: string;
}): Promise<PriceBookServiceItem> {
  return (
    await apiClient.post<PriceBookServiceItem>(`${path}/service-items`, data)
  ).data;
}
export async function updateServiceItem(
  itemId: string,
  data: {
    branch_id?: string;
    category_id: string;
    code: string;
    name: string;
    customer_description: string;
    status: "draft" | "active" | "inactive" | "archived";
    expected_version: number;
  },
): Promise<PriceBookServiceItem> {
  return (
    await apiClient.put<PriceBookServiceItem>(`${path}/service-items/${itemId}`, data)
  ).data;
}
export async function createPriceVersion(
  itemId: string,
  data: {
    branch_id?: string;
    tax_classification_id: string;
    currency: string;
    unit_price: string;
    effective_at: string;
    components: Array<{
      component_type: "labor" | "material" | "other_direct";
      code?: string;
      label: string;
      quantity: string;
      unit_cost?: string;
    }>;
  },
): Promise<PriceBookVersion> {
  return (
    await apiClient.post<PriceBookVersion>(
      `${path}/service-items/${itemId}/versions`,
      data,
    )
  ).data;
}
export async function activatePriceVersion(
  versionId: string,
  version: number,
): Promise<PriceBookVersion> {
  return (
    await apiClient.post<PriceBookVersion>(
      `${path}/versions/${versionId}/activate`,
      {
        expected_version: version,
        reason: "Owner activated Price Book version.",
      },
    )
  ).data;
}
export async function createOptionGroup(data: {
  code: string;
  name: string;
  minimum_selections: number;
  maximum_selections: number;
}): Promise<PriceBookOptionGroup> {
  return (
    await apiClient.post<PriceBookOptionGroup>(`${path}/option-groups`, data)
  ).data;
}
export async function addOption(
  groupId: string,
  data: { service_item_id: string; label: string; position: number },
): Promise<PriceBookOption> {
  return (
    await apiClient.post<PriceBookOption>(
      `${path}/option-groups/${groupId}/options`,
      data,
    )
  ).data;
}
export async function createReviewBatch(data: {
  configuration_version: string;
  review_type:
    | "commercial_content"
    | "candidate_prices"
    | "tax_classification"
    | "membership"
    | "source_conflict";
  selector: Record<string, unknown>;
  service_codes: string[];
  exclusions: string[];
  candidate_set_digest: string;
  idempotency_key: string;
}): Promise<PriceBookReviewBatch> {
  return (
    await apiClient.post<PriceBookReviewBatch>(
      `${path}/activation-readiness/review-batches`,
      data,
    )
  ).data;
}
export async function decideReviewBatch(
  batchId: string,
  data: {
    expected_version: number;
    expected_digest: string;
    decision: "approved" | "returned" | "excluded";
    reason: string;
  },
): Promise<PriceBookReviewBatch> {
  return (
    await apiClient.post<PriceBookReviewBatch>(
      `${path}/activation-readiness/review-batches/${batchId}/decision`,
      data,
    )
  ).data;
}
export async function createAdjustmentProposal(data: {
  source_price_book_version: string;
  recommendation_identity: string;
  affected_service_codes: string[];
  owner_exclusions: string[];
  transformation_kind: "percentage" | "fixed_amount";
  transformation: Record<string, string>;
  impacts: Array<Record<string, string>>;
  limitations: string[];
  effective_at: string;
  proposal_digest: string;
}): Promise<PriceBookAdjustmentProposal> {
  return (
    await apiClient.post<PriceBookAdjustmentProposal>(
      `${path}/activation-readiness/adjustment-proposals`,
      data,
    )
  ).data;
}
export async function decideAdjustmentProposal(
  proposalId: string,
  data: { expected_version: number; expected_digest: string; decision: "approved" | "returned" | "rejected"; reason: string },
): Promise<PriceBookAdjustmentProposal> {
  return (
    await apiClient.post<PriceBookAdjustmentProposal>(
      `${path}/activation-readiness/adjustment-proposals/${proposalId}/decision`,
      data,
    )
  ).data;
}
export async function materializeAdjustmentProposal(
  proposalId: string,
  data: { expected_version: number; expected_digest: string; idempotency_key: string },
): Promise<PriceBookBulkMaterialization> {
  return (
    await apiClient.post<PriceBookBulkMaterialization>(
      `${path}/activation-readiness/adjustment-proposals/${proposalId}/materialize`,
      data,
    )
  ).data;
}
