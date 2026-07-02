---
name: systematic-debugging
description: >-
  Systematic root-cause debugging: investigate before fixing, log hypotheses, trace
  data flow, and stop to reassess after 3 failed fix attempts. Use when debugging a
  non-obvious failure, when a fix attempt did not work, or when asked to find a root
  cause. Skip for trivial errors whose cause is stated in the error message.
---

# Systematic debugging

## Provenance

Distilled from the gstack `/investigate` skill (local checkout,
`/Users/tsurai/Documents/GitHub/gstack/investigate/SKILL.md`) — method only, none of
the gstack runtime (no telemetry, gbrain, or scope-freeze tooling carried over).

## The Iron Law

No fixes without investigation. Reproduce the failure first, read the actual error
(not what you assume it says), and locate the failing layer before editing anything.
A fix that skips investigation is a guess.

## Hypothesis loop

Before each probe, state the current hypothesis in one line: what you believe is
wrong and why. Design the cheapest observation that can falsify it — a log line, an
assertion, a targeted read — and run it. Record what each probe ruled out; an
in-conversation trail is fine, the point is an explicit record, not a file format.
If the hypothesis is wrong, don't guess again blind — return to gathering evidence.

## Trace the data, not the blame

Follow the value through the layers it passes through (input → transform → output)
until you find the first place reality diverges from expectation. Fix at the
divergence point, not at the symptom. A fix proposed before tracing the data flow is
a guess, not a diagnosis.

## The 3-strikes stop rule

After 3 failed fix attempts, STOP. Do not try variant #4 of the same idea.
Re-read the evidence, list what every failed attempt assumed in common, and
question that shared assumption — it is usually a wrong architectural belief, not a
string of bad luck. Escalate or ask the user rather than continuing to guess.

## Exit criteria

A fix ships only with the reproducing check that now passes — see
`verification-before-completion` for the evidence bar before claiming done.
