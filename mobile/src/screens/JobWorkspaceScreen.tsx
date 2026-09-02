import { useState } from "react";
import { Linking, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import type { DayAssignment, EmployeeOperationsService } from "../api/employeeOperations";
import { colors, spacing } from "../design/tokens";
import { useAssignmentDetail } from "../myDay/useAssignmentDetail";
import type { NetworkMonitor } from "../network/networkMonitor";
import type { FieldService, JobAction } from "../api/fieldService";
import { useFieldJob } from "../field/useFieldJob";
import { PrimaryButton } from "../components/PrimaryButton";

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

function actionFor(status: string | null): { action: JobAction; label: string } | null {
  if (status === "active") return { action: "start", label: "Start Work" };
  if (status === "in_progress") return { action: "pause", label: "Pause Work" };
  if (status === "paused") return { action: "resume", label: "Resume Work" };
  return null;
}

export function JobWorkspaceScreen({ appointmentId, businessDate, initialAssignment, initialTimezone, service, fieldService, network, canExecute }: { appointmentId: string; businessDate: string; initialAssignment: DayAssignment | null; initialTimezone: string; service: EmployeeOperationsService; fieldService: FieldService; network: NetworkMonitor; canExecute: boolean }) {
  const detail = useAssignmentDetail(service, network, appointmentId, initialAssignment);
  const field = useFieldJob(fieldService, network, businessDate, appointmentId, initialAssignment?.job_id ?? null);
  const [directionsError, setDirectionsError] = useState(false);
  const [summary, setSummary] = useState(""); const [customerName, setCustomerName] = useState(""); const [dispositionReason, setDispositionReason] = useState("");
  const timezone = detail.timezone ?? initialTimezone;
  const stale = (detail.status === "offline" || detail.status === "error") && detail.assignment !== null;
  const fieldStale = field.status !== "live";
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
    <Text style={styles.readOnly}>Read-only assigned work. Job status and My Time remain independent.</Text>
    {directionsError && <Text accessibilityRole="alert" style={styles.message}>Directions are unavailable on this device. The service address remains shown below.</Text>}
    {message && <Text accessibilityRole="alert" style={stale ? styles.stale : styles.message}>{message}</Text>}
    {detail.status === "loading" && !detail.assignment && <Text accessibilityLabel="Loading authoritative assignment detail">Loading assignment…</Text>}
    {detail.assignment && <Detail assignment={detail.assignment} timezone={timezone} stale={stale} onDirections={() => void openDirections()} />}
    {detail.assignment?.job_id && <View style={styles.detail}>
      <Text accessibilityRole="header" style={styles.sectionTitle}>Field status</Text>
      <Text style={styles.kicker}>{field.status === "live" ? "LIVE — SERVER CONFIRMED" : field.status === "mutation_uncertain" ? "MUTATION OUTCOME UNCERTAIN" : "LAST CONFIRMED — STALE"}</Text>
      {field.message && <Text accessibilityRole="alert" style={fieldStale ? styles.stale : styles.message}>{field.message}</Text>}
      {field.item && <><Text style={styles.line}>Dispatch: {field.item.assignment_status}</Text><Text style={styles.line}>Travel: {field.item.arrival_state.replaceAll("_", " ")}</Text><Text style={styles.line}>Job: {field.item.job_status ?? "not available"}</Text></>}
      {!canExecute && <Text style={styles.readOnly}>Read-only: your effective permissions do not allow field mutations.</Text>}
      {canExecute && field.mutationsAllowed && field.item?.arrival_state !== "en_route" && field.item?.arrival_state !== "arrived" && <PrimaryButton label="On My Way" accessibilityLabel="Confirm On My Way with ACP Enterprise" onPress={() => void field.arrival("en_route")} />}
      {canExecute && field.mutationsAllowed && field.item?.arrival_state === "en_route" && <PrimaryButton label="Confirm Arrival" accessibilityLabel="Confirm arrival with ACP Enterprise" onPress={() => void field.arrival("arrived")} />}
      {canExecute && field.mutationsAllowed && field.item?.arrival_state === "arrived" && actionFor(field.item.job_status) && <PrimaryButton label={actionFor(field.item.job_status)!.label} onPress={() => void field.transition(actionFor(field.item!.job_status)!.action)} />}
      {canExecute && field.mutationsAllowed && field.item?.job_status === "in_progress" && field.field?.completion_ready && <PrimaryButton label="Complete Work" accessibilityLabel="Complete Job after confirmed requirements" onPress={() => void field.transition("complete")} />}
      {canExecute && field.mutationsAllowed && field.field && !field.field.work_summary_recorded && <View style={styles.section}><Text style={styles.sectionTitle}>Work performed</Text><TextInput accessibilityLabel="Work performed summary" multiline value={summary} onChangeText={setSummary} placeholder="Summarize completed work" style={styles.input} /><PrimaryButton label="Record Work Summary" disabled={!summary.trim()} onPress={() => void field.workSummary(summary)} /></View>}
      {canExecute && field.mutationsAllowed && field.field && !field.field.customer_disposition && <View style={styles.section}><Text style={styles.sectionTitle}>Customer disposition</Text><TextInput accessibilityLabel="Customer name for approval" value={customerName} onChangeText={setCustomerName} placeholder="Customer name for approval" style={styles.input} /><PrimaryButton label="Record Customer Approval" disabled={!customerName.trim()} onPress={() => void field.customerDisposition("approved", customerName.trim(), null)} /><TextInput accessibilityLabel="Reason customer approval unavailable" multiline value={dispositionReason} onChangeText={setDispositionReason} placeholder="Reason unavailable or refused" style={styles.input} /><PrimaryButton label="Customer Unavailable" disabled={!dispositionReason.trim()} onPress={() => void field.customerDisposition("unavailable", null, dispositionReason.trim())} /></View>}
      {field.field && <View style={styles.section}><Text style={styles.sectionTitle}>Completion readiness</Text><Text style={styles.line}>{field.field.completion_ready ? "Ready for completion" : "Blocked by authoritative requirements"}</Text>{field.field.missing_requirements.map((value) => <Text key={value} style={styles.line}>• {value.replaceAll("_", " ")}</Text>)}<Text style={styles.line}>Estimate/commercial authority: {field.field.commercial_authorization.replaceAll("_", " ")}</Text><Text style={styles.line}>Invoice handoff: {field.field.invoice_handoff_status ?? "not ready"}</Text></View>}
      <View style={styles.section}><Text style={styles.sectionTitle}>Field product sources</Text><Text style={styles.line}>Photos and documents: SOURCE_REQUIRED</Text><Text style={styles.line}>Installed equipment: SOURCE_REQUIRED for assignment-scoped Customer equipment</Text><Text style={styles.line}>Estimate presentation: SOURCE_REQUIRED for assignment-scoped read contract</Text><Text style={styles.line}>Payment collection: NOT AUTHORIZED</Text><Text style={styles.line}>Customer communication is server-owned; Mobile never sends arbitrary messages.</Text></View>
      <Text style={styles.readOnly}>Job status and My Time are separate authorities. Field actions never clock you in or out.</Text>
    </View>}
  </ScrollView>;
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, readOnly: { color: colors.muted, fontSize: 15, lineHeight: 22 }, message: { color: colors.text, fontSize: 16 }, stale: { color: colors.warning, fontWeight: "700", fontSize: 16, backgroundColor: "#FFF7D6", borderRadius: 12, padding: spacing.md }, detail: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.lg, gap: spacing.md }, kicker: { fontSize: 13, fontWeight: "800", color: colors.brandDark }, customer: { fontSize: 24, fontWeight: "800", color: colors.text }, window: { fontSize: 17, fontWeight: "700", color: colors.brandDark }, section: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.md, gap: spacing.sm }, sectionTitle: { fontSize: 17, fontWeight: "700", color: colors.text }, line: { fontSize: 16, lineHeight: 23, color: colors.text }, input: { minHeight: 52, borderWidth: 1, borderColor: colors.border, borderRadius: 10, padding: spacing.md, fontSize: 16, color: colors.text, backgroundColor: colors.canvas }, directions: { alignItems: "center", alignSelf: "flex-start", borderColor: colors.brand, borderRadius: 10, borderWidth: 1, justifyContent: "center", minHeight: 48, marginTop: spacing.sm, paddingHorizontal: spacing.md }, directionsText: { color: colors.brand, fontSize: 16, fontWeight: "700" } });
