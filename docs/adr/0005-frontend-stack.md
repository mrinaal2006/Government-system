# ADR 0005: Frontend stack and version pinning

**Status:** Accepted (Phase 1)

**Decision.** React 19, TypeScript 5.9, Vite 7, Tailwind CSS 4, React Router 7,
TanStack Query 5, Vitest 3, Playwright 1.63 (matches the provisioned browser).
Newer majors (TypeScript 7, Vite 8, Vitest 5) existed at the time but were not
adopted for a government foundation until they have a longer stability record.
All versions are pinned exactly and locked in `package-lock.json`.

Fonts (Noto Sans, Noto Sans Devanagari) are self-hosted from npm packages; the UI
loads nothing from third-party origins, which allows a strict CSP. ECharts and
Leaflet/MapLibre are added in the phases that use them (3 and 6).

**Known limitation.** ESLint 9 is end-of-life upstream; ESLint 10 is blocked by
`eslint-plugin-jsx-a11y` / `eslint-plugin-react-hooks` peer ranges. It is a
development-only tool (not shipped). Upgrade when the plugins support ESLint 10.
