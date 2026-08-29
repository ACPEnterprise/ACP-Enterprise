import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import type { PunchAction, PunchState, TimeEntry, TimekeepingService } from "../api/timekeeping";
import { PrimaryButton } from "../components/PrimaryButton";
import { colors, spacing } from "../design/tokens";
import type { NetworkMonitor } from "../network/networkMonitor";
import { useTimeclock } from "../timeclock/useTimeclock";

function labelForState(state: PunchState["state"]) { return state === "not_clocked_in" ? "Clocked out" : state === "clocked_in" ? "Clocked in" : "On break"; }
function formatServerTime(value: string | null, timezone?: string) { if (!value) return "Not available"; return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(new Date(value)); }
function duration(entry: TimeEntry) { if (entry.approved_duration_minutes !== null) return `${Math.floor(entry.approved_duration_minutes / 60)}h ${entry.approved_duration_minutes % 60}m`; if (entry.start_at && entry.end_at) return `${Math.round((Date.parse(entry.end_at) - Date.parse(entry.start_at)) / 60000)} minutes`; return "In progress"; }
function Entry({ entry }: { entry: TimeEntry }) { const manual = entry.provenance === "authorized_manual_entry"; return <View accessible accessibilityLabel={`${manual ? "Authorized manual entry" : "Employee punch"}, ${entry.work_date}, ${entry.state}`} style={styles.entry}><Text style={styles.entryTitle}>{entry.work_date}</Text><Text>{manual ? "Authorized manual entry" : "Employee punch"}</Text><Text>{formatServerTime(entry.start_at, entry.timezone)} – {formatServerTime(entry.end_at, entry.timezone)}</Text><Text>{duration(entry)} · {entry.state}</Text>{entry.supersedes_revision_id && <Text>Corrected authoritative entry</Text>}</View>; }
function Actions({ state, disabled, onPunch }: { state: PunchState["state"]; disabled: boolean; onPunch(action: PunchAction): void }) { if (state === "not_clocked_in") return <PrimaryButton label="Clock In" accessibilityLabel="Clock in using server time" disabled={disabled} onPress={() => onPunch("clock_in")} />; if (state === "on_break") return <PrimaryButton label="End Break" accessibilityLabel="End break using server time" disabled={disabled} onPress={() => onPunch("break_end")} />; return <View style={styles.actions}><PrimaryButton label="Start Break" accessibilityLabel="Start break using server time" disabled={disabled} onPress={() => onPunch("break_start")} /><PrimaryButton label="Clock Out" accessibilityLabel="Clock out using server time" disabled={disabled} onPress={() => onPunch("clock_out")} /></View>; }

export function TimeScreen({ service, network, canPunch }: { service: TimekeepingService; network: NetworkMonitor; canPunch: boolean }) {
  const clock = useTimeclock(service, network); const stale = clock.status === "offline" || clock.status === "error";
  return <ScrollView testID="time-scroll" style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={clock.status === "loading" || clock.status === "recovering"} onRefresh={() => void clock.refresh()} accessibilityLabel="Refresh authoritative time status" />}>
    <Text accessibilityRole="header" style={styles.title}>My Time</Text>
    {clock.message && <Text accessibilityRole="alert" style={styles.message}>{clock.message}</Text>}
    {!clock.punchState && clock.status === "loading" && <Text accessibilityLabel="Loading authoritative time status">Loading time status…</Text>}
    {clock.punchState && <View accessible accessibilityLabel={`Current authoritative state: ${labelForState(clock.punchState.state)}${stale ? ", stale" : ""}`} style={styles.status}><Text style={styles.kicker}>{stale ? "LAST CONFIRMED — STALE" : "CURRENT STATUS"}</Text><Text style={styles.state}>{labelForState(clock.punchState.state)}</Text><Text>Last transition: {formatServerTime(clock.punchState.occurred_at)}</Text><Text>Server checked: {formatServerTime(clock.punchState.server_observed_at)}</Text></View>}
    {clock.punchState && canPunch && <Actions state={clock.punchState.state} disabled={clock.busy || stale || clock.status !== "ready"} onPunch={(action) => void clock.punch(action)} />}
    {clock.punchState && !canPunch && <Text accessibilityRole="alert">Punch actions are not available for your account.</Text>}
    <Text accessibilityRole="header" style={styles.sectionTitle}>Current period</Text>
    {clock.timecard?.pay_period && <Text>{clock.timecard.pay_period.period_start} through {clock.timecard.pay_period.period_end} · {clock.timecard.pay_period.timezone}</Text>}
    {clock.timecard?.entries.length === 0 && <Text>No authoritative time entries are available for this period.</Text>}
    {clock.timecard?.entries.map((entry) => <Entry key={entry.revision_id} entry={entry} />)}
  </ScrollView>;
}
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, sectionTitle: { fontSize: 22, fontWeight: "700", color: colors.text, marginTop: spacing.md }, status: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 14, padding: spacing.lg, gap: spacing.sm }, kicker: { fontSize: 13, fontWeight: "700", color: colors.muted }, state: { fontSize: 28, fontWeight: "800", color: colors.text }, message: { fontSize: 16, color: colors.text }, actions: { gap: spacing.md }, entry: { backgroundColor: colors.surface, borderRadius: 12, padding: spacing.md, gap: spacing.xs, borderLeftWidth: 5, borderLeftColor: colors.brand }, entryTitle: { fontSize: 18, fontWeight: "700", color: colors.text } });
