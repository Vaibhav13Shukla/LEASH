# LEASH design contract

LEASH is a precision instrument that makes an AI agent's earned trust visible.
The visual north star is **a flight instrument panel printed on fine paper**:
warm, restrained, precise, and calm under failure.

## Non-negotiables

- Light, paper-first UI. No dark default, gradients, glass, neon, decorative
  3D, emoji, or generic AI imagery.
- Fraunces is reserved for display numbers and headings; Inter is the UI
  typeface; JetBrains Mono is mandatory for telemetry, policy tiers, IDs,
  timestamps, and tool names.
- The base is an 8px rhythm. Layout is carried by white space and hairlines,
  not by dense cards or shadows.
- `#2F5D3A` is the sole product accent. Green, amber, and red are reserved
  for actual policy state only.
- Motion explains an actual change: data enters, an error budget burns, a
  tier changes, or a permission is denied. Respect reduced-motion settings.

## State language

- T3: granted / full authority / deep green.
- T2: watch / reversible writes / amber.
- T1: revoked / read-only / signal red.
- T0: quarantined / no tools / signal red.

The pivotal interaction is deliberately quiet: when the broker receives a
SigNoz alert, the tier changes, the error arc turns red, and a single evidence
banner identifies the alert. The interface does not shake, flash, or pretend.

## Accessibility

Interactive controls retain visible 2px green focus rings, all state changes
are textually represented, semantic colour is never the only cue, and reduced
motion converts animation into immediate updates.
