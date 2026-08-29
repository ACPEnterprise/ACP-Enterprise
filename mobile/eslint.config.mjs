import js from "@eslint/js";
import hooks from "eslint-plugin-react-hooks";
import reactNative from "eslint-plugin-react-native";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "babel.config.js"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ["**/*.{ts,tsx}"], plugins: { "react-hooks": hooks, "react-native": reactNative }, rules: { ...hooks.configs.recommended.rules, "react-native/no-inline-styles": "warn" } },
);
