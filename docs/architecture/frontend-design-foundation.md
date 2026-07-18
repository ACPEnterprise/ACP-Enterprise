# Frontend Design Foundation

## Purpose

The ACP Enterprise design foundation provides a stable visual and configuration contract for a long-lived enterprise platform. It separates platform identity, deployment identity, semantic presentation, and component implementation so future themes and white-label deployments do not require feature rewrites.

ACP Enterprise is the platform. A customer company is a deployment of the platform and is not part of the default product identity.

## Design philosophy

The interface communicates American craftsmanship, professionalism, trust, industrial precision, and enterprise quality. The ACP palette draws restrained inspiration from American national colors while remaining modern and timeless. Liberty Blue carries primary identity and interaction. Heritage Red is a controlled accent; it must never dominate the interface.

ACP Enterprise must not resemble a patriotic website, political experience, or decorative marketing campaign. Operational clarity always takes precedence over visual novelty.

## Token layers

The styling architecture has three layers:

1. **ACP brand palette** defines Liberty Blue, Heritage Red, White, Slate, Steel, and supporting status palettes.
2. **Semantic tokens** map the palette to purposes such as background, surface, content, border, action, focus, navigation, and status.
3. **Components and application code** consume semantic CSS variables or semantic Tailwind utilities only.

Palette variables beginning with `--acp-` or `--palette-` are private design ingredients. They may be referenced by theme definitions, but never directly by feature or component styles. Reusable values for spacing, radius, elevation, duration, easing, layering, icons, and content widths also come from the foundation scales.

Typography is semantic. Application code uses Display, Heading XL/L/M/S, Body L, Body, Body S, Caption, Overline, or Monospace roles rather than choosing arbitrary font sizes. Tailwind exposes these as names such as `text-display`, `text-heading-l`, and `text-body-s`.

## Theme contract

Dark and light themes expose the same complete semantic variable contract. Dark is the initial platform default. `ThemeProvider` applies a `data-theme` attribute to the document root and supports `dark`, `light`, or system preference without requiring changes in consuming components.

Theme definitions own palette-to-semantic mapping. Components must not contain theme conditionals or select palette colors based on the active theme.

## Brand configuration and white-labeling

`BrandConfiguration` is the stable deployment contract for logo assets, compact logo, wordmark, product and optional company identity, tagline, document title, favicon, default theme, environment, and support information.

The platform default populates ACP Enterprise product identity only. Company identity remains undefined until deployment configuration supplies it. No logo is invented or assumed.

The future Brand Identity Region may render the configured logo, wordmark, optional tagline, and optional environment badge using this contract. A white-label deployment replaces configuration and may override palette variables at its branding boundary; it must not modify feature components or the semantic token names.

## Accessibility foundation

Keyboard focus uses a centralized, visible `:focus-visible` treatment with a forced-colors fallback. Text selection is theme-aware. Status communication must combine color with text, icons, shape, or another non-color cue.

Motion exists to improve comprehension. It may communicate hierarchy, focus, loading, transitions, and spatial relationships. Motion must never exist solely for decoration or entertainment. All design-system motion uses the centralized duration and easing tokens and respects `prefers-reduced-motion`.

## Consumption rules

- Use semantic CSS variables or semantic Tailwind aliases.
- Use semantic typography roles rather than raw font sizes.
- Use foundation spacing, radius, shadow, motion, z-index, icon, and width scales.
- Do not reference ACP palette variables from components or features.
- Do not hardcode reusable colors, spacing, typography, shadows, radii, animation values, breakpoints, or z-index values.
- Do not add a second styling system or component-level theme branching.
- New semantic tokens require both light and dark definitions and documentation of their purpose.
