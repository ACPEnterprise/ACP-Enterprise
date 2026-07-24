import { createBrowserRouter, type RouteObject } from "react-router";

import { ApplicationShell } from "../layout";
import { ProtectedRoute } from "../auth";
import { appointmentsHandle, commandCenterHandle, customersHandle, dispatchHandle, engineeringHandle, jobsHandle, missionControlHandle, notFoundHandle } from "./routeMetadata";

export const appRoutes: RouteObject[] = [
  {
    path: "/login",
    lazy: async () => {
      const module = await import("../routes/LoginRoute");
      return { Component: module.LoginRoute };
    },
  },
  {
    path: "/",
    Component: ProtectedRoute,
    children: [
      {
        Component: ApplicationShell,
        children: [
          {
            index: true,
            handle: commandCenterHandle,
            lazy: async () => ({
              Component: (await import("../routes/CommandCenterRoute")).CommandCenterRoute,
            }),
          },
          {
            path: "mission-control",
            handle: missionControlHandle,
            lazy: async () => {
              const module = await import("../routes/MissionControlRoute");
              return { Component: module.MissionControlRoute };
            },
          },
          {
            path: "customers",
            handle: customersHandle,
            lazy: async () => {
              const module = await import("../routes/CustomersRoute");
              return { Component: module.CustomersRoute };
            },
          },
          {
            path: "dispatch",
            handle: dispatchHandle,
            lazy: async () => ({ Component: (await import("../routes/DispatchRoute")).DispatchRoute }),
          },
          {
            path: "jobs",
            handle: jobsHandle,
            lazy: async () => ({ Component: (await import("../routes/JobsRoute")).JobsRoute }),
          },
          {
            path: "jobs/:jobId",
            handle: jobsHandle,
            lazy: async () => ({ Component: (await import("../routes/JobDetailRoute")).JobDetailRoute }),
          },
          {
            path: "appointments/:appointmentId",
            handle: appointmentsHandle,
            lazy: async () => ({ Component: (await import("../routes/AppointmentDetailRoute")).AppointmentDetailRoute }),
          },
          {
            path: "engineering",
            handle: engineeringHandle,
            lazy: async () => ({ Component: (await import("../features/engineering-mobile/MobileEngineeringListPage")).MobileEngineeringListPage }),
          },
          {
            path: "engineering/:commandId",
            handle: engineeringHandle,
            lazy: async () => ({ Component: (await import("../features/engineering-mobile/MobileEngineeringDetailPage")).MobileEngineeringDetailPage }),
          },
          {
            path: "*",
            handle: notFoundHandle,
            lazy: async () => {
              const module = await import("../routes/NotFoundRoute");
              return { Component: module.NotFoundRoute };
            },
          },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(appRoutes);
