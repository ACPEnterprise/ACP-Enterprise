import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { Capability } from "../permissions/capabilities";
import { can } from "../permissions/capabilities";
import { HomeScreen } from "../screens/HomeScreen";
import { TimeScreen } from "../screens/TimeScreen";
import { SignInScreen } from "../screens/SignInScreen";
import { ActivationScreen } from "../screens/ActivationScreen";
import { linking } from "../linking/linking";
import type { TimekeepingService } from "../api/timekeeping";
import type { NetworkMonitor } from "../network/networkMonitor";

const Tabs = createBottomTabNavigator(); const Stack = createNativeStackNavigator();
export function AuthorizedTabs({ capabilities, timekeeping, network }: { capabilities: readonly Capability[]; timekeeping: TimekeepingService; network: NetworkMonitor }) { return <Tabs.Navigator screenOptions={{ headerShown: false, tabBarStyle: { minHeight: 60 } }}><Tabs.Screen name="Home" component={HomeScreen} />{can(capabilities, "time.self.view") && <Tabs.Screen name="Time" options={{ title: "My Time" }}>{() => <TimeScreen service={timekeeping} network={network} canPunch={can(capabilities, "time.self.punch")} />}</Tabs.Screen>}</Tabs.Navigator>; }
export function AppNavigator({ authenticated, capabilities = [], timekeeping, network }: { authenticated: boolean; capabilities?: readonly Capability[]; timekeeping: TimekeepingService; network: NetworkMonitor }) { return <NavigationContainer linking={linking as never}><Stack.Navigator screenOptions={{ headerShown: false }}>{authenticated ? <Stack.Screen name="App">{() => <AuthorizedTabs capabilities={capabilities} timekeeping={timekeeping} network={network} />}</Stack.Screen> : <><Stack.Screen name="SignIn" component={SignInScreen} /><Stack.Screen name="Activation" component={ActivationScreen} /></>}</Stack.Navigator></NavigationContainer>; }
