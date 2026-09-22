/* Run against a local docs/ server; use an already installed Playwright. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const publicationData = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/publication_review_samples.json'), 'utf8'));
const reportData = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/report_review_samples.json'), 'utf8'));
const base = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:8765/type-examples/';
const output = path.join(root, '.omx/state/publication-review');
const PUBLICATION_STORAGE_KEY = 'openfiscal-docs-analysis:publication-exclusions:v1';
const REPORT_STORAGE_KEY = 'openfiscal-docs-analysis:report-exclusions:v1';
fs.mkdirSync(output, { recursive: true });

const groups = publicationData.groups;
const byId = new Map(groups.map(group => [String(group.id), group]));
const expectedReportPayload = {
  version: 1,
  source: 'openfiscal-report-review',
  updated_at: '2026-09-23T00:00:00.000Z',
  source_checked_at: String(reportData.source_checked_at ?? ''),
  applied_exclusion_sets: (reportData.exclusion_sets || []).map(set => set.id),
  records: [
    {
      id: String(reportData.groups[0].id),
      excluded: true,
      reason: '보고서 선택은 간행물 작업 중 보존되어야 함',
      odt_id: String(reportData.groups[0].odt_id ?? ''),
      data_name: String(reportData.groups[0].data_name ?? ''),
      classification_path: String(reportData.groups[0].classification_path ?? ''),
    },
  ],
};
const expectedReportRaw = JSON.stringify(expectedReportPayload);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  const source = text.replace(/^\ufeff/, '');
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (inQuotes) {
      if (char === '"' && source[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ',') {
      row.push(cell);
      cell = '';
    } else if (char === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (char !== '\r') {
      cell += char;
    }
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}
function rowsByHeader(csv) {
  const rows = parseCsv(csv);
  const header = rows.shift();
  return { header, rows: rows.map(row => Object.fromEntries(header.map((name, index) => [name, row[index] ?? '']))) };
}
async function downloadText(page, clickSelector, filename) {
  const downloadPromise = page.waitForEvent('download');
  await page.click(clickSelector);
  const download = await downloadPromise;
  const filePath = path.join(output, filename || download.suggestedFilename());
  await download.saveAs(filePath);
  return fs.readFileSync(filePath, 'utf8');
}
async function gotoPage(page) {
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.locator('#cards .sample').first().waitFor();
}
async function switchToPublications(page) {
  await page.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
  await page.locator('#publicationControls').waitFor({ state: 'visible' });
  await page.locator('#reviewPanel').waitFor({ state: 'visible' });
  await page.locator('#cards .sample').first().waitFor();
}
async function openReviewTools(page) {
  const tools = page.locator('details.review-tools');
  if (await tools.count()) {
    const open = await tools.evaluate(element => element.open);
    if (!open) await tools.locator('summary').click();
  }
}
async function clearChoices(page, accept) {
  await openReviewTools(page);
  await page.evaluate(value => { window.confirm = () => value; }, accept);
  await page.click('#clearReview');
}
async function storageRaw(page, key) {
  return page.evaluate(name => localStorage.getItem(name), key);
}
async function storagePayload(page, key = PUBLICATION_STORAGE_KEY) {
  return page.evaluate(name => JSON.parse(localStorage.getItem(name)), key);
}
async function setPublicationDecision(page, id, excluded, reason) {
  const checkbox = page.locator(`[data-exclude-id="${id}"]`);
  await checkbox.scrollIntoViewIfNeeded();
  if (await checkbox.isChecked() !== excluded) await checkbox.click();
  const reasonBox = page.locator(`[data-reason-id="${id}"]`);
  assert.equal(await reasonBox.isEnabled(), excluded, 'Publication reason textarea is enabled only for excluded records');
  if (excluded && reason !== undefined) {
    await reasonBox.click();
    await reasonBox.fill('');
    await reasonBox.pressSequentially(reason);
    assert.equal(await reasonBox.evaluate(element => document.activeElement === element), true, 'Publication autosave must not steal focus from reason input');
  }
}
async function selectVisiblePublication(page, id) {
  await page.selectOption('#publicationTypeSelect', String(id));
  await page.locator(`[data-exclude-id="${id}"]`).waitFor();
}
function expectedPublicationRecord(group, excluded, reason) {
  return {
    id: String(group.id),
    excluded,
    reason,
    type: String(group.type ?? ''),
    data_name: String(group.data_name ?? ''),
    category_code: String(group.category_code ?? ''),
  };
}
function findGroup(predicate, message) {
  const group = groups.find(predicate);
  assert.ok(group, message);
  return group;
}
function csvIdColumn(header) {
  return header.includes('group_id') ? 'group_id' : 'id';
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--no-sandbox'],
  });
  try {
    assert.equal(groups.length, 15, 'Fixture contract remains 15 publication groups');
    assert.equal(publicationData.summary?.record_count, 1698, 'Fixture contract remains 1,698 publication records');
    assert.equal(publicationData.summary?.file_count, 1695, 'Fixture contract remains 1,695 downloadable publication files');
    assert.equal(publicationData.summary?.no_attachment_count, 3, 'Fixture contract remains 3 publication rows without downloadable files');
    assert.equal(publicationData.summary?.representative_documents, 43, 'Fixture contract remains 43 publication sample documents');

    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await gotoPage(page);
    await page.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: REPORT_STORAGE_KEY, value: expectedReportRaw });
    await switchToPublications(page);

    assert.equal(await page.locator('#cards .sample').count(), 12, 'Publication groups are paginated at 12 per page');
    assert.match(await page.locator('#countline').innerText(), /15개|1–12/, 'Publication count reflects review groups, not legacy sample cards');
    assert.match(await page.locator('#stats').innerText(), /1,695|1,698/, 'Publication stats show corrected record/file totals');
    assert.match(await page.locator('#reviewSummary').innerText(), /제외\s*0/, 'Fresh publications do not inherit legacy status selections');
    assert.equal(await page.locator('#publicationWorkbook').getAttribute('href'), '../data/publication_full_list.xlsx', 'Publication workbook link points to the full XLSX snapshot');
    const workbookDownloadPromise = page.waitForEvent('download');
    await page.click('#publicationWorkbook');
    const workbookDownload = await workbookDownloadPromise;
    assert.equal(workbookDownload.suggestedFilename(), 'publication_full_list.xlsx', 'Publication workbook link downloads the XLSX snapshot');
    await workbookDownload.saveAs(path.join(output, 'publication_full_list.xlsx'));
    assert.ok(fs.statSync(path.join(output, 'publication_full_list.xlsx')).size > 0, 'Downloaded publication workbook is non-empty');
    assert.equal(await storageRaw(page, REPORT_STORAGE_KEY), expectedReportRaw, 'Opening publications does not rewrite report review storage');

    const quotedReason = '간행물 제외 후보, "확인 필요"\n두 번째 줄';
    const first = findGroup(group => group.documents?.length || group.sample?.documents?.length, 'Need one publication group with preview documents');
    const second = findGroup(group => String(group.id) !== String(first.id), 'Need a second publication group');
    await selectVisiblePublication(page, String(first.id));
    assert.ok((await page.locator('#publicationTypeSelect option:checked').innerText()).includes(first.category_code), 'Publication select label includes category code');
    assert.ok((await page.locator('#cards').innerText()).includes(first.category_code), 'Publication card shows category code badge');
    await setPublicationDecision(page, String(first.id), true, quotedReason);
    let payload = await storagePayload(page);
    assert.equal(payload.version, 1);
    assert.equal(payload.source, 'openfiscal-publication-review');
    assert.ok(payload.updated_at, 'Publication review payload includes updated_at');
    assert.deepEqual(payload.records.find(record => record.id === String(first.id)), expectedPublicationRecord(first, true, quotedReason));
    assert.equal(await storageRaw(page, REPORT_STORAGE_KEY), expectedReportRaw, 'Publication selection preserves report localStorage byte-for-byte');

    await page.reload({ waitUntil: 'networkidle' });
    await switchToPublications(page);
    await selectVisiblePublication(page, String(first.id));
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Publication exclusion persists after reload');
    assert.equal(await page.locator(`[data-reason-id="${first.id}"]`).inputValue(), quotedReason, 'Publication reason persists after reload');
    if (await page.locator('#cards .preview').count()) {
      await page.locator('#cards .preview').first().click();
      assert.equal(await page.locator('#viewer').evaluate(element => element.open), true, 'Publication preview opens in the shared viewer');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#viewer').evaluate(element => element.open), false, 'Publication preview viewer closes with Escape');
    }
    if (await page.locator('#cards [data-document-index="1"]').count()) {
      await page.locator('#cards [data-document-index="1"]').click();
      assert.equal(await page.locator('#cards [data-document-index="1"]').getAttribute('aria-pressed'), 'true', 'Publication document tabs switch the representative document');
    }

    await page.selectOption('#publicationTypeSelect', '__ALL__');
    await page.selectOption('#publicationTypeSelect', String(first.id));
    assert.equal(await page.locator('#cards .sample').count(), 1, 'Publication type filter can isolate one group');
    await page.fill('#publicationSearch', String(first.data_name).slice(0, 4));
    assert.equal(await page.locator('#cards .sample').count(), 1, 'Publication search filters by data name/content within type');
    await page.selectOption('#reviewFilter', 'excluded');
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).count(), 1, 'Publication excluded filter shows the checked type');
    await page.selectOption('#reviewFilter', 'unselected');
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).count(), 0, 'Publication unselected filter hides the checked type');
    await page.selectOption('#reviewFilter', 'all');
    await page.click('#publicationReset');
    await page.fill('#publicationSearch', first.category_code);
    assert.equal(await page.locator('#cards .sample').count(), groups.filter(group => group.category_code === first.category_code).length, 'Publication search matches server category code');
    assert.ok((await page.locator('#cards').innerText()).includes(first.category_code), 'Category-code search result displays the matched code');
    await page.click('#publicationReset');
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Publication reset does not clear reviewer choices');
    assert.equal(await page.locator('#reviewFilter').inputValue(), 'all', 'Publication reset clears the review filter');

    await setPublicationDecision(page, String(first.id), false);
    const uncheckedCsvText = await downloadText(page, '#publicationCsv', 'publication-unchecked-current.csv');
    let parsed = rowsByHeader(uncheckedCsvText);
    let idColumn = csvIdColumn(parsed.header);
    const uncheckedRow = parsed.rows.find(row => row[idColumn] === String(first.id));
    assert.equal(uncheckedRow.exclusion_decision, '', 'Unchecked publication CSV row has blank decision');
    assert.equal(uncheckedRow.exclusion_reason, '', 'Unchecked publication CSV row does not leak retained draft reason');
    await setPublicationDecision(page, String(first.id), true, quotedReason);

    await page.selectOption('#publicationTypeSelect', '__ALL__');
    await page.click('#publicationReset');
    await clearChoices(page, true);
    await page.fill('#bulkReason', '전체 간행물 일괄 제외');
    await openReviewTools(page);
    await page.click('#bulkExclude');
    await page.selectOption('#reviewFilter', 'excluded');
    assert.match(await page.locator('#countline').innerText(), /15개/, 'Publication bulk exclude applies beyond the first 12-card page');
    payload = await storagePayload(page);
    assert.equal(payload.records.filter(record => record.excluded).length, groups.length);
    assert.equal(payload.records.every(record => record.reason === '전체 간행물 일괄 제외'), true);
    await openReviewTools(page);
    await page.click('#bulkRestore');
    payload = await storagePayload(page);
    assert.equal(payload.records.filter(record => record.excluded).length, 0, 'Publication bulk restore applies beyond the first page');

    await page.click('#publicationReset');
    await selectVisiblePublication(page, String(first.id));
    await setPublicationDecision(page, String(first.id), true, quotedReason);
    await page.selectOption('#publicationTypeSelect', '__ALL__');
    await selectVisiblePublication(page, String(second.id));
    await setPublicationDecision(page, String(second.id), true, '두 번째 간행물 제외');
    await page.fill('#publicationSearch', '__no_matching_publication__');
    await openReviewTools(page);
    const finalCsvText = await downloadText(page, '#exportExcluded', 'openfiscal-publication-exclusions.csv');
    parsed = rowsByHeader(finalCsvText);
    idColumn = csvIdColumn(parsed.header);
    assert.deepEqual(parsed.header, ['group_id', 'type', 'category_code', 'record_count', 'file_count', 'no_attachment_count', 'years', 'extensions', 'exclusion_decision', 'exclusion_reason']);
    const firstExportRow = parsed.rows.find(row => row[idColumn] === String(first.id));
    assert.equal(firstExportRow.category_code, String(first.category_code), 'Publication CSV includes server category code');
    assert.equal(firstExportRow.record_count, String(first.record_count), 'Publication CSV uses full record count');
    assert.equal(firstExportRow.file_count, String(first.file_count), 'Publication CSV uses downloadable file count');
    assert.equal(firstExportRow.no_attachment_count, String(first.no_attachment_count), 'Publication CSV includes no-attachment count');
    assert.deepEqual(parsed.rows.map(row => row[idColumn]).sort(), [String(first.id), String(second.id)].sort(), 'Publication final export includes all excluded records irrespective current filters');
    assert.equal(parsed.rows.find(row => row[idColumn] === String(first.id)).exclusion_reason, quotedReason, 'Publication CSV preserves quotes/newlines/Korean reasons');

    await page.click('#publicationReset');
    const currentCsvText = await downloadText(page, '#publicationCsv', 'openfiscal-publication-review-filtered.csv');
    parsed = rowsByHeader(currentCsvText);
    idColumn = csvIdColumn(parsed.header);
    assert.ok(parsed.header.includes('exclusion_decision'));
    assert.equal(parsed.rows.find(row => row[idColumn] === String(first.id)).exclusion_reason, quotedReason, 'Publication filtered CSV exports current reasons');

    await openReviewTools(page);
    const backupText = await downloadText(page, '#backupReview', 'openfiscal-publication-review-backup.json');
    const backup = JSON.parse(backupText);
    assert.equal(backup.version, 1);
    assert.equal(backup.source, 'openfiscal-publication-review');
    assert.ok(backup.records.find(record => record.id === String(first.id)).excluded);
    assert.equal(await storageRaw(page, REPORT_STORAGE_KEY), expectedReportRaw, 'Publication backup preserves report storage');

    await clearChoices(page, false);
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Publication clear cancel keeps existing choices');
    await clearChoices(page, true);
    assert.equal(await page.locator('[data-exclude-id]:checked').count(), 0, 'Publication clear accept resets all visible choices');
    const importInput = page.locator('#importReview');
    await importInput.setInputFiles({
      name: 'openfiscal-publication-review-backup.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(backup), 'utf8'),
    });
    await page.locator(`[data-exclude-id="${first.id}"]`).waitFor();
    await selectVisiblePublication(page, String(first.id));
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Publication JSON backup round-trip restores choices');

    const beforeInvalid = await storageRaw(page, PUBLICATION_STORAGE_KEY);
    page.on('dialog', dialog => dialog.accept());
    await importInput.setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{bad json', 'utf8') });
    assert.equal(await storageRaw(page, PUBLICATION_STORAGE_KEY), beforeInvalid, 'Malformed publication import does not mutate current decisions');
    await importInput.setInputFiles({
      name: 'report-review-backup.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(expectedReportPayload), 'utf8'),
    });
    assert.equal(await storageRaw(page, PUBLICATION_STORAGE_KEY), beforeInvalid, 'Report JSON cannot be imported into publication review');
    assert.equal(await storageRaw(page, REPORT_STORAGE_KEY), expectedReportRaw, 'Wrong-source publication import does not mutate reports');

    const delayed = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    await gotoPage(delayed);
    await delayed.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: REPORT_STORAGE_KEY, value: expectedReportRaw });
    await switchToPublications(delayed);
    await delayed.evaluate(() => {
      const originalText = File.prototype.text;
      window.__resolveDelayedFileText = null;
      Object.defineProperty(File.prototype, 'text', {
        configurable: true,
        value() {
          if (this.name === 'delayed-publication-backup.json') {
            return new Promise(resolve => { window.__resolveDelayedFileText = resolve; });
          }
          return originalText.call(this);
        },
      });
    });
    const delayedPayload = {
      version: 1,
      source: 'openfiscal-publication-review',
      records: [expectedPublicationRecord(first, true, '비동기 복원은 간행물에만 적용')],
    };
    const delayedBeforePublication = await storageRaw(delayed, PUBLICATION_STORAGE_KEY);
    const delayedImportInput = delayed.locator('#importReview');
    await delayedImportInput.setInputFiles({
      name: 'delayed-publication-backup.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(delayedPayload), 'utf8'),
    });
    await delayed.locator('#sourceFilters button').filter({ hasText: '재정보고서' }).click();
    assert.equal(await storageRaw(delayed, PUBLICATION_STORAGE_KEY), delayedBeforePublication, 'Delayed import does not apply before file text resolves');
    await delayed.evaluate(text => window.__resolveDelayedFileText(text), JSON.stringify(delayedPayload));
    await delayed.waitForFunction(({ key, id }) => {
      const raw = localStorage.getItem(key);
      return raw && JSON.parse(raw).records.some(record => record.id === id && record.excluded && record.reason.includes('비동기'));
    }, { key: PUBLICATION_STORAGE_KEY, id: String(first.id) });
    assert.equal(await storageRaw(delayed, REPORT_STORAGE_KEY), expectedReportRaw, 'Delayed publication import preserves report storage while report tab is active');
    await delayed.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    await selectVisiblePublication(delayed, String(first.id));
    assert.equal(await delayed.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Delayed import result is visible after switching back to publications');
    assert.equal(await delayed.locator(`[data-reason-id="${first.id}"]`).inputValue(), '비동기 복원은 간행물에만 적용');
    await delayed.close();

    const eventContext = await browser.newContext({ viewport: { width: 1200, height: 900 } });
    const publisher = await eventContext.newPage();
    const observer = await eventContext.newPage();
    await gotoPage(publisher);
    await publisher.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: REPORT_STORAGE_KEY, value: expectedReportRaw });
    await switchToPublications(publisher);
    await gotoPage(observer);
    assert.equal(await storageRaw(observer, REPORT_STORAGE_KEY), expectedReportRaw, 'Second tab starts with the seeded report storage');
    await selectVisiblePublication(publisher, String(first.id));
    await setPublicationDecision(publisher, String(first.id), true, '다른 탭 저장 이벤트 반영');
    await observer.waitForFunction(({ key, id }) => {
      const raw = localStorage.getItem(key);
      return raw && JSON.parse(raw).records.some(record => record.id === id && record.reason.includes('다른 탭'));
    }, { key: PUBLICATION_STORAGE_KEY, id: String(first.id) });
    assert.equal(await storageRaw(observer, REPORT_STORAGE_KEY), expectedReportRaw, 'Publication storage event preserves report storage in report tab');
    await observer.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    await selectVisiblePublication(observer, String(first.id));
    assert.equal(await observer.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Report-tab observer applies publication storage event before switching sources');
    assert.equal(await observer.locator(`[data-reason-id="${first.id}"]`).inputValue(), '다른 탭 저장 이벤트 반영');
    await eventContext.close();

    await page.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: PUBLICATION_STORAGE_KEY, value: '{ corrupted' });
    await page.reload({ waitUntil: 'networkidle' });
    await switchToPublications(page);
    assert.match(await page.locator('#storageStatus').innerText(), /손상|corrupt|오류|error|읽지 못했습니다/i, 'Corrupted publication payload is surfaced');
    assert.equal(await storageRaw(page, PUBLICATION_STORAGE_KEY), '{ corrupted', 'Corrupted publication payload is not silently overwritten on load');
    assert.equal(await storageRaw(page, REPORT_STORAGE_KEY), expectedReportRaw, 'Corrupted publication storage does not harm report choices');

    await page.evaluate(key => localStorage.removeItem(key), PUBLICATION_STORAGE_KEY);
    await page.reload({ waitUntil: 'networkidle' });
    await switchToPublications(page);
    await selectVisiblePublication(page, String(first.id));
    await setPublicationDecision(page, String(first.id), true, '스크린샷 확인');
    await page.screenshot({ path: path.join(output, 'after-desktop-selected.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(`[data-exclude-id="${first.id}"]`).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'after-mobile-selected.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Publication review controls do not create mobile horizontal overflow');
    await page.close();

    const noStorage = await browser.newPage({ viewport: { width: 900, height: 900 } });
    await noStorage.addInitScript(({ reportKey, reportRaw }) => {
      const memory = new Map([[reportKey, reportRaw]]);
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
          getItem(name) { return memory.has(name) ? memory.get(name) : null; },
          setItem(name, value) { if (name === reportKey) memory.set(name, String(value)); else throw new Error('publication localStorage disabled by test'); },
          removeItem(name) { memory.delete(name); },
          clear() { memory.clear(); },
          key(index) { return Array.from(memory.keys())[index] || null; },
          get length() { return memory.size; },
        },
      });
    }, { reportKey: REPORT_STORAGE_KEY, reportRaw: expectedReportRaw });
    await gotoPage(noStorage);
    await switchToPublications(noStorage);
    await selectVisiblePublication(noStorage, String(first.id));
    await setPublicationDecision(noStorage, String(first.id), true, '메모리 상태에서 사용 가능');
    assert.equal(await noStorage.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Publication storage-disabled mode remains usable in memory');
    assert.match(await noStorage.locator('#storageStatus').innerText(), /저장|storage|브라우저|localStorage|오류/i, 'Publication storage-disabled mode warns the reviewer');
    assert.equal(await storageRaw(noStorage, REPORT_STORAGE_KEY), expectedReportRaw, 'Publication storage-disabled mode preserves report storage');
    await noStorage.close();

    const failedPublications = await browser.newPage();
    await failedPublications.route('**/publication_review_samples.json', route => route.fulfill({ status: 503, body: 'unavailable' }));
    await gotoPage(failedPublications);
    assert.ok(await failedPublications.locator('#cards .sample').count() > 0, 'Report view survives publication review data failure');
    await failedPublications.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    assert.match(await failedPublications.locator('#cards').innerText(), /불러오지 못했습니다/);
    await failedPublications.close();

    assert.deepEqual(errors, []);
    console.log('PASS: publication review persistence, source isolation, filters/reset, all-page bulk actions, CSV/JSON export-import, storage failures, mobile screenshots and independent fetch errors');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
