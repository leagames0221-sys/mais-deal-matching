# design_tokens — mais-deal-matching UI 配色 / typography SSoT

> Week 4 FastAPI UI + 生成 doc / report は本 file の design tokens を literal 採用。
> source: MAIS HP (https://cr-mais.jp/) 観察 + original proposal HTML (`~/Desktop/mais_fde_aitools_proposal.html`) で実証済 slate palette。

---

## 観察元 (MAIS HP)

- URL: https://cr-mais.jp/
- 観察: dark navy/charcoal logo + off-white background + gray text + sans-serif modern + sophisticated minimal、 generous whitespace、 strategic SVG icons
- mood: 「simplicity meeting sophistication」 corporate executive aesthetic

## color palette (slate scale + 1 warm accent)

```css
:root {
  /* 9-step neutral (slate) */
  --c-ink: #0a0e27; /* logo / 主見出 */
  --c-ink-soft: #1e293b; /* sub 見出 / nav */
  --c-text: #334155; /* 本文 */
  --c-text-soft: #64748b; /* 補足 text */
  --c-line: #e2e8f0; /* divider */
  --c-line-soft: #eef2f7; /* zebra row */
  --c-bg: #fafaf9; /* page background */
  --c-bg-card: #ffffff; /* card */
  --c-accent: #475569; /* button / link primary */

  /* warm accent (highlight only、 ~5% 使用比率) */
  --c-mark: #b45309; /* h2 内強調 */

  /* hero gradient */
  --c-hero-from: #0f172a;
  --c-hero-to: #1e293b;
}
```

採用比率: ~95% neutral slate + ~5% warm amber = MAIS HP の sophisticated atmosphere に literal 一致 (φ-friendly ratio)。

## typography (黄金比 φ=1.618 scale)

```css
:root {
  --fs-xs: 0.764rem; /* badge / caption */
  --fs-sm: 0.875rem; /* table / sub */
  --fs-base: 1rem; /* body */
  --fs-md: 1.125rem; /* lead paragraph */
  --fs-lg: 1.382rem; /* h3 */
  --fs-xl: 1.618rem; /* h2 */
  --fs-2xl: 2.618rem; /* h1 desktop */
  --fs-3xl: 4.236rem; /* hero display */
}
```

font-family: `'Noto Sans JP', sans-serif`、 mono は `'JetBrains Mono', monospace` (数値 / code 用)。

## spacing (φ scale)

```css
:root {
  --sp-1: 0.382rem;
  --sp-2: 0.618rem;
  --sp-3: 1rem;
  --sp-4: 1.618rem;
  --sp-5: 2.618rem;
  --sp-6: 4.236rem;
  --sp-7: 6.854rem;
}
```

## line-height

```css
:root {
  --lh-tight: 1.3; /* 大見出 */
  --lh-snug: 1.45; /* 中見出 / table */
  --lh-base: 1.85; /* 本文 (日本語適性) */
  --lh-loose: 2; /* code block / loose layout */
}
```

## font-weight 分布

- 300 (light): hero lead paragraph
- 400 (regular): body default
- 500 (medium): badge / hero h1 accent / meta dt
- 600 (semibold): section number / table th / tool ID
- 700 (bold): h1 / h2 / h3 / h4 / strong / KPI num / tool title

900 weight は使用しない (静かな自信、 corporate executive aesthetic)。

## 採用元先行実装

本 design tokens は `~/Desktop/mais_fde_aitools_proposal.html` (MAIS 内部宛 FDE/AIP 提案、 約 49 KB) で literal 実証済。 同 file は 黄金比 audit clean、 mobile responsive (480px / 768px breakpoint)、 print-friendly。

## Week 4 UI 適用

FastAPI + Jinja2 で T1 matching UI を実装する Week 4 時に、 本 design tokens を `static/css/tokens.css` に copy + Jinja template から import する流れを想定。

## 関連

- original proposal (literal 採用 base): `~/Desktop/mais_fde_aitools_proposal.html`
- MAIS HP source: https://cr-mais.jp/
- 黄金比 audit history: original proposal logbook `internal/other-projects/internal_proposal/CURRENT_STATE.md` 2026-05-12 entry
