# DESIGN_SYSTEM.md — Dogfood 2026 (Team CodeHawk)

**Rebuilt in Phase 5 from a live self-check of [raptors.dev](https://www.raptors.dev/)** —
Hackathon Raptors' actual site, referenced by `hackraptors.pdf`. This supersedes the system
originally derived from `reference_design.pdf` (RiskSentinel X), per an explicit later decision
to make the reference the actual design-system source, not positioning/copy only (see
`PLAN.md`'s Open Questions for both the original decision and this reversal).

**Method:** rather than eyeballing `hackraptors.pdf`'s poster imagery, the live site's DOM was
inspected directly — `getComputedStyle()` on real elements, and every `:root` custom property —
so every value below is a real, measured number, not an estimate. Where the reference has no
equivalent (it's a marketing site with no dense data UI), that's stated explicitly rather than
silently invented.

**This file is the single source of truth for tokens.** Per `PLAN.md` §3, mirror everything in
Sections 2–6 into `web/tailwind.config.ts` (`theme.extend`) and/or `web/src/styles/tokens.ts`,
then re-skin existing components. Where the reference's layout implies a token that conflicts
with this file, **this file wins**.

---

## 1. Design intent

raptors.dev's actual UI chrome is **genuinely monochrome** — ink-on-cream, with a dark-mode
variant, and no saturated brand hue anywhere in its `:root` custom properties, its buttons, or
its badges (all confirmed by reading the live computed styles, not assumed from the colorful
poster artwork, which is the *content*, not the *chrome*). Applied to a hackathon platform:

- **Content is the colour, chrome is not.** The illustrated event posters/submission covers are
  where colour lives, exactly as on the reference. UI elements — buttons, badges, nav, panels —
  stay ink and cream.
- **One ink scale doubles as the brand scale.** There is no separate "primary blue" to sample;
  the darkest ink tone (`#1F2426`) *is* the primary action colour, used the way a brand hue
  usually would be (filled primary buttons, the accent band). This is a disclosed adaptation of
  what's actually there, not an invented palette.
- **Outline over fill.** The reference's real buttons and badges are transparent-background,
  ink-border, ink-text — filled colour is the exception, reserved for the one primary CTA per
  view and for semantic status.
- **Status still needs colour + a label.** The reference has no functional status UI to sample
  (it's a portfolio, not a workflow app) — `PLAN.md` §4.5 still requires status never be colour
  alone, so §2.5's tints are a necessary, disclosed adaptation, kept close to the reference's
  editorial, slightly muted tone rather than bright SaaS hues.
- **Tight, confident type.** Real measured headings carry noticeably negative letter-spacing
  (≈ −3%) at medium (500) weight, not bold — an editorial voice, not a corporate one.
- **A serif accent phrase, not one word.** The reference sets a short italic Playfair Display
  phrase inline within a Satoshi headline (`"specializing on"` in their hero) — a few words, not
  a single word.

---

## 2. Colour

### 2.1 Brand / accent — the ink scale itself (see §1)

| Token | Hex | Use |
|---|---|---|
| `brand-500` | `#1F2426` | Primary buttons, links, active nav, focus ring, full-bleed accent band — real measured ink from raptors.dev's `--dark` |
| `brand-600` | `#171B1C` | Button hover, link hover |
| `brand-700` | `#0E1112` | Button active/pressed |
| `brand-100` | `#E7E9E9` | Selected row, info badge bg, chip bg |
| `brand-50`  | `#F1F2F2` | Subtle tinted panel / hovered table row |
| `brand-25`  | `#F8F9F9` | Hero wash, page-top tint — real measured `--body-bg` |

### 2.2 Ink (text)

| Token | Hex | Use |
|---|---|---|
| `ink-900` | `#1F2426` | Display / hero headings — real measured `--dark` |
| `ink-800` | `#282D2E` | H2–H4, table headline values, emphasis |
| `ink-700` | `#3C4344` | Body copy |
| `ink-600` | `#565D5F` | Secondary body, table cell text |
| `ink-500` | `#6F7678` | Meta, captions, helper text |
| `ink-400` | `#8C9294` | Eyebrow labels, column headers, monospace IDs |

### 2.3 Surface

| Token | Hex | Use |
|---|---|---|
| `surface-0` | `#FFFFFF` | Cards, panels, table bodies, modals |
| `surface-50` | `#FCFCFC` | Inset panel inside a card |
| `surface-100` | `#F1F2F2` | Table header row, card footer strip |
| `surface-200` | `#F8F9F9` | Page background — real measured `--body-bg` |
| `navy-900` | `#12181A` | Dark-mode background equivalent, shadow tint source (see §6) — real measured `--body-bg-dark` |
| `navy-800` | `#1F2426` | Dark product-frame chrome, mobile nav overlay — real measured `--menu-bg` (`#1F2426E6`, 90% opacity) |

### 2.4 Border

| Token | Hex | Use |
|---|---|---|
| `border-default` | `#DEE0E0` | Card and input borders |
| `border-subtle` | `#EAEBEB` | Table row hairlines, dividers |
| `border-strong` | `#C9CCCC` | Hovered/focused container, active tab underline base |

### 2.5 Status — adapted, not sourced (see §1)

Each status is a **tint + text colour + required text label**. Never colour alone.

| Status | Bg | Text | Platform meaning |
|---|---|---|---|
| `danger` | `#FBEDEC` | `#B3271E` | Deadline passed, validation error, destructive confirm, rejected |
| `warning` | `#FBF2E4` | `#9C5B0E` | Needs attention: unsubmitted scores, incomplete rubric, results hidden |
| `success` | `#EAF3EC` | `#2F6B45` | Saved, submitted, complete, green acceptance check |
| `info` | `#EBEEEE` | `#33393A` | Neutral state: draft, pending assignment, in review — ink-tinted, since the reference has no blue to reuse here |

Accessibility: every pairing above clears WCAG AA (4.5:1) on its own tint. `ink-500` and lighter are
for ≥13px non-essential meta only — never for body copy or form labels.

### 2.6 Role badges

Roles use ink + border, **not** the status palette (a role is not a state):

- `participant` → `surface-100` bg / `ink-700` text / `border-default`
- `judge` → `brand-100` bg / `brand-700`-equivalent (`ink-800`) text / `brand-500` @ 20% border
- `organizer` → `navy-800` bg / `#FFFFFF` text
- `admin` → `navy-800` bg / `#FFFFFF` text, with a distinguishing glyph prefix

---

## 3. Typography

### 3.1 Families — real, self-hosted, sourced from raptors.dev's live stylesheet

Confirmed by reading the live site's `:root` custom properties directly: `--sans:
"Satoshi Variable"`, `--serif: "Playfair Display"`. Both are self-hosted under
`web/public/fonts/` — `PLAN.md` §1 forbids CDN font requests in the served app, so this
supersedes the earlier "system stacks are canonical" decision (Phase 5.1) now that a request
explicitly asked for these named fonts.

| Token | Stack |
|---|---|
| `font-sans` | `Satoshi, -apple-system, "Segoe UI", system-ui, Roboto, Helvetica, Arial, sans-serif` |
| `font-serif-accent` | `"Playfair Display", Georgia, "Times New Roman", serif` — *italic only* |
| `font-mono` | `Consolas, "SF Mono", ui-monospace, monospace` — unchanged; the reference has no visible mono usage to sample |

**What's actually committed:** Satoshi static instances at weights 400/500/700 (Fontshare's
discrete API only offers fixed weights, not the full variable axis — a "weight 600" treatment
below uses 700, the closest available). Playfair Display at weight 700 normal and weight 600
italic (Google Fonts) — the italic 600 face is the one actually used, matching the reference's
own italic accent treatment.

The reference sets a short italic phrase inline in the hero (`"specializing on"`, not a single
word) at the same size as the surrounding headline. Use a short phrase, not one word; it never
appears in product UI, only the landing hero.

### 3.2 Scale

Real, measured from the live DOM where noted; interpolated where the reference has nothing to
sample (it has no dense app UI). Px values assume a 16px root.

| Token | Size / line-height | Weight | Tracking | Use | Source |
|---|---|---|---|---|---|
| `display` | `clamp(2.5rem, 6vw, 4.375rem)` (70px max) / 1.05 | 500 | `-0.03em` | Landing hero only | **Real**: raptors.dev's actual H1 |
| `h1` | `2.5rem` (40px) / 1.25 | 500 | `-0.03em` | Page titles | **Real**: raptors.dev's actual H2 (their H1 is used once, in the hero — that's `display` above) |
| `h2` | `1.75rem` (28px) / 1.3 | 500 | `-0.03em` | Section headings | Interpolated between `h1` and `h3` |
| `h3` | `1.5rem` (24px) / 1.42 | 500 | `-0.03em` | Card titles, panel headers | **Real**: raptors.dev's actual H3 |
| `body-lg` | `1.125rem` (18px) / 1.67 | 400 | `0` | Landing / intro copy | **Real**: raptors.dev's actual `<p>` |
| `body` | `0.9375rem` (15px) / 1.6 | 400 | `0` | App body, table cells, form values | Interpolated — kept smaller than `body-lg` so dense tables/forms stay compact; the reference has no such UI to sample |
| `label` | `0.875rem` (14px) / 1.4 | 700 | `0.03em`, uppercase | Form labels, buttons, nav | **Real**: raptors.dev's actual button (14px/600/uppercase/0.48px ≈ 0.03em; 700 used since 600 wasn't sourced, see §3.1) |
| `meta` | `0.75rem` (12px) / 1.4 | 400 | `0` | Helper text, timestamps, captions | Interpolated |
| `eyebrow` | `0.6875rem` (11px) / 1.2 | 700 | `0.03em`, uppercase | Section kickers, table column headers | Same convention as `label`, one step down — real badge tracking was 0.36px/12px ≈ 0.03em |
| `mono` | `0.75rem` (12px) / 1.4 | 400 | `0` | IDs, hashes, trace/audit values | Unchanged |

### 3.3 Numerals

Headline metrics (`94 / 100`, `43 of 51 scored`) use `h1`/`h2` size at weight 700 with
`font-variant-numeric: tabular-nums`. **All** numeric table columns and countdowns use
`tabular-nums` so digits don't jitter on update.

---

## 4. Spacing & layout

4px base scale (Tailwind default `1 = 0.25rem`). Use only: `1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24`.

| Token | Value | Use |
|---|---|---|
| `space-card` | `24px` (`p-6`) | Card / panel padding |
| `space-card-sm` | `16px` (`p-4`) | Dense card, table cell block |
| `space-stack` | `12px` | Gap between related elements |
| `space-group` | `24px` | Gap between groups in a form/panel |
| `space-section` | `64px` desktop / `40px` mobile | Vertical rhythm between page sections |
| `space-hero` | `96px` desktop / `56px` mobile | Landing hero padding |

**Containers**

- `container-page`: `max-width: 1200px`, side padding `24px` desktop / `16px` mobile.
- `container-prose`: `max-width: 65ch` for any paragraph run (docs, empty-state copy).
- Landing sections use an asymmetric split (label/heading left, content right) — a 12-col grid with
  a `4 / 8` split on desktop, stacking to one column below `768px`.

**Breakpoints** (must all be verified per `PLAN.md` §4.5)

| Name | Width |
|---|---|
| `sm` | 375px (mobile target) |
| `md` | 768px (tablet target) |
| `lg` | 1024px |
| `xl` | 1280px (desktop target) |

Tables below `md` become stacked key/value cards — never a horizontal scrollbar on a primary view.
Remember (Phase 0/1 audit finding): `sm` means **375px, on the phone** here, the opposite of
Tailwind's 640px default — a layout meant to switch *above* mobile must use `md:`, not `sm:`.

---

## 5. Radii

Real, measured from the live DOM: buttons `10px`, badges `50px` (a true pill).

| Token | Value | Use |
|---|---|---|
| `radius-sm` | `6px` | Small inputs, chips |
| `radius-md` | `10px` | Buttons, inputs, selects — **real measured value** |
| `radius-lg` | `14px` | Cards, panels, table containers |
| `radius-xl` | `18px` | Product-frame / dashboard preview shells, modals |
| `radius-full` | `999px` | Badges, avatars, dot indicators, pill counters — **real measured value** |

---

## 6. Elevation

Shadows are ink-tinted and low-opacity; the reference leans on borders, not depth.

| Token | Value |
|---|---|
| `shadow-none` | flat + `1px` `border-default` — **the default for cards** |
| `shadow-sm` | `0 1px 2px rgba(31, 36, 38, 0.05)` |
| `shadow-md` | `0 4px 16px rgba(31, 36, 38, 0.06)` — hovered interactive card |
| `shadow-lg` | `0 16px 48px rgba(31, 36, 38, 0.10)` — dropdowns, popovers, modals, toasts |

Never stack a shadow on a bordered table row. One elevation level per surface.

---

## 7. Components

### 7.1 Buttons

Height `36px` (`sm: 32px`, `lg: 44px`), `radius-md` (10px, real), `label` type (uppercase,
real), `padding: 0 16px`, `transition: 120ms ease-out`. Trailing arrow icon sits right of the
label at `8px` gap.

| Variant | Rest | Hover | Active | Disabled |
|---|---|---|---|---|
| `primary` | `brand-500` bg / white text | `brand-600` | `brand-700` | `brand-500` @ 40%, `cursor-not-allowed` |
| `secondary` | `surface-0` bg / `ink-800` text / `border-default` | `surface-100` bg, `border-strong` | `surface-200` | 50% opacity |
| `ghost` | transparent / `ink-700` text | `surface-100` bg | `surface-200` | 50% opacity |
| `danger` | `#B3271E` bg / white text | `#93211A` | `#761A14` | 40% opacity |

Real raptors.dev buttons are all outline (`secondary`/`ghost` above); `primary` (filled ink) is
the one addition a functional app needs for a clear single call-to-action per view, per §1.

**One `primary` per view.** In-flight state: disable the control, swap the label to a spinner +
`Saving…` — required by `PLAN.md` §4.1 to block double-submits.

### 7.2 Inputs

`40px` height, `radius-md`, `surface-0` bg, `1px border-default`, `body` type, `12px` horizontal
padding. Label above at `label` type / `ink-800`, `6px` gap. Helper/error text below at `meta`.

- Focus: `border-color: brand-500` + `box-shadow: 0 0 0 3px rgba(31,36,38,0.18)`.
- Error: `border-color: #B3271E`, error message in `#B3271E` at `meta`, `aria-invalid` +
  `aria-describedby` set. Validation fires on blur and on change after first blur
  (`PLAN.md` §4.3).
- Never remove the focus ring. Never signal error with colour alone — always the message text.

### 7.3 Cards & panels

`surface-0`, `radius-lg` (14px), `1px border-default`, `shadow-none`, `p-6`. Optional header row
(`h3` + right-aligned `meta`) separated by a `border-subtle` hairline. Optional footer strip on
`surface-100` with `meta` text for audit/attribution lines.

### 7.4 Tables

The core product surface. Use everywhere lists of data appear (gallery, assignments, scores, audit).

- Header row: `surface-100` bg, `eyebrow` type in `ink-400`, `border-subtle` bottom.
- Body rows: `surface-0`, `border-subtle` hairline between rows, `44px` min height, `12px 16px` cell
  padding, `body` in `ink-600` with the primary column in `ink-800` weight 500.
- Hover: `brand-50` bg. Selected: `brand-100` bg + `2px brand-500` left border.
- Numeric / ID columns: right-aligned, `tabular-nums`; IDs in `mono` / `ink-400`.
- Status column: badge from §2.5 with its text label.
- Every table ships the loading / empty / error states from §7.7.

### 7.5 Badges

`radius-full` (a true pill, real measured value), `eyebrow` type (uppercase, `700`, `0.03em`
tracking), `2px 12px` padding, tint + text from §2.5 or §2.6, always with a text label.

### 7.6 Navigation

- Top bar: `64px`, `surface-0`, `1px border-subtle` bottom, sticky. Wordmark left, links centre-left
  at `label` / `ink-700`, actions right (`ghost` "Log in" + `primary` CTA).
- Active link: `ink-900` + `2px brand-500` underline.
- Role-aware: links the current role can't use are **absent**, not disabled (`PLAN.md` §4.4).
- Sidebar (dashboards): `220px`, `surface-100` bg, `eyebrow` section label in `ink-400`, items at
  `label`; active item = `surface-0` bg + `brand-500` left border + `ink-900` text.
- Below `md`: top bar collapses to a hamburger sheet; sidebar becomes a horizontal scroll strip.

### 7.7 Feedback states (build once in `web/src/components/feedback/`)

| State | Spec |
|---|---|
| `Toast` | Bottom-right, `surface-0`, `radius-lg`, `shadow-lg`, `4px` left border in the status colour, status icon + `body` message. Auto-dismiss 5s (success/info); errors persist until dismissed. `role="status"`, errors `role="alert"`. |
| `Skeleton` | `surface-200` blocks at `radius-sm`, matching the real content's line heights. 1.4s ease-in-out opacity pulse (0.6→1). No spinner for whole-page loads. |
| `EmptyState` | Centred, max `container-prose`: `h3` headline stating *why* it's empty, `body` in `ink-600` stating what to do next, then one `primary` action **only if the current role can act**. |
| `ErrorState` | Same layout, `danger` icon, plain-language message (never a status code or stack trace), `secondary` "Try again" button. |
| `InlineStatus` | Autosave indicator next to forms: `meta` type — `Saving…` (`ink-500` + spinner) / `Saved` (`success` text + check glyph) / `Unsaved changes` (`warning` text). |
| `ConfirmDialog` | `radius-xl`, `shadow-lg`, max `480px`. `h3` title, `body` consequence in plain language ("This deletes 3 submissions and cannot be undone."), `danger` confirm + `secondary` cancel. Focus trapped, `Esc` cancels. |

### 7.8 Metric tiles

Dashboard headline numbers (`PLAN.md` §4.4 — lead with what matters). `surface-0`, `radius-lg`,
`border-default`, `p-6`: `eyebrow` label in `ink-400`, value at `h1` / weight 700 / `tabular-nums` /
`ink-800`, optional `meta` sub-line in `ink-500`. A tile's value turns `brand-500` only when it's
*the* number the page is about.

### 7.9 Stepper / process strip

A numbered strip (`01` → `05`) mapping to the judging lifecycle. Full-bleed `brand-500` band
(now ink-black, not blue — see §1), white text, `01`-style `mono` index in white @ 60%,
`eyebrow` label, `h3` value, `meta` caption, arrow glyph between steps; `1px` white @ 20%
dividers. Stacks vertically below `md`.

---

## 8. Motion

| Token | Value |
|---|---|
| `duration-fast` | `120ms` — hover, focus, button press |
| `duration-base` | `200ms` — disclosure, toast in/out, tab change |
| `duration-slow` | `320ms` — modal / sheet |
| `ease-standard` | `cubic-bezier(0.2, 0, 0.2, 1)` |

Animate `opacity` and `transform` only. No parallax, no scroll-jacking, no entrance animation on
data tables. Honour `@media (prefers-reduced-motion: reduce)`: drop transforms, keep opacity ≤ 80ms,
and freeze the skeleton pulse.

---

## 9. Accessibility floor (non-negotiable, per `PLAN.md` §4.5)

- Body text ≥ 4.5:1 contrast, ≥ 15px. `meta`/`eyebrow` greys are for supporting text only.
- Visible focus on every interactive element: `2px brand-500` outline, `2px` offset. Never
  `outline: none` without an equivalent replacement.
- Status, role, and results-hidden states carry a text label (and icon where space allows) in
  addition to colour.
- All interactions keyboard-operable; `Enter`/`Space` activate; tab order follows visual order;
  modals trap focus and restore it on close.
- Icons that carry meaning get `aria-label`; decorative ones get `aria-hidden="true"`.
- Tables use real `<th scope>`; forms use real `<label for>`.

---

## 10. Landing page composition

Built in Phase 5 (`web/src/pages/LandingPage.tsx` — no landing page existed before that; see
`PLAN.md`'s Open Questions). Composition, using the tokens above:

1. **Nav** — wordmark, section links, `ghost` log-in + `primary` CTA (§7.6). Reuses the app's
   real functional nav rather than a separate marketing nav.
2. **Hero** — `eyebrow` kicker, `display` headline with a short italic Playfair Display phrase
   (not one word — matches the reference exactly), `body-lg` subhead (max `container-prose`),
   `primary` + `ghost` CTA pair, then a 3-column hairline-divided claim strip, closing with a
   `meta` audience line.
3. **Product proof** — asymmetric `4 / 8` split: left `eyebrow` + `h2` + `body` + text link;
   right a real product panel showing **actual live data** (`GET /api/events`,
   `GET /api/gallery` — not a mockup).
4. **Numbered list section** — `eyebrow` label left, `body-lg` intro right, then `01/02/03` rows
   with `border-subtle` hairlines; the active row gets a `brand-500` left border.
5. **Timeline / trail** — `mono` timestamp column, label column, right-aligned value column; the
   final row tinted `success` as the outcome. Illustrative (the real audit log is organizer/admin
   only, so it can't be shown to an anonymous visitor).
6. **Capability cards** — horizontal card row, `01`-style index top-right, two-tone heading
   (`brand-500` lead sentence + `ink-800` continuation), `body` in `ink-600`, an "Explore
   feature" text link, horizontal scroll below `lg`.
7. **Dashboard preview** — `4 / 8` split with an illustrative app-shell panel (metric tiles +
   recent decision rows with status badges).
8. **Accent band** — full-bleed `brand-500` (ink-black) numbered strip (§7.9) + a `meta` caption
   row.
9. **Footer** — wordmark, one-line positioning statement, link row, hairline divider, `meta`
   legal row. Names Hackathon Raptors as the kind of organization this is built for (copy only,
   per the positioning decision this design-system rebuild doesn't override).

Copy tone: short declarative sentences, no exclamation marks, no growth-marketing superlatives.
State what the system does and who is accountable — e.g. "Judges score. Normalization decides."

---

## 11. Implementation checklist

- [x] `web/tailwind.config.ts` → `theme.extend` carries §2–§6 verbatim (colours, fontFamily,
      fontSize, spacing, borderRadius, boxShadow, transitionDuration) — unchanged mechanism,
      just re-derived values in `tokens.ts`.
- [x] `web/src/styles/tokens.ts` exports the same values for TS consumers; nothing hardcodes a hex.
- [x] Self-hosted `@font-face` rules under `web/public/fonts/` — Satoshi (400/500/700) and
      Playfair Display (700 normal, 600 italic), zero external font requests.
- [x] `web/src/components/ui/` (Button, Input, Card, Badge, MetricTile) matches §7 — Badge
      switched to a true pill (`rounded-full`) to match the real measured radius.
- [x] `web/src/components/feedback/` (Toast, Skeleton, EmptyState, ErrorState, InlineStatus)
      matches §7.7. `ConfirmDialog` and a dedicated `Table` primitive are not yet built —
      pages that need confirmation or tabular layout currently compose their own; flag if a
      screen needs either and neither exists.
- [x] Landing page built per §10 (Phase 5 — see `PLAN.md`'s Open Questions for why this was a
      correction, not a re-check).
- [x] `grep` for raw hex values in `web/src/` returns only `tokens.ts` (the only real hits found
      were HTML entity codes like `&#10003;`, not colours).
