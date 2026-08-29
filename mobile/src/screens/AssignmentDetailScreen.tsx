import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import type { DayAssignment, EmployeeOperationsService } from "../api/employeeOperations";
import { colors, spacing } from "../design/tokens";
import { useAssignmentDetail } from "../myDay/useAssignmentDetail";
import type { NetworkMonitor } from "../network/networkMonitor";

function formatWindow(value: string, timezone: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(new Date(value));
}

function locationLines(assignment: DayAssignment) {
  const location = assignment.service_location;
  return [location.label, location.address_line_1, location.address_line_2, `${location.city}, ${location.state} ${location.postal_code}`, location.country === "US" ? null : location.country].filter(Boolean);
}

function Detail({ assignment, timezone, stale }: { assignment: DayAssignment; timezone: string; stale: boolean }) {
  return <View accessible accessibilityLabel={`${stale ? "Stale assignment detail" : "Authoritative assignment detail"}, ${assignment.customer_display_name}, ${assignment.appointment_status}, ${assignment.assignment_role}`} style={styles.detail}>
    <Text style={styles.kicker}>{stale ? "LAST CONFIRMED — STALE" : "ASSIGNED WORK"}</Text>
    <Text accessibilityRole="header" style={styles.customer}>{assignment.customer_display_name}</Text>
    <Text style={styles.window}>{formatWindow(assignment.window_start_at, timezone)} – {formatWindow(assignment.window_end_at, timezone)}</Text>
    <View style={styles.section}><Text style={styles.sectionTitle}>Service location</Text>{locationLines(assignment).map((line, index) => <Text key={`${index}-${line}`} style={styles.line}>{line}</Text>)}</View>
    {assignment.service_category && <View style={styles.section}><Text style={styles.sectionTitle}>Service category</Text><Text style={styles.line}>{assignment.service_category}</Text></View>}
    <View style={styles.section}><Text style={styles.sectionTitle}>Assignment</Text><Text style={styles.line}>Appointment {assignment.appointment_number}</Text><Text style={styles.line}>Appointment status: {assignment.appointment_status}</Text>{assignment.job_number && <Text style={styles.line}>Job {assignment.job_number}</Text>}{assignment.job_status && <Text style={styles.line}>Job status: {assignment.job_status}</Text>}<Text style={styles.line}>{assignment.assignment_role === "primary" ? "Primary assignment" : "Crew assignment"} · {assignment.assignment_status}</Text></View>
  </View>;
}

export function AssignmentDetailScreen({ appointmentId, initialAssignment, initialTimezone, service, network }: { appointmentId: string; initialAssignment: DayAssignment | null; initialTimezone: string; service: EmployeeOperationsService; network: NetworkMonitor }) {
  const detail = useAssignmentDetail(service, network, appointmentId, initialAssignment);
  const timezone = detail.timezone ?? initialTimezone;
  const stale = (detail.status === "offline" || detail.status === "error") && detail.assignment !== null;
  const message = detail.status === "not_authorized" ? "You are not authorized to view this assignment."
    : detail.status === "identity_not_ready" ? "Your employee account is not ready for assigned work."
    : detail.status === "session_expired" ? "Your session has expired. Please sign in again."
    : detail.status === "not_available" ? "This assignment is no longer available in your authoritative My Day."
    : detail.status === "offline" ? (stale ? "You're offline. This detail is last confirmed and may be stale." : "You're offline. Connect to confirm this assignment.")
    : detail.status === "error" ? (stale ? "Unable to refresh. This detail is last confirmed and may be stale." : "Unable to load this assignment. Check your connection and try again.")
    : null;
  return <ScrollView testID="assignment-detail-scroll" style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={detail.status === "loading" || detail.refreshing} onRefresh={() => void detail.refresh()} accessibilityLabel="Refresh authoritative assignment detail" />}>
    <Text accessibilityRole="header" style={styles.title}>Assignment Detail</Text>
    {message && <Text accessibilityRole="alert" style={stale ? styles.stale : styles.message}>{message}</Text>}
    {detail.status === "loading" && !detail.assignment && <Text accessibilityLabel="Loading authoritative assignment detail">Loading assignment…</Text>}
    {detail.assignment && <Detail assignment={detail.assignment} timezone={timezone} stale={stale} />}
  </ScrollView>;
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, message: { color: colors.text, fontSize: 16 }, stale: { color: colors.warning, fontWeight: "700", fontSize: 16, backgroundColor: "#FFF7D6", borderRadius: 12, padding: spacing.md }, detail: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.lg, gap: spacing.md }, kicker: { fontSize: 13, fontWeight: "800", color: colors.brandDark }, customer: { fontSize: 24, fontWeight: "800", color: colors.text }, window: { fontSize: 17, fontWeight: "700", color: colors.brandDark }, section: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.md, gap: spacing.xs }, sectionTitle: { fontSize: 17, fontWeight: "700", color: colors.text }, line: { fontSize: 16, lineHeight: 23, color: colors.text } });
