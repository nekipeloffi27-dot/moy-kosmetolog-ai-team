# Mobile stack — moy-kosmetolog (iOS + Android)

## Stack

- **Kotlin Multiplatform** for everything except platform-specific
  integrations
- **Compose Multiplatform** for shared UI (single source of truth across
  iOS + Android)
- **Ktor Client** for HTTP
- **SQLDelight** for local cache
- **kotlinx.serialization** for JSON
- **kotlinx.datetime** for time (NOT java.time, NOT Date)
- **Decompose** for navigation + state holders (component-based)
- **Koin** for DI
- **Kermit** for logging

## Why this stack

- Single codebase for iOS + Android UI, business logic, and storage layer.
- Compose Multiplatform is production-ready for our complexity in 2026.
- Decompose handles back-stack and process-death cleanly on both platforms.
- Ktor + kotlinx.serialization auto-generates the typed API client from
  OpenAPI.

## Layout

```
mobile/
├── composeApp/
│   ├── src/
│   │   ├── commonMain/
│   │   │   └── kotlin/com/moykosmetolog/
│   │   │       ├── App.kt
│   │   │       ├── di/
│   │   │       ├── ui/
│   │   │       │   ├── theme/          # OUR design tokens, NOT MD3 defaults
│   │   │       │   ├── components/     # buttons, cards, etc.
│   │   │       │   └── screens/
│   │   │       ├── feature/             # one folder per feature
│   │   │       │   ├── booking/
│   │   │       │   └── profile/
│   │   │       ├── data/
│   │   │       │   ├── api/             # Ktor client wrappers
│   │   │       │   ├── db/              # SQLDelight
│   │   │       │   └── repository/
│   │   │       └── domain/              # pure business logic, no platform
│   │   ├── androidMain/
│   │   │   └── kotlin/...               # Android-only entry, push tokens
│   │   ├── iosMain/
│   │   │   └── kotlin/...               # iOS-only entry, push tokens
│   │   └── commonTest/
│   ├── build.gradle.kts
├── iosApp/                                # SwiftUI shim for iOS entry
└── gradle/
```

## Conventions

- **All UI in `commonMain`**. The only iOS-specific code is the Swift shim in
  `iosApp/` plus push notification token handling in `iosMain`.
- **Design tokens in `ui/theme/`** mirror `DESIGN_SYSTEM.md` exactly. Define
  `Colors.kt`, `Typography.kt`, `Spacing.kt`, `Shapes.kt`, `Motion.kt`.
- **NOT Material 3 defaults**. Use `MaterialTheme` ONLY as the wrapper that
  feeds OUR tokens — never the auto-generated MD3 palette.
- **Lucide icons via Compose vector resources**. Convert SVGs from
  lucide.dev into XML vector assets.
- **No SwiftUI / UIKit / Jetpack views in feature code**. If you need a
  platform-specific component (camera, file picker), wrap it in an `expect`/
  `actual` declaration.
- **Datetimes**: `kotlinx.datetime.Instant` for storage, convert to
  `LocalDateTime` with system timezone for display.
- **Money in kopecks** as `Long` everywhere.

## Theming example (commonMain)

```kotlin
// ui/theme/Colors.kt
object KosmColors {
    val bgCanvas        = Color(0xFFFAF7F2)
    val bgElevated      = Color(0xFFFFFFFF)
    val bgTinted        = Color(0xFFF3EDE4)
    val textPrimary     = Color(0xFF1F1B16)
    val textSecondary   = Color(0xFF5C544A)
    val accent          = Color(0xFF2D5F4F)
    val accentSoft      = Color(0xFFE8EFE9)
    val blush           = Color(0xFFE8A89A)
    val blushSoft       = Color(0xFFFBEDE8)
    val border          = Color(0xFFE5DCD0)
}

// ui/theme/Typography.kt — uses Fraunces + Manrope (bundled as font assets)
object KosmTypography {
    val display = TextStyle(
        fontFamily = FraunsesFamily,
        fontWeight = FontWeight.Medium,
        fontSize = 56.sp,
        lineHeight = 64.sp,
        letterSpacing = (-0.02).em,
    )
    val h1 = TextStyle(/* … */)
    val body = TextStyle(
        fontFamily = ManropeFamily,
        fontSize = 15.sp,
        lineHeight = 24.sp,
    )
    // …
}
```

## Navigation

Decompose components:

```kotlin
class RootComponent(componentContext: ComponentContext) : ComponentContext by componentContext {
    private val navigation = StackNavigation<Config>()

    val childStack = childStack(
        source = navigation,
        initialConfiguration = Config.Home,
        childFactory = ::createChild,
    )

    @Serializable
    sealed class Config {
        @Serializable data object Home : Config()
        @Serializable data class Booking(val masterId: String) : Config()
    }
}
```

## Testing

- Unit tests in `commonTest` cover domain + repository layers.
- UI tests use Compose UI testing in `androidUnitTest` (iOS UI tests are
  expensive — defer).

## Build & deployment

- Android: `./gradlew :composeApp:assembleRelease` → Play Store internal
  testing track.
- iOS: `xcodebuild` from `iosApp/` → TestFlight.

## Pre-existing repo

Repo: see `GITHUB_REPO_MOBILE` in `.env`.
Default branch: `main`.
PR title format: `[<feature_id_short>] <task title>`.
Branch naming: `feat/<feature_id_short>/<slug>`.
