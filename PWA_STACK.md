# PWA stack — moy-kosmetolog/packages/web

## Stack (actual, not aspirational)

- **Next.js 16** with App Router
- **React 19**
- **TypeScript** (strict mode)
- **Tailwind CSS 4**
- **Halo DS** — custom design system in `halo-ds/`, NOT shadcn/ui
- **TanStack Query** for server state
- **Zustand** for client state (e.g. auth store in `lib/store/auth.ts`)
- **MediaPipe FaceMesh** for face-landmark detection in scan flow
- **axios** API client (`lib/api.ts`)
- date-fns for dates
- Lucide icons (in addition to Halo iconography where relevant)

## PWA specifics

- Service worker in `public/sw.js`
- Manifest in `public/manifest.json`
- Offline fallback in `public/offline.html`
- PWA icons in `public/icons/`
- `display: standalone` for true-app feel on iOS/Android
- Safe-area-inset awareness for BottomNav on iOS

## Repo layout (inside packages/web/)

```
packages/web/
├── app/                       # Next.js App Router pages
│   ├── layout.tsx
│   ├── page.tsx               # Root → redirects
│   ├── globals.css
│   ├── callback/              # OAuth callbacks
│   │   ├── telegram/page.tsx
│   │   └── yandex/page.tsx
│   └── main/                  # Authenticated routes
│       ├── layout.tsx
│       ├── home/page.tsx
│       ├── chat/page.tsx
│       ├── diary/page.tsx
│       ├── profile/page.tsx
│       ├── scan/page.tsx
│       ├── scan/result/page.tsx
│       ├── onboarding/page.tsx
│       ├── otp/page.tsx
│       └── welcome/page.tsx
├── components/                # Feature components (NOT design-system)
│   ├── auth/
│   ├── home/
│   ├── navigation/
│   ├── scan/
│   └── shared/
├── halo-ds/                   # CUSTOM design system — source of truth
│   ├── components/
│   │   ├── HaloButton.tsx
│   │   ├── HaloGlass.tsx
│   │   ├── HaloRing.tsx
│   │   ├── HaloSheet.tsx
│   │   ├── HaloSpark.tsx
│   │   ├── HaloTabBar.tsx
│   │   ├── HaloType.tsx
│   │   └── utils.ts
│   ├── theme.ts               # TS theme tokens
│   ├── tokens.css             # CSS variable design tokens
│   └── animations.css
├── lib/
│   ├── api.ts                 # axios + auth interceptor
│   ├── auth.ts
│   ├── cosmeticApi.ts
│   ├── queries.ts             # TanStack Query hooks
│   ├── skin-i18n.ts           # i18n for skin condition labels
│   ├── useFaceMesh.ts         # MediaPipe hook
│   ├── mediapipe-preloader.ts
│   ├── themes.ts
│   ├── utils.ts
│   ├── Providers.tsx
│   ├── ThemeProvider.tsx
│   └── store/auth.ts          # Zustand auth store
├── public/                    # Static, PWA manifest, sw.js, icons
├── middleware.ts              # Next.js auth guard
├── tailwind.config.ts (Tailwind 4: in some setups via CSS @theme)
├── tsconfig.json
└── package.json
```

## Halo DS — design system rules

**This is non-negotiable.** Halo DS is the project's design language. Don't
reach for shadcn, MUI, Chakra, or hand-rolled CSS-in-JS.

Components live in `halo-ds/components/`:

- `HaloButton` — primary/secondary/ghost variants
- `HaloGlass` — frosted surface (used SPARINGLY — see anti-references)
- `HaloRing` — circular progress (used for skin score)
- `HaloSheet` — bottom sheet
- `HaloSpark` — small accent indicator
- `HaloTabBar` — bottom tab bar
- `HaloType` — typography component with semantic variants

Tokens come from `halo-ds/tokens.css` (CSS variables) and `halo-ds/theme.ts`
(TS object). Use them — never hardcode hex colors or pixel values inside
feature components.

Tailwind 4 reads design tokens via `@theme` blocks in `globals.css`. Use
Tailwind classes that map to tokens, e.g. `bg-canvas` rather than
`bg-[#FAF7F2]`.

If a needed component doesn't exist in Halo DS:
- Small one-off → write in `components/<feature>/` using existing Halo
  primitives + Tailwind.
- General-purpose → propose extending Halo DS in the PR description.

## Conventions

- **Mobile-first**. Default styles target 375px. Use `md:` / `lg:` for wider.
- **No `style={{...}}`** unless the value is computed at runtime.
- **One default export per component file**. PascalCase. File name = component
  name.
- **API calls via TanStack Query**, never raw `fetch()` in `useEffect`. Hooks
  live in `lib/queries.ts` (extend it, don't bypass it).
- **Auth state via Zustand store** (`lib/store/auth.ts`). Don't introduce a
  second auth source of truth.
- **Anonymous flows**: for scan + cosmetic_analysis the user can be
  unauthenticated. The store provides an `anonymous_token` (UUID stored in
  localStorage). The API axios instance attaches it automatically when no
  JWT is present.

## Anthropic API integration (when adding chat-like features)

The backend handles LLM calls (`packages/api-python/app/modules/chat/`).
The PWA only renders responses streamed from the API. Don't call Anthropic
directly from the PWA.

Backend uses correct shape: endpoint `/v1/messages`, `x-api-key` header,
`anthropic-version: 2023-06-01`, system as top-level field, images via
`source` block.

## Forms

```tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const schema = z.object({
  phone: z.string().regex(/^\+7\d{10}$/, "Введи телефон в формате +7XXXXXXXXXX"),
});
```

Error messages in Russian, "ты"-form.

## Testing

- Unit/component tests with vitest + @testing-library/react.
- Test user-facing behavior, not implementation.
- No snapshot tests except for design-token-derived components.

## Code style

- Existing project config: ESLint + (likely) Prettier — follow.
- TypeScript strict. No `any`. Use `unknown` and narrow.

## Working in the monorepo

- Workspace root is at the repo root, not at `packages/web/`. Some `pnpm`
  commands need to be run from root.
- For local dev: `pnpm --filter web dev` from root, or `cd packages/web &&
  pnpm dev`.
- Builds: `pnpm --filter web build`.

## Pre-existing repo

Repo: monorepo `moy-kosmetolog`, work in `packages/web/`. See
`GITHUB_REPO_PWA` env var: `moy-kosmetolog#packages/web`.
Default branch: `main`.
PR title format: `[<feature_id_short>] <task title>`.
Branch naming: `feat/<feature_id_short>/<slug>`.
