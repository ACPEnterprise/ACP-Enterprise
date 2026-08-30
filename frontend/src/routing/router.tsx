import { createBrowserRouter, type RouteObject } from "react-router";

import { ApplicationShell } from "../layout";
import { ProtectedRoute } from "../auth";
import { TechnicianRouteGuard } from "../features/technician/TechnicianRouteGuard";
import {
  accountsPayableHandle,
  financialReportsHandle,
  businessEconomicsHandle,
  administrationHandle,
  auditHandle,
  reportsHandle,
  operatorGuideHandle,
  ownerOperationsHandle,
  appointmentsHandle,
  commandCenterHandle,
  customerDetailHandle,
  customersHandle,
  dispatchHandle,
  engineeringHandle,
  estimatesHandle,
  inventoryHandle,
  purchasingHandle,
  invoicesHandle,
  paymentsHandle,
  payrollHandle,
  revenueCycleHandle,
  jobsHandle,
  liaHandle,
  missionControlHandle,
  notFoundHandle,
  priceBookHandle,
  schedulingHandle,
  technicianHandle,
  workdayHandle,
} from "./routeMetadata";
import { RouteErrorBoundary } from "./RouteErrorBoundary";

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
              Component: (await import("../routes/CommandCenterRoute"))
                .CommandCenterRoute,
            }),
          },
          {
            path: "lia",
            handle: liaHandle,
            lazy: async () => ({ Component: (await import("../routes/LiaRoute")).LiaRoute }),
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
            ErrorBoundary: RouteErrorBoundary,
            lazy: async () => {
              const module = await import("../routes/CustomersRoute");
              return { Component: module.CustomersRoute };
            },
          },
          {
            path: "customers/:customerId",
            handle: customerDetailHandle,
            ErrorBoundary: RouteErrorBoundary,
            lazy: async () => ({
              Component: (await import("../routes/CustomerDetailRoute"))
                .CustomerDetailRoute,
            }),
          },
          {
            path: "scheduling",
            handle: schedulingHandle,
            lazy: async () => ({ Component: (await import("../routes/SchedulingRoute")).SchedulingRoute }),
          },
          {
            Component: TechnicianRouteGuard,
            children: [
              {
                path: "technician",
                handle: technicianHandle,
                lazy: async () => ({
                  Component: (await import("../routes/TechnicianRoute")).TechnicianRoute,
                }),
              },
            ],
          },
          {
            path: "workday",
            handle: workdayHandle,
            lazy: async () => ({
              Component: (await import("../routes/WorkdayRoute")).WorkdayRoute,
            }),
          },
          {
            path: "dispatch",
            handle: dispatchHandle,
            lazy: async () => ({
              Component: (await import("../routes/DispatchRoute"))
                .DispatchRoute,
            }),
          },
          {
            path: "estimates",
            handle: estimatesHandle,
            lazy: async () => ({
              Component: (await import("../routes/EstimatesRoute"))
                .EstimatesRoute,
            }),
          },
          {
            path: "invoices",
            handle: invoicesHandle,
            lazy: async () => ({
              Component: (await import("../routes/InvoicesRoute"))
                .InvoicesRoute,
            }),
          },
          {
            path: "invoices/:invoiceId",
            handle: invoicesHandle,
            lazy: async () => ({
              Component: (await import("../routes/InvoiceDetailRoute"))
                .InvoiceDetailRoute,
            }),
          },
          {
            path: "payments",
            handle: paymentsHandle,
            lazy: async () => ({ Component: (await import("../routes/PaymentsRoute")).PaymentsRoute }),
          },
          {
            path: "payments/:receiptId",
            handle: paymentsHandle,
            lazy: async () => ({ Component: (await import("../routes/PaymentDetailRoute")).PaymentDetailRoute }),
          },
          {
            path: "payroll",
            handle: payrollHandle,
            lazy: async () => ({ Component: (await import("../routes/PayrollRoute")).PayrollRoute }),
          },
          {
            path: "revenue-cycle",
            handle: revenueCycleHandle,
            lazy: async () => ({
              Component: (await import("../routes/RevenueCycleRoute"))
                .RevenueCycleRoute,
            }),
          },
          {
            path: "accounts-payable",
            handle: accountsPayableHandle,
            lazy: async () => ({ Component: (await import("../routes/AccountsPayableRoute")).AccountsPayableRoute }),
          },
          {
            path: "financial-reports",
            handle: financialReportsHandle,
            lazy: async () => ({ Component: (await import("../routes/FinancialReportsRoute")).FinancialReportsRoute }),
          },
          {
            path: "business-economics",
            handle: businessEconomicsHandle,
            lazy: async () => ({ Component: (await import("../routes/BusinessEconomicsRoute")).BusinessEconomicsRoute }),
          },
          {
            path: "price-book",
            handle: priceBookHandle,
            lazy: async () => ({
              Component: (await import("../routes/PriceBookRoute"))
                .PriceBookRoute,
            }),
          },
          {
            path: "inventory",
            handle: inventoryHandle,
            lazy: async () => ({
              Component: (await import("../routes/InventoryRoute"))
                .InventoryRoute,
            }),
          },
          {
            path: "purchasing",
            handle: purchasingHandle,
            lazy: async () => ({
              Component: (await import("../routes/PurchasingRoute"))
                .PurchasingRoute,
            }),
          },
          {
            path: "jobs",
            handle: jobsHandle,
            lazy: async () => ({
              Component: (await import("../routes/JobsRoute")).JobsRoute,
            }),
          },
          {
            path: "jobs/:jobId",
            handle: jobsHandle,
            lazy: async () => ({
              Component: (await import("../routes/JobDetailRoute"))
                .JobDetailRoute,
            }),
          },
          {
            path: "appointments/:appointmentId",
            handle: appointmentsHandle,
            lazy: async () => ({
              Component: (await import("../routes/AppointmentDetailRoute"))
                .AppointmentDetailRoute,
            }),
          },
          {
            path: "engineering",
            handle: engineeringHandle,
            lazy: async () => ({
              Component: (
                await import("../features/engineering-mobile/MobileEngineeringListPage")
              ).MobileEngineeringListPage,
            }),
          },
          {
            path: "engineering/:commandId",
            handle: engineeringHandle,
            lazy: async () => ({
              Component: (
                await import("../features/engineering-mobile/MobileEngineeringDetailPage")
              ).MobileEngineeringDetailPage,
            }),
          },
          {
            path: "owner-operations",
            handle: ownerOperationsHandle,
            lazy: async () => ({ Component: (await import("../routes/OwnerOperationsRoute")).OwnerOperationsRoute }),
          },
          {
            path: "audit",
            handle: auditHandle,
            lazy: async () => ({ Component: (await import("../routes/AuditRoute")).AuditRoute }),
          },
          {
            path: "reports",
            handle: reportsHandle,
            lazy: async () => ({ Component: (await import("../routes/ReportCenterRoute")).ReportCenterRoute }),
          },
          {
            path: "operator-guide",
            handle: operatorGuideHandle,
            lazy: async () => ({ Component: (await import("../routes/OperatorGuideRoute")).OperatorGuideRoute }),
          },
          {
            path: "administration",
            handle: administrationHandle,
            lazy: async () => ({
              Component: (
                await import("../features/administration/AdministrationRoute")
              ).AdministrationRoute,
            }),
          },
          {
            path: "administration/identity-onboarding",
            handle: administrationHandle,
            lazy: async () => ({
              Component: (
                await import(
                  "../features/administration/IdentityOnboardingRoute"
                )
              ).IdentityOnboardingRoute,
            }),
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
