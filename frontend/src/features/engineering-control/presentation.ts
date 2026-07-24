export const engineeringLabel = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

export const timestamp = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Not recorded";

export const shortHead = (value: string) => value.slice(0, 10);
