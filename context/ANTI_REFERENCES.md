# Anti-references — what we explicitly avoid

When tempted to take a "standard" design path, check this list. If your draft
resembles one of these, redo.

## ❌ Russian SaaS / CRM aesthetic

Bitrix24, amoCRM, YClients, DIKIDI. Cluttered, gradient-buttoned, mid-2010s
bootstrap derivative. Avoid: bright Material-style shadows, blue-on-white,
sidebar nav with 14 icons, dashboards stuffed with widgets.

## ❌ Clinical / medical portal

White-on-white, blue accents, stock photo of doctor in lab coat, calendar
that looks like an EHR. We are wellness, not medicine. Even though some
masters are licensed cosmetologists/dermatologists, the surface should NOT
feel like a clinic CRM.

## ❌ Banking app aesthetic

Tinkoff/Sber/T-Bank-style sharp dark surfaces, electric blue/yellow accents,
giant numbers, transactional energy. We are warm and slow. They are fast and
transactional.

## ❌ Generic AI slop

Purple-to-pink gradients, glassmorphism / frosted overlays, bento card grids
on landing, Inter font for everything, twelve mini-feature cards with line
icons, "trusted by 12,000+ companies", floating chat bubble. This is the
default Claude/Cursor/v0 output when you don't constrain it. **Don't ship it.**

## ❌ Wedding / mass-market beauty

Overly pink, frilly script fonts, gold-foil flourishes, butterflies, hearts.
We are premium-modern beauty, not "Pinterest wedding 2014".

## ❌ Tech-startup landing tropes

- Hero with a giant blue/purple gradient blob behind a 3D iPhone mockup
- "Built for modern teams" type messaging
- Pricing page with three columns and one "highlighted"
- Footer with 50 links in 6 columns
- Auto-rotating customer logo bar
- "How it works" with 3 numbered circles

## ❌ Material 3 default

Floating action buttons, segmented controls everywhere, MD3 chip rows, the
default Material color generator outputs. Even on Android — we use Compose
Multiplatform with a CUSTOM design system, not MD3 defaults.

## ❌ iOS native default

System blue, default San Francisco font, default tab bar styling, modal
sheets with grabber handles styled exactly like the OS. We can be PLATFORM-AWARE
without being PLATFORM-DEFAULT.

## ❌ "Cute" illustration style

Corporate Memphis, isometric pastels, cartoon people with no chins. If we use
illustration, it's restrained line work in warm brown, NOT vector-pastels-and-blobs.

## ❌ Booking-tool defaults

Calendly's exact look, Cal.com's grid, OpenTable's date picker chrome. We are
NOT a generic booking tool. Time selection should feel intentional and warm.

---

**Test**: if you removed our brand colors from your mockup and replaced them
with someone else's, could the layout pass as Linear/Notion/Cal/etc?
If yes — the layout has no personality. Make it feel like moy-kosmetolog.
