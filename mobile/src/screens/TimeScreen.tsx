import { Text, StyleSheet } from "react-native";
import { Screen } from "../components/Screen";
import { colors } from "../design/tokens";
export function TimeScreen() { return <Screen><Text accessibilityRole="header" style={styles.title}>My Time</Text><Text style={styles.body}>Time information will load from ACP Enterprise.</Text><Text style={styles.note}>The server remains authoritative for identity, punch state, timestamps, timezone, and timecard evidence.</Text></Screen>; }
const styles = StyleSheet.create({ title: { fontSize: 30, fontWeight: "800", color: colors.text }, body: { fontSize: 18, color: colors.text }, note: { fontSize: 16, lineHeight: 24, color: colors.muted } });
