# ACP UI Shared Primitives

## Role and ownership

`frontend/src/ui` is the approved source for reusable interface primitives in ACP Enterprise. Feature modules compose these primitives and must not create local substitutes for an existing ACP UI control without an approved architectural exception.

The initial public library includes Button, IconButton, Card and its sections, Badge, Alert, Field, native Input/Select/Textarea/Checkbox controls, Spinner, EmptyState, VisuallyHidden, Stack, Inline, and Cluster.

## Composition over configuration

Primitives are narrowly responsible. Card sections are optional compositions; Field coordinates labels and descriptions without cloning controls; EmptyState accepts action slots rather than defining workflows. Primitives contain no API access, business validation, navigation, analytics, permissions, or feature language.

Do not add speculative variants. Extend an existing primitive when the new behavior preserves its semantic role and is broadly reusable. A new primitive requires architectural approval when it introduces a new interaction model, accessibility contract, overlay, state manager, or feature-independent pattern.

## Accessibility contract

Native HTML is the default. Buttons and controls retain native keyboard behavior. Field supplies stable IDs, labels, helper and validation descriptions, required state, invalid state, and disabled state. Checkbox remains a native checkbox; indeterminate state is synchronized through its DOM property and exposed as mixed state.

Alerts are static unless a caller explicitly requests polite or assertive announcement. Visual severity does not determine announcement urgency. Spinners are either explicitly decorative or require an accessible label. VisuallyHidden supplies nonvisual text and must not wrap focusable controls.

Status must never rely on color alone. Badges and alerts require meaningful text; icons supplement rather than replace it.

## Token consumption

ACP UI consumes semantic Tailwind aliases and semantic CSS variables from the design foundation. Components must not reference ACP palette variables or hardcode reusable colors, spacing, typography, shadows, radii, breakpoints, motion, icon sizes, or z-index values.

Layout primitives accept a restrained named spacing scale backed by `--space-*` tokens. Consumer `className` is for layout integration, not redefining primitive invariants.

## Icon policy

Lucide React is the approved icon source. Shared controls accept React nodes instead of wrapping every icon. Button and IconButton icons are decorative because text or an accessible label carries meaning. Standalone meaningful icons require visible text or VisuallyHidden text. Status icons must accompany a label. Icon sizing follows the design-system icon scale.

## Extension rules

Correct:

```tsx
<Field label="Email" helperText="Use a monitored address" required>
  <Input type="email" />
</Field>

<Button leadingIcon={<Plus />}>Create record</Button>
```

Prohibited:

```tsx
// Feature-owned duplicate button and raw palette usage.
<button className="bg-[var(--acp-liberty-blue-600)]">Create record</button>

// Custom ARIA checkbox replacing a native control.
<div role="checkbox" aria-checked="false" />
```

Feature teams should request an extension when the existing primitive cannot express a broadly reusable semantic state. Dialogs, menus, tooltips, toasts, tables, navigation, and higher-level layout remain outside this package until separately approved.
