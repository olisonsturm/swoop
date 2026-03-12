# Incident Regression Bank

This directory tracks real bug reports and high-confidence failure modes that
must stay covered forever.

Rules:

- Every real bug fix adds one incident entry to `manifest.json`.
- An incident entry must point to either a tracked raw fixture or a concrete
  regression test node.
- Prefer sanitized real payloads when the failure depends on Google response
  shape. Prefer a focused Python reproduction when the failure is internal
  logic, selection, or pricing behavior.
- Keep the incident summary short and behavior-focused so future contributors
  can tell what broke without reading the full issue thread.
