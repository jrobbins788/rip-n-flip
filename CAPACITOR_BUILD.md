# FLIP n' RIP — Android Build (Capacitor)

This wraps the React PWA in a Capacitor Android shell so you can ship to Google Play as a `.aab`.

The web app is fully PWA-ready (manifest, service worker, offline page, install prompt, safe-area), so users can also install from the browser without the Play Store.

---

## Prerequisites (one-time, on your dev machine)

> The Emergent preview pod **cannot** build native Android — Android SDK + JDK 17 + Gradle aren't installed and the AAB signing must happen on a machine you control. Build locally.

1. **Node 20.x** (already used by this repo) and **yarn 1.22**
2. **JDK 17** — `brew install openjdk@17` (macOS) or apt equivalent
3. **Android Studio** (latest) — installs Android SDK + Build Tools + Platform 34
4. Set `ANDROID_HOME` env var to your SDK path

---

## First-time setup

From a fresh clone, run these once:

```bash
cd frontend
yarn install
yarn build              # produces ./build (Capacitor's webDir)
npx cap add android     # creates ./android folder (commit this)
npx cap sync android    # copies build/ + plugins into android/
```

`yarn build` may fail in the preview pod due to size — run it on your dev machine.

---

## Day-to-day build loop

```bash
cd frontend
yarn build && npx cap sync android
npx cap open android    # opens Android Studio
```

In Android Studio:

* **Run → Run 'app'** to test on emulator / connected device.
* **Build → Generate Signed Bundle / APK → Android App Bundle (.aab)** to produce the Play Store artifact.

---

## App identity

| Field | Value |
| --- | --- |
| App ID | `com.flipnrip.app` |
| App Name | `FLIP n' RIP` |
| Web Dir | `build` |
| Splash BG | `#050505` (matches dark theme) |
| Status Bar | `DARK` style, `#050505` background |
| Min SDK | 22 (Capacitor 7 default — Android 5.1+) |
| Target SDK | 34 (Play Store requirement) |

---

## Splash + Icons

Replace these after running `npx cap add android`:

* `android/app/src/main/res/mipmap-*/ic_launcher.png` — use `frontend/public/icon-192.png` or upgrade with the Image Asset Studio in Android Studio
* `android/app/src/main/res/drawable/splash.png` — generate at the sizes Android wants

A quick way to bulk-generate:

```bash
npm i -g @capacitor/assets
# Place a 1024×1024 PNG at frontend/resources/icon-only.png
# Place a 2732×2732 PNG (logo on dark bg) at frontend/resources/splash.png
npx capacitor-assets generate --android
```

---

## Production-mode SW notes

* The PWA service worker (`public/sw.js`) is bundled into the `build/` output. Capacitor serves it from the WebView, so the app remains offline-capable even installed from the Play Store.
* Set `server.androidScheme: "https"` in `capacitor.config.json` (already done) so the SW is allowed to register.

---

## Play Store checklist

- [ ] Bump version in `android/app/build.gradle` (`versionCode` + `versionName`)
- [ ] Sign with upload keystore (Android Studio → Generate Signed Bundle)
- [ ] Privacy policy URL (required for Play Store account)
- [ ] Feature graphic 1024×500 + 2 phone screenshots (per Play Store)
- [ ] Content rating questionnaire
- [ ] Submit `.aab` to internal testing → closed → open → production track

---

## Useful commands

```bash
npx cap doctor                # checks env health
npx cap copy android          # only copies web assets (faster than sync)
npx cap update android        # updates plugins
```
