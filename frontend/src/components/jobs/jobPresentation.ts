import type { JobStatus } from "../../types/jobs";

export type JobAction = "activate" | "start" | "pause" | "resume" | "complete" | "cancel" | "reopen";

export const statusLabels: Record<JobStatus, string> = {
  draft: "Draft", ready: "Ready", in_progress: "In progress", paused: "Paused",
  completed: "Completed", cancelled: "Cancelled",
};

export const actionsByStatus: Record<JobStatus, readonly JobAction[]> = {
  draft: ["activate", "cancel"], ready: ["start", "cancel"],
  in_progress: ["pause", "complete"], paused: ["resume"],
  completed: ["reopen"], cancelled: ["reopen"],
};

export const actionLabels: Record<JobAction, string> = {
  activate: "Activate", start: "Start work", pause: "Pause work", resume: "Resume work",
  complete: "Complete Job", cancel: "Cancel Job", reopen: "Reopen Job",
};
