# Design system

Source of truth: approved mockups (https://claude.ai/artifact/1FACLDLoSx3hTmETMXnVr9). Live showcase: `/en/design` and `/es/design`.

## Tokens
- Defined once as CSS variables in `apps/web/styles/tokens.css`; Tailwind maps them in `apps/web/tailwind.config.ts` (`bg-primary`, `text-flag-text`, `rounded-card`, …). Components never use raw hex values.
- Colour rule: **blue = primary / good**, **orange = needs attention**. Never red vs green (colour-blind safe). Score bars switch to orange below 70.
- Type: IBM Plex Sans + IBM Plex Mono, self-hosted with `@fontsource`. Mono is for data values, codes and canonical field names.
- Radius: 4 px chips · 6 px nav · 8 px controls · 10 px inner panels · 12 px cards. Touch targets ≥ 44 px.

## Components (`apps/web/components`)
| Component | File | Notes |
|---|---|---|
| Header + LifecycleNav | `layout/Header.tsx`, `layout/LifecycleNav.tsx` | 1–5 lifecycle steps, `aria-current="page"` on the active step |
| LanguageSwitcher | `layout/LanguageSwitcher.tsx` | `EN | ES`, keeps the current path, cookie `NEXT_LOCALE` |
| Button / ButtonLink | `ui/Button.tsx` | primary · secondary · ghost · attention · attentionOutline · inverse; hover/focus/disabled |
| Card | `ui/Card.tsx` | default · attention · dark |
| Badge | `ui/Badge.tsx` | language · format · flag · success · info |
| Alert | `ui/Alert.tsx` | warning · pii · info |
| IssueCard | `ui/IssueCard.tsx` | slots for options/preview so the parent wires live updates |
| OptionRadio | `ui/OptionRadio.tsx` | Radix RadioGroup + hints |
| BeforeAfter | `ui/BeforeAfter.tsx` | `aria-live` so changes are announced |
| KpiTile | `ui/KpiTile.tsx` | tones positive · attention · neutral |
| ScoreBar | `ui/ScoreBar.tsx` | `role="meter"` |
| DataTable | `ui/DataTable.tsx` | horizontal scroll in a focusable region |
| CodeBlock | `ui/CodeBlock.tsx` | dark, copy button; code is never translated |
| Tabs | `ui/Tabs.tsx` | Radix Tabs, light (ML models) and dark (recipe) variants; disabled = "later" |
| EmptyState, Skeleton/SkeletonGroup, WakingUp | `ui/*.tsx` | loading/empty/cold-start states, all translated |

## i18n rules enforced by tooling
- `react/jsx-no-literals` (`noStrings`) + `no-restricted-syntax` on `aria-label`/`alt`/`title`/`placeholder`: no hardcoded UI text in JSX. Data values and code live in constants.
- `scripts/check_i18n.py`: same keys and same ICU placeholders in `en.json` and `es.json`, no empty values.
- Formatting through `apps/web/lib/format.ts` (`en-CA` / `es-CO`), currency code always visible.
- `npm run test:a11y`: axe (WCAG 2.1 A/AA + best practices) on `/en`, `/es`, `/en/design`, `/es/design` at 1280 and 375 px, plus a horizontal-overflow check.
