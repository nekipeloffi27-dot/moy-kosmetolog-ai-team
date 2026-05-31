# CLAUDE.md — frontend web (PWA) agent

You are working inside a sandboxed clone of the moy-kosmetolog PWA repo. The
full project context (PROJECT.md), design system (DESIGN_SYSTEM.md), and PWA
stack conventions (PWA_STACK.md) are appended to this file.

Read **TASK.md** in `/prompts/TASK.md` for the specific work.

## Hard constraints

- Do NOT run `git`, `git push`, `gh`.
- Do NOT add npm dependencies without explicit license in TASK.md.
- Do NOT touch `src/components/ui/` shadcn primitives unless TASK.md explicitly
  asks for it (these are shared system pieces — changes there ripple).
- The design system tokens in DESIGN_SYSTEM.md and `tailwind.config.ts` are the
  source of truth. If they disagree, raise it in code comments — don't silently
  diverge.
- The mockup section of TASK.md is the visual spec. Match it.

## Definition of done

- All TASK.md acceptance criteria satisfied at 375px width AND at desktop width.
- `pnpm typecheck` passes.
- `pnpm lint` passes with zero warnings on files you touched.
- `pnpm test --run` passes.
- Lighthouse (mobile) wouldn't lose more than 2 points on accessibility for
  your additions.
- No unrelated changes in `git status`.

---
