# DESIGN_SYSTEM.md — Dogfood 2026 (Team CodeHawk)

Derived from `reference_landing.pdf` (RiskSentinel X landing page). Token values below were
extracted from the reference file's actual fills and type sizes, not eyeballed.

**This file is the single source of truth for tokens.** Per `PLAN.md` §3, mirror everything in
Sections 2–6 into `web/tailwind.config.ts` (`theme.extend`) and/or `web/src/styles/tokens.ts`, then
re-skin existing components. Where the reference PDF's layout implies a token that conflicts with
this file, **this file wins** — the PDF is layout/composition guidance only.

---

## 1. Design intent

The reference reads as **institutional software, not marketing**: near-white page, one saturated
blue, navy ink, generous whitespace, and thin hairline rules instead of heavy borders. Product
surfaces (tables, panels, dashboards) are shown *as themselves* — real data, monospace IDs,
timestamps — and are the visual hero. Nothing is decorative.

Applied to a hackathon platform, that means:

- **Data is the decoration.** Score tables, judge progress, submission lists, audit trails get the
  visual weight. No hero illustrations, gradients-as-filler, or stock imagery.
- **One accent colour, used sparingly.** Blue marks the single primary action per view, active nav,
  and links. Everything else is ink and grey.
- **Status is stated, never only coloured.** Reference badges (`Block` / `Review` / `Allow`) pair a
  tinted background with a text label. `PLAN.md` §4.5 requires this — keep it.
- **Hairlines over boxes.** Row separators and 1px borders on `border-subtle`, not shadows or fills.
- **Honest density.** Small, high-contrast type in tables; large type only for page titles and
  headline numbers.

---

## 2. Colour

### 2.1 Brand / accent

| Token | Hex | Use |
|---|---|---|
| `brand-500` | `#2F6BFF` | Primary buttons, links, active nav, focus ring, full-bleed accent band |
| `brand-600` | `#255DF5` | Button hover, link hover |
| `brand-700` | `#2450CF` | Button active/pressed |
| `brand-100` | `#ECF2FF` | Selected row, info badge bg, chip bg |
| `brand-50`  | `#F2F6FF` | Subtle tinted panel / hovered table row |
| `brand-25`  | `#F5FAFF` | Hero wash, page-top tint |

### 2.2 Ink (text)

| Token | Hex | Use |
|---|---|---|
| `ink-900` | `#171D29` | Display / hero headings |
| `ink-800` | `#17283E` | H2–H4, table headline values, emphasis |
| `ink-700` | `#43516A` | Body copy |
| `ink-600` | `#64758D` | Secondary body, table cell text |
| `ink-500` | `#7B8DA5` | Meta, captions, helper text |
| `ink-400` | `#8B95A6` | Eyebrow labels, column headers, monospace IDs |

### 2.3 Surface

| Token | Hex | Use |
|---|---|---|
| `surface-0` | `#FFFFFF` | Cards, panels, table bodies, modals |
| `surface-50` | `#FCFCFD` | Inset panel inside a card |
| `surface-100` | `#F7F9FC` | Table header row, card footer strip |
| `surface-200` | `#F4F6FA` | Page background |
| `navy-900` | `#071936` | Shadow tint source only (see §6) |
| `navy-800` | `#1F2B42` | Dark product-frame chrome (used sparingly) |

### 2.4 Border

| Token | Hex | Use |
|---|---|---|
| `border-default` | `#E6EBF2` | Card and input borders |
| `border-subtle` | `#EDF0F5` | Table row hairlines, dividers |
| `border-strong` | `#DCE3EC` | Hovered/focused container, active tab underline base |

### 2.5 Status

Each status is a **tint + text colour + required text label**. Never colour alone.

| Status | Bg | Text | Platform meaning |
|---|---|---|---|
| `danger` | `#FFF1EF` | `#B42318` | Deadline passed, validation error, destructive confirm, rejected |
| `warning` | `#FFF7E8` | `#B54708` | Needs attention: unsubmitted scores, incomplete rubric, results hidden |
| `success` | `#ECF8F2` | `#177148` | Saved, submitted, complete, green acceptance check |
| `info` | `#ECF2FF` | `#2450CF` | Neutral state: draft, pending assignment, in review |

Accessibility: every pairing above clears WCAG AA (4.5:1) on its own tint. `ink-500` and lighter are
for ≥13px non-essential meta only — never for body copy or form labels.

### 2.6 Role badges

Roles use ink + border, **not** the status palette (a role is not a state):

