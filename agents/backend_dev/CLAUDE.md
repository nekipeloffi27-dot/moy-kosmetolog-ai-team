# CLAUDE.md — backend agent (moy-kosmetolog)

You are working inside a sandboxed clone of the moy-kosmetolog backend repo.
The full project context (PROJECT.md), design system (DESIGN_SYSTEM.md — for
reference even though you're backend), and backend stack conventions
(BACKEND_STACK.md) are appended to this file below.

Read the **TASK.md** in `/prompts/TASK.md` for the specific work to do.

## Hard constraints (cannot be overridden)

- Do NOT run `git`, `git push`, `gh`, or any version-control commands.
- Do NOT add or modify dependencies (requirements.txt, pyproject.toml) without
  explicit license in TASK.md.
- Do NOT touch files in `alembic/versions/` from earlier migrations — only
  create new migration files.
- Do NOT delete tests. Only modify a test if the behavior it tested has
  genuinely changed in TASK.md.
- The API contract section of TASK.md is THE specification. Match it exactly.

## Definition of done

- All TASK.md acceptance criteria satisfied.
- `ruff check .` passes with no warnings on files you touched.
- `black --check .` passes.
- `pytest` passes for any tests relevant to your change.
- No unrelated changes in `git status`.

When you believe you're done, just stop. The wrapper script will commit and
push.

---
