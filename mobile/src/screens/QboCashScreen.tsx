import { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import type { QboEvidenceService, QboEvidence } from "../api/qboEvidence";
import type { NetworkMonitor } from "../network/networkMonitor";
import { colors, spacing } from "../design/tokens";
import { ApiFailure } from "../api/types";

function failure(error: unknown) { if (error instanceof ApiFailure && error.kind === "forbidden") return "Accounting evidence is not available with your current permissions."; if (error instanceof ApiFailure && error.kind === "offline") return "You're offline. Connect to refresh accounting evidence."; return "Accounting evidence is unavailable."; }
function stateLabel(value: string) { return value.replaceAll("_", " ").toUpperCase(); }

export function QboCashScreen({ service, network }: { service: QboEvidenceService; network: NetworkMonitor }) {
  const [data, setData] = useState<QboEvidence | null>(null); const [status, setStatus] = useState<"loading" | "ready" | "error">("loading"); const [message, setMessage] = useState<string | null>(null);
  const refresh = useCallback(async () => { setStatus("loading"); setMessage(null); try { setData(await service.cash()); setStatus("ready"); } catch (error) { setStatus("error"); setMessage(failure(error)); } }, [service]);
  useEffect(() => { let active = true; void network.isConnected().then((connected) => { if (active && connected) void refresh(); else if (active) { setStatus("error"); setMessage("You're offline. Connect to refresh accounting evidence."); } }); return () => { active = false; }; }, [network, refresh]);
  return <ScrollView style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={status === "loading"} onRefresh={() => void refresh()} accessibilityLabel="Refresh accounting evidence" />}>
    <Text accessibilityRole="header" style={styles.title}>Cash &amp; accounting</Text><Text style={styles.intro}>Read-only source evidence. Mobile cannot match, post, approve, or reconcile transactions.</Text>
    {message && <Text accessibilityRole="alert" style={styles.error}>{message}</Text>}
    {status === "loading" && <Text>Loading accounting evidence…</Text>}
    {status === "error" && <Text>UNAVAILABLE — retry when the source is available.</Text>}
    {data && <><View style={styles.card}><Text style={styles.heading}>Evidence status</Text><Text>{stateLabel(data.completeness)} · refresh {stateLabel(data.refresh_state)}</Text><Text>Basis: {data.accounting_basis} · as of {data.as_of ?? "UNAVAILABLE"}</Text><Text>Source: {data.source} · mode {data.mode}</Text></View>
      <View style={styles.card}><Text style={styles.heading}>Cash accounts</Text>{data.accounts.length ? data.accounts.map((account) => <View key={account.source_id} style={styles.row}><Text style={styles.account}>{account.name}</Text><Text>{account.balance.amount ?? "UNAVAILABLE"} {account.balance.currency ?? ""}</Text><Text style={styles.meta}>{stateLabel(account.balance.state)} · {account.account_subtype ?? account.account_type}</Text></View>) : <Text>UNAVAILABLE — no account balance evidence.</Text>}<Text style={styles.meta}>Total cash: UNAVAILABLE — no canonical aggregate was provided.</Text></View>
      <View style={styles.card}><Text style={styles.heading}>Exceptions</Text><Text>Unmatched bank transactions: UNAVAILABLE — not provided by this contract.</Text><Text>Ambiguous matches: UNAVAILABLE — not provided by this contract.</Text><Text>Reconciliation status: {data.conflicts.length ? "ATTENTION REQUIRED" : "UNAVAILABLE — no reconciliation status projection"}</Text><Text>Last reconciled-through date: UNAVAILABLE.</Text><Text>Cash Flow completeness: {stateLabel(data.completeness)}</Text></View>
      {data.reports.length > 0 && <View style={styles.card}><Text style={styles.heading}>Reports</Text>{data.reports.map((report) => <View key={report.report_key}><Text>{report.label} · {stateLabel(report.state)}</Text><Text style={styles.meta}>As of {report.as_of ?? "UNAVAILABLE"}{report.limitation ? ` · ${report.limitation}` : ""}</Text></View>)}</View>}
      {data.conflicts.length > 0 && <View style={styles.card}><Text style={styles.heading}>Items requiring attention</Text>{data.conflicts.map((conflict) => <View key={conflict.conflict_id}><Text>{conflict.subject_label} · {conflict.fact_name} · {stateLabel(conflict.state)}</Text><Text style={styles.meta}>{conflict.limitation}</Text></View>)}</View>}
      {data.limitations.map((limitation) => <Text key={limitation} style={styles.meta}>{limitation}</Text>)}
    </>}
  </ScrollView>;
}
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, intro: { color: colors.muted, fontSize: 15, lineHeight: 22 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.md, gap: spacing.xs }, heading: { fontSize: 18, fontWeight: "800", color: colors.text }, row: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.sm, gap: spacing.xs }, account: { fontSize: 16, fontWeight: "700", color: colors.text }, meta: { color: colors.muted, fontSize: 13, lineHeight: 19 }, error: { color: colors.danger, fontSize: 16 } });