- `participant` → `surface-100` bg / `ink-700` text / `border-default`
- `judge` → `brand-100` bg / `brand-700` text / `brand-500` @ 20% border
- `organizer` → `navy-800` bg / `#FFFFFF` text
- `admin` → `navy-800` bg / `#FFFFFF` text, with a distinguishing glyph prefix

---

## 3. Typography

### 3.1 Families

| Token | Stack |
|---|---|
| `font-sans` | `Inter, "Inter var", -apple-system, "Segoe UI", system-ui, sans-serif` |
| `font-serif-accent` | `"Instrument Serif", Georgia, "Times New Roman", serif` — *italic only* |
| `font-mono` | `"JetBrains Mono", Consolas, ui-monospace, monospace` |

> **Offline constraint (`PLAN.md` §1):** no CDN font links. Self-host `Inter` (and the accent serif,
> if used) as `.woff2` under `web/public/fonts/` with `@font-face` + `font-display: swap`. If a
> self-hosted file isn't committed, fall back to the system stack above — do **not** add a
> `fonts.googleapis.com` `<link>`.

The reference uses the italic serif for exactly one word in the hero (`workspace.`). Use it at most
once per page, in the landing hero only. It never appears in product UI.

### 3.2 Scale

Ratios are taken from the reference; px values assume a 16px root.

| Token | Size / line-height | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | `clamp(2.25rem, 4.5vw, 3.5rem)` / 1.05 | 700 | `-0.02em` | Landing hero only |
| `h1` | `2.125rem` (34px) / 1.15 | 700 | `-0.015em` | Page titles |
| `h2` | `1.75rem` (28px) / 1.2 | 600 | `-0.01em` | Section headings |
| `h3` | `1.25rem` (20px) / 1.3 | 600 | `0` | Card titles, panel headers |
| `body-lg` | `1.125rem` (18px) / 1.6 | 400 | `0` | Landing / intro copy |
| `body` | `0.9375rem` (15px) / 1.55 | 400 | `0` | App body, table cells, form values |
| `label` | `0.8125rem` (13px) / 1.4 | 500 | `0` | Form labels, buttons, nav |
| `meta` | `0.75rem` (12px) / 1.4 | 400 | `0` | Helper text, timestamps, captions |
| `eyebrow` | `0.6875rem` (11px) / 1.2 | 600 | `0.12em`, uppercase | Section kickers, table column headers |
| `mono` | `0.75rem` (12px) / 1.4 | 400 | `0` | IDs, hashes, trace/audit values |

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

---

## 5. Radii

| Token | Value | Use |
|---|---|---|
| `radius-sm` | `6px` | Badges, chips, small inputs |
| `radius-md` | `8px` | Buttons, inputs, selects |
| `radius-lg` | `12px` | Cards, panels, table containers |
| `radius-xl` | `16px` | Product-frame / dashboard preview shells, modals |
| `radius-full` | `999px` | Avatars, dot indicators, pill counters |

---

## 6. Elevation

Shadows are navy-tinted and low-opacity; the reference leans on borders, not depth.

| Token | Value |
|---|---|
| `shadow-none` | flat + `1px` `border-default` — **the default for cards** |
| `shadow-sm` | `0 1px 2px rgba(7, 25, 54, 0.05)` |
| `shadow-md` | `0 4px 16px rgba(7, 25, 54, 0.06)` — hovered interactive card |
| `shadow-lg` | `0 16px 48px rgba(7, 25, 54, 0.10)` — dropdowns, popovers, modals, toasts |

Never stack a shadow on a bordered table row. One elevation level per surface.

---

## 7. Components

### 7.1 Buttons

Height `36px` (`sm: 32px`, `lg: 44px`), `radius-md`, `label` type, `padding: 0 16px`,
`transition: 120ms ease-out`. Trailing arrow icon sits right of the label at `8px` gap.

| Variant | Rest | Hover | Active | Disabled |
|---|---|---|---|---|
| `primary` | `brand-500` bg / white text | `brand-600` | `brand-700` | `brand-500` @ 40%, `cursor-not-allowed` |
| `secondary` | `surface-0` bg / `ink-800` text / `border-default` | `surface-100` bg, `border-strong` | `surface-200` | 50% opacity |
| `ghost` | transparent / `ink-700` text | `surface-100` bg | `surface-200` | 50% opacity |
| `danger` | `#B42318` bg / white text | `#98180F` | `#7F1410` | 40% opacity |

**One `primary` per view.** In-flight state: disable the control, swap the label to a spinner +
`Saving…` — required by `PLAN.md` §4.1 to block double-submits.

### 7.2 Inputs

