import type { PropsWithChildren } from "react";
import { StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing } from "../design/tokens";
export function Screen({ children }: PropsWithChildren) { return <SafeAreaView style={styles.safe}><View style={styles.body}>{children}</View></SafeAreaView>; }
const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { flex: 1, padding: spacing.lg, gap: spacing.md } });
