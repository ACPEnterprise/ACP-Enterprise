import { useState } from "react";
import { Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { WebView } from "react-native-webview";
import type { PayStatement, PayrollService } from "../api/payroll";
import { ApiFailure } from "../api/types";
import { colors, spacing } from "../design/tokens";
import type { NetworkMonitor } from "../network/networkMonitor";
import { useMyPay } from "../payroll/useMyPay";

function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function StatementCard({ statement, onOpen }: { statement: PayStatement; onOpen(): void }) {
  return <View accessible accessibilityLabel={`Pay statement version ${statement.version}, ${label(statement.payment_status)}, ${statement.corrected ? "corrected" : "original"}`} style={styles.card}>
    <Text style={styles.cardTitle}>{statement.corrected ? "Corrected pay statement" : "Pay statement"}</Text>
    <Text>Payment: {label(statement.payment_status)}</Text><Text>Statement status: {label(statement.lifecycle)}</Text>
    <Text>{statement.ytd_status === "available" ? "Year-to-date totals available" : "Year-to-date totals unavailable"}</Text>
    <Pressable accessibilityRole="button" accessibilityLabel="Securely view pay statement" onPress={onOpen} style={styles.button}><Text style={styles.buttonText}>View Statement</Text></Pressable>
  </View>;
}
export function MyPayScreen({ service, network }: { service: PayrollService; network: NetworkMonitor }) {
  const pay = useMyPay(service, network); const [artifact, setArtifact] = useState<string | null>(null); const [artifactState, setArtifactState] = useState<"idle" | "loading" | "error">("idle");
  const stale = pay.state === "offline" && pay.statements.length > 0;
  const message = pay.state === "offline" ? (stale ? "You're offline. Statement metadata is last confirmed and may be stale; artifacts cannot be opened." : "You're offline. Connect to load My Pay.") : pay.state === "forbidden" ? "My Pay is not authorized for your account." : pay.state === "session_expired" ? "Your session has expired. Please sign in again." : pay.state === "error" ? "My Pay is temporarily unavailable. Pull to retry." : null;
  async function open(statement: PayStatement) { if (!(await network.isConnected())) { setArtifactState("error"); return; } setArtifactState("loading"); try { setArtifact(await service.artifact(statement.id)); setArtifactState("idle"); } catch (error) { setArtifactState("error"); if (error instanceof ApiFailure && error.kind === "unauthenticated") await pay.refresh(); } }
  return <><ScrollView style={styles.safe} contentContainerStyle={styles.body} refreshControl={<RefreshControl refreshing={pay.state === "loading" || pay.refreshing} onRefresh={() => void pay.refresh()} accessibilityLabel="Refresh My Pay" />}>
    <Text accessibilityRole="header" style={styles.title}>My Pay</Text><Text style={styles.private}>Private employee self-service · Preview authority</Text>
    {pay.payrollStatus && <View style={styles.status}><Text style={styles.cardTitle}>Current Payroll status</Text><Text>{pay.payrollStatus.statement_count} statement{pay.payrollStatus.statement_count === 1 ? "" : "s"}</Text><Text>Payment: {label(pay.payrollStatus.payment_status)}</Text><Text>YTD: {label(pay.payrollStatus.ytd_status)}</Text>{pay.payrollStatus.has_correction && <Text>Includes corrected statement evidence</Text>}</View>}
    {message && <Text accessibilityRole="alert" style={stale ? styles.stale : styles.message}>{message}</Text>}{artifactState === "loading" && <Text accessibilityLabel="Loading protected pay statement">Loading protected statement…</Text>}{artifactState === "error" && <Text accessibilityRole="alert" style={styles.message}>Unable to open the protected statement. Check your connection and try again.</Text>}
    {pay.state === "empty" && <View style={styles.card}><Text style={styles.cardTitle}>No pay statements available</Text><Text>Your authorized statements will appear here when issued.</Text></View>}
    {pay.statements.map((statement) => <StatementCard key={statement.id} statement={statement} onOpen={() => void open(statement)} />)}
  </ScrollView><Modal visible={artifact !== null} animationType="slide" onRequestClose={() => setArtifact(null)}><View style={styles.viewer}><View style={styles.viewerHeader}><Text accessibilityRole="header" style={styles.cardTitle}>Protected Pay Statement</Text><Pressable accessibilityRole="button" accessibilityLabel="Close protected pay statement" onPress={() => setArtifact(null)} style={styles.button}><Text style={styles.buttonText}>Close</Text></Pressable></View>{artifact && <WebView source={{ html: artifact, baseUrl: "about:blank" }} javaScriptEnabled={false} domStorageEnabled={false} sharedCookiesEnabled={false} thirdPartyCookiesEnabled={false} originWhitelist={[]} incognito cacheEnabled={false} />}</View></Modal></>;
}
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, private: { color: colors.muted }, status: { backgroundColor: "#EAF4F6", borderRadius: 14, padding: spacing.lg, gap: spacing.xs }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.lg, gap: spacing.sm }, cardTitle: { fontSize: 19, fontWeight: "800", color: colors.text }, button: { minHeight: 48, paddingHorizontal: spacing.md, borderRadius: 10, backgroundColor: colors.brand, alignItems: "center", justifyContent: "center", alignSelf: "flex-start" }, buttonText: { color: "white", fontWeight: "800" }, message: { fontSize: 16, color: colors.text }, stale: { color: colors.warning, fontWeight: "700", backgroundColor: "#FFF7D6", padding: spacing.md, borderRadius: 12 }, viewer: { flex: 1, backgroundColor: colors.surface, paddingTop: spacing.xl }, viewerHeader: { padding: spacing.md, flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderBottomWidth: 1, borderBottomColor: colors.border } });
