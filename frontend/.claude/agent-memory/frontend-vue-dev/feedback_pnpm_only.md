---
name: Use pnpm only, never npx or npm
description: Always use pnpm for frontend commands — npx and npm are not permitted
type: feedback
---

Always use `pnpm` for frontend package management and script execution. Never use `npx` or `npm`.

**Why:** User explicitly rejected an `npx tsc` command and reminded that pnpm is the required tool.

**How to apply:** For type-checking use `pnpm exec tsc --noEmit`. For running scripts use `pnpm run <script>`. For installing packages use `pnpm add`. Never fall back to npx even for one-off tool invocations.
