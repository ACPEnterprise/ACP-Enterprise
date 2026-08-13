export const customersPath = () => "/customers";
export const customerDetailPath = (customerId: string) =>
  `/customers/${customerId}`;

export const jobsPath = () => "/jobs";
export const jobDetailPath = (jobId: string) => `/jobs/${jobId}`;
export const appointmentDetailPath = (appointmentId: string) => `/appointments/${appointmentId}`;
export const schedulingPath = () => "/scheduling";
export const dispatchPath = () => "/dispatch";
