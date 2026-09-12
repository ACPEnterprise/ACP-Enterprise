export const customersPath = () => "/customers";
export const customerDetailPath = (customerId: string) =>
  `/customers/${customerId}`;
export const customerLocationPath = (customerId: string, locationId: string) =>
  `${customerDetailPath(customerId)}#service-location-${locationId}`;

export const jobsPath = () => "/jobs";
export const jobDetailPath = (jobId: string) => `/jobs/${jobId}`;
export const appointmentDetailPath = (appointmentId: string) => `/appointments/${appointmentId}`;
export const schedulingPath = () => "/scheduling";
export const dispatchPath = () => "/dispatch";

export function schedulingReturnPath(value: string | null): string {
  if (!value) return schedulingPath();
  try {
    const url = new URL(value, "https://acp.invalid");
    return url.origin === "https://acp.invalid" && url.pathname === schedulingPath()
      ? `${url.pathname}${url.search}`
      : schedulingPath();
  } catch {
    return schedulingPath();
  }
}

export const withSchedulingReturn = (path: string, returnTo: string) => {
  const url = new URL(path, "https://acp.invalid");
  url.searchParams.set("returnTo", returnTo);
  return `${url.pathname}${url.search}${url.hash}`;
};
