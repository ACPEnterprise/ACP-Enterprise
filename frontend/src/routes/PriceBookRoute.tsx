import axios from "axios";
import { useMemo, useState, type FormEvent } from "react";

import { useAuth, useHasPermission } from "../auth";
import { usePriceBook, usePriceBookMutations } from "../hooks/usePriceBook";
import type { PriceBookOperatorCatalog, PriceBookServiceItem, PriceBookVersion } from "../types/priceBook";
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
  Textarea,
} from "../ui";

const recoveryMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    const recovery = (error.response?.data as { detail?: { recovery?: string } })
      ?.detail?.recovery;
    if (recovery === "RETRY_AFTER_REFRESH") return "Price Book authority changed. Refresh before continuing.";
    if (recovery === "USER_CORRECTION_REQUIRED") return "Price Book evidence requires correction. Review the retained inputs.";
    if (recovery === "TEMPORARILY_UNAVAILABLE") return "Price Book is temporarily unavailable. Your inputs were retained.";
    if (recovery === "OWNER_ADMIN_ACTION_REQUIRED") return "Price Book requires owner or administrator action before continuing.";
    if (recovery === "TERMINAL_FAILURE") return "The Price Book resource is no longer available. Refresh authoritative state.";
  }
  return "Price Book operation failed safely. Refresh authoritative state before retrying.";
};

const localDateTime = (value: string) => value.slice(0, 16);

