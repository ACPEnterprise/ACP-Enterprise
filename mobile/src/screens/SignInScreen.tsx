import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { ApiFailure } from "../api/types";
import { PrimaryButton } from "../components/PrimaryButton";
import { Screen } from "../components/Screen";
import { colors, spacing, touchTarget } from "../design/tokens";

function safeMessage(error: unknown) {
  const kind = error instanceof ApiFailure ? error.kind : "unavailable";
  if (kind === "invalid_credentials" || kind === "unauthenticated") return "The email or password is incorrect.";
  if (kind === "offline") return "You're offline. Connect to sign in.";
  if (kind === "rate_limited") return "Too many sign-in attempts. Wait a moment and try again.";
  return "ACP sign-in is temporarily unavailable. Please try again.";
}

export function SignInScreen({ onSignIn }: { onSignIn(email: string, password: string): Promise<void> }) {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  async function submit() { if (busy || !email.trim() || !password) return; setBusy(true); setError(null); try { await onSignIn(email, password); setPassword(""); } catch (value) { setPassword(""); setError(safeMessage(value)); } finally { setBusy(false); } }
  return <Screen>
    <Text accessibilityRole="header" style={styles.title}>ACP Employee</Text><Text style={styles.body}>Sign in with your ACP account.</Text>
    {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    <View style={styles.field}><Text style={styles.label}>Email</Text><TextInput accessibilityLabel="ACP login email" autoCapitalize="none" autoComplete="email" keyboardType="email-address" textContentType="username" value={email} onChangeText={setEmail} editable={!busy} style={styles.input} /></View>
    <View style={styles.field}><Text style={styles.label}>Password</Text><View style={styles.passwordRow}><TextInput accessibilityLabel="ACP account password" autoCapitalize="none" autoComplete="current-password" textContentType="password" secureTextEntry={!visible} value={password} onChangeText={setPassword} editable={!busy} onSubmitEditing={() => void submit()} style={styles.passwordInput} /><Pressable accessibilityRole="button" accessibilityLabel={visible ? "Hide password" : "Show password"} onPress={() => setVisible((value) => !value)} style={styles.visibility}><Text style={styles.visibilityText}>{visible ? "Hide" : "Show"}</Text></Pressable></View></View>
    <PrimaryButton label={busy ? "Signing in…" : "Sign In"} accessibilityLabel="Sign in to ACP Employee" disabled={busy || !email.trim() || !password} onPress={() => void submit()} />
    <Text style={styles.note}>Use the ACP credentials you established during secure activation.</Text>
  </Screen>;
}
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 18, color: colors.text }, error: { color: colors.danger, fontSize: 16, fontWeight: "600" }, field: { gap: spacing.xs }, label: { fontSize: 16, fontWeight: "700", color: colors.text }, input: { minHeight: touchTarget, borderColor: colors.border, borderWidth: 1, borderRadius: 10, backgroundColor: colors.surface, paddingHorizontal: spacing.md, fontSize: 17, color: colors.text }, passwordRow: { flexDirection: "row", borderColor: colors.border, borderWidth: 1, borderRadius: 10, backgroundColor: colors.surface, alignItems: "center" }, passwordInput: { minHeight: touchTarget, flex: 1, paddingHorizontal: spacing.md, fontSize: 17, color: colors.text }, visibility: { minHeight: touchTarget, minWidth: 64, justifyContent: "center", alignItems: "center" }, visibilityText: { color: colors.brand, fontWeight: "700" }, note: { fontSize: 15, color: colors.muted, lineHeight: 22 } });
