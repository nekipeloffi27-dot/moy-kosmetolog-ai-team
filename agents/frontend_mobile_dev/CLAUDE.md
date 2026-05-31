# CLAUDE.md — frontend mobile (KMP + Compose Multiplatform) agent

You are working inside a sandboxed clone of the moy-kosmetolog mobile repo.
Full project context (PROJECT.md), design system (DESIGN_SYSTEM.md), and
mobile stack conventions (MOBILE_STACK.md) are appended below.

Read **TASK.md** in `/prompts/TASK.md` for the work.

## Hard constraints

- Do NOT run `git`, `git push`, `gh`.
- Do NOT add Gradle dependencies without explicit license in TASK.md.
- Do NOT use Material 3 defaults — always feed our tokens.
- Do NOT add new font families. Fraunces + Manrope are the only display+body
  fonts. JetBrains Mono only for code-display contexts.
- Do NOT touch `iosApp/` SwiftUI shim unless TASK.md explicitly directs.
- The mockup section of TASK.md is the visual spec. Match it but adapt to
  Compose Multiplatform idioms.

## Definition of done

- All TASK.md acceptance criteria met.
- `./gradlew :composeApp:assembleDebug` succeeds.
- Where unit tests are appropriate (domain/repo/util): added and passing.
- Theme tokens used everywhere — `grep -E "Color\(0x" --include=*.kt -r src/commonMain/kotlin/com/moykosmetolog/feature/` returns nothing in the files you added (all colors via theme).
- No unrelated changes in `git status`.

---
