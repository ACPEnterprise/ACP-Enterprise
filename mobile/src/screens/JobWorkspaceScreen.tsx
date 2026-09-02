import { useState } from "react";
import { Linking, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import type { DayAssignment, EmployeeOperationsService } from "../api/employeeOperations";
import { fieldIdempotencyKey, type FieldService } from "../api/fieldService";
import { colors, spacing } from "../design/tokens";
import { useAssignmentDetail } from "../myDay/useAssignmentDetail";
import type { NetworkMonitor } from "../network/networkMonitor";
import { useFieldWorkspace } from "../field/useFieldWorkspace";
import { PrimaryButton } from "../components/PrimaryButton";
import { useFieldContext } from "../field/useFieldContext";

function lifecycleAction(status: string | null) {
  if (status === "active") return { action: "start" as const, label: "Start Work" };
  if (status === "in_progress") return { action: "pause" as const, label: "Pause Work" };
  if (status === "paused") return { action: "resume" as const, label: "Resume Work" };
  return null;
}

function formatWindow(value: string, timezone: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(new Date(value));
}

function locationLines(assignment: DayAssignment) {
  const location = assignment.service_location;
  return [location.label, location.address_line_1, location.address_line_2, `${location.city}, ${location.state} ${location.postal_code}`, location.country === "US" ? null : location.country].filter(Boolean);
}

export function directionsUrl(assignment: DayAssignment, platform: "ios" | "android" = Platform.OS === "ios" ? "ios" : "android") {
  const address = locationLines(assignment).join(", ");
  const destination = encodeURIComponent(address);
  return platform === "ios" ? `https://maps.apple.com/?daddr=${destination}` : `geo:0,0?q=${destination}`;
}

function Detail({ assignment, timezone, stale, onDirections }: { assignment: DayAssignment; timezone: string; stale: boolean; onDirections(): void }) {
  return <View accessible accessibilityLabel={`${stale ? "Stale assignment detail" : "Authoritative assignment detail"}, ${assignment.customer_display_name}, ${assignment.appointment_status}, ${assignment.assignment_role}`} style={styles.detail}>
    <Text style={styles.kicker}>{stale ? "LAST CONFIRMED — STALE" : "ASSIGNED WORK"}</Text>
    <Text accessibilityRole="header" style={styles.customer}>{assignment.customer_display_name}</Text>
    <Text style={styles.window}>{formatWindow(assignment.window_start_at, timezone)} – {formatWindow(assignment.window_end_at, timezone)}</Text>
    <View style={styles.section}><Text style={styles.sectionTitle}>Service location</Text>{locationLines(assignment).map((line, index) => <Text key={`${index}-${line}`} style={styles.line}>{line}</Text>)}<Pressable accessibilityRole="link" accessibilityLabel={`Open directions to ${assignment.service_location.label}`} onPress={onDirections} style={styles.directions}><Text style={styles.directionsText}>Open Directions</Text></Pressable></View>
    {assignment.service_category && <View style={styles.section}><Text style={styles.sectionTitle}>Service category</Text><Text style={styles.line}>{assignment.service_category}</Text></View>}
    <View style={styles.section}><Text style={styles.sectionTitle}>Assignment</Text><Text style={styles.line}>Appointment {assignment.appointment_number}</Text><Text style={styles.line}>Appointment status: {assignment.appointment_status}</Text>{assignment.job_number && <Text style={styles.line}>Job {assignment.job_number}</Text>}{assignment.job_status && <Text style={styles.line}>Job status: {assignment.job_status}</Text>}<Text style={styles.line}>{assignment.assignment_role === "primary" ? "Primary assignment" : "Crew assignment"} · {assignment.assignment_status}</Text></View>
  </View>;
}

export function JobWorkspaceScreen({ appointmentId, initialAssignment, initialTimezone, businessDate, service, fieldService, network, canReadField = false, canExecuteField = false, canReadAssets = false, canReadEstimates = false }: { appointmentId: string; initialAssignment: DayAssignment | null; initialTimezone: string; businessDate?: string; service: EmployeeOperationsService; fieldService: FieldService; network: NetworkMonitor; canReadField?: boolean; canExecuteField?: boolean; canReadAssets?: boolean; canReadEstimates?: boolean }) {
  const detail = useAssignmentDetail(service, network, appointmentId, initialAssignment);
  const [directionsError, setDirectionsError] = useState(false);
  const [summary, setSummary] = useState("");
  const timezone = detail.timezone ?? initialTimezone;
  const serviceDate = businessDate ?? detail.assignment?.window_start_at.slice(0, 10) ?? initialAssignment?.window_start_at.slice(0, 10) ?? new Date().toISOString().slice(0, 10);
  const field = useFieldWorkspace(fieldService, network, appointmentId, detail.assignment?.job_id ?? initialAssignment?.job_id ?? null, serviceDate, canReadField);
  const context = useFieldContext(fieldService, network, detail.assignment?.job_id ?? initialAssignment?.job_id ?? null, canReadAssets, canReadEstimates);
  const stale = (detail.status === "offline" || detail.status === "error") && detail.assignment !== null;
  const message = detail.status === "not_authorized" ? "You are not authorized to view this assignment."
    : detail.status === "identity_not_ready" ? "Your employee account is not ready for assigned work."
    : detail.status === "session_expired" ? "Your session has expired. Please sign in again."
    : detail.status === "not_available" ? "This assignment is no longer available in your authoritative My Day."
    : detail.status === "offline" ? (stale ? "You're offline. This detail is last confirmed and may be stale." : "You're offline. Connect to confirm this assignment.")
    : detail.status === "error" ? (stale ? "Unable to refresh. This detail is last confirmed and may be stale." : "Unable to load this assignment. Check your connection and try again.")
    : null;
  async function openDirections() {
    if (!detail.assignment) return;
    const url = directionsUrl(detail.assignment);
    setDirectionsError(false);
    try {
      if (!(await Linking.canOpenURL(url))) throw new Error("No map application");
      await Linking.openURL(url);
    } catch {
      setDirectionsError(true);
    }
  }
  return <ScrollView testID="job-workspace-scroll" style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={detail.status === "loading" || detail.refreshing} onRefresh={() => void detail.refresh()} accessibilityLabel="Refresh authoritative Job workspace" />}>
    <Text accessibilityRole="header" style={styles.title}>Job Workspace</Text>
    <Text style={styles.readOnly}>{canExecuteField ? "Authorized field evidence. Job status and My Time remain independent." : "Read-only assigned work. Job status and My Time remain independent."}</Text>
    {directionsError && <Text accessibilityRole="alert" style={styles.message}>Directions are unavailable on this device. The service address remains shown below.</Text>}
    {message && <Text accessibilityRole="alert" style={stale ? styles.stale : styles.message}>{message}</Text>}
    {detail.status === "loading" && !detail.assignment && <Text accessibilityLabel="Loading authoritative assignment detail">Loading assignment…</Text>}
    {detail.assignment && <Detail assignment={detail.assignment} timezone={timezone} stale={stale} onDirections={() => void openDirections()} />}
    {canReadField && detail.assignment?.job_id && <View style={styles.detail} accessible accessibilityLabel="Authoritative field workflow">
      <Text style={styles.sectionTitle}>Field workflow</Text>
      {field.status === "loading" && <Text>Refreshing authoritative field state…</Text>}
      {field.status === "offline" && <Text accessibilityRole="alert" style={styles.stale}>You're offline. Field actions are disabled; displayed state may be stale.</Text>}
      {field.status === "forbidden" && <Text accessibilityRole="alert">This assignment is no longer available for field execution.</Text>}
      {(field.status === "conflict" || field.status === "error") && <Text accessibilityRole="alert">Field state changed or could not be confirmed. It has been refreshed before another action.</Text>}
      {field.item && <><Text>Travel status: {field.item.arrival_state.replaceAll("_", " ")}</Text><Text>Assignment: {field.item.assignment_status}</Text></>}
      {field.job && <><Text>Work summary: {field.job.work_summary_recorded ? "Recorded" : "Required"}</Text><Text>Customer disposition: {field.job.customer_disposition ?? "Not recorded"}</Text><Text>Completion readiness: {field.job.completion_ready ? "Ready" : `Blocked — ${field.job.missing_requirements.join(", ") || "requirements pending"}`}</Text><Text>Invoice handoff: {field.job.invoice_handoff_status ?? "Not available"}</Text></>}
      {canExecuteField && field.item && field.item.job_id && field.item.job_version && <View style={styles.section}>
        {field.item.arrival_state === "pending" && <PrimaryButton label="Begin Travel" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.arrival(appointmentId, "en_route", field.item!.assignment_version))} />}
        {field.item.arrival_state === "en_route" && <PrimaryButton label="Mark Arrived" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.arrival(appointmentId, "arrived", field.item!.assignment_version))} />}
        {field.item.arrival_state === "arrived" && lifecycleAction(field.item.job_status) && <PrimaryButton label={lifecycleAction(field.item.job_status)!.label} disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.transition(field.item!.job_id!, lifecycleAction(field.item!.job_status)!.action, field.item!.job_version!))} />}
        {field.job?.completion_ready && field.item.job_status === "in_progress" && <PrimaryButton label="Complete Work" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.transition(field.item!.job_id!, "complete", field.item!.job_version!))} />}
        <Text style={styles.sectionTitle}>Work performed</Text><TextInput accessibilityLabel="Work performed summary" multiline value={summary} onChangeText={setSummary} editable={field.status === "ready"} style={styles.input} placeholder="Describe completed work" />
        <PrimaryButton label="Save Work Summary" disabled={!summary.trim() || field.status !== "ready"} onPress={() => void field.mutate(async () => { await fieldService.workSummary(field.item!.job_id!, summary.trim(), field.item!.job_version!, field.item!.assignment_version, fieldIdempotencyKey("work-summary")); setSummary(""); })} />
        <Text style={styles.sectionTitle}>Customer work approval</Text><PrimaryButton label="Customer Approved Work" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.customerDisposition(field.item!.job_id!, "approved", null, null, field.item!.job_version!, field.item!.assignment_version, fieldIdempotencyKey("approval-approved")))} /><PrimaryButton label="Customer Unavailable" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.customerDisposition(field.item!.job_id!, "unavailable", null, null, field.item!.job_version!, field.item!.assignment_version, fieldIdempotencyKey("approval-unavailable")))} /><PrimaryButton label="Customer Refused" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.customerDisposition(field.item!.job_id!, "refused", null, null, field.item!.job_version!, field.item!.assignment_version, fieldIdempotencyKey("approval-refused")))} />
        <PrimaryButton label="Refresh Invoice Handoff" disabled={field.status !== "ready"} onPress={() => void field.mutate(() => fieldService.refreshHandoff(field.item!.job_id!, field.item!.job_version!, field.item!.assignment_version))} />
        <Text style={styles.readOnly}>Every field action is reconciled from authoritative Job and assignment state. Job actions never create a Timekeeping punch.</Text>
      </View>}
      {(canReadAssets || canReadEstimates) && <View style={styles.section} accessible accessibilityLabel="Assignment scoped field context">
        <Text style={styles.sectionTitle}>Field context</Text>
        {context.status === "loading" && <Text>Refreshing latest field context…</Text>}
        {context.status === "stale" && <Text accessibilityRole="alert" style={styles.stale}>LAST CONFIRMED — STALE. Actions requiring current context remain unavailable.</Text>}
        {context.status === "offline" && <Text accessibilityRole="alert">Equipment and Estimate information are unavailable offline until first confirmed.</Text>}
        {context.status === "denied" && <Text accessibilityRole="alert">Permission or assignment changed. Field context is no longer available.</Text>}
        {context.status === "unavailable" && <Text accessibilityRole="alert">Equipment or Estimate information is unavailable. Pull to refresh when connected.</Text>}
        {canReadAssets && context.equipment && <View accessibilityLabel="Assigned Job equipment">
          <Text style={styles.sectionTitle}>Equipment</Text>
          {context.equipment.items.length === 0 ? <Text style={styles.line}>No equipment is explicitly related to this Job.</Text> : context.equipment.items.map((asset) => <View key={asset.asset_id} style={styles.contextCard}><Text style={styles.sectionTitle}>{asset.display_name}</Text><Text style={styles.line}>{[asset.manufacturer, asset.model].filter(Boolean).join(" · ") || "Equipment details unavailable"}</Text><Text style={styles.line}>Status: {asset.lifecycle}</Text><Text style={styles.line}>Installed: {asset.installation_state ?? "Evidence unavailable"}</Text><Text style={styles.line}>Warranty: {asset.warranty_state ?? "Evidence unavailable — coverage not determined"}</Text><Text style={styles.line}>Service history: {asset.service_history.length} of {context.equipment?.history_limit ?? 10} bounded records</Text><Text style={styles.line}>Protected evidence: {asset.evidence.some((item) => item.protected_document_available) ? "Available through protected server authority" : "None confirmed"}</Text></View>)}
          <Text style={styles.readOnly}>Photo/document upload: SOURCE_REQUIRED. No device file is published or retried.</Text>
        </View>}
        {canReadAssets && context.readiness && <View><Text style={styles.sectionTitle}>My field readiness</Text><Text style={styles.line}>Workforce profile: {context.readiness.workforce_profile_available ? "Available" : "Not configured"}</Text><Text style={styles.line}>Branch eligibility: {context.readiness.branch_eligible ? "Confirmed" : "Not confirmed"}</Text><Text style={styles.line}>Availability: {context.readiness.availability_state ?? "No current evidence"}</Text>{context.readiness.fleet.map((asset) => <Text key={asset.asset_id} style={styles.line}>{asset.display_name}: {asset.out_of_service ? "Out of service" : asset.readiness_state ?? "Readiness unavailable"}; inspection {asset.inspection_state ?? "unavailable"}; maintenance {asset.maintenance_state ?? "unavailable"}</Text>)}<Text style={styles.readOnly}>Inspection interaction: POLICY_REQUIRED.</Text></View>}
        {canReadEstimates && context.estimate && <View accessibilityLabel="Assigned Job Estimate presentation"><Text style={styles.sectionTitle}>Estimate</Text>{!context.estimate.available ? <Text style={styles.line}>No current issued Estimate is related to this Job.</Text> : <><Text style={styles.line}>{context.estimate.estimate_number} · {context.estimate.estimate_status}</Text><Text style={styles.line}>{context.estimate.proposal_title}</Text>{context.estimate.lines.map((line) => <Text key={line.position} style={styles.line}>{line.title}: {line.line_total.toFixed(2)} {line.currency}</Text>)}<Text style={styles.line}>Total: {context.estimate.total_amount?.toFixed(2)} {context.estimate.currency}</Text><Text style={styles.line}>Customer decision: {context.estimate.acceptance_status}</Text><Text style={styles.readOnly}>Presentation is revision {context.estimate.revision_number}; Mobile cannot rewrite it. Delivery remains server-authority required.</Text></>}</View>}
      </View>}
      <View style={styles.section} accessible accessibilityLabel="Additional field capability readiness">
        <Text style={styles.sectionTitle}>Additional field tools</Text>
        <Text style={styles.line}>Customer messages: sent only by ACP Enterprise when enabled</Text>
        <Text style={styles.line}>Notifications and push delivery: source/provider required</Text>
        <Text style={styles.line}>Payment collection: not authorized in ACP Employee</Text>
      </View>
    </View>}
  </ScrollView>;
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, readOnly: { color: colors.muted, fontSize: 15, lineHeight: 22 }, message: { color: colors.text, fontSize: 16 }, stale: { color: colors.warning, fontWeight: "700", fontSize: 16, backgroundColor: "#FFF7D6", borderRadius: 12, padding: spacing.md }, detail: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.lg, gap: spacing.md }, contextCard: { borderColor: colors.border, borderWidth: 1, borderRadius: 10, padding: spacing.md, gap: spacing.sm, marginVertical: spacing.sm }, kicker: { fontSize: 13, fontWeight: "800", color: colors.brandDark }, customer: { fontSize: 24, fontWeight: "800", color: colors.text }, window: { fontSize: 17, fontWeight: "700", color: colors.brandDark }, section: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.md, gap: spacing.sm }, sectionTitle: { fontSize: 17, fontWeight: "700", color: colors.text }, line: { fontSize: 16, lineHeight: 23, color: colors.text }, input: { minHeight: 100, borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: spacing.md, fontSize: 16, textAlignVertical: "top", color: colors.text, backgroundColor: colors.surface }, directions: { alignItems: "center", alignSelf: "flex-start", borderColor: colors.brand, borderRadius: 10, borderWidth: 1, justifyContent: "center", minHeight: 48, marginTop: spacing.sm, paddingHorizontal: spacing.md }, directionsText: { color: colors.brand, fontSize: 16, fontWeight: "700" } });
