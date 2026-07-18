import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { brandConfig } from "./branding/brandConfig";
import { applyBrandDocumentMetadata } from "./branding/documentMetadata";
import { ThemeProvider } from "./theme/ThemeProvider";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root application element was not found.");
}

applyBrandDocumentMetadata(brandConfig);

createRoot(rootElement).render(
  <StrictMode>
    <ThemeProvider preference={brandConfig.defaultTheme}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
