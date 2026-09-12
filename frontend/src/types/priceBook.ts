export interface PriceBookCategory { id: string; company_id: string; parent_id: string | null; code: string; name: string; description: string | null; status: string; version: number }
export interface TaxClassification { id: string; company_id: string; code: string; name: string; taxable: boolean; status: string; version: number }
export interface PriceBookServiceItem { id: string; company_id: string; branch_id: string | null; category_id: string; code: string; name: string; customer_description: string; internal_description?: string | null; status: string; current_version_id: string | null; version: number }
export interface PriceBookComponent { id: string; component_type: "labor" | "material"; code: string | null; label: string; quantity: string; unit_cost?: string | null; position: number }
export interface PriceBookVersion { id: string; company_id: string; service_item_id: string; branch_id: string | null; tax_classification_id: string; revision: number; currency: string; unit_price: string; effective_at: string; expires_at: string | null; status: string; rounding_mode: string; version: number; components: PriceBookComponent[] }
export interface PriceBookOptionGroup { id: string; company_id: string; code: string; name: string; minimum_selections: number; maximum_selections: number; status: string }
export interface PriceBookOption { id: string; company_id: string; option_group_id: string; service_item_id: string; label: string; position: number }
export interface PriceBookCatalog { categories: PriceBookCategory[]; tax_classifications: TaxClassification[]; service_items: PriceBookServiceItem[]; versions: PriceBookVersion[]; option_groups: PriceBookOptionGroup[]; options: PriceBookOption[] }
export interface PriceBookOperatorCatalog extends PriceBookCatalog { internal_components: PriceBookComponent[] }
export interface EffectivePriceBookOption { group_id: string; group_name: string; minimum_selections: number; maximum_selections: number; option_id: string; option_label: string }
export interface EffectivePriceBookItem { item_id: string; item_code: string; item_name: string; customer_description: string; category_id: string; category_name: string; price_version_id: string; unit_price: string; currency: string; effective_at: string; expires_at: string | null; tax_classification_name: string; taxable: boolean; options: EffectivePriceBookOption[] }
export interface EffectivePriceBookCatalog { effective_at: string; items: EffectivePriceBookItem[] }
export interface PriceBookSnapshot { id: string; service_item_id: string; price_version_id: string; quantity: string; unit_price: string; extended_amount: string; currency: string; digest: string; snapshot_data: Record<string, unknown> }
export interface BulkDraftComponent { component_type: "labor" | "material"; label: string; quantity: string; unit_cost?: string }
export interface BulkDraftCandidate { client_ref: string; branch_id?: string; category_id?: string; code: string; name: string; customer_description: string; internal_description?: string; tax_classification_id?: string; currency: string; unit_price?: string; effective_at?: string; components: BulkDraftComponent[] }
export interface BulkDraftIssue { code: string; field: string; message: string }
export interface BulkDraftRowValidation { client_ref: string; can_save: boolean; readiness: "INCOMPLETE" | "READY_FOR_REVIEW"; issues: BulkDraftIssue[] }
export interface BulkDraftValidation { can_save: boolean; rows: BulkDraftRowValidation[] }
export interface BulkDraftResult { created: Array<{ client_ref: string; service_item: PriceBookServiceItem; draft_version: PriceBookVersion; readiness: string; issues: BulkDraftIssue[] }> }
