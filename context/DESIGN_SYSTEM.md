# Design system — moy-kosmetolog (Halo DS)

Этот файл — канонический источник визуального языка и голоса продукта.  
Реализация — **Halo DS** в `packages/web/halo-ds/`. Исходники значений:
- `halo-ds/tokens.css` — CSS-переменные, все 4 темы
- `halo-ds/theme.ts` — TypeScript, переключение тем
- `halo-ds/components/` — компоненты

Если значение здесь расходится с кодом Halo DS — **побеждает код**. Предлагай правки в `tokens.css`, не дивергируй.

## 1. Бренд

Атмосфера: тёплый, успокаивающий, премиальный — но не клинический. Что-то между Aman и Glossier.

**Не мы**: аптечный белый, корпоративный медицинский синий, SaaS-фиолетовый, финтех-резкость, bento grids, glassmorphism.

## 2. Цвета

Halo DS — 4 темы. Тема задаётся через `[data-halo-theme]` на `<html>`. Переключение: `applyHaloTheme()` из `halo-ds/theme.ts`.

**Никогда не хардкодить hex в JSX.** Использовать CSS-переменные (`var(--halo-accent)`) или Tailwind-классы (`text-halo-accent`, `bg-halo-card`).

### Тема: cream (default — «тёплая бумага»)

```
Поверхности:
  --halo-paper:        #FAF5EE      ← фон страницы
  --halo-paper-deep:   #F3EADC      ← углублённые поверхности
  --halo-card-bg:      rgba(255,253,248, 0.62)   ← glass-карточки
  --halo-border:       rgba(42,31,24, 0.08)

Текст (ink):
  --halo-ink:          #2A1F18      ← основной
  --halo-ink-soft:     #6B5D52      ← вторичный
  --halo-ink-mute:     #A89A8E      ← третичный/placeholder

Акцент (терракота):
  --halo-accent:       #D9613A
  --halo-accent-deep:  #A6431F
  --halo-accent-soft:  #FFE6DC
  --halo-warm:         #E8B98C

Кольца / семантика:
  --halo-ring-1:  #D9613A   (hydration — терракота)
  --halo-ring-2:  #C9924A   (texture — янтарь)
  --halo-ring-3:  #647A4E   (tone — зелёный)
  --halo-green:   #647A4E
  --halo-amber:   #C9924A
  --halo-red:     #D9613A
```

### Тема: rose
```
  --halo-paper:   #FBF3F2
  --halo-accent:  #C0436F   (малиновый)
```

### Тема: sage
```
  --halo-paper:   #F3F6EE
  --halo-accent:  #4F7A4D   (зелёный шалфей)
```

### Тема: midnight (dark)
```
  --halo-paper:          #161210
  --halo-ink:            #F5EFE4
  --halo-accent:         #E87A55   (тёплый терракота на тёмном)
```

### Правила

- Фон страницы — `--halo-paper` (тёплый, не `#FFFFFF`).
- Акцент (`--halo-accent`) меняется от темы. Не предполагай терракоту — всегда читай через переменную.
- Для нейтрального текста: `--halo-ink-*`. Никогда `text-gray-500`, `text-zinc-400` и т.д.
- Ошибки / danger: `--halo-red` (в cream-теме совпадает с акцентом — это намеренно).

### Расхождение в globals.css

В `packages/web/app/globals.css` живёт старая параллельная система (`--color-primary`, `--color-peach`, `--background-gradient` и т.д.). Она предшествует Halo DS и используется некоторыми старыми компонентами вне halo-ds/. **Для новых компонентов использовать только Halo DS токены.** Старые переменные не убирать без ревью.

## 3. Типографика

### Шрифты (загружены в `app/layout.tsx` через Google Fonts)

| Семейство | Роль | Компонент |
|---|---|---|
| **Instrument Serif** (italic + regular) | Заголовки, «ритуальные» тексты | `<HaloHeading>` |
| **Inter** 400/500/600/700/800 | Тело, UI-метки, числа | основной шрифт body |
| **JetBrains Mono** 400/500/600/700 | Micro-теги, юниты, шаги (`:: STEP 03`) | `<HaloMono>` |

```css
--halo-font-serif: "Instrument Serif", "DM Serif Display", Georgia, serif;
--halo-font-sans:  "Inter", -apple-system, "SF Pro Display", system-ui, sans-serif;
--halo-font-mono:  "JetBrains Mono", "SF Mono", ui-monospace, monospace;
```

### Правила типографики

- **Instrument Serif** — для заголовков, эмоциональных хедлайнов. Используй `<HaloHeading>`.
- **Inter** — для всего интерфейса: кнопки, подписи, тело. Дефолтный шрифт `<body>`.
- **JetBrains Mono** — только для micro-тегов и технических меток. Используй `<HaloMono upper>`.
- Числовые баллы (паттерн «72/100»): **Inter 800**, не serif. Serif — для словесного контекста вокруг числа.
- Курсивный акцент внутри заголовка: `<HaloHeading>привет, <HaloEm>Аня</HaloEm></HaloHeading>`.
- Минимальный размер текста на экране: 12px. Основное тело — 13.5–15px.

### Запрещённые шрифты

