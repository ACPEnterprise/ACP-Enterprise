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
import type { EmployeeOperationsService } from "../api/employeeOperations";
import { MyDayScreen } from "../screens/MyDayScreen";
import { AssignmentDetailScreen } from "../screens/AssignmentDetailScreen";
import type { DayAssignment } from "../api/employeeOperations";

type MyDayStackParams = { MyDayList: undefined; AssignmentDetail: { appointmentId: string; assignment: DayAssignment; timezone: string } };
const Tabs = createBottomTabNavigator(); const Stack = createNativeStackNavigator(); const MyDayStack = createNativeStackNavigator<MyDayStackParams>();
function MyDayNavigation({ employeeOperations, network }: { employeeOperations: EmployeeOperationsService; network: NetworkMonitor }) { return <MyDayStack.Navigator><MyDayStack.Screen name="MyDayList" options={{ headerShown: false }}>{({ navigation }) => <MyDayScreen service={employeeOperations} network={network} onOpenAssignment={(assignment, timezone) => navigation.navigate("AssignmentDetail", { appointmentId: assignment.appointment_id, assignment, timezone })} />}</MyDayStack.Screen><MyDayStack.Screen name="AssignmentDetail" options={{ title: "Assignment Detail" }}>{({ route }) => <AssignmentDetailScreen appointmentId={route.params.appointmentId} initialAssignment={route.params.assignment} initialTimezone={route.params.timezone} service={employeeOperations} network={network} />}</MyDayStack.Screen></MyDayStack.Navigator>; }
export function AuthorizedTabs({ capabilities, timekeeping, employeeOperations, network }: { capabilities: readonly Capability[]; timekeeping: TimekeepingService; employeeOperations: EmployeeOperationsService; network: NetworkMonitor }) { return <Tabs.Navigator screenOptions={{ headerShown: false, tabBarStyle: { minHeight: 60 } }}>{can(capabilities, "my_day.view") ? <Tabs.Screen name="MyDay" options={{ title: "My Day" }}>{() => <MyDayNavigation employeeOperations={employeeOperations} network={network} />}</Tabs.Screen> : <Tabs.Screen name="Home" component={HomeScreen} />}{can(capabilities, "time.self.view") && <Tabs.Screen name="Time" options={{ title: "My Time" }}>{() => <TimeScreen service={timekeeping} network={network} canPunch={can(capabilities, "time.self.punch")} />}</Tabs.Screen>}</Tabs.Navigator>; }
export function AppNavigator({ authenticated, capabilities = [], timekeeping, employeeOperations, network }: { authenticated: boolean; capabilities?: readonly Capability[]; timekeeping: TimekeepingService; employeeOperations: EmployeeOperationsService; network: NetworkMonitor }) { return <NavigationContainer linking={linking as never}><Stack.Navigator screenOptions={{ headerShown: false }}>{authenticated ? <Stack.Screen name="App">{() => <AuthorizedTabs capabilities={capabilities} timekeeping={timekeeping} employeeOperations={employeeOperations} network={network} />}</Stack.Screen> : <><Stack.Screen name="SignIn" component={SignInScreen} /><Stack.Screen name="Activation" component={ActivationScreen} /></>}</Stack.Navigator></NavigationContainer>; }
