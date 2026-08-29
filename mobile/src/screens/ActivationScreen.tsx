import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { ApiFailure } from "../api/types";
import { PrimaryButton } from "../components/PrimaryButton";
import { Screen } from "../components/Screen";
import { colors, spacing, touchTarget } from "../design/tokens";

function invitationMessage(error: unknown) {
  const kind = error instanceof ApiFailure ? error.kind : "unavailable";
  if (kind === "offline") return "You're offline. Connect to complete activation.";
  if (kind === "invitation_invalid" || kind === "conflict" || kind === "invalid_credentials") return "This activation link is no longer available. Ask your ACP administrator for a current invitation.";
  if (kind === "not_ready") return "That password does not meet ACP credential requirements. Use a longer, unique password and try again.";
  return "Activation is temporarily unavailable. Please try again.";
}

export function ActivationScreen({ token, onActivate, onComplete }: { token: string | null; onActivate(token: string, password: string): Promise<void>; onComplete(): void }) {
  const [password, setPassword] = useState(""); const [confirmation, setConfirmation] = useState(""); const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false); const [complete, setComplete] = useState(false); const [error, setError] = useState<string | null>(null);
  const valid = token !== null && password.length > 0 && password === confirmation;
  async function submit() { if (!valid || busy || !token) return; setBusy(true); setError(null); try { await onActivate(token, password); setPassword(""); setConfirmation(""); setComplete(true); } catch (value) { setPassword(""); setConfirmation(""); setError(invitationMessage(value)); } finally { setBusy(false); } }
  if (complete) return <Screen><Text accessibilityRole="header" style={styles.title}>Activation complete</Text><Text style={styles.body}>Your ACP credential is ready. Sign in to continue to your authorized employee workspace.</Text><PrimaryButton label="Continue to Sign In" onPress={onComplete} /></Screen>;
  return <Screen><Text accessibilityRole="header" style={styles.title}>Activate your ACP account</Text><Text style={styles.body}>Create the password you will use to sign in to ACP Employee.</Text>
    {!token && <Text accessibilityRole="alert" style={styles.error}>This activation link is invalid. Ask your ACP administrator for a current invitation.</Text>}{error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    <View style={styles.field}><Text style={styles.label}>Password</Text><TextInput accessibilityLabel="New ACP account password" autoComplete="new-password" textContentType="newPassword" secureTextEntry={!visible} value={password} onChangeText={setPassword} editable={!busy && token !== null} style={styles.input} /></View>
    <View style={styles.field}><Text style={styles.label}>Confirm password</Text><TextInput accessibilityLabel="Confirm new ACP account password" autoComplete="new-password" secureTextEntry={!visible} value={confirmation} onChangeText={setConfirmation} editable={!busy && token !== null} onSubmitEditing={() => void submit()} style={styles.input} /></View>
    <Pressable accessibilityRole="button" accessibilityLabel={visible ? "Hide activation passwords" : "Show activation passwords"} onPress={() => setVisible((value) => !value)} style={styles.visibility}><Text style={styles.visibilityText}>{visible ? "Hide passwords" : "Show passwords"}</Text></Pressable>
    {password && confirmation && password !== confirmation && <Text accessibilityRole="alert" style={styles.error}>Passwords do not match.</Text>}
    <PrimaryButton label={busy ? "Activating…" : "Activate Account"} disabled={!valid || busy} onPress={() => void submit()} />
    <Text style={styles.note}>Your password is sent directly to ACP Enterprise for credential establishment and is never stored by this app.</Text>
  </Screen>;
}
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 17, lineHeight: 24, color: colors.text }, error: { color: colors.danger, fontSize: 16, fontWeight: "600" }, field: { gap: spacing.xs }, label: { fontSize: 16, fontWeight: "700", color: colors.text }, input: { minHeight: touchTarget, borderColor: colors.border, borderWidth: 1, borderRadius: 10, backgroundColor: colors.surface, paddingHorizontal: spacing.md, fontSize: 17, color: colors.text }, visibility: { minHeight: touchTarget, alignSelf: "flex-start", justifyContent: "center" }, visibilityText: { color: colors.brand, fontWeight: "700" }, note: { color: colors.muted, fontSize: 15, lineHeight: 22 } });
