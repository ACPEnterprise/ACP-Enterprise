import { StyleSheet, Text } from "react-native";
import { PrimaryButton } from "../components/PrimaryButton";
import { Screen } from "../components/Screen";
import { colors } from "../design/tokens";
export function AccountScreen({ onLogout }: { onLogout(): Promise<void> }) { return <Screen><Text accessibilityRole="header" style={styles.title}>Account</Text><Text style={styles.body}>Your ACP session and employee permissions are managed by ACP Enterprise.</Text><PrimaryButton label="Sign Out" accessibilityLabel="Sign out and clear this device session" onPress={() => void onLogout()} /></Screen>; }
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 17, lineHeight: 24, color: colors.text } });
