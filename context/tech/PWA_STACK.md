# PWA stack — moy-kosmetolog/packages/web

## Stack (actual)

- **Next.js 16.2.6** — App Router
- **React 19.2.4**
- **TypeScript** (strict)
- **Tailwind CSS 4** (`@tailwindcss/postcss ^4`) — без `tailwind.config.ts`, токены через CSS `@theme` в `globals.css` и `halo-ds/tokens.css`
- **Halo DS** — кастомная дизайн-система в `halo-ds/`, NOT shadcn/ui
- **TanStack Query 5** — server state
- **Zustand 5** — client state (auth store в `lib/store/auth.ts`)
- **axios 1.x** — HTTP клиент (`lib/api.ts`)
- **lucide-react 1.x** — иконки
- **class-variance-authority + clsx + tailwind-merge** — утилиты для cn() и variant-стилей
- **@mediapipe/tasks-vision** — face landmark detection в scan flow

## PWA-специфика

- Service worker: `public/sw.js` (кастомный, bump-версии через `scripts/bump-sw-version.js`)
- Manifest: `public/manifest.json`
- Offline fallback: `public/offline.html`
- PWA иконки: `public/icons/icon-192.png`, `icon-512.png`
- Регистрация SW — в `app/layout.tsx` через inline script
- `display: standalone` в manifest для iOS/Android
- viewport: `userScalable: false`, `viewportFit: cover` — для safe-area на iPhone

## App Router layout (маршруты)

```
packages/web/app/
├── layout.tsx              — Root layout (шрифты, ThemeProvider, Providers, SW)
├── page.tsx                — Root → redirect
├── globals.css             — Tailwind + Halo DS + старые CSS-переменные
├── callback/
│   ├── telegram/           — Telegram OAuth callback
│   └── yandex/             — Yandex OAuth callback
└── main/                   — Authenticated routes
    ├── layout.tsx           — Main layout (ConditionalBottomNav)
    ├── welcome/             — Экран входа/регистрации (публичный)
    ├── otp/                 — OTP-верификация (публичный)
    ├── onboarding/          — Заполнение SkinProfile
    ├── home/                — Главный экран (виджеты: балл, рутина, статья, погода)
    ├── scan/                — AI-скан лица + result
    ├── chat/                — AI-чат с Claude
    ├── diary/               — Дневник кожи
    └── profile/             — Профиль пользователя
```

**Публичные пути** (без авторизации, из `middleware.ts`): `/main/welcome`, `/main/otp`, `/main/scan`, `/main/scan/result`, `/callback`

## Компоненты

```
packages/web/components/
├── auth/
│   ├── AuthLoadingOverlay.tsx
│   ├── LoginSheet.tsx
│   └── TelegramLoginButton.tsx
├── home/
│   ├── ArticleSheetContent.tsx
│   └── TaskRow.tsx
├── navigation/
│   ├── BottomNav.tsx
│   └── ConditionalBottomNav.tsx
├── scan/
│   ├── CareCard.tsx
│   ├── CosmeticAuthGate.tsx
│   ├── CosmeticResultCard.tsx
│   ├── FaceMeshOverlay.tsx
│   ├── FrozenMeshOverlay.tsx
│   ├── ProductPickerSheet.tsx
│   ├── ScanTypeModal.tsx
│   └── SkinDefectOverlay.tsx
└── shared/
    ├── MarkdownMessage.tsx
    ├── PageTransition.tsx
    ├── Skeleton.tsx
    └── SkeletonScreens.tsx
```

## Halo DS — правила

**Не-negotiable.** Halo DS — дизайн-язык проекта. Не тянуть shadcn, MUI, Chakra, ручной CSS-in-JS.

```
halo-ds/
├── tokens.css         — CSS-переменные (цвета, типографика, радиусы, тени, motion) + 4 темы
├── animations.css     — keyframes + helper классы (.halo-anim-*, .halo-scroll, .halo-press)
├── theme.ts           — applyHaloTheme('cream'|'rose'|'sage'|'midnight') + preload script
└── components/
    ├── HaloButton.tsx      — variants: primary / accent / ghost / soft
    ├── HaloGlass.tsx       — glass card container
    ├── HaloRing.tsx        — 3-кольцевой дайал (hydration/texture/tone)
    ├── HaloSheet.tsx       — rubber-drag bottom sheet
    ├── HaloSpark.tsx       — inline sparkline
    ├── HaloTabBar.tsx      — iOS-style bottom tab bar со sliding pill
    ├── HaloType.tsx        — HaloHeading (Instrument Serif), HaloMono (JB Mono), HaloEm (italic)
    ├── utils.ts            — cn() helper
    └── index.ts            — barrel export
```

Если нужный компонент отсутствует:
- Одноразовый → пиши в `components/<feature>/` на Halo-примитивах
- Общий → предложи расширить Halo DS в PR description

## Auth

- **Middleware**: `middleware.ts` читает cookie `access_token`, декодирует `exp` из JWT-payload (без верификации подписи) и редиректит на `/main/welcome` если токен протух или отсутствует
- **Client state**: Zustand store в `lib/store/auth.ts` (`useAuthStore`: `isAuthed`, `login()`, `logout()`)
- **Токены**: хранятся в cookies (`access_token`), Zustand читает их при инициализации
- **Anonymous flow**: для scan без авторизации — `anonymous_token` (UUID в localStorage). axios-интерсептор в `lib/api.ts` подставляет его когда нет JWT

## Data fetching

- Все API-вызовы через **TanStack Query** (`lib/queries.ts`). Не вызывать axios напрямую в `useEffect`.
- Axios instance в `lib/api.ts` — базовый URL, auth interceptor
- Backend вызывается через `/api/v1/...` (nginx проксирует на порт 3000)

## Соглашения

- **Mobile-first**. Дефолтные стили для 375px. `md:` / `lg:` для широких экранов
- **Нет `style={{...}}`** если значение не вычисляется в runtime
- **Один default export** на файл компонента. PascalCase. Имя файла = имя компонента
- **Файлы маршрутов**: `page.tsx`, `layout.tsx` (kebab-case папки, PascalCase файлы компонентов)
- TypeScript strict. Нет `any`. Используй `unknown` и сужай тип

## Темы

4 темы: `cream`, `rose`, `sage`, `midnight`. Переключение через `applyHaloTheme()` из `halo-ds/theme.ts`. Новые темы — добавлять блок `[data-halo-theme="x"] { … }` в `tokens.css`, не добавлять per-component код.

## Работа в монорепе

- Для локальной разработки: `cd packages/web && npm run dev`
- Сборка: `npm run build` из `packages/web/`
- Репо: `moy-kosmetolog`, рабочая папка `packages/web/`
- Ветки: `feat/<feature_id_short>/<slug>`, PR: `[<feature_id_short>] <task title>`
