import NetInfo from "@react-native-community/netinfo";
export interface NetworkMonitor { isConnected(): Promise<boolean>; subscribe(listener: (connected: boolean) => void): () => void; }
export const deviceNetworkMonitor: NetworkMonitor = {
  isConnected: async () => (await NetInfo.fetch()).isConnected === true,
  subscribe: (listener) => NetInfo.addEventListener((state) => listener(state.isConnected === true)),
};
