import { useState, type FormEvent } from "react";
import axios from "axios";
import { useAuth, useHasPermission } from "../auth";
import {
  useCandidateReview,
  useActivationReadiness,
  usePriceBookAudit,
  usePriceBook,
  usePriceBookMutations,
} from "../hooks/usePriceBook";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Spinner,
} from "../ui";

const priceBookRecoveryMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const recovery = (
      error.response?.data as { detail?: { recovery?: string } }
    )?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH")
      return "Price Book authority changed. Refresh before continuing.";
    if (recovery === "USER_CORRECTION_REQUIRED")
      return "Price Book evidence requires correction. Review the retained inputs.";
    if (recovery === "TEMPORARILY_UNAVAILABLE")
      return "Price Book is temporarily unavailable. Your inputs were retained.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED")
      return "Price Book requires owner or administrator action before continuing.";
    if (recovery === "TERMINAL_FAILURE")
      return "The Price Book resource is no longer available. Refresh authoritative state.";
  }
  return "Price Book operation failed safely. Refresh authoritative state before retrying.";
};

const digestServiceCodes = async (codes: string[]) => {
  const evidence = new TextEncoder().encode(JSON.stringify([...codes].sort()));
  const digest = await crypto.subtle.digest("SHA-256", evidence);
  return Array.from(new Uint8Array(digest), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
};

export function PriceBookRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_PRICE_BOOK_READ");
  const canManage = useHasPermission("COMPANY_PRICE_BOOK_MANAGE");
  const canActivate = useHasPermission("COMPANY_PRICE_BOOK_ACTIVATE");
  const canApproveTax = useHasPermission("COMPANY_ACCOUNTING_FINANCE_APPROVE");
  const [branch, setBranch] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [catalogOffset, setCatalogOffset] = useState(0);
  const catalogPageSize = 50;
  const catalog = usePriceBook(branch || undefined, canRead, {
    search: search.trim() || undefined,
    categoryId: categoryFilter === "all" ? undefined : categoryFilter,
    itemStatus: statusFilter === "all" ? undefined : statusFilter,
    limit: catalogPageSize,
    offset: catalogOffset,
  });
  const mutations = usePriceBookMutations();
  const emptyCategory = {
    code: "",
    name: "",
    description: "",
    parentId: "",
    position: "",
    status: "draft" as "draft" | "active" | "archived",
  };
  const [category, setCategory] = useState(emptyCategory);
  const [editCategory, setEditCategory] = useState<{ id: string; version: number } | null>(null);
  const [tax, setTax] = useState({ code: "", name: "", taxable: true });
  const [optionGroup, setOptionGroup] = useState({
    code: "",
    name: "",
    minimum_selections: 0,
    maximum_selections: 1,
  });
  const [option, setOption] = useState({
    groupId: "",
    serviceItemId: "",
    label: "",
    position: "1",
  });
  const [item, setItem] = useState({
    category_id: "",
    code: "",
    name: "",
    customer_description: "",
    internal_description: "",
  });
  const [editItem, setEditItem] = useState<{
    id: string;
    version: number;
    status: "draft" | "active" | "inactive" | "archived";
  } | null>(null);
  const [draft, setDraft] = useState({
    itemId: "",
    taxId: "",
    price: "",
    effective: "",
    componentType: "labor" as "labor" | "material" | "other_direct",
    componentLabel: "",
    componentQuantity: "1",
    componentCost: "",
  });
  const [draftComponents, setDraftComponents] = useState<Array<{
    component_type: "labor" | "material" | "other_direct";
    label: string;
    quantity: string;
    unit_cost?: string;
  }>>([]);
  const [editDraft, setEditDraft] = useState<{ id: string; version: number } | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string>();
  const [candidateOffset, setCandidateOffset] = useState(0);
  const candidatePageSize = 50;
  const [candidateCategory, setCandidateCategory] = useState("");
  const [candidateAdmission, setCandidateAdmission] = useState<"" | "admitted" | "held">("");
  const [candidateReviewFlag, setCandidateReviewFlag] = useState("");
  const [reviewVersionId, setReviewVersionId] = useState<string>();
  const activationReadiness = useActivationReadiness(reviewVersionId);
  const reviewAudit = usePriceBookAudit(reviewVersionId);
  const candidateReview = useCandidateReview(
    {
      search: search.trim() || undefined,
      category: candidateCategory.trim() || undefined,
      admission_status: candidateAdmission || undefined,
      review_flag: candidateReviewFlag || undefined,
      limit: candidatePageSize,
      offset: candidateOffset,
    },
    canRead && Boolean(activeCompany),
  );
  const selectedService = catalog.data?.service_items.find(
    (service) => service.id === selectedServiceId,
  );
  const selectedCandidate = useCandidateReview(
    { search: selectedService?.code, limit: 10 },
    canRead && Boolean(activeCompany) && Boolean(selectedService),
  );
  const [reviewType, setReviewType] = useState<
    | "commercial_content"
    | "candidate_prices"
    | "tax_classification"
    | "membership"
    | "source_conflict"
  >("candidate_prices");
  const [savedReview, setSavedReview] = useState<{
    id: string;
    digest: string;
    version: number;
    count: number;
  } | null>(null);
  const [adjustment, setAdjustment] = useState({
    kind: "percentage" as "percentage" | "fixed_amount",
    value: "",
    effective: "",
  });
  const [savedAdjustment, setSavedAdjustment] = useState<{
    id: string;
    digest: string;
    version: number;
    count: number;
    status: string;
  } | null>(null);
  if (!activeCompany)
    return (
      <Alert variant="danger">
        Select an accessible Company before opening Price Book.
      </Alert>
    );
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Price Book.</Alert>
    );
  const performMutation = async (
    operation: () => Promise<unknown>,
    onSuccess?: () => void,
  ) => {
    try {
      await operation();
      onSuccess?.();
    } catch {
      /* The governed recovery state is announced below. */
    }
  };
  const submitCategory = async (event: FormEvent) => {
    event.preventDefault();
    await performMutation(
      () =>
        editCategory
          ? mutations.categoryUpdate.mutateAsync({
              categoryId: editCategory.id,
              data: {
                code: category.code,
                name: category.name,
                description: category.description || undefined,
                parent_id: category.parentId || undefined,
                position: category.position ? Number(category.position) : undefined,
                status: category.status,
                expected_version: editCategory.version,
              },
            })
          : mutations.category.mutateAsync({
              code: category.code,
              name: category.name,
              description: category.description || undefined,
              parent_id: category.parentId || undefined,
              position: category.position ? Number(category.position) : undefined,
            }),
      () => {
        setCategory(emptyCategory);
        setEditCategory(null);
      },
    );
  };
  const submitTax = async (event: FormEvent) => {
    event.preventDefault();
    await performMutation(
      () => mutations.tax.mutateAsync(tax),
      () => setTax({ code: "", name: "", taxable: true }),
    );
  };
  const submitOptionGroup = async (event: FormEvent) => {
    event.preventDefault();
    await performMutation(
      () => mutations.optionGroup.mutateAsync(optionGroup),
      () =>
        setOptionGroup({
          code: "",
          name: "",
          minimum_selections: 0,
          maximum_selections: 1,
        }),
    );
  };
  const submitOption = async (event: FormEvent) => {
    event.preventDefault();
    await performMutation(
      () =>
        mutations.option.mutateAsync({
          groupId: option.groupId,
          data: {
            service_item_id: option.serviceItemId,
            label: option.label,
            position: Number(option.position),
          },
        }),
      () =>
        setOption({ groupId: "", serviceItemId: "", label: "", position: "1" }),
    );
  };
  const submitItem = async (event: FormEvent) => {
    event.preventDefault();
    await performMutation(
      () =>
        editItem
          ? mutations.itemUpdate.mutateAsync({
              itemId: editItem.id,
              data: {
                ...item,
                branch_id: branch || undefined,
                status: editItem.status,
                expected_version: editItem.version,
              },
            })
          : mutations.item.mutateAsync({
              ...item,
              branch_id: branch || undefined,
            }),
      () => {
        setItem({
          category_id: "",
          code: "",
          name: "",
          customer_description: "",
          internal_description: "",
        });
        setEditItem(null);
      },
    );
  };
  const submitDraft = async (event: FormEvent) => {
    event.preventDefault();
    const pendingComponent = draft.componentLabel
      ? [{
          component_type: draft.componentType,
          label: draft.componentLabel,
          quantity: draft.componentQuantity,
          unit_cost: draft.componentCost || undefined,
        }]
      : [];
    await performMutation(() =>
      editDraft
        ? mutations.versionUpdate.mutateAsync({
            versionId: editDraft.id,
            data: {
              expected_version: editDraft.version,
              tax_classification_id: draft.taxId,
              currency: "USD",
              unit_price: draft.price,
              effective_at: new Date(draft.effective).toISOString(),
              components: [...draftComponents, ...pendingComponent],
            },
          })
        : mutations.version.mutateAsync({
        itemId: draft.itemId,
        data: {
          branch_id: branch || undefined,
          tax_classification_id: draft.taxId,
          currency: "USD",
          unit_price: draft.price,
          effective_at: new Date(draft.effective).toISOString(),
          components: [...draftComponents, ...pendingComponent],
        },
          }),
      () => {
        setDraftComponents([]);
        setEditDraft(null);
      },
    );
  };
  const saveVisibleReview = async () => {
    const codes = filteredServices.map((service) => service.code).sort();
    if (codes.length === 0) return;
    const digest = await digestServiceCodes(codes);
    await performMutation(async () => {
      const saved = await mutations.reviewBatch.mutateAsync({
        configuration_version: "owner-review-workspace-v1",
        review_type: reviewType,
        selector: {
          branch_id: branch || null,
          search: normalizedSearch || null,
          status: statusFilter,
        },
        service_codes: codes,
        exclusions: [],
        candidate_set_digest: digest,
        idempotency_key: `owner-review-${reviewType}-${digest.slice(0, 24)}`,
      });
      setSavedReview({
        id: saved.id,
        digest: saved.candidate_set_digest,
        version: saved.version,
        count: saved.service_codes.length,
      });
    });
  };
  const approveSavedReview = async () => {
    if (!savedReview) return;
    await performMutation(async () => {
      const decided = await mutations.reviewDecision.mutateAsync({
        batchId: savedReview.id,
        data: {
          expected_version: savedReview.version,
          expected_digest: savedReview.digest,
          decision: "approved",
          reason:
            "Owner approved this filtered candidate group for review readiness. Activation remains separate.",
        },
      });
      setSavedReview({ ...savedReview, version: decided.version });
    });
  };
  const saveAdjustmentPreview = async () => {
    const value = Number(adjustment.value);
    if (!Number.isFinite(value) || !adjustment.effective) return;
    const impacts = filteredServices.flatMap((service) => {
      const active = versions.find(
        (version) =>
          version.id === service.current_version_id &&
          version.status === "active",
      );
      if (!active) return [];
      const current = Number(active.unit_price);
      const proposed =
        Math.round(
          (adjustment.kind === "percentage"
            ? current * (1 + value / 100)
            : current + value) * 100,
        ) / 100;
      if (proposed < 0) return [];
      return [
        {
          service_code: service.code,
          current_price: current.toFixed(2),
          proposed_price: proposed.toFixed(2),
          absolute_change: (proposed - current).toFixed(2),
        },
      ];
    });
    if (impacts.length === 0) return;
    const effectiveAt = new Date(adjustment.effective).toISOString();
    const codes = impacts.map((impact) => impact.service_code).sort();
    const digestBytes = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(
        JSON.stringify({
          codes,
          kind: adjustment.kind,
          value: adjustment.value,
          effectiveAt,
          impacts,
        }),
      ),
    );
    const digest = Array.from(new Uint8Array(digestBytes), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    await performMutation(async () => {
      const saved = await mutations.adjustmentProposal.mutateAsync({
        source_price_book_version: "current-active-selection",
        recommendation_identity: `owner-bulk-${digest}`,
        affected_service_codes: codes,
        owner_exclusions: [],
        transformation_kind: adjustment.kind,
        transformation: { [adjustment.kind]: adjustment.value },
        impacts,
        limitations: [
          "No profit effect is asserted where cost evidence is incomplete.",
        ],
        effective_at: effectiveAt,
        proposal_digest: digest,
      });
      setSavedAdjustment({
        id: saved.id,
        digest,
        version: saved.version,
        count: impacts.length,
        status: saved.status,
      });
    });
  };
  const approveAdjustment = async () => {
    if (!savedAdjustment) return;
    await performMutation(async () => {
      const saved = await mutations.adjustmentDecision.mutateAsync({
        proposalId: savedAdjustment.id,
        data: {
          expected_version: savedAdjustment.version,
          expected_digest: savedAdjustment.digest,
          decision: "approved",
          reason: "Owner approved this exact bulk price preview.",
        },
      });
      setSavedAdjustment({
        ...savedAdjustment,
        version: saved.version,
        status: saved.status,
      });
    });
  };
  const createAdjustmentDrafts = async () => {
    if (!savedAdjustment || savedAdjustment.status !== "approved") return;
    await performMutation(async () => {
      await mutations.adjustmentMaterialize.mutateAsync({
        proposalId: savedAdjustment.id,
        data: {
          expected_version: savedAdjustment.version,
          expected_digest: savedAdjustment.digest,
          idempotency_key: `materialize-${savedAdjustment.digest.slice(0, 40)}`,
        },
      });
      setSavedAdjustment(null);
    });
  };
  const failedMutation = [
    mutations.category,
    mutations.tax,
    mutations.item,
    mutations.itemUpdate,
    mutations.version,
    mutations.activate,
    mutations.optionGroup,
    mutations.option,
    mutations.reviewBatch,
    mutations.reviewDecision,
    mutations.adjustmentProposal,
    mutations.adjustmentDecision,
    mutations.adjustmentMaterialize,
    mutations.activationReview,
  ].find((mutation) => mutation.isError);
  const services = catalog.data?.service_items ?? [];
  const versions = catalog.data?.versions ?? [];
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const filteredServices = services.filter((service) => {
    const serviceCategory = catalog.data?.categories.find(
      (category) => category.id === service.category_id,
    );
    const matchesCategory =
      categoryFilter === "all" || service.category_id === categoryFilter;
    const matchesSearch =
      !normalizedSearch ||
      [
        service.code,
        service.name,
        service.customer_description,
        serviceCategory?.code,
        serviceCategory?.name,
      ].some((value) =>
        value?.toLocaleLowerCase().includes(normalizedSearch),
      );
    return (
      matchesCategory &&
      matchesSearch &&
      (statusFilter === "all" || service.status === statusFilter)
    );
  });
  const selectedCategory = catalog.data?.categories.find(
    (category) => category.id === selectedService?.category_id,
  );
  const selectedEvidence = selectedCandidate.data?.items.find(
    (candidate) =>
      candidate.native_service_item_id === selectedService?.id ||
      candidate.service_code === selectedService?.code,
  );
  const activeCount = services.filter(
    (service) => service.status === "active",
  ).length;
  const ownerReviewCount = new Set([
    ...services
      .filter((service) => service.status === "draft")
      .map((service) => service.id),
    ...versions
      .filter((version) => version.status === "draft")
      .map((version) => version.service_item_id),
  ]).size;
  const missingPriceCount = services.filter(
    (service) =>
      !versions.some((version) => version.service_item_id === service.id),
  ).length;
  const categoryDisplayName = (categoryId: string) => {
    const categories = catalog.data?.categories ?? [];
    const byId = new Map(categories.map((category) => [category.id, category]));
    const names: string[] = [];
    const visited = new Set<string>();
    let current = byId.get(categoryId);
    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      names.unshift(current.name);
      current = current.parent_id ? byId.get(current.parent_id) : undefined;
    }
    return names.length ? names.join(" › ") : "Category unavailable";
  };
  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-10">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Sales / Commercial Operations
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Price Book</h1>
        <p className="mt-2 text-content-muted">
          Create controlled service prices and activate immutable commercial
          versions.
        </p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Catalog scope</CardTitle>
          <CardDescription>
            Company-wide items are visible in every Branch. Branch items remain
            local.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            aria-label="Price Book Branch"
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
          >
            <option value="">All Company prices</option>
            {activeCompany.branches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </CardContent>
      </Card>
      {catalog.isPending ? (
        <Spinner label="Loading Price Book" />
      ) : catalog.isError ? (
        <Alert variant="danger">Price Book could not be loaded.</Alert>
      ) : (
        <>
          {failedMutation && (
            <Alert variant="danger" role="alert" aria-live="assertive">
              {priceBookRecoveryMessage(failedMutation.error)}
            </Alert>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Browse Price Book by category</CardTitle>
              <CardDescription>
                Start with an authoritative category, then review the services
                in that category. Candidate review and activation remain
                separate administrative workflows below.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Button
                variant={categoryFilter === "all" ? "primary" : "secondary"}
                onClick={() => {
                  setCategoryFilter("all");
                  setCatalogOffset(0);
                }}
              >
                All categories
              </Button>
              {(catalog.data?.categories ?? []).map((catalogCategory) => (
                <Button
                  key={catalogCategory.id}
                  variant={
                    categoryFilter === catalogCategory.id
                      ? "primary"
                      : "secondary"
                  }
                  onClick={() => {
                    setCategoryFilter(catalogCategory.id);
                    setCatalogOffset(0);
                  }}
                >
                  {categoryDisplayName(catalogCategory.id)}
                </Button>
              ))}
            </CardContent>
          </Card>
          <section
            aria-label="Price Book readiness"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Card>
              <CardHeader>
                <CardDescription>Matching services</CardDescription>
                <CardTitle>{catalog.data?.total_service_items ?? 0}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader>
                <CardDescription>Active on this page</CardDescription>
                <CardTitle>{activeCount}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader>
                <CardDescription>Ready for review on this page</CardDescription>
                <CardTitle>{ownerReviewCount}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader>
                <CardDescription>Missing price evidence on this page</CardDescription>
                <CardTitle>{missingPriceCount}</CardTitle>
              </CardHeader>
            </Card>
          </section>
          <Card>
            <CardHeader>
              <CardTitle>All County candidate review</CardTitle>
              <CardDescription>
                Source-backed draft candidates are visible here before any price
                becomes active. Held items remain isolated until their source
                conflict is resolved.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {candidateReview.isPending ? (
                <Spinner label="Loading candidate review" />
              ) : candidateReview.isError ? (
                <Alert variant="danger">
                  Candidate evidence could not be loaded. Native Price Book
                  authority was not changed.
                </Alert>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div><strong>{candidateReview.data?.counts.admitted ?? 0}</strong><p className="text-sm text-content-muted">Draft — ready for review</p></div>
                    <div><strong>{candidateReview.data?.counts.held ?? 0}</strong><p className="text-sm text-content-muted">Held — source conflict</p></div>
                    <div><strong>{candidateReview.data?.counts.material_mapping_required ?? 0}</strong><p className="text-sm text-content-muted">Need material mapping</p></div>
                    <div><strong>{candidateReview.data?.counts.activation_ready ?? 0}</strong><p className="text-sm text-content-muted">Activation ready</p></div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Input
                      aria-label="Filter candidate category"
                      placeholder="Candidate category"
                      value={candidateCategory}
                      onChange={(event) => {
                        setCandidateCategory(event.target.value);
                        setCandidateOffset(0);
                      }}
                    />
                    <Select
                      aria-label="Filter candidate admission state"
                      value={candidateAdmission}
                      onChange={(event) => {
                        setCandidateAdmission(event.target.value as "" | "admitted" | "held");
                        setCandidateOffset(0);
                      }}
                    >
                      <option value="">All candidate states</option>
                      <option value="admitted">Draft — ready for review</option>
                      <option value="held">Held — source conflict</option>
                    </Select>
                    <Select
                      aria-label="Filter candidate review requirement"
                      value={candidateReviewFlag}
                      onChange={(event) => {
                        setCandidateReviewFlag(event.target.value);
                        setCandidateOffset(0);
                      }}
                    >
                      <option value="">All review requirements</option>
                      <option value="PRICE_EVIDENCE_REVIEW_REQUIRED">Price review required</option>
                      <option value="TAX_REVIEW_REQUIRED">Tax review required</option>
                      <option value="MATERIAL_MAPPING_REQUIRED">Material mapping required</option>
                      <option value="SOURCE_CONFLICT">Source conflict</option>
                    </Select>
                  </div>
                  <div className="space-y-3" aria-label="All County candidate services">
                    {(candidateReview.data?.items ?? []).map((candidate) => (
                      <article
                        key={candidate.candidate_identity}
                        className="rounded-lg border border-stroke p-4"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <p className="text-xs text-content-muted">{candidate.category} · {candidate.service_code}</p>
                            <h3 className="font-semibold">{candidate.name}</h3>
                          </div>
                          <Badge variant={candidate.admission_status === "held" ? "danger" : "warning"}>
                            {candidate.admission_status === "held" ? "Held — source conflict" : "Draft — ready for review"}
                          </Badge>
                        </div>
                        <p className="mt-2 text-sm">{candidate.customer_description}</p>
                        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                          <div><dt className="text-content-muted">Candidate price</dt><dd>${candidate.candidate_prices.standard ?? "Not supplied"} — not active</dd></div>
                          <div><dt className="text-content-muted">Source</dt><dd>{candidate.source_sheet}, row {candidate.source_row}</dd></div>
                          <div><dt className="text-content-muted">Price evidence</dt><dd>{candidate.price_derivation === "OWNER_OVERRIDE" ? "Owner workbook value" : "Workbook formula"}</dd></div>
                        </dl>
                        <p className="mt-3 text-xs text-content-muted">
                          {candidate.review_flags.map((flag) => flag.replaceAll("_", " ").toLocaleLowerCase()).join(" · ")}
                        </p>
                        {candidate.conflict_reason && (
                          <Alert variant="warning">
                            Workbook pricing differs from illustrative Water Heater script examples. No source was selected automatically.
                          </Alert>
                        )}
                      </article>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-sm text-content-muted" aria-live="polite">
                      Showing {candidateReview.data?.total ? candidateOffset + 1 : 0}–{Math.min(candidateOffset + (candidateReview.data?.items.length ?? 0), candidateReview.data?.total ?? 0)} of {candidateReview.data?.total ?? 0} candidates.
                    </p>
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={candidateOffset === 0}
                        onClick={() => setCandidateOffset((offset) => Math.max(0, offset - candidatePageSize))}
                      >
                        Previous candidates
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={candidateOffset + (candidateReview.data?.items.length ?? 0) >= (candidateReview.data?.total ?? 0)}
                        onClick={() => setCandidateOffset((offset) => offset + candidatePageSize)}
                      >
                        Next candidates
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
          {reviewVersionId && (
            <Card>
              <CardHeader>
                <CardTitle>Activation checklist</CardTitle>
                <CardDescription>
                  Each approval applies only to this exact draft revision. Editing the draft makes prior approvals stale. Activation remains a separate final action.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {activationReadiness.isPending ? <Spinner label="Loading activation checklist" /> : activationReadiness.isError ? (
                  <Alert variant="danger">Activation evidence could not be loaded.</Alert>
                ) : activationReadiness.data && (
                  <>
                    <p><strong>{activationReadiness.data.service_code}</strong> · {activationReadiness.data.activation_ready ? "Ready for explicit activation" : "Not ready to activate"}</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {activationReadiness.data.remaining_blockers.map((blocker) => (
                        <div key={blocker} className="rounded border border-stroke p-3 text-sm">
                          {blocker.replaceAll("_", " ").toLocaleLowerCase()}
                        </div>
                      ))}
                    </div>
                    {activationReadiness.data.material_mapping_required && (
                      <Alert variant="warning">Material mapping is incomplete. This affects internal material readiness; it is not silently treated as Inventory consumption.</Alert>
                    )}
                    <div className="flex flex-wrap gap-2">
                      {canManage && !activationReadiness.data.price_approved && <Button onClick={() => void mutations.activationReview.mutateAsync({ versionId: reviewVersionId, decision: "price", expectedVersion: activationReadiness.data!.draft_version, reason: "Owner approved the ACP selling price shown for this exact draft." })}>Approve selling price</Button>}
                      {canApproveTax && !activationReadiness.data.tax_approved && <Button onClick={() => void mutations.activationReview.mutateAsync({ versionId: reviewVersionId, decision: "tax", expectedVersion: activationReadiness.data!.draft_version, reason: "Authorized finance reviewer approved the selected tax classification for this exact draft." })}>Approve tax classification</Button>}
                      {canManage && !activationReadiness.data.effective_date_approved && <Button onClick={() => void mutations.activationReview.mutateAsync({ versionId: reviewVersionId, decision: "effective-date", expectedVersion: activationReadiness.data!.draft_version, reason: "Owner approved the effective date shown for this exact draft." })}>Approve effective date</Button>}
                      {canActivate && !activationReadiness.data.activation_authorized && <Button disabled={!activationReadiness.data.price_approved || !activationReadiness.data.tax_approved || !activationReadiness.data.effective_date_approved} onClick={() => void mutations.activationReview.mutateAsync({ versionId: reviewVersionId, decision: "activation-authorization", expectedVersion: activationReadiness.data!.draft_version, reason: "Authorized owner approved this exact draft for a later explicit activation command." })}>Authorize later activation</Button>}
                      {canActivate && activationReadiness.data.activation_ready && <Button onClick={() => void performMutation(() => mutations.activate.mutateAsync({ id: reviewVersionId, version: activationReadiness.data!.draft_version }))}>Activate reviewed version</Button>}
                    </div>
                    <div>
                      <h3 className="font-semibold">Review and activation history</h3>
                      {reviewAudit.isPending ? <Spinner label="Loading Price Book history" /> : (
                        <ul className="mt-2 space-y-2 text-sm">
                          {(reviewAudit.data ?? []).map((entry) => <li key={entry.id}><strong>{entry.action.replaceAll("_", " ")}</strong> · {entry.reason} · {new Date(entry.occurred_at).toLocaleString()}</li>)}
                        </ul>
                      )}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Activation readiness</CardTitle>
              <CardDescription>
                Review customer content and prices in groups. Tax decisions and
                internal cost completion stay visible as separate work; saving
                or approving a review never activates a price.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="rounded-lg border border-stroke p-4">
                  <strong>Customer use</strong>
                  <p className="mt-1 text-sm text-content-muted">
                    Description, candidate price, options and membership
                    eligibility determine what can be presented on an Estimate.
                  </p>
                </div>
                <div className="rounded-lg border border-stroke p-4">
                  <strong>Tax decision</strong>
                  <p className="mt-1 text-sm text-content-muted">
                    Reusable treatment classes can be reviewed by an accountant
                    without answering once per service.
                  </p>
                </div>
                <div className="rounded-lg border border-stroke p-4">
                  <strong>Internal costing</strong>
                  <p className="mt-1 text-sm text-content-muted">
                    Missing cost detail affects planned Economics and
                    price-review insight, not an otherwise complete customer
                    price.
                  </p>
                </div>
              </div>
              {canManage && (
                <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-end">
                  <label className="space-y-1 text-sm font-medium">
                    Review the visible group
                    <Select
                      aria-label="Bulk review type"
                      value={reviewType}
                      onChange={(event) => {
                        setReviewType(event.target.value as typeof reviewType);
                        setSavedReview(null);
                      }}
                    >
                      <option value="candidate_prices">Candidate prices</option>
                      <option value="commercial_content">
                        Customer content
                      </option>
                      <option value="tax_classification">
                        Tax classification
                      </option>
                      <option value="membership">Membership</option>
                      <option value="source_conflict">Source conflicts</option>
                    </Select>
                  </label>
                  <Button
                    onClick={() => void saveVisibleReview()}
                    loading={mutations.reviewBatch.isPending}
                    disabled={filteredServices.length === 0}
                  >
                    Save {filteredServices.length} as draft
                  </Button>
                  <Button
                    onClick={() => void approveSavedReview()}
                    loading={mutations.reviewDecision.isPending}
                    disabled={!savedReview}
                  >
                    Approve saved group
                  </Button>
                </div>
              )}
              {savedReview && (
                <Alert variant="success" role="status">
                  Saved a review group containing {savedReview.count} services.
                  Activation is still separate.
                </Alert>
              )}
            </CardContent>
          </Card>
          {canManage && (
            <Card>
              <CardHeader>
                <CardTitle>Bulk price adjustment</CardTitle>
                <CardDescription>
                  Preview the currently filtered active services. Approval creates
                  successor drafts only; activation remains a separate action.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 sm:grid-cols-3">
                  <Select
                    aria-label="Bulk adjustment method"
                    value={adjustment.kind}
                    onChange={(event) =>
                      setAdjustment({
                        ...adjustment,
                        kind: event.target.value as typeof adjustment.kind,
                      })
                    }
                  >
                    <option value="percentage">Percentage</option>
                    <option value="fixed_amount">Fixed amount</option>
                  </Select>
                  <Input
                    aria-label="Bulk adjustment value"
                    type="number"
                    step="0.01"
                    value={adjustment.value}
                    onChange={(event) =>
                      setAdjustment({ ...adjustment, value: event.target.value })
                    }
                  />
                  <Input
                    aria-label="Bulk adjustment effective date"
                    type="datetime-local"
                    value={adjustment.effective}
                    onChange={(event) =>
                      setAdjustment({
                        ...adjustment,
                        effective: event.target.value,
                      })
                    }
                  />
                </div>
                <p className="text-sm text-content-muted">
                  Preview scope: {filteredServices.filter((service) => service.current_version_id).length} active-priced services. No historical version will be changed.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => void saveAdjustmentPreview()}
                    disabled={!adjustment.value || !adjustment.effective}
                    loading={mutations.adjustmentProposal.isPending}
                  >
                    Save exact preview
                  </Button>
                  {canActivate && (
                    <Button
                      onClick={() => void approveAdjustment()}
                      disabled={!savedAdjustment || savedAdjustment.status !== "draft"}
                      loading={mutations.adjustmentDecision.isPending}
                    >
                      Approve preview
                    </Button>
                  )}
                  <Button
                    onClick={() => void createAdjustmentDrafts()}
                    disabled={!savedAdjustment || savedAdjustment.status !== "approved"}
                    loading={mutations.adjustmentMaterialize.isPending}
                  >
                    Create successor drafts
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => setSavedAdjustment(null)}
                    disabled={!savedAdjustment}
                  >
                    Cancel preview
                  </Button>
                </div>
                {savedAdjustment && (
                  <Alert variant="success" role="status">
                    Exact preview saved for {savedAdjustment.count} services · {savedAdjustment.status}. No price is active.
                  </Alert>
                )}
              </CardContent>
            </Card>
          )}
          {canManage && (
            <section className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>New category</CardTitle>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitCategory(e)}
                  >
                    <Select
                      aria-label="Choose category to edit"
                      value={editCategory?.id ?? ""}
                      onChange={(event) => {
                        const selected = catalog.data?.categories.find(
                          (candidate) => candidate.id === event.target.value,
                        );
                        if (!selected) {
                          setEditCategory(null);
                          setCategory(emptyCategory);
                          return;
                        }
                        setEditCategory({ id: selected.id, version: selected.version });
                        setCategory({
                          code: selected.code,
                          name: selected.name,
                          description: selected.description ?? "",
                          parentId: selected.parent_id ?? "",
                          position: selected.position?.toString() ?? "",
                          status: selected.status as "draft" | "active" | "archived",
                        });
                      }}
                    >
                      <option value="">Create a new category</option>
                      {catalog.data?.categories.map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          Edit {candidate.name}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label="Category code"
                      placeholder="Code"
                      value={category.code}
                      onChange={(e) =>
                        setCategory({ ...category, code: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Category name"
                      placeholder="Name"
                      value={category.name}
                      onChange={(e) =>
                        setCategory({ ...category, name: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Category description"
                      placeholder="Description"
                      value={category.description}
                      onChange={(e) => setCategory({ ...category, description: e.target.value })}
                    />
                    <Select
                      aria-label="Parent category"
                      value={category.parentId}
                      onChange={(e) => setCategory({ ...category, parentId: e.target.value })}
                    >
                      <option value="">No parent category</option>
                      {catalog.data?.categories
                        .filter((candidate) => candidate.id !== editCategory?.id)
                        .map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
                    </Select>
                    <Input
                      aria-label="Category order"
                      type="number"
                      min="1"
                      placeholder="Display order"
                      value={category.position}
                      onChange={(e) => setCategory({ ...category, position: e.target.value })}
                    />
                    {editCategory && (
                      <Select
                        aria-label="Category status"
                        value={category.status}
                        onChange={(e) => setCategory({ ...category, status: e.target.value as "draft" | "active" | "archived" })}
                      >
                        <option value="draft">Draft</option>
                        <option value="active">Active</option>
                        <option value="archived">Archived</option>
                      </Select>
                    )}
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.category.isPending || mutations.categoryUpdate.isPending}
                    >
                      {editCategory ? "Save category" : "Create category"}
                    </Button>
                    {editCategory && (
                      <Button type="button" variant="ghost" fullWidth onClick={() => { setEditCategory(null); setCategory(emptyCategory); }}>
                        Cancel category edit
                      </Button>
                    )}
                  </form>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>{editItem ? "Edit service item" : "New service item"}</CardTitle>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitItem(e)}
                  >
                    <Select
                      aria-label="Service category"
                      value={item.category_id}
                      onChange={(e) =>
                        setItem({ ...item, category_id: e.target.value })
                      }
                      required
                    >
                      <option value="">Category</option>
                      {catalog.data?.categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label="Service code"
                      placeholder="Code"
                      value={item.code}
                      onChange={(e) =>
                        setItem({ ...item, code: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Service name"
                      placeholder="Name"
                      value={item.name}
                      onChange={(e) =>
                        setItem({ ...item, name: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Customer description"
                      placeholder="Customer description"
                      value={item.customer_description}
                      onChange={(e) =>
                        setItem({
                          ...item,
                          customer_description: e.target.value,
                        })
                      }
                      required
                    />
                    <Input
                      aria-label="Internal service notes"
                      placeholder="Internal technical or cost notes"
                      value={item.internal_description}
                      onChange={(e) => setItem({ ...item, internal_description: e.target.value })}
                    />
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.item.isPending || mutations.itemUpdate.isPending}
                    >
                      {editItem ? "Save service item" : "Create service item"}
                    </Button>
                    {editItem && (
                      <Button
                        fullWidth
                        type="button"
                        variant="ghost"
                        onClick={() => {
                          setEditItem(null);
                          setItem({ category_id: "", code: "", name: "", customer_description: "", internal_description: "" });
                        }}
                      >
                        Cancel edit
                      </Button>
                    )}
                  </form>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>{editDraft ? "Edit draft price version" : "Draft price version"}</CardTitle>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitDraft(e)}
                  >
                    <Select
                      aria-label="Price service item"
                      value={draft.itemId}
                      onChange={(e) =>
                        setDraft({ ...draft, itemId: e.target.value })
                      }
                      required
                    >
                      <option value="">Service item</option>
                      {catalog.data?.service_items.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name}
                        </option>
                      ))}
                    </Select>
                    <Select
                      aria-label="Tax classification"
                      value={draft.taxId}
                      onChange={(e) =>
                        setDraft({ ...draft, taxId: e.target.value })
                      }
                      required
                    >
                      <option value="">Tax classification</option>
                      {catalog.data?.tax_classifications.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label="Unit price"
                      type="number"
                      min="0"
                      step="0.0001"
                      placeholder="Unit price"
                      value={draft.price}
                      onChange={(e) =>
                        setDraft({ ...draft, price: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Effective time"
                      type="datetime-local"
                      value={draft.effective}
                      onChange={(e) =>
                        setDraft({ ...draft, effective: e.target.value })
                      }
                      required
                    />
                    <Select
                      aria-label="Component type"
                      value={draft.componentType}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          componentType: e.target.value as "labor" | "material" | "other_direct",
                        })
                      }
                    >
                      <option value="labor">Labor</option>
                      <option value="material">Material</option>
                      <option value="other_direct">Other direct cost</option>
                    </Select>
                    <Input
                      aria-label="Component label"
                      placeholder="Component label"
                      value={draft.componentLabel}
                      onChange={(e) =>
                        setDraft({ ...draft, componentLabel: e.target.value })
                      }
                      required={draftComponents.length === 0}
                    />
                    <Input
                      aria-label="Expected component quantity"
                      type="number"
                      min="0.0001"
                      step="0.0001"
                      value={draft.componentQuantity}
                      onChange={(e) =>
                        setDraft({ ...draft, componentQuantity: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Expected component unit cost"
                      type="number"
                      min="0"
                      step="0.0001"
                      placeholder="Leave blank when cost evidence is unavailable"
                      value={draft.componentCost}
                      onChange={(e) =>
                        setDraft({ ...draft, componentCost: e.target.value })
                      }
                    />
                    <p className="text-xs text-content-muted">
                      Expected inputs support planning only. They do not prove purchased or consumed materials, and missing cost is never treated as zero.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      fullWidth
                      disabled={!draft.componentLabel || !draft.componentQuantity}
                      onClick={() => {
                        setDraftComponents([
                          ...draftComponents,
                          {
                            component_type: draft.componentType,
                            label: draft.componentLabel,
                            quantity: draft.componentQuantity,
                            unit_cost: draft.componentCost || undefined,
                          },
                        ]);
                        setDraft({
                          ...draft,
                          componentLabel: "",
                          componentQuantity: "1",
                          componentCost: "",
                        });
                      }}
                    >
                      Add expected input
                    </Button>
                    {draftComponents.length > 0 && (
                      <ul className="space-y-2 text-sm" aria-label="Staged expected inputs">
                        {draftComponents.map((component, index) => (
                          <li key={`${component.component_type}:${component.label}:${index}`} className="flex items-center justify-between gap-3 rounded-md bg-surface-muted p-2">
                            <span>{component.component_type.replaceAll("_", " ")} · {component.label} · {component.quantity}{component.unit_cost ? ` × USD ${component.unit_cost}` : " · cost evidence missing"}</span>
                            <Button type="button" variant="ghost" onClick={() => setDraftComponents(draftComponents.filter((_, candidate) => candidate !== index))}>Remove</Button>
                          </li>
                        ))}
                      </ul>
                    )}
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.version.isPending || mutations.versionUpdate.isPending}
                    >
                      {editDraft ? "Save draft price version" : "Create draft"}
                    </Button>
                    {editDraft && (
                      <Button type="button" variant="ghost" fullWidth onClick={() => { setEditDraft(null); setDraftComponents([]); }}>
                        Cancel draft edit
                      </Button>
                    )}
                  </form>
                </CardContent>
              </Card>
            </section>
          )}
          {canManage && (
            <section className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>Tax classification</CardTitle>
                  <CardDescription>
                    Define the internal tax treatment carried into snapshots.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitTax(e)}
                  >
                    <Input
                      aria-label="Tax code"
                      placeholder="Code"
                      value={tax.code}
                      onChange={(e) => setTax({ ...tax, code: e.target.value })}
                      required
                    />
                    <Input
                      aria-label="Tax name"
                      placeholder="Name"
                      value={tax.name}
                      onChange={(e) => setTax({ ...tax, name: e.target.value })}
                      required
                    />
                    <label className="flex min-h-11 items-center gap-3">
                      <input
                        type="checkbox"
                        checked={tax.taxable}
                        onChange={(e) =>
                          setTax({ ...tax, taxable: e.target.checked })
                        }
                      />
                      Taxable
                    </label>
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.tax.isPending}
                    >
                      Create tax classification
                    </Button>
                  </form>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Customer option group</CardTitle>
                  <CardDescription>
                    Define explicit required and maximum selections.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitOptionGroup(e)}
                  >
                    <Input
                      aria-label="Option group code"
                      placeholder="Code"
                      value={optionGroup.code}
                      onChange={(e) =>
                        setOptionGroup({ ...optionGroup, code: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Option group name"
                      placeholder="Name"
                      value={optionGroup.name}
                      onChange={(e) =>
                        setOptionGroup({ ...optionGroup, name: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Minimum selections"
                      type="number"
                      min="0"
                      value={optionGroup.minimum_selections}
                      onChange={(e) =>
                        setOptionGroup({
                          ...optionGroup,
                          minimum_selections: Number(e.target.value),
                        })
                      }
                      required
                    />
                    <Input
                      aria-label="Maximum selections"
                      type="number"
                      min="1"
                      value={optionGroup.maximum_selections}
                      onChange={(e) =>
                        setOptionGroup({
                          ...optionGroup,
                          maximum_selections: Number(e.target.value),
                        })
                      }
                      required
                    />
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.optionGroup.isPending}
                    >
                      Create option group
                    </Button>
                  </form>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Add customer option</CardTitle>
                </CardHeader>
                <CardContent>
                  <form
                    className="space-y-3"
                    onSubmit={(e) => void submitOption(e)}
                  >
                    <Select
                      aria-label="Option group"
                      value={option.groupId}
                      onChange={(e) =>
                        setOption({ ...option, groupId: e.target.value })
                      }
                      required
                    >
                      <option value="">Option group</option>
                      {catalog.data?.option_groups.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name}
                        </option>
                      ))}
                    </Select>
                    <Select
                      aria-label="Option service item"
                      value={option.serviceItemId}
                      onChange={(e) =>
                        setOption({ ...option, serviceItemId: e.target.value })
                      }
                      required
                    >
                      <option value="">Service item</option>
                      {catalog.data?.service_items.map((service) => (
                        <option key={service.id} value={service.id}>
                          {service.name}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label="Option label"
                      placeholder="Customer label"
                      value={option.label}
                      onChange={(e) =>
                        setOption({ ...option, label: e.target.value })
                      }
                      required
                    />
                    <Input
                      aria-label="Option position"
                      type="number"
                      min="1"
                      value={option.position}
                      onChange={(e) =>
                        setOption({ ...option, position: e.target.value })
                      }
                      required
                    />
                    <Button
                      fullWidth
                      type="submit"
                      loading={mutations.option.isPending}
                    >
                      Add option
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </section>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Customer option sets</CardTitle>
              <CardDescription>
                Good/Better/Best and other genuine alternatives connected to Price Book services.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {catalog.data?.option_groups.length ? (
                <div className="grid gap-3 md:grid-cols-2">
                  {catalog.data.option_groups.map((group) => {
                    const groupOptions = catalog.data?.options
                      .filter((candidate) => candidate.option_group_id === group.id)
                      .sort((left, right) => left.position - right.position) ?? [];
                    return (
                      <section key={group.id} className="rounded-lg border border-stroke p-4" aria-label={`Option set ${group.name}`}>
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div><p className="text-xs text-content-muted">{group.code}</p><h3 className="font-semibold">{group.name}</h3></div>
                          <Badge variant={group.status === "active" ? "success" : "neutral"}>{group.status}</Badge>
                        </div>
                        <p className="mt-2 text-xs text-content-muted">Choose at least {group.minimum_selections} and at most {group.maximum_selections}.</p>
                        <ol className="mt-3 space-y-2">
                          {groupOptions.map((choice) => {
                            const service = catalog.data?.service_items.find((item) => item.id === choice.service_item_id);
                            return <li key={choice.id} className="rounded-md bg-surface-muted p-3 text-sm"><strong>{choice.label}</strong><span className="text-content-muted"> · {service ? `${service.code} · ${service.name}` : "Connected service unavailable"}</span></li>;
                          })}
                        </ol>
                        {groupOptions.length === 0 && <p className="mt-3 text-sm text-content-muted">No service choices are connected yet.</p>}
                      </section>
                    );
                  })}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-stroke p-4 text-sm text-content-muted">No customer option sets are configured.</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Service prices</CardTitle>
              <CardDescription>
                Search by customer language or service code. Activation remains
                a separate authorized action.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4 grid gap-3 sm:grid-cols-3">
                <Input
                  aria-label="Search Price Book"
                  placeholder="Search services"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setCandidateOffset(0);
                    setCatalogOffset(0);
                  }}
                />
                <Select
                  aria-label="Filter Price Book category"
                  value={categoryFilter}
                  onChange={(event) => {
                    setCategoryFilter(event.target.value);
                    setCatalogOffset(0);
                  }}
                >
                  <option value="all">All categories</option>
                  {catalog.data?.categories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {categoryDisplayName(category.id)}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Filter Price Book status"
                  value={statusFilter}
                  onChange={(event) => {
                    setStatusFilter(event.target.value);
                    setCatalogOffset(0);
                  }}
                >
                  <option value="all">All states</option>
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="inactive">Inactive</option>
                  <option value="archived">Archived</option>
                </Select>
              </div>
              <nav aria-label="Browse Price Book categories" className="mb-4 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant={categoryFilter === "all" ? "primary" : "ghost"}
                  onClick={() => {
                    setCategoryFilter("all");
                    setCatalogOffset(0);
                  }}
                >
                  All categories
                </Button>
                {catalog.data?.categories.map((category) => (
                  <Button
                    key={category.id}
                    type="button"
                    variant={categoryFilter === category.id ? "primary" : "ghost"}
                    onClick={() => {
                      setCategoryFilter(category.id);
                      setCatalogOffset(0);
                    }}
                  >
                    {categoryDisplayName(category.id)}
                  </Button>
                ))}
              </nav>
              <p className="mb-3 text-sm text-content-muted" aria-live="polite">
                Showing {catalog.data?.total_service_items ? catalogOffset + 1 : 0}–{Math.min(catalogOffset + services.length, catalog.data?.total_service_items ?? 0)} of {catalog.data?.total_service_items ?? 0} services.
              </p>
              {selectedService && (
                <section
                  aria-label="Selected service details"
                  className="mb-4 rounded-lg border border-stroke bg-surface-muted p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs text-content-muted">
                        {selectedCategory
                          ? categoryDisplayName(selectedCategory.id)
                          : "Category unavailable"} ·{" "}
                        {selectedService.code}
                      </p>
                      <h3 className="text-lg font-semibold">{selectedService.name}</h3>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => setSelectedServiceId(undefined)}
                    >
                      Back to results
                    </Button>
                  </div>
                  <p className="mt-2">{selectedService.customer_description}</p>
                  {canManage && selectedService.internal_description && (
                    <p className="mt-2 rounded-md bg-surface-muted p-3 text-sm">
                      <strong>Internal notes:</strong> {selectedService.internal_description}
                    </p>
                  )}
                  {selectedService.status === "draft" && (
                    <Alert>
                      This Draft service is available for owner review. It cannot be selected in an Estimate until an authorized owner explicitly activates it.
                    </Alert>
                  )}
                  {selectedCandidate.isPending ? (
                    <Spinner label="Loading service evidence" />
                  ) : selectedCandidate.isError || !selectedEvidence ? (
                    <Alert variant="warning">
                      Native service details are available, but source evidence could not be loaded.
                    </Alert>
                  ) : (
                    <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                      <div><dt className="text-content-muted">Status</dt><dd>{selectedEvidence.admission_status === "held" ? "Held — source conflict" : "Draft — ready for review"}</dd></div>
                      <div><dt className="text-content-muted">Candidate price</dt><dd>${selectedEvidence.candidate_prices.standard ?? "Not supplied"} — not active</dd></div>
                      <div><dt className="text-content-muted">Source</dt><dd>{selectedEvidence.source_sheet}, row {selectedEvidence.source_row}</dd></div>
                      <div><dt className="text-content-muted">Remaining review</dt><dd>{selectedEvidence.review_flags.length ? selectedEvidence.review_flags.map((flag) => flag.replaceAll("_", " ").toLocaleLowerCase()).join(" · ") : "No review flags"}</dd></div>
                    </dl>
                  )}
                </section>
              )}
              {!catalog.isPending && filteredServices.length === 0 && (
                <Alert variant="warning">
                  No Price Book services match this search and filter combination.
                </Alert>
              )}
              <ul className="space-y-3">
                {filteredServices.map((service) => {
                  const itemVersions = versions.filter(
                    (v) => v.service_item_id === service.id,
                  );
                  const reviewState = itemVersions.some(
                    (version) => version.status === "draft",
                  )
                    ? "Ready for owner review"
                    : itemVersions.length === 0
                      ? "Missing price evidence"
                      : "Configured";
                  return (
                    <li
                      key={service.id}
                      className="rounded-lg border border-stroke p-4"
                    >
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                          <div className="flex flex-wrap gap-2">
                            <strong>{service.name}</strong>
                            <code>{service.code}</code>
                            <Badge
                              variant={
                                service.status === "active"
                                  ? "success"
                                  : "neutral"
                              }
                            >
                              {service.status}
                            </Badge>
                            <Badge variant="neutral">{reviewState}</Badge>
                          </div>
                          <p className="mt-1 text-sm text-content-muted">
                            {service.customer_description}
                          </p>
                          <Button
                            className="mt-2"
                            type="button"
                            variant="secondary"
                            onClick={() => setSelectedServiceId(service.id)}
                          >
                            Open service details
                          </Button>
                          {canManage && (
                            <Button
                              className="mt-2"
                              type="button"
                              variant="ghost"
                              onClick={() => {
                                setItem({
                                  category_id: service.category_id,
                                  code: service.code,
                                  name: service.name,
                                  customer_description: service.customer_description,
                                  internal_description: service.internal_description ?? "",
                                });
                                setEditItem({
                                  id: service.id,
                                  version: service.version,
                                  status: service.status as "draft" | "active" | "inactive" | "archived",
                                });
                              }}
                            >
                              Edit service details
                            </Button>
                          )}
                        </div>
                      </div>
                      <div className="mt-3 grid gap-2">
                        {itemVersions.map((version) => (
                          <div
                            key={version.id}
                            className="flex flex-col gap-2 rounded-md bg-surface-muted p-3 sm:flex-row sm:items-center sm:justify-between"
                          >
                            <div>
                              <span>
                                Revision {version.revision} · {version.currency}{" "}
                                {version.unit_price} · {version.status}
                              </span>
                              <p className="text-xs text-content-muted">
                                Effective {new Date(version.effective_at).toLocaleString()} · {version.cost_readiness === "COST_COMPLETE" ? "Cost evidence complete" : "Insufficient cost evidence"}
                              </p>
                              {canManage && version.expected_direct_cost && (
                                <p className="text-xs text-content-muted">
                                  Expected direct cost {version.currency} {version.expected_direct_cost} · Expected direct contribution {version.currency} {version.expected_direct_contribution}
                                </p>
                              )}
                              {canManage && version.components.length > 0 && (
                                <div className="mt-2 text-xs text-content-muted">
                                  <p>
                                    Expected inputs only — these do not record a
                                    purchase, Inventory movement, or Job consumption.
                                  </p>
                                  <ul
                                    className="mt-1 space-y-1"
                                    aria-label={`Expected inputs for revision ${version.revision}`}
                                  >
                                    {version.components.map((component) => (
                                      <li key={`${component.position}:${component.label}`}>
                                        {component.component_type.replaceAll("_", " ")} ·{" "}
                                        {component.label} · {component.quantity}
                                        {component.unit_cost == null
                                          ? " · cost evidence missing"
                                          : ` × ${version.currency} ${component.unit_cost}`}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {version.status === "draft" && itemVersions.some((candidate) => candidate.status === "active") && (
                                <p className="text-xs font-medium text-content-muted">
                                  Change from active: {version.currency} {(Number(version.unit_price) - Number(itemVersions.find((candidate) => candidate.status === "active")?.unit_price ?? 0)).toFixed(2)}
                                </p>
                              )}
                            </div>
                            {canActivate && version.status === "draft" && (
                              <Button variant="secondary" onClick={() => setReviewVersionId(version.id)}>Review activation</Button>
                            )}
                            {canManage && version.status === "draft" && (
                              <Button
                                variant="ghost"
                                onClick={() => {
                                  setEditDraft({ id: version.id, version: version.version });
                                  setDraft({
                                    itemId: version.service_item_id,
                                    taxId: version.tax_classification_id,
                                    price: version.unit_price,
                                    effective: version.effective_at.slice(0, 16),
                                    componentType: "labor",
                                    componentLabel: "",
                                    componentQuantity: "1",
                                    componentCost: "",
                                  });
                                  setDraftComponents(version.components.map((component) => ({
                                    component_type: component.component_type,
                                    label: component.label,
                                    quantity: component.quantity,
                                    unit_cost: component.unit_cost,
                                  })));
                                }}
                              >
                                Edit draft price
                              </Button>
                            )}
                            {canActivate && version.status === "active" && (
                              <Button
                                variant="ghost"
                                loading={mutations.versionLifecycle.isPending}
                                onClick={() => void mutations.versionLifecycle.mutateAsync({ versionId: version.id, action: "inactivate", expectedVersion: version.version })}
                              >
                                Inactivate price version
                              </Button>
                            )}
                            {canActivate && version.status === "inactive" && (
                              <Button
                                variant="ghost"
                                loading={mutations.versionLifecycle.isPending}
                                onClick={() => void mutations.versionLifecycle.mutateAsync({ versionId: version.id, action: "archive", expectedVersion: version.version })}
                              >
                                Archive price version
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={catalogOffset === 0}
                  onClick={() => setCatalogOffset((offset) => Math.max(0, offset - catalogPageSize))}
                >
                  Previous services
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={catalogOffset + services.length >= (catalog.data?.total_service_items ?? 0)}
                  onClick={() => setCatalogOffset((offset) => offset + catalogPageSize)}
                >
                  Next services
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
