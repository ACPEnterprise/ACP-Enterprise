import { useCallback, useEffect, useRef, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import type { FieldService, ItineraryItem } from "../api/fieldService";
import type { NetworkMonitor } from "../network/networkMonitor";
import { colors, spacing } from "../design/tokens";

function dateKey(offset: number) { const value = new Date(); value.setHours(12, 0, 0, 0); value.setDate(value.getDate() + offset); return value.toISOString().slice(0, 10); }
function window(value: string) { return new Intl.DateTimeFormat(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" }).format(new Date(value)); }

export function JobsScreen({ service, network }: { service: FieldService; network: NetworkMonitor }) {
  const [items, setItems] = useState<ItineraryItem[]>([]); const [state, setState] = useState<"loading" | "live" | "stale" | "offline" | "error">("loading");
  const itemsRef = useRef<ItineraryItem[]>([]);
  const refresh = useCallback(async () => {
    if (!(await network.isConnected())) { setState(itemsRef.current.length ? "stale" : "offline"); return; }
    setState("loading");
    try { const days = await Promise.all([0, 1, 2].map((offset) => service.itinerary(dateKey(offset)))); const next = days.flatMap((day) => day.items); itemsRef.current = next; setItems(next); setState("live"); }
    catch { setState(itemsRef.current.length ? "stale" : "error"); }
  }, [network, service]);
  useEffect(() => { void Promise.resolve().then(refresh); }, [refresh]);
  return <ScrollView style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={state === "loading"} onRefresh={() => void refresh()} accessibilityLabel="Refresh assigned Jobs" />}>
    <Text accessibilityRole="header" style={styles.title}>Jobs</Text><Text style={styles.boundary}>Today and the next two service days · assigned work only</Text>
    {state !== "live" && <Text accessibilityRole="alert" style={styles.stale}>{state === "stale" ? "LAST CONFIRMED — STALE. Job actions are disabled." : state === "offline" ? "You're offline. Connect to load assigned Jobs." : state === "error" ? "Assigned Jobs are unavailable." : "Loading assigned Jobs…"}</Text>}
    {state === "live" && items.length === 0 && <Text>No assigned Jobs in this bounded window.</Text>}
    {items.map((item) => <View key={`${item.appointment_id}-${item.window_start_at}`} style={styles.card}><Text style={styles.job}>{item.job_number ? `Job ${item.job_number}` : `Appointment ${item.appointment_number}`}</Text><Text style={styles.line}>{window(item.window_start_at)} · {item.customer_display_name}</Text><Text style={styles.line}>{item.service_location_label}</Text><Text style={styles.line}>{item.job_status ?? "Job not established"} · {item.arrival_state.replaceAll("_", " ")}</Text></View>)}
    <View style={styles.gate}><Text style={styles.gateTitle}>Completed/recent</Text><Text>Source required: the accepted Employee itinerary does not expose bounded completed history.</Text></View>
  </ScrollView>;
}
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, boundary: { color: colors.muted, fontSize: 15 }, stale: { color: colors.warning, fontWeight: "700", backgroundColor: "#FFF7D6", borderRadius: 12, padding: spacing.md }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.lg, gap: spacing.xs }, job: { fontSize: 19, fontWeight: "800", color: colors.text }, line: { fontSize: 16, lineHeight: 23, color: colors.text }, gate: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.md, gap: spacing.xs }, gateTitle: { fontSize: 17, fontWeight: "700", color: colors.text } });
