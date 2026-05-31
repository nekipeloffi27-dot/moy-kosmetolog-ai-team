# Design system — moy-kosmetolog

This file is canonical for **visual taste and voice**. The implementation
is **Halo DS** in `packages/web/halo-ds/` — its `tokens.css` and `theme.ts`
are the source of truth for actual values used in code. This document
explains the philosophy and naming.

If a value here disagrees with Halo DS code, Halo DS wins. Propose updates
to Halo DS in a PR rather than diverging.

## 1. Brand essence

Atmosphere: warm, calming, premium-but-not-clinical. Think Aman hotel ×
Glossier × Aesop.

We are **not**: pharmacy white, corporate medical blue, generic SaaS purple,
fintech-sharp, banking-cold, wedding-pink. See `ANTI_REFERENCES.md`.

## 2. Color philosophy

We work in a warm-cream palette with deep emerald as the trust accent and
warm coral as the warmth accent. Specific values:

**Light mode** (defaults — implementation in `halo-ds/tokens.css`):

```
bg-canvas       cream            #FAF7F2
bg-elevated     white-warm       #FFFFFF
bg-tinted       warm-gray        #F3EDE4
bg-sunken       deeper-cream     #ECE3D5

text-primary    warm near-black  #1F1B16
text-secondary                   #5C544A
text-tertiary                    #8A8278

accent          deep forest      #2D5F4F   ← trust, primary CTA
accent-soft                      #E8EFE9
accent-strong                    #1B4538

blush           warm coral       #E8A89A   ← warmth, secondary CTA
blush-soft                       #FBEDE8
blush-strong                     #C97361

border                           #E5DCD0
border-strong                    #C4B8A8
border-focus    = accent
```

**Dark mode**: invert with WARM character. Never pure black. See
`halo-ds/tokens.css` `[data-theme="dark"]` block.

### Rules

- Page background is **canvas** (cream), not white. Cards on top use
  **elevated**.
- **Accent** = trust signals (booking confirmations, completed scans,
  primary CTAs that need authority).
- **Blush** = warmth (start trial, claim, get-started CTAs).
- Never use red/blue/purple/yellow except for semantic states
  (danger/info/etc.) — never decoratively.

## 3. Typography

### Families

