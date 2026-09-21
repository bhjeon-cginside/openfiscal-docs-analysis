# Design

## Source of truth
Active · 2026-09-21 · `docs/type-examples/`. Evidence: existing page and live
GitHub Pages screenshot; `docs/data/type_samples.json`; report manifest; official
UOPKOFDA03 HTML (`clsDivLc`, `clsDivMc`, `clsDivSc`, `odtNm`).

## Brand
Evidence-first Korean public-finance document review. Preserve navy/blue, white
cards, restrained badges, readable document images. Avoid unverified judgments.

## Product goals
Browse report samples by 대분류 → 중분류 → 소분류 → 재정데이터명 to support later
exclusion decisions. Export exact review units. Do not decide exclusions, rename
source files, publish originals, or change the main inventory in this task.

## Personas and jobs
Analysts inspect representative content before choosing reports to exclude.
Desktop review is primary; mobile browsing and keyboard use remain supported.

## Information architecture
Keep `/type-examples/` and link to inventory. Reports use cascading classification
filters; publications retain a separate legacy view. A report review unit is
classification path + `odtId` + `odtNm`, not a filename or inferred title category.
Missing middle/small levels remain empty and are displayed as 해당 없음.

## Design principles
Show full classification, source snapshot, file counts, coverage and missing
previews. Existing broad exclusion labels must not become new group decisions.

## Visual language
Reuse current CSS tokens: navy header, blue links, muted secondary text, pale
background, white rounded cards. Native selects; no new icon/font dependency.

## Components
Source switch, four labeled cascading selects, search, reset, filtered summary,
CSV export, paginated sample cards, document tabs and image enlargement dialog.

## Accessibility
Aim for WCAG 2.2 AA: visible focus, labels, native keyboard controls, descriptive
image alternatives, live result counts, dialog close/Escape and focus restoration.

## Responsive behavior
Filters and cards wrap on narrow screens. No page-wide horizontal scroll at
390px. Controls remain touchable and long Korean names wrap rather than truncate.

## Interaction states
Explicit loading/error/empty states; child filters reset when a parent changes.
Missing preview is not an exclusion decision. Images load lazily.

## Content voice
Use source terminology, distinguish 재정데이터명 from individual 파일명. Report
review state is 제외 여부 미선정; original publication decisions are legacy only.

## Implementation constraints
Static GitHub Pages; existing Python renderers; no new project dependencies.
Generated report review data and assets are separate from legacy sample outputs.
Preserve existing user modifications to report manifest. Test joins and filters,
desktop/mobile screenshots and sample image loading before completion.

## Open questions
- [ ] Analyst: future exclusion decisions and persistence/import workflow are
  out of scope; blank review columns in export support the next step.
