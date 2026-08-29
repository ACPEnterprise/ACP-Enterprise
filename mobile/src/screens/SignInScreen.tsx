import { Text, StyleSheet } from "react-native";
import { Screen } from "../components/Screen";
import { colors } from "../design/tokens";
export function SignInScreen() { return <Screen><Text accessibilityRole="header" style={styles.title}>ACP Employee</Text><Text style={styles.body}>Sign in with your ACP account.</Text><Text style={styles.note}>Authentication UI will connect to the existing ACP login contract during qualification. No employee PIN or separate mobile identity is used.</Text></Screen>; }
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 18, color: colors.text }, note: { fontSize: 16, color: colors.muted, lineHeight: 24 } });