Fraunces, Manrope, Roboto, Arial, Helvetica, Open Sans, Space Grotesk, Montserrat, Poppins, Nunito, Playfair Display.

## 4. Spacing scale (4px grid)

```
--halo-s-1:  4px
--halo-s-2:  8px
--halo-s-3:  12px
--halo-s-4:  16px
--halo-s-5:  20px
--halo-s-6:  24px
--halo-s-8:  32px
--halo-s-10: 40px
```

## 5. Border radius

```
--halo-r-xs:   8px    (мелкие чипы, dense-контролы)
--halo-r-sm:   12px   (поля, маленькие кнопки)
--halo-r-md:   16px   (default для карточек, кнопок)
--halo-r-lg:   20px   (крупные карточки, sheet-ы)
--halo-r-xl:   24px
--halo-r-2xl:  28px
--halo-r-pill: 999px  (пилюли, аватары)
```

Использовать `rounded-halo-md` (Tailwind utility) или `radius="md"` prop — не `rounded-md`.

## 6. Иконки

- Библиотека: **lucide-react** (уже в deps, `^1.16.0`)
- Размеры: 20px в tab bar, 16–18px в строках/списках, 12–14px в статусах
- Stroke: 1.5 (обычный) / 1.8–1.9 (активное состояние)
- Для scan/sparkle: иконка `Sparkles` из lucide

## 7. Компоненты Halo DS

| Потребность | Компонент |
|---|---|
| Любая grouped/contained поверхность | `<HaloGlass>` |
| Основная CTA | `<HaloButton variant="primary">` |
| Акцентная CTA (после скана и т.д.) | `<HaloButton variant="accent">` |
| Вторичное действие | `<HaloButton variant="soft">` |
| Ghost / tertiary | `<HaloButton variant="ghost">` |
| Micro-тег (uppercase mono) | `<HaloMono upper>` |
| Serif-заголовок | `<HaloHeading size="sm\|md\|lg\|xl">` |
| Курсивный акцент в заголовке | `<HaloEm>` |
| Визуализация баллов кожи | `<HaloRing values={[0.78, 0.62, 0.91]} />` |
| Sparkline-график | `<HaloSpark data={[…]} />` |
| Нижняя навигация | `<HaloTabBar tabs={…} />` |
| Bottom sheet / детали / picker | `<HaloSheet open onClose>` |

Если нужный компонент в Halo DS отсутствует — пиши в `components/<feature>/` на Halo-примитивах. Не тяни shadcn, MUI, Chakra.

## 8. Layout

- **Mobile-first**. Приложение 360–430px шириной. Большие desktop-лейауты не добавлять без задачи.
- Паддинг glass-карточек: 16–20px. Border-radius: 14–20px.
- Зазор между карточками: 8–12px. Между секциями: 16–22px.
- Нижняя часть tab-routed экранов: `padding-bottom: 110px` — чтобы не перекрывал tab bar.
- Touch targets ≥ 44px, зазор ≥ 8px.

## 9. Анимации

- Entrance-эффекты: `.halo-anim-fade-up`, `.halo-anim-fade-in`, `.halo-anim-sheet-in` (из `animations.css`)
- Easing: `var(--halo-ease)` (decel) / `var(--halo-ease-out)` (spring с overshoot)
- Длительности: `--halo-dur-fast: 180ms`, `--halo-dur-base: 300ms`, `--halo-dur-slow: 520ms`
- Тактильный фидбек: класс `halo-press` (scale 0.97 on active)
- `prefers-reduced-motion` уже обработан в `animations.css`

Запрещено: bounce-spring ротации, параллакс-декорации, бесконечные вращения, particle/sparkle-эффекты.

## 10. Голос (Russian, «ты»)

Тёплый, знающий, кратко.

### Результат скана
✅ «ты сегодня на 72 — двигаемся»  
✅ «за неделю +4 — это хороший знак»  
❌ «Ваш результат анализа кожи: 72/100»

### Empty state
✅ «тут пока пусто. сделай первый скан — займёт минуту»  
❌ «Записи отсутствуют»

### Ошибка
✅ «не получилось загрузить — попробуй ещё раз?»  
❌ «Произошла ошибка. Код 502»

### Правила
- «ты», low-case начало фраз, разговорный тон
- Числа всегда парятся со словами: «+4 за неделю», «осталось 2 шага»
- Без эмодзи в продуктовом UI (✦ и иконки — ок)
- Без восклицательных знаков кроме настоящего праздника
- Нет «Уважаемый пользователь», «Вы», «Клиент»

## 11. Что НЕ делать (строго)

- Хардкодить hex/rgb в JSX style props — только CSS-переменные или Tailwind
- `box-shadow: 0 2px 4px rgba(0,0,0,0.1)` — только `var(--halo-shadow-card)` и семейство
- Вводить новый акцентный цвет — есть один акцент, он theme-driven
- `rounded-md` (Tailwind default) — использовать `rounded-halo-md`
- Градиентные кнопки или градиентный текст
- Декоративные эмодзи (исключения: 🔥 для стриков, ✦ для sparkle/scan)
- `text-gray-500`, `bg-white` — нейтралы только через `--halo-ink-*` и `--halo-paper`
- Bento grids, glassmorphism-наводнение, SaaS-градиенты