- **Headings**: [Fraunces](https://fonts.google.com/specimen/Fraunces) —
  variable serif with optical sizing. Weights 400–500.
- **Body**: [Manrope](https://fonts.google.com/specimen/Manrope) — geometric
  sans-serif.
- **Mono** (code only, never UI): JetBrains Mono.

Use the `HaloType` component for semantic variants rather than ad-hoc
font-family classes.

### Banned fonts

Inter, Roboto, Arial, Helvetica, Open Sans, Lato, Space Grotesk, Montserrat,
Poppins, Nunito, Source Sans, Playfair Display.

### Scale (implemented in `HaloType`)

```
Display      Fraunces 500   56 / 64    -0.02em
H1           Fraunces 400   40 / 48    -0.015em
H2           Fraunces 400   28 / 36    -0.01em
H3           Fraunces 500   22 / 30    -0.005em
H4           Manrope  600   17 / 24
Body L       Manrope  400   17 / 26
Body         Manrope  400   15 / 24
Body S       Manrope  400   13 / 20
Caption      Manrope  500   12 / 16    +0.02em
Button       Manrope  500   15 / 20
```

### Rules

- Don't bold mid-sentence in prose. Semibold for labels and headings only.
- No H1 inside cards. H1 is page-level.
- Numbers in prices use tabular-nums.

## 4. Spacing scale

Multiples of 4. Tailwind-compatible: `p-4` = 16px, `gap-6` = 24px.

## 5. Radius

```
xs: 4    small chips, dense controls
sm: 8    inputs, small buttons
md: 12   default for buttons, cards, dialogs
lg: 20   large cards, sheets
xl: 32   hero containers, large CTAs
full     pills, avatars, circular icons
```

## 6. Elevation

Border-first, shadow-rarely:

```
--shadow-soft:     0 4px 24px -8px rgba(48, 38, 27, 0.08)
--shadow-elevated: 0 24px 64px -16px rgba(48, 38, 27, 0.12)
```

Use only on floating UI (modals, popovers, dropdowns), not every card.

## 7. Iconography

Lucide outline, stroke 1.5px, sizes **16 / 20 / 24** only. Color inherits.
Icon-only buttons require `aria-label`; decorative icons get `aria-hidden`.

## 8. Motion

```
ease-default:    cubic-bezier(0.32, 0.72, 0, 1)
duration-fast:   180ms  (hover, focus)
duration-base:   240ms  (most UI)
duration-slow:   400ms  (page transitions, drawer open)
duration-delight: 600ms (one-off moments)
```

Respect `prefers-reduced-motion: reduce` — fall back to instant.

NEVER: bouncing spring rotations, parallax decoration, perpetual rotation,
particle/sparkle effects.

## 9. Imagery

**Hero photography**: warm natural light, real moments — hands, touch,
the moment between actions. No posed stock smiles, no clinical sterility,
no hyper-saturation.

**Avatars**: real photos preferred; fallback is initials on `--bg-tinted`
in warm-text color.

**Empty states**: line illustration in warm brown on cream, OR soft macro
photography. Never robot mascots, never the corporate "ghost" empty
illustration.

## 10. Voice (Russian, "ты")

Warm, knowledgeable, brief.

### Booking confirmation

✅ "Записываем тебя к Анне. Она будет ждать в 14:00 — приходи на пять минут раньше."
❌ "Ваша запись успешно создана. Уведомление отправлено."

### Empty state

✅ "Тут пока пусто. Создай первую запись — это займёт минуту."
❌ "Записи отсутствуют."

### Error

✅ "Не получилось сохранить — кажется, мы куда-то задумались. Попробуй ещё раз?"
❌ "Произошла ошибка. Код 500."

### Rules

- No "Уважаемый клиент", "пользователь", "вы". Always "ты".
- No emoji in production UI (sparingly OK in marketing copy).
- No exclamation marks except in genuine celebration.
- Time: "в 14:00".
- Money: "1 200 ₽" with thin space (`U+202F`).

## 11. Layout principles

1. One visual anchor per screen.
2. Generous whitespace.
3. Asymmetry welcome — avoid 2×2 bento grids.
4. Mobile-first.
5. Touch targets ≥ 44px on mobile, ≥ 8px gap between.

## 12. Using Halo DS in practice

When building a screen in `packages/web/`:

```tsx
import { HaloButton, HaloType, HaloSheet } from "@/halo-ds/components";

function BookingConfirm() {
  return (
    <section className="bg-canvas min-h-screen p-6">
      <HaloType variant="h2">Запись подтверждена</HaloType>
      <HaloType variant="body" className="text-text-secondary mt-2">
        Завтра в 14:00, к Анне. Приходи на пять минут раньше.
      </HaloType>
      <HaloButton variant="primary" className="mt-8">
        Добавить в календарь
      </HaloButton>
    </section>
  );
}
```

Tailwind classes resolve to design tokens through `@theme` in `globals.css`.

## 13. What we DON'T do (recap)

- Glassmorphism / neumorphism — `HaloGlass` exists but is used sparingly
  on hero surfaces only, never on standard cards.
- Generic SaaS bento card grids.
- Auto-rotating carousels.
- Stock photography of generic "beautiful women smiling".
- Tabs/accordions on landing — write the content.
- Notification dots on everything.
- Emoji in production UI (sparingly in marketing copy is OK).
- AI-art generated illustrations.
- Drop shadows on every card.
- Material 3 default styling.
- shadcn/ui — we have Halo DS instead.

## 14. For mobile (Compose Multiplatform)

When implementing in `packages/mobile/` (KMP + Compose Multiplatform), the
design system reappears as Kotlin theme objects (`Colors.kt`, `Typography.kt`,
etc.) mirroring the values here. The mobile agent rebuilds Halo's visual
language in Compose, not by copying components.

See `tech/MOBILE_STACK.md` for the Kotlin shape.
