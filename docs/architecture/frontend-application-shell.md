# Frontend Application Shell

## Purpose and ownership

The ACP Enterprise Application Shell is the persistent operating environment for every frontend module. It owns application geometry, brand presentation, primary navigation, the application header, workspace landmarks, responsive navigation state, route metadata presentation, theme controls, and the future AI workspace boundary.

The shell is infrastructure, not a feature page. It does not fetch business data, format domain values, evaluate permissions, infer deployment identity, or contain Customer, analytics, or other module logic. Feature routes own their content and render through the shell workspace outlet.

## Component hierarchy

```text
ApplicationShell
├── SkipLink
├── Sidebar
│   ├── BrandRegion
│   └── PrimaryNavigation
├── ShellBody
│   ├── ApplicationHeader
│   └── Workspace
│       └── Outlet
└── AIWorkspace
```

`Workspace` is the single main landmark and programmatic focus target. `AIWorkspace` is absent while closed and reserves a sibling extension point without presenting unfinished functionality.

## Routing hierarchy

React Router Data Mode owns URL state. The router is created once outside the React render tree.

```text
/
└── ApplicationShell
    ├── index → /mission-control
    ├── mission-control
    ├── customers
    └── * → not found
```

Child routes are lazy module boundaries. Thin route adapters preserve feature ownership. The shell persists across module navigation while routed content changes through `Outlet`.

## Navigation catalog and permissions

The typed navigation catalog separates registration from availability. Only Mission Control and Customers are currently available and visible. Future modules may remain registered as hidden definitions until their routes are operational.

Navigation visibility is not authorization. Future permission integration will filter eligible entries before rendering and independently guard route and service access. Business modules must not treat a hidden link as a security control.

## Workspace metadata

Typed route handles provide page title, breadcrumbs, contextual help identity, and future AI context. The deepest matched route is the single metadata source for the header, document title, breadcrumbs, and workspace context. Feature components do not imperatively mutate shell state.

## Brand and theme integration

`BrandRegion` consumes `BrandConfiguration`. It supports configured full and compact logos, wordmark or product-name fallback, optional company identity, tagline, and environment. It never infers a company name.

The theme provider exposes resolved theme, preference, and a typed preference setter. User preference supports system, light, and dark modes and is persisted locally; deployment configuration remains the fallback. Shell components consume semantic design tokens and contain no palette or theme branching.

## Header extension boundaries

The header owns accessible, explicitly inactive boundaries for global search, Notification Center, and account functionality. Notification Center is reserved for future recommendations, technician alerts, integration failures, shortages, expiring estimates, approvals, compliance notices, background jobs, and system warnings. These boundaries do not imply operational functionality.

## Responsive behavior

One semantic hierarchy supports all viewport sizes. Desktop uses a persistent collapsible sidebar. Smaller viewports use a shell-specific temporary navigation panel with Escape dismissal, body-scroll management, concealed inactive navigation, and focus restoration. This implementation is not a generic Drawer primitive.

## Accessibility

- A focus-visible skip link targets `#main-workspace`.
- Primary navigation uses native links and `aria-current="page"`.
- Breadcrumbs use a labeled navigation landmark and ordered list.
- The workspace is the only main landmark and accepts programmatic focus.
- Collapsed navigation retains accessible link names.
- Mobile navigation has explicit open and close controls, Escape behavior, and focus return.
- Route changes update the document title. New link navigations move focus to the workspace; history traversal does not force focus.
- Global focus and reduced-motion policies remain authoritative.

## Feature onboarding

1. Add a feature-owned route adapter or route module.
2. Register the route beneath `ApplicationShell`.
3. Provide typed workspace metadata.
4. Add navigation only when the module is operational.
5. Add permission metadata when authorization-aware frontend routing is introduced.
6. Keep business data, state, and presentation outside the shell.

Shell structure must not change merely to add a module.

## Notification and AI boundaries

Notification Center is an inactive header composition boundary. AI Workspace is closed and absent by default. Neither performs network calls or holds fake state. Future AI panel state belongs to shell infrastructure rather than feature pages, while feature routes may supply non-sensitive contextual metadata.

## Direct-link deployment requirement

The eventual web servers for `preview.allcountyhomeservices.com` and `command.allcountyhomeservices.com` must serve the SPA `index.html` for unknown frontend paths. Without history fallback, direct requests to `/mission-control`, `/customers`, and future nested routes will fail before React Router loads. This sprint does not modify deployment infrastructure.

## Extension rules and non-goals

- Use semantic tokens and approved primitives.
- Do not import feature modules into shell components.
- Do not add fake or disabled future navigation entries.
- Do not place authorization decisions in navigation components.
- Do not introduce deployment-specific identity in the shell.
- Do not add business fetching, analytics, Customer logic, authentication, notifications, global search, or AI behavior to the shell.
- New overlay or interaction primitives require separate architectural review.
