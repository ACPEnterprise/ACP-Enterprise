import { StyleSheet, Text, View } from "react-native";
import type { TimekeepingService } from "../api/timekeeping";
import { colors, spacing } from "../design/tokens";
import type { NetworkMonitor } from "../network/networkMonitor";
import { useJobClock } from "../timeclock/useJobClock";
import { PrimaryButton } from "./PrimaryButton";

function serverTime(value: string | null) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not active"; }

export function JobClockPanel({ service, network, jobId, appointmentId, enabled }: { service: TimekeepingService; network: NetworkMonitor; jobId: string; appointmentId: string; enabled: boolean }) {
  const clock = useJobClock(service, network, enabled);
  if (!enabled) return null;
  const thisJobActive = clock.state?.active === true && clock.state.job_id === jobId;
  const anotherJobActive = clock.state?.active === true && clock.state.job_id !== jobId;
  const unsafe = clock.status !== "ready" || clock.busy;
  return <View style={styles.panel} accessible accessibilityLabel="Authoritative Job work clock">
    <Text style={styles.title}>Job work clock</Text>
    <Text style={styles.separate}>Job work evidence is separate from My Time and Job lifecycle status.</Text>
    {clock.message && <Text accessibilityRole="alert" style={clock.status === "offline" || clock.status === "error" ? styles.stale : styles.message}>{clock.message}</Text>}
    {!clock.state && clock.status === "loading" && <Text>Loading current Job clock…</Text>}
    {clock.state && <View><Text style={styles.state}>{thisJobActive ? "Clocked onto this Job" : anotherJobActive ? "Clocked onto another Job" : "Not clocked onto a Job"}</Text><Text>Started: {serverTime(thisJobActive ? clock.state.started_at : null)}</Text><Text>Server checked: {serverTime(clock.state.server_observed_at)}</Text></View>}
    {anotherJobActive && <Text accessibilityRole="alert">Clock off the active assigned Job before clocking onto this one.</Text>}
    {clock.state && !anotherJobActive && <PrimaryButton label={thisJobActive ? "Clock Off This Job" : "Clock On To This Job"} accessibilityLabel={`${thisJobActive ? "Clock off" : "Clock on to"} this assigned Job using server time`} disabled={unsafe} onPress={() => void clock.mutate(thisJobActive ? "stop" : "start", jobId, appointmentId)} />}
  </View>;
}

const styles = StyleSheet.create({ panel: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.md, gap: spacing.sm }, title: { fontSize: 17, fontWeight: "700", color: colors.text }, separate: { color: colors.muted, fontSize: 15, lineHeight: 22 }, state: { color: colors.text, fontSize: 19, fontWeight: "800", marginBottom: spacing.xs }, message: { color: colors.text, fontSize: 16 }, stale: { color: colors.warning, fontWeight: "700", fontSize: 16 } });
