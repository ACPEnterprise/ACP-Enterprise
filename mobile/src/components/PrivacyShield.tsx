import { type ReactNode, useEffect, useState } from "react";
import { AppState, type AppStateStatus, StyleSheet, Text, View } from "react-native";
import { colors, spacing } from "../design/tokens";

/** Obscures authenticated UI in OS task-switcher snapshots while the app is inactive. */
export function PrivacyShield({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppStateStatus>(AppState.currentState);
  useEffect(() => {
    const subscription = AppState.addEventListener("change", setState);
    return () => subscription.remove();
  }, []);
  return (
    <View style={styles.container}>
      {children}
      {state !== "active" ? (
        <View accessibilityLabel="ACP Employee protected" accessibilityViewIsModal style={styles.shield}>
          <Text style={styles.title}>ACP Employee</Text>
          <Text style={styles.message}>Protected while the app is inactive</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  shield: { ...StyleSheet.absoluteFillObject, alignItems: "center", backgroundColor: colors.brandDark, justifyContent: "center", padding: spacing.lg, zIndex: 1000 },
  title: { color: colors.surface, fontSize: 28, fontWeight: "700" },
  message: { color: colors.surface, fontSize: 16, marginTop: spacing.sm, textAlign: "center" },
});