export function PriceBookRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_PRICE_BOOK_READ");
  const canManage = useHasPermission("COMPANY_PRICE_BOOK_MANAGE");
  const canActivate = useHasPermission("COMPANY_PRICE_BOOK_ACTIVATE");
  const [branch, setBranch] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("current");
  const [selectedItemId, setSelectedItemId] = useState("");
  const catalog = usePriceBook(branch || undefined, canRead, canManage);
  const mutations = usePriceBookMutations();
  const [category, setCategory] = useState({ code: "", name: "" });
  const [categoryEdit, setCategoryEdit] = useState({ id: "", version: 1, name: "", description: "", parent_id: "", status: "active" as "active" | "archived" });
  const [tax, setTax] = useState({ code: "", name: "", taxable: true });
  const [taxEdit, setTaxEdit] = useState({ id: "", version: 1, name: "", taxable: true, status: "active" as "active" | "inactive" | "archived" });
  const [optionGroup, setOptionGroup] = useState({ code: "", name: "", minimum_selections: 0, maximum_selections: 1 });
  const [option, setOption] = useState({ groupId: "", serviceItemId: "", label: "", position: "1" });
  const [item, setItem] = useState({ category_id: "", code: "", name: "", customer_description: "" });
  const [itemEdit, setItemEdit] = useState({ id: "", version: 1, category_id: "", name: "", customer_description: "", internal_description: "" });
  const [draft, setDraft] = useState({
    itemId: "",
    versionId: "",
    version: 1,
    taxId: "",
    price: "",
    effective: "",
    componentType: "labor" as "labor" | "material",
    componentLabel: "",
    componentQuantity: "1",
    componentCost: "",
  });

  const data = catalog.data;
  const filteredItems = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (data?.service_items ?? []).filter((value) => {
      const matchesSearch = !needle || `${value.code} ${value.name} ${value.customer_description}`.toLowerCase().includes(needle);
      const matchesCategory = !categoryFilter || value.category_id === categoryFilter;
      const matchesStatus = statusFilter === "all" || (statusFilter === "current" ? value.status !== "archived" : value.status === statusFilter);
      return matchesSearch && matchesCategory && matchesStatus;
    });
  }, [categoryFilter, data?.service_items, search, statusFilter]);
  const selectedItem = data?.service_items.find((value) => value.id === selectedItemId) ?? filteredItems[0];
  const selectedVersions = (data?.versions ?? []).filter((value) => value.service_item_id === selectedItem?.id);
  const currentVersion = selectedVersions.find((value) => value.id === selectedItem?.current_version_id);
  const failedMutation = Object.values(mutations).find((mutation) => mutation.isError);

  const perform = async (operation: () => Promise<unknown>, success?: () => void) => {
    try {
      await operation();
      success?.();
    } catch {
      // Governed recovery is rendered without reflecting backend details.
    }
  };
  const submitCategory = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.category.mutateAsync(category), () => setCategory({ code: "", name: "" }));
  };
  const submitItem = async (event: FormEvent) => {
    event.preventDefault();
    await perform(
      () => mutations.item.mutateAsync({ ...item, branch_id: branch || undefined }),
      () => setItem({ category_id: "", code: "", name: "", customer_description: "" }),
    );
  };
  const submitCategoryEdit = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.updateCategory.mutateAsync({ id: categoryEdit.id, data: { expected_version: categoryEdit.version, name: categoryEdit.name, description: categoryEdit.description || undefined, parent_id: categoryEdit.parent_id || undefined, status: categoryEdit.status } }));
  };
  const chooseCategory = (id: string) => {
    const value = data?.categories.find((entry) => entry.id === id);
    setCategoryEdit(value ? { id: value.id, version: value.version, name: value.name, description: value.description ?? "", parent_id: value.parent_id ?? "", status: value.status as "active" | "archived" } : { id: "", version: 1, name: "", description: "", parent_id: "", status: "active" });
  };
  const submitItemEdit = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.updateItem.mutateAsync({ id: itemEdit.id, data: { expected_version: itemEdit.version, category_id: itemEdit.category_id, name: itemEdit.name, customer_description: itemEdit.customer_description, internal_description: itemEdit.internal_description || undefined } }));
  };
  const editItem = (value: PriceBookServiceItem) => setItemEdit({ id: value.id, version: value.version, category_id: value.category_id, name: value.name, customer_description: value.customer_description, internal_description: value.internal_description ?? "" });
  const submitTax = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.tax.mutateAsync(tax), () => setTax({ code: "", name: "", taxable: true }));
  };
  const chooseTax = (id: string) => {
    const value = data?.tax_classifications.find((entry) => entry.id === id);
    setTaxEdit(value ? { id: value.id, version: value.version, name: value.name, taxable: value.taxable, status: value.status as "active" | "inactive" | "archived" } : { id: "", version: 1, name: "", taxable: true, status: "active" });
  };
  const submitTaxEdit = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.updateTax.mutateAsync({ id: taxEdit.id, data: { expected_version: taxEdit.version, name: taxEdit.name, taxable: taxEdit.taxable, status: taxEdit.status } }));
  };
  const submitOptionGroup = async (event: FormEvent) => {
    event.preventDefault();
    await perform(() => mutations.optionGroup.mutateAsync(optionGroup), () => setOptionGroup({ code: "", name: "", minimum_selections: 0, maximum_selections: 1 }));
  };
  const submitOption = async (event: FormEvent) => {
    event.preventDefault();
    await perform(
      () => mutations.option.mutateAsync({ groupId: option.groupId, data: { service_item_id: option.serviceItemId, label: option.label, position: Number(option.position) } }),
      () => setOption({ groupId: "", serviceItemId: "", label: "", position: "1" }),
    );
  };
  const draftPayload = () => ({
    tax_classification_id: draft.taxId,
    currency: "USD",
    unit_price: draft.price,
    effective_at: new Date(draft.effective).toISOString(),
    components: [{
      component_type: draft.componentType,
      label: draft.componentLabel,
      quantity: draft.componentQuantity,
      unit_cost: draft.componentCost || undefined,
    }],
  });
  const submitDraft = async (event: FormEvent) => {
    event.preventDefault();
    if (draft.versionId) {
      await perform(() => mutations.updateVersion.mutateAsync({ id: draft.versionId, data: { ...draftPayload(), expected_version: draft.version } }));
    } else {
      await perform(() => mutations.version.mutateAsync({ itemId: draft.itemId, data: { ...draftPayload(), branch_id: branch || undefined } }));
    }
  };
  const editDraft = (version: PriceBookVersion) => {
    const internalComponents = data && "internal_components" in data
      ? (data as PriceBookOperatorCatalog).internal_components
      : [];
    const component = internalComponents.find((value) => version.components.some((item) => item.id === value.id)) ?? version.components[0];
    setDraft({
      itemId: version.service_item_id,
      versionId: version.id,
      version: version.version,
      taxId: version.tax_classification_id,
      price: version.unit_price,
      effective: localDateTime(version.effective_at),
      componentType: component?.component_type ?? "labor",
      componentLabel: component?.label ?? "",
      componentQuantity: component?.quantity ?? "1",
      componentCost: component?.unit_cost ?? "",
    });
  };

  if (!activeCompany) return <Alert variant="danger">Select an accessible Company before opening Price Book.</Alert>;
  if (!canRead) return <Alert variant="danger">You are not authorized to view Price Book.</Alert>;

  return <div className="mx-auto max-w-7xl space-y-6 pb-10">
    <header>
      <p className="text-sm font-semibold text-action-primary">Sales / Commercial Operations</p>
      <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Price Book</h1>
      <p className="mt-2 text-content-muted">Build, review, and activate controlled service pricing without changing historical versions.</p>
    </header>

    <Card>
      <CardHeader><CardTitle>Find services</CardTitle><CardDescription>Company-wide services appear in every Branch. Branch services remain local.</CardDescription></CardHeader>
      <CardContent><div className="grid gap-3 md:grid-cols-4">
        <Select aria-label="Price Book Branch" value={branch} onChange={(event) => setBranch(event.target.value)}><option value="">All Company prices</option>{activeCompany.branches.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select>
        <Input aria-label="Search Price Book" placeholder="Search code, name, or description" value={search} onChange={(event) => setSearch(event.target.value)} />
        <Select aria-label="Filter category" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="">All categories</option>{data?.categories.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select>
        <Select aria-label="Filter status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="current">Current</option><option value="draft">Draft</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="archived">Archived</option><option value="all">All history</option></Select>
      </div></CardContent>
    </Card>

    {catalog.isPending ? <Spinner label="Loading Price Book" /> : catalog.isError ? <Alert variant="danger">Price Book could not be loaded.</Alert> : <>
      {failedMutation && <Alert variant="danger" role="alert" aria-live="assertive">{recoveryMessage(failedMutation.error)}</Alert>}
      <div className="grid gap-5 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,2fr)]">
        <Card><CardHeader><CardTitle>Services</CardTitle><CardDescription>{filteredItems.length} matching items</CardDescription></CardHeader><CardContent><ul className="space-y-2">{filteredItems.map((value) => <li key={value.id}><button type="button" className="w-full rounded-lg border border-stroke p-3 text-left hover:bg-surface-muted" onClick={() => setSelectedItemId(value.id)}><span className="flex items-center justify-between gap-2"><strong>{value.name}</strong><Badge variant={value.status === "active" ? "success" : "neutral"}>{value.status}</Badge></span><span className="mt-1 block text-sm text-content-muted">{value.code} · {data?.categories.find((entry) => entry.id === value.category_id)?.name ?? "Uncategorized"}</span></button></li>)}</ul></CardContent></Card>
        <ServiceDetail item={selectedItem} versions={selectedVersions} currentVersion={currentVersion} canManage={canManage} canActivate={canActivate} onEditItem={editItem} onEditDraft={editDraft} onActivate={(version) => void perform(() => mutations.activate.mutateAsync({ id: version.id, version: version.version }))} onTransition={(version, action) => void perform(() => mutations.transition.mutateAsync({ id: version.id, version: version.version, action }))} />
      </div>

      {canManage && <section aria-label="Price Book maintenance" className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Maintain category</CardTitle><CardDescription>Renaming and grouping preserve every historical reference.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitCategoryEdit(event)}><Select aria-label="Category to maintain" value={categoryEdit.id} onChange={(event) => chooseCategory(event.target.value)} required><option value="">Choose category</option>{data?.categories.map((value) => <option key={value.id} value={value.id}>{value.name} · {value.status}</option>)}</Select><Input aria-label="Updated category name" value={categoryEdit.name} onChange={(event) => setCategoryEdit({ ...categoryEdit, name: event.target.value })} required /><Textarea aria-label="Category description" value={categoryEdit.description} onChange={(event) => setCategoryEdit({ ...categoryEdit, description: event.target.value })} /><Select aria-label="Parent category" value={categoryEdit.parent_id} onChange={(event) => setCategoryEdit({ ...categoryEdit, parent_id: event.target.value })}><option value="">Top-level category</option>{data?.categories.filter((value) => value.status === "active" && value.id !== categoryEdit.id).map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Category state" value={categoryEdit.status} onChange={(event) => setCategoryEdit({ ...categoryEdit, status: event.target.value as "active" | "archived" })}><option value="active">Active</option><option value="archived">Archived</option></Select><Button fullWidth type="submit" disabled={!categoryEdit.id} loading={mutations.updateCategory.isPending}>Save category</Button></form></CardContent></Card>
        <Card><CardHeader><CardTitle>Maintain selected service</CardTitle><CardDescription>Use “Edit item details” above; active price history remains unchanged.</CardDescription></CardHeader><CardContent>{itemEdit.id ? <form className="space-y-3" onSubmit={(event) => void submitItemEdit(event)}><Select aria-label="Updated service category" value={itemEdit.category_id} onChange={(event) => setItemEdit({ ...itemEdit, category_id: event.target.value })} required>{data?.categories.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Input aria-label="Updated service name" value={itemEdit.name} onChange={(event) => setItemEdit({ ...itemEdit, name: event.target.value })} required /><Textarea aria-label="Updated customer description" value={itemEdit.customer_description} onChange={(event) => setItemEdit({ ...itemEdit, customer_description: event.target.value })} required /><Textarea aria-label="Internal service notes" value={itemEdit.internal_description} onChange={(event) => setItemEdit({ ...itemEdit, internal_description: event.target.value })} /><Button fullWidth type="submit" loading={mutations.updateItem.isPending}>Save service details</Button></form> : <p className="text-content-muted">Choose a service and select “Edit item details.”</p>}</CardContent></Card>
      </section>}

      {canManage && <section aria-label="Price Book management" className="grid gap-4 lg:grid-cols-3">
        <Card><CardHeader><CardTitle>New category</CardTitle><CardDescription>Categories are grouped alphabetically and may have a parent.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitCategory(event)}><Input aria-label="Category code" placeholder="Code" value={category.code} onChange={(event) => setCategory({ ...category, code: event.target.value })} required /><Input aria-label="Category name" placeholder="Name" value={category.name} onChange={(event) => setCategory({ ...category, name: event.target.value })} required /><Button fullWidth type="submit" loading={mutations.category.isPending}>Create category</Button></form></CardContent></Card>
        <Card><CardHeader><CardTitle>New service item</CardTitle><CardDescription>Create the service identity before drafting its price.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitItem(event)}><Select aria-label="Service category" value={item.category_id} onChange={(event) => setItem({ ...item, category_id: event.target.value })} required><option value="">Choose category</option>{data?.categories.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Input aria-label="Service code" placeholder="Service code" value={item.code} onChange={(event) => setItem({ ...item, code: event.target.value })} required /><Input aria-label="Service name" placeholder="Service name" value={item.name} onChange={(event) => setItem({ ...item, name: event.target.value })} required /><Textarea aria-label="Customer description" placeholder="What the customer will see" value={item.customer_description} onChange={(event) => setItem({ ...item, customer_description: event.target.value })} required /><Button fullWidth type="submit" loading={mutations.item.isPending}>Create service item</Button></form></CardContent></Card>
        <Card><CardHeader><CardTitle>{draft.versionId ? "Edit draft" : "Draft price"}</CardTitle><CardDescription>Internal costs are visible only to Price Book managers.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitDraft(event)}><Select aria-label="Price service item" value={draft.itemId} onChange={(event) => setDraft({ ...draft, itemId: event.target.value, versionId: "" })} required><option value="">Choose service</option>{data?.service_items.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Tax classification" value={draft.taxId} onChange={(event) => setDraft({ ...draft, taxId: event.target.value })} required><option value="">Choose tax treatment</option>{data?.tax_classifications.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Input aria-label="Customer price" type="number" min="0" step="0.0001" value={draft.price} onChange={(event) => setDraft({ ...draft, price: event.target.value })} required /><Input aria-label="Effective time" type="datetime-local" value={draft.effective} onChange={(event) => setDraft({ ...draft, effective: event.target.value })} required /><Select aria-label="Component type" value={draft.componentType} onChange={(event) => setDraft({ ...draft, componentType: event.target.value as "labor" | "material" })}><option value="labor">Labor</option><option value="material">Material</option></Select><Input aria-label="Component label" placeholder="Component description" value={draft.componentLabel} onChange={(event) => setDraft({ ...draft, componentLabel: event.target.value })} required /><div className="grid grid-cols-2 gap-2"><Input aria-label="Component quantity" type="number" min="0.0001" step="0.0001" value={draft.componentQuantity} onChange={(event) => setDraft({ ...draft, componentQuantity: event.target.value })} required /><Input aria-label="Internal unit cost" type="number" min="0" step="0.0001" value={draft.componentCost} onChange={(event) => setDraft({ ...draft, componentCost: event.target.value })} /></div><Button fullWidth type="submit" loading={mutations.version.isPending || mutations.updateVersion.isPending}>{draft.versionId ? "Save draft changes" : "Create draft"}</Button></form></CardContent></Card>
      </section>}
      {canManage && <section aria-label="Price Book configuration" className="grid gap-4 lg:grid-cols-3">
        <Card><CardHeader><CardTitle>Tax classification</CardTitle><CardDescription>Create or maintain tax treatment stored with every price snapshot.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitTax(event)}><Input aria-label="Tax code" placeholder="Tax code" value={tax.code} onChange={(event) => setTax({ ...tax, code: event.target.value })} required /><Input aria-label="Tax name" placeholder="Tax name" value={tax.name} onChange={(event) => setTax({ ...tax, name: event.target.value })} required /><label className="flex min-h-11 items-center gap-3"><input type="checkbox" checked={tax.taxable} onChange={(event) => setTax({ ...tax, taxable: event.target.checked })} />Taxable</label><Button fullWidth type="submit" loading={mutations.tax.isPending}>Create tax classification</Button></form><form className="mt-5 space-y-3 border-t border-stroke pt-4" onSubmit={(event) => void submitTaxEdit(event)}><Select aria-label="Tax classification to maintain" value={taxEdit.id} onChange={(event) => chooseTax(event.target.value)} required><option value="">Choose existing classification</option>{data?.tax_classifications.map((value) => <option key={value.id} value={value.id}>{value.name} · {value.status}</option>)}</Select><Input aria-label="Updated tax name" value={taxEdit.name} onChange={(event) => setTaxEdit({ ...taxEdit, name: event.target.value })} required /><label className="flex min-h-11 items-center gap-3"><input aria-label="Updated taxable state" type="checkbox" checked={taxEdit.taxable} onChange={(event) => setTaxEdit({ ...taxEdit, taxable: event.target.checked })} />Taxable</label><Select aria-label="Tax classification state" value={taxEdit.status} onChange={(event) => setTaxEdit({ ...taxEdit, status: event.target.value as "active" | "inactive" | "archived" })}><option value="active">Active</option><option value="inactive">Inactive</option><option value="archived">Archived</option></Select><Button fullWidth type="submit" disabled={!taxEdit.id} loading={mutations.updateTax.isPending}>Save tax classification</Button></form></CardContent></Card>
        <Card><CardHeader><CardTitle>Customer option group</CardTitle><CardDescription>Set required and maximum customer selections.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitOptionGroup(event)}><Input aria-label="Option group code" placeholder="Group code" value={optionGroup.code} onChange={(event) => setOptionGroup({ ...optionGroup, code: event.target.value })} required /><Input aria-label="Option group name" placeholder="Group name" value={optionGroup.name} onChange={(event) => setOptionGroup({ ...optionGroup, name: event.target.value })} required /><div className="grid grid-cols-2 gap-2"><Input aria-label="Minimum selections" type="number" min="0" value={optionGroup.minimum_selections} onChange={(event) => setOptionGroup({ ...optionGroup, minimum_selections: Number(event.target.value) })} required /><Input aria-label="Maximum selections" type="number" min="1" value={optionGroup.maximum_selections} onChange={(event) => setOptionGroup({ ...optionGroup, maximum_selections: Number(event.target.value) })} required /></div><Button fullWidth type="submit" loading={mutations.optionGroup.isPending}>Create option group</Button></form></CardContent></Card>
        <Card><CardHeader><CardTitle>Add customer option</CardTitle><CardDescription>Connect an existing service to a customer-visible choice.</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => void submitOption(event)}><Select aria-label="Option group" value={option.groupId} onChange={(event) => setOption({ ...option, groupId: event.target.value })} required><option value="">Choose group</option>{data?.option_groups.filter((value) => value.status === "active").map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Select aria-label="Option service item" value={option.serviceItemId} onChange={(event) => setOption({ ...option, serviceItemId: event.target.value })} required><option value="">Choose service</option>{data?.service_items.map((value) => <option key={value.id} value={value.id}>{value.name}</option>)}</Select><Input aria-label="Option label" placeholder="Customer label" value={option.label} onChange={(event) => setOption({ ...option, label: event.target.value })} required /><Input aria-label="Option position" type="number" min="1" value={option.position} onChange={(event) => setOption({ ...option, position: event.target.value })} required /><Button fullWidth type="submit" loading={mutations.option.isPending}>Add option</Button></form></CardContent></Card>
      </section>}
    </>}
  </div>;
}

