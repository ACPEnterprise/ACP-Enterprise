import { Pressable, StyleSheet, Text } from "react-native";
import { colors, spacing, touchTarget } from "../design/tokens";
export function PrimaryButton({ label, onPress }: { label: string; onPress(): void }) { return <Pressable accessibilityRole="button" onPress={onPress} style={styles.button}><Text style={styles.text}>{label}</Text></Pressable>; }
const styles = StyleSheet.create({ button: { minHeight: touchTarget, backgroundColor: colors.brand, borderRadius: 10, paddingHorizontal: spacing.md, justifyContent: "center", alignItems: "center" }, text: { color: colors.surface, fontSize: 17, fontWeight: "700" } });
