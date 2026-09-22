# Design

## Source of truth
Active · 2026-09-23 · `docs/type-examples/`. Evidence: existing page and live
GitHub Pages screenshot; `docs/data/type_samples.json`; report manifest; official
UOPKOFDA03 HTML (`clsDivLc`, `clsDivMc`, `clsDivSc`, `odtNm`).

## Brand
Evidence-first Korean public-finance document review. Preserve navy/blue, white
cards, restrained badges, readable document images. Avoid unverified judgments.

## Product goals
Browse report samples by 대분류 → 중분류 → 소분류 → 재정데이터명 to support later
exclusion decisions. Users can check groups, record reasons, save progress in
their browser and export the final exclusion list. Do not automatically decide
exclusions, rename source files, publish originals, or change the main inventory.

## Personas and jobs
Analysts inspect representative content before choosing reports to exclude.
Desktop review is primary; mobile browsing and keyboard use remain supported.

## Information architecture
Keep `/type-examples/` and link to inventory. Reports use cascading classification
filters; publications use a separate type-based review with search and pagination. A report review unit is
classification path + `odtId` + `odtNm`, not a filename or inferred title category.
Missing middle/small levels remain empty and are displayed as 해당 없음.
Publication units preserve the existing sample type IDs and join full inventory
counts from `documents.csv`; source category codes join the publication manifest.
Show `ofdBrdiDtsClsCd` codes without changing stable sample IDs. Report taxonomy
and odt IDs must not be invented. Distinguish 1,698 inventory rows from 1,695
attachments and three no-attachment records; provide a full-list Excel download.
Legacy publication decisions are reference artifacts, never initial user selections.

## Design principles
Show full classification, source snapshot, file counts, coverage and missing
previews. Existing broad exclusion labels must not become new group decisions.

## Visual language
Reuse current CSS tokens: navy header, blue links, muted secondary text, pale
background, white rounded cards. Native selects; no new icon/font dependency.

## Components
Source switch, four labeled cascading selects, search, reset, filtered summary,
CSV export, paginated sample cards, document tabs and image enlargement dialog.
Each report/publication card has an exclusion checkbox and optional reason. A review panel
shows global selected counts, final CSV export and a review-state filter. Bulk
actions target every group matching current filters, not just the visible page.
Backup/restore JSON and confirmed reset live in a secondary disclosure section.

## Accessibility
Aim for WCAG 2.2 AA: visible focus, labels, native keyboard controls, descriptive
image alternatives, live result counts, dialog close/Escape and focus restoration.

## Responsive behavior
Filters and cards wrap on narrow screens. No page-wide horizontal scroll at
390px. Controls remain touchable and long Korean names wrap rather than truncate.

## Interaction states
Explicit loading/error/empty states; child filters reset when a parent changes.
Missing preview is not an exclusion decision. Images load lazily.
Persist choices in versioned localStorage keyed by stable group ID. Unchecked
means not selected, not confirmed inclusion. Show storage failures and retain
in-memory operation/export; do not overwrite unreadable saved data silently.
Unknown saved IDs remain in backups with an explicit warning. Final CSV covers
all currently known excluded groups regardless of filters. Restoring JSON replaces
existing choices only after validation and confirmation.
Stores, backup source markers, CSV exports and reset scope are separate for reports
and publications. Preserve the report v1 storage contract. Async imports capture
their source before file reading, and storage events update only the matching store.
Share the review UI/helpers rather than duplicating the workflow. Publication
inventory generation and sample generation dates are distinct from a source check.

## Content voice
Use source terminology, distinguish 재정데이터명 from individual 파일명. Report
review state is 제외 미선택 or 제외 선택; original publication decisions are legacy only.
State plainly that browser storage is not shared, can be cleared, and is not a
server-side decision. Checking a card excludes its entire data group, not merely
the representative document or image currently displayed.

Explicit project decisions are separate from inferred legacy judgments. The
user-designated ZIP spreadsheet set (2026-09-21) contains exactly three groups.
Apply its versioned ID once to new or existing browser reviews, preserving all
other groups. Record applied set IDs alongside choices; subsequent uncheck,
confirmed clear or explicit backup restore must not be undone on reload.

## Implementation constraints
Static GitHub Pages; existing Python renderers; no new project dependencies.
Generated report review data and assets are separate from legacy sample outputs.
Preserve existing user modifications to report manifest. Test joins and filters,
desktop/mobile screenshots and sample image loading before completion.

## Open questions
- [ ] Shared accounts, real-time collaboration and server-side storage remain
  out of scope. JSON backup/import supports manual transfer between browsers.