`40px` height, `radius-md`, `surface-0` bg, `1px border-default`, `body` type, `12px` horizontal
padding. Label above at `label` type / `ink-800`, `6px` gap. Helper/error text below at `meta`.

- Focus: `border-color: brand-500` + `box-shadow: 0 0 0 3px rgba(47,107,255,0.18)`.
- Error: `border-color: #B42318`, error message in `#B42318` at `meta`, `aria-invalid` +
  `aria-describedby` set. Validation fires on blur and on change after first blur
  (`PLAN.md` §4.3).
- Never remove the focus ring. Never signal error with colour alone — always the message text.

### 7.3 Cards & panels

`surface-0`, `radius-lg`, `1px border-default`, `shadow-none`, `p-6`. Optional header row
(`h3` + right-aligned `meta`) separated by a `border-subtle` hairline. Optional footer strip on
`surface-100` with `meta` text — used in the reference for provenance lines
("One payment. One accountable record."); use it for audit/attribution lines.

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

`radius-sm`, `eyebrow` type (11px/600/uppercase, `0.06em`), `2px 8px` padding, tint + text from
§2.5 or §2.6, always with a text label.

### 7.6 Navigation

- Top bar: `64px`, `surface-0`, `1px border-subtle` bottom, sticky. Wordmark left, links centre-left
  at `label` / `ink-700`, actions right (`ghost` "Log in" + `primary` CTA), as in the reference.
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
*the* number the page is about (the reference does this once, for the risk score).

### 7.9 Stepper / process strip

The reference's numbered strip (`01` → `05`) maps to the judging lifecycle. Full-bleed `brand-500`
band, white text, `01`-style `mono` index in white @ 60%, `eyebrow` label, `h3` value, `meta`
caption, arrow glyph between steps; `1px` white @ 20% dividers. Stacks vertically below `md`.

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

## 10. Landing page composition (from the reference)

Rebuild the landing page in this order, using the tokens above:

1. **Nav** — wordmark, 4 section links, `ghost` log-in + `primary` CTA (§7.6).
2. **Hero** — `eyebrow` kicker, `display` headline with one italic-serif accent word, `body-lg`
   subhead (max `container-prose`), `primary` + `ghost` CTA pair, then a 3-column hairline-divided
   claim strip (bold term + one-line description), closing with a `meta` audience line.
3. **Product proof** — asymmetric `4 / 8` split: left `eyebrow` + `h2` + `body` + text link; right a
   real product panel (`radius-xl` frame, tabs, metric tile, evidence list) showing actual seeded data.
4. **Numbered list section** — `eyebrow` label left, `body-lg` intro right, then `01/02/03` rows with
   `border-subtle` hairlines; the active row gets a `brand-500` left border.
5. **Timeline / trail** — `mono` timestamp column, label column, right-aligned value column; the final
   row tinted `danger`/`success` as the outcome. Maps to the audit log.
6. **Capability cards** — horizontal card row, `01`-style index top-right, two-tone heading (`brand-500`
   lead sentence + `ink-800` continuation), `body` in `ink-600`, an "Explore feature" text link,
   horizontal scroll with a progress rail below `lg`.
7. **Dashboard preview** — `4 / 8` split with a full app-shell panel (sidebar + metric tiles + recent
   decision rows with status badges).
8. **Accent band** — full-bleed `brand-500` numbered strip (§7.9) + a `meta` caption row.
9. **Footer** — wordmark, one-line positioning statement, link row, hairline divider, `meta` legal row.

Copy tone: short declarative sentences, no exclamation marks, no growth-marketing superlatives.
State what the system does and who is accountable — e.g. "Judges score. Normalization decides."

---

## 11. Implementation checklist

- [ ] `web/tailwind.config.ts` → `theme.extend` carries §2–§6 verbatim (colours, fontFamily,
      fontSize, spacing, borderRadius, boxShadow, transitionDuration).
- [ ] `web/src/styles/tokens.ts` exports the same values for TS consumers; nothing hardcodes a hex.
- [ ] Self-hosted `@font-face` rules under `web/public/fonts/` — zero external font requests.
- [ ] `web/src/components/ui/` (Button, Input, Card, Badge, Table, MetricTile) matches §7.
- [ ] `web/src/components/feedback/` (Toast, Skeleton, EmptyState, ErrorState, InlineStatus,
      ConfirmDialog) matches §7.7.
- [ ] Existing Tailwind-default components re-skinned — no mixed old/new styling left behind.
- [ ] Landing page rebuilt per §10.
- [ ] `grep` for raw hex values in `web/src/` returns only `tokens.ts` / `tailwind.config.ts`.
