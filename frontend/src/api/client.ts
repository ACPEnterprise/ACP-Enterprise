import axios from "axios";

const apiBaseUrl =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10_000,
  headers: {
    "Content-Type": "application/json",
  },
});
