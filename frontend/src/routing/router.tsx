import { Navigate, createBrowserRouter, type RouteObject } from "react-router";

import { ApplicationShell } from "../layout";
import { customersHandle, missionControlHandle, notFoundHandle } from "./routeMetadata";

export const appRoutes: RouteObject[] = [
  {
    path: "/",
    Component: ApplicationShell,
    children: [
      { index: true, element: <Navigate to="/mission-control" replace /> },
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
        path: "*",
        handle: notFoundHandle,
        lazy: async () => {
          const module = await import("../routes/NotFoundRoute");
          return { Component: module.NotFoundRoute };
        },
      },
    ],
  },
];

export const router = createBrowserRouter(appRoutes);
