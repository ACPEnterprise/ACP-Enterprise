import { Text, StyleSheet } from "react-native";
import { Screen } from "../components/Screen";
import { colors } from "../design/tokens";
export function HomeScreen() { return <Screen><Text accessibilityRole="header" style={styles.title}>Home</Text><Text style={styles.body}>Your employee workspace is ready.</Text><Text style={styles.note}>Employee information and future actions will appear here only when provided by ACP Enterprise.</Text></Screen>; }
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 18, color: colors.text }, note: { fontSize: 16, lineHeight: 24, color: colors.muted } });
