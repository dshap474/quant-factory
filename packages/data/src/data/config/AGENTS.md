# config
- What: package-local bridge to shared repo config and DB-root resolution.
- Why: centralizes runtime paths so callers do not read env directly.
- Keep: config lookup, path normalization, and compatibility aliases here.
- Avoid: provider secrets, family rules, or dataset-specific defaults here.
