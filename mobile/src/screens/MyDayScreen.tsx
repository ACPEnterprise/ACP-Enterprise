import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import type { DayAssignment, EmployeeOperationsService } from "../api/employeeOperations";
import { colors, spacing } from "../design/tokens";
import type { NetworkMonitor } from "../network/networkMonitor";
import { useMyDay } from "../myDay/useMyDay";

function formatWindow(value: string, timezone: string) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: timezone }).format(new Date(value));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeZone: "UTC" }).format(new Date(`${value}T12:00:00Z`));
}

function address(assignment: DayAssignment) {
  const location = assignment.service_location;
  return [location.address_line_1, location.address_line_2, `${location.city}, ${location.state} ${location.postal_code}`, location.country === "US" ? null : location.country].filter(Boolean).join(", ");
}

function AssignmentCard({ assignment, timezone, stale }: { assignment: DayAssignment; timezone: string; stale: boolean }) {
  const identity = assignment.job_number ? `Job ${assignment.job_number}` : `Appointment ${assignment.appointment_number}`;
  return <View accessible accessibilityLabel={`${stale ? "Stale assignment" : "Assignment"}, ${formatWindow(assignment.window_start_at, timezone)} to ${formatWindow(assignment.window_end_at, timezone)}, ${assignment.customer_display_name}, ${address(assignment)}, ${assignment.appointment_status}, ${assignment.assignment_role}`} style={styles.card}>
    <Text style={styles.window}>{formatWindow(assignment.window_start_at, timezone)} – {formatWindow(assignment.window_end_at, timezone)}</Text>
    <Text style={styles.customer}>{assignment.customer_display_name}</Text>
    <Text style={styles.address}>{address(assignment)}</Text>
    {assignment.service_category && <Text style={styles.category}>{assignment.service_category}</Text>}
    <View style={styles.metadata}>
      <Text>{identity}</Text>
      <Text>{assignment.appointment_status} · {assignment.assignment_role === "primary" ? "Primary assignment" : "Crew assignment"}</Text>
      {assignment.job_status && <Text>Job status: {assignment.job_status}</Text>}
    </View>
  </View>;
}

export function MyDayScreen({ service, network }: { service: EmployeeOperationsService; network: NetworkMonitor }) {
  const myDay = useMyDay(service, network);
  const stale = (myDay.status === "offline" || myDay.status === "error") && myDay.day !== null;
  const message = myDay.status === "not_authorized" ? "My Day is not available for your account."
    : myDay.status === "identity_not_ready" ? "Your employee account is not ready for assigned work."
    : myDay.status === "session_expired" ? "Your session has expired. Please sign in again."
    : myDay.status === "offline" ? (stale ? "You're offline. These assignments are last confirmed and may be stale." : "You're offline. Connect to load your assigned work.")
    : myDay.status === "error" ? (stale ? "Unable to refresh My Day. These assignments are last confirmed and may be stale." : "Unable to load My Day. Check your connection and try again.")
    : null;
  return <ScrollView testID="my-day-scroll" style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl testID="my-day-refresh" refreshing={myDay.status === "loading" || myDay.refreshing} onRefresh={() => void myDay.refresh()} accessibilityLabel="Refresh authoritative assigned work" />}>
    <Text accessibilityRole="header" style={styles.title}>My Day</Text>
    {myDay.day && <><Text style={styles.date}>{formatDate(myDay.day.business_date)}</Text><Text style={styles.timezone}>Schedule times shown in {myDay.day.timezone}</Text></>}
    {message && <Text accessibilityRole="alert" style={stale ? styles.stale : styles.message}>{message}</Text>}
    {myDay.status === "loading" && !myDay.day && <Text accessibilityLabel="Loading authoritative assigned work">Loading assigned work…</Text>}
    {myDay.status === "empty" && <View accessible accessibilityLabel="No assigned work today" style={styles.empty}><Text style={styles.emptyTitle}>Your day is clear</Text><Text>No work is currently assigned to you today.</Text></View>}
    {myDay.day?.assignments.map((assignment) => <AssignmentCard key={assignment.appointment_id} assignment={assignment} timezone={myDay.day!.timezone} stale={stale} />)}
  </ScrollView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
  title: { fontSize: 30, fontWeight: "800", color: colors.text }, date: { fontSize: 20, fontWeight: "700", color: colors.text }, timezone: { fontSize: 14, color: colors.muted },
  message: { fontSize: 16, color: colors.text }, stale: { fontSize: 16, color: colors.warning, fontWeight: "700", backgroundColor: "#FFF7D6", padding: spacing.md, borderRadius: 12 },
  empty: { backgroundColor: colors.surface, borderRadius: 14, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border }, emptyTitle: { fontSize: 22, fontWeight: "700", color: colors.text },
  card: { backgroundColor: colors.surface, borderRadius: 14, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  window: { color: colors.brandDark, fontSize: 18, fontWeight: "800" }, customer: { color: colors.text, fontSize: 21, fontWeight: "700" }, address: { color: colors.text, fontSize: 16, lineHeight: 23 }, category: { color: colors.brandDark, fontSize: 16, fontWeight: "600" }, metadata: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm, gap: spacing.xs },
});
