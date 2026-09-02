import { StyleSheet, Text } from "react-native";
import { PrimaryButton } from "../components/PrimaryButton";
import { Screen } from "../components/Screen";
import { colors } from "../design/tokens";
import type { Capability } from "../permissions/capabilities";
export function AccountScreen({ environmentName, capabilities, onLogout }: { environmentName: string; capabilities: readonly Capability[]; onLogout(): Promise<void> }) { return <Screen><Text accessibilityRole="header" style={styles.title}>Account</Text><Text style={styles.body}>Your identity, Company, Branch, and permissions are verified by ACP Enterprise.</Text><Text accessibilityLabel={`Connected environment ${environmentName}`} style={styles.body}>Environment: {environmentName}</Text><Text accessibilityLabel={`${capabilities.length} active mobile capabilities`} style={styles.body}>Access: {capabilities.length} active mobile capabilities</Text><Text style={styles.body}>App version 0.1.0 · Session protected on this device</Text><PrimaryButton label="Sign Out" accessibilityLabel="Sign out and clear this device session" onPress={() => void onLogout()} /></Screen>; }
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 17, lineHeight: 24, color: colors.text } });
