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

const Tabs = createBottomTabNavigator(); const Stack = createNativeStackNavigator();
export function AuthorizedTabs({ capabilities }: { capabilities: readonly Capability[] }) { return <Tabs.Navigator screenOptions={{ headerShown: false, tabBarStyle: { minHeight: 60 } }}><Tabs.Screen name="Home" component={HomeScreen} />{can(capabilities, "time.self.view") && <Tabs.Screen name="Time" component={TimeScreen} options={{ title: "My Time" }} />}</Tabs.Navigator>; }
export function AppNavigator({ authenticated, capabilities = [] }: { authenticated: boolean; capabilities?: readonly Capability[] }) { return <NavigationContainer linking={linking as never}><Stack.Navigator screenOptions={{ headerShown: false }}>{authenticated ? <Stack.Screen name="App">{() => <AuthorizedTabs capabilities={capabilities} />}</Stack.Screen> : <><Stack.Screen name="SignIn" component={SignInScreen} /><Stack.Screen name="Activation" component={ActivationScreen} /></>}</Stack.Navigator></NavigationContainer>; }
