import React from "react";
import { Text } from "react-native";
import { Screen } from "./Screen";
import { PrimaryButton } from "./PrimaryButton";
type State = { failed: boolean };
export class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { failed: false };
  static getDerivedStateFromError(): State { return { failed: true }; }
  render() { return this.state.failed ? <Screen><Text accessibilityRole="header">ACP Employee needs to recover</Text><Text>No work was recorded. Please try again.</Text><PrimaryButton label="Try again" onPress={() => this.setState({ failed: false })} /></Screen> : this.props.children; }
}