function ServiceDetail({ item, versions, currentVersion, canManage, canActivate, onEditItem, onEditDraft, onActivate, onTransition }: { item?: PriceBookServiceItem; versions: PriceBookVersion[]; currentVersion?: PriceBookVersion; canManage: boolean; canActivate: boolean; onEditItem: (item: PriceBookServiceItem) => void; onEditDraft: (version: PriceBookVersion) => void; onActivate: (version: PriceBookVersion) => void; onTransition: (version: PriceBookVersion, action: "inactivate" | "archive") => void }) {
  if (!item) return <Card><CardHeader><CardTitle>Item detail</CardTitle></CardHeader><CardContent><p className="text-content-muted">No services match these filters.</p></CardContent></Card>;
  return <Card><CardHeader><CardTitle>{item.name}</CardTitle><CardDescription>{item.code} · {item.branch_id ? "Branch price" : "Company-wide price"}</CardDescription></CardHeader><CardContent className="space-y-5">
    <div><h3 className="font-semibold">Customer description</h3><p className="mt-1 text-content-muted">{item.customer_description}</p>{canManage && item.internal_description && <><h3 className="mt-3 font-semibold">Internal notes</h3><p className="mt-1 text-content-muted">{item.internal_description}</p></>}{canManage && <Button className="mt-3" onClick={() => onEditItem(item)}>Edit item details</Button>}</div>
    <div className="rounded-lg border border-stroke p-4"><p className="text-sm font-medium text-content-muted">Current active version</p>{currentVersion ? <p className="mt-1 text-lg font-semibold">{currentVersion.currency} {currentVersion.unit_price} · effective {new Date(currentVersion.effective_at).toLocaleDateString()}</p> : <p className="mt-1">No active price</p>}</div>
    <div><h3 className="font-semibold">Draft and version history</h3><div className="mt-2 space-y-2">{versions.map((version) => <div key={version.id} className="rounded-md bg-surface-muted p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span>Revision {version.revision} · {version.currency} {version.unit_price}</span><Badge variant={version.status === "active" ? "success" : "neutral"}>{version.status}</Badge></div><p className="mt-1 text-sm text-content-muted">Effective {new Date(version.effective_at).toLocaleString()}{version.expires_at ? ` until ${new Date(version.expires_at).toLocaleString()}` : ""}</p><div className="mt-2 flex flex-wrap gap-2">{canManage && version.status === "draft" && <Button onClick={() => onEditDraft(version)}>Edit draft</Button>}{canActivate && version.status === "draft" && <Button onClick={() => onActivate(version)}>Review and activate</Button>}{canActivate && version.status === "active" && <Button onClick={() => onTransition(version, "inactivate")}>Inactivate version</Button>}{canActivate && ["draft", "inactive", "superseded"].includes(version.status) && <Button onClick={() => onTransition(version, "archive")}>Archive version</Button>}</div></div>)}</div></div>
  </CardContent></Card>;
}
