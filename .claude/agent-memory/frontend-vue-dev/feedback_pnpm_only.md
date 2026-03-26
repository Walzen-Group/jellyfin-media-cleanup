---
name: Use pnpm exclusively
description: Always use pnpm for frontend commands, never npm or npx
type: feedback
---

Always use `pnpm` for frontend commands -- never `npm`, `npx`, or `yarn`.

**Why:** User corrected use of `npx` for vue-tsc. The project uses pnpm as stated in CLAUDE.md.

**How to apply:** Any frontend command (install, dev, build, type-check) must use `pnpm` prefix. For running local binaries, use `pnpm` instead of `npx`.
