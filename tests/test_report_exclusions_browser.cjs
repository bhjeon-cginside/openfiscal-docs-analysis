/* Run against a local docs/ server; use an already installed Playwright. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/report_review_samples.json'), 'utf8'));
const base = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:8765/type-examples/';
const output = path.join(root, '.omx/state/exclusion-review');
const STORAGE_KEY = 'openfiscal-docs-analysis:report-exclusions:v1';
fs.mkdirSync(output, { recursive: true });

const byId = new Map(data.groups.map(group => [String(group.id), group]));
const csvCell = value => {
  const text = String(value ?? '');
  const safe = /^[=+@\-\t\r]/.test(text) ? `'${text}` : text;
  return `"${safe.replace(/"/g, '""')}"`;
};
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
async function gotoReview(page) {
  await page.goto(base, { waitUntil: 'networkidle' });
  await page.locator('#cards .sample').first().waitFor();
  await page.locator('#reviewPanel').waitFor({ state: 'visible' });
}
async function setDecision(page, id, excluded, reason) {
  const checkbox = page.locator(`[data-exclude-id="${id}"]`);
  await checkbox.scrollIntoViewIfNeeded();
  if (await checkbox.isChecked() !== excluded) await checkbox.click();
  const reasonBox = page.locator(`[data-reason-id="${id}"]`);
  assert.equal(await reasonBox.isEnabled(), excluded, 'Reason textarea is enabled only for excluded records');
  if (excluded && reason !== undefined) {
    await reasonBox.click();
    await reasonBox.fill('');
    await reasonBox.pressSequentially(reason);
    assert.equal(await reasonBox.evaluate(element => document.activeElement === element), true, 'Autosave must not steal focus from reason input');
  }
}
async function visibleCardTextForId(page, id) {
  return page.locator(`[data-exclude-id="${id}"]`).locator('xpath=ancestor::article[contains(@class,"sample")][1]').innerText();
}
async function resetFilters(page) {
  await page.click('#resetButton');
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
async function storagePayload(page) {
  return page.evaluate(key => JSON.parse(localStorage.getItem(key)), STORAGE_KEY);
}
function expectedRecord(group, excluded, reason) {
  return {
    id: String(group.id),
    excluded,
    reason,
    odt_id: String(group.odt_id ?? ''),
    data_name: String(group.data_name ?? ''),
    classification_path: String(group.classification_path ?? ''),
  };
}
function findGroup(predicate, message) {
  const group = data.groups.find(predicate);
  assert.ok(group, message);
  return group;
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await gotoReview(page);

    const distinctNames = new Set(data.groups.map(group => group.data_name)).size;
    assert.equal(data.groups.length, 60, 'Fixture contract remains 60 report groups');
    assert.equal(distinctNames, 59, 'Fixture contract remains 59 distinct financial data names');
    const initialSummary = await page.locator('#reviewSummary').innerText();
    assert.match(initialSummary, /제외\s*3/);
    assert.match(initialSummary, /재정데이터명\s*3/);
    assert.match(initialSummary, /첨부\s*11/);
    const declaredIds = data.exclusion_sets.flatMap(set => set.records.map(record => record.id)).sort();
    assert.deepEqual((await storagePayload(page)).records.filter(r => r.excluded).map(r => r.id).sort(), declaredIds);
    await clearChoices(page, true);
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#reviewPanel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#reviewSummary').innerText(), /제외\s*0/, 'Explicit clear must not reapply the same declared set');
    assert.equal(await page.locator('[data-reason-id]:enabled').count(), 0, 'Unchecked records do not enable reason inputs');

    const quotedReason = '업무 제외 후보, "중복"\n한글 사유';
    const first = findGroup(group => group.documents?.length, 'Need one visible group with documents');
    await page.selectOption('#dataNameSelect', String(first.id));
    await setDecision(page, String(first.id), true, quotedReason);
    assert.match(await page.locator('#reviewSummary').innerText(), /제외\s*1/);
    let payload = await storagePayload(page);
    assert.equal(payload.version, 1);
    assert.equal(payload.source, 'openfiscal-report-review');
    assert.ok(payload.updated_at, 'Review payload includes updated_at');
    assert.ok(payload.source_checked_at, 'Review payload includes source_checked_at');
    assert.deepEqual(payload.records.find(record => record.id === String(first.id)), expectedRecord(first, true, quotedReason));

    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#reviewPanel').waitFor({ state: 'visible' });
    await page.selectOption('#dataNameSelect', String(first.id));
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Exclusion choice persists after reload');
    assert.equal(await page.locator(`[data-reason-id="${first.id}"]`).inputValue(), quotedReason, 'Reason persists after reload');

    await setDecision(page, String(first.id), false);
    const uncheckedCsvText = await downloadText(page, '#csvButton', 'unchecked-current-decisions.csv');
    const uncheckedCsv = rowsByHeader(uncheckedCsvText);
    const uncheckedIdColumn = uncheckedCsv.header.includes('id') ? 'id' : 'group_id';
    const uncheckedRow = uncheckedCsv.rows.find(row => row[uncheckedIdColumn] === String(first.id));
    assert.equal(uncheckedRow.exclusion_decision, '', 'Unchecked current CSV row has blank decision');
    assert.equal(uncheckedRow.exclusion_reason, '', 'Unchecked current CSV row does not leak retained draft reason');
    await setDecision(page, String(first.id), true, quotedReason);

    const duplicateName = data.groups.find(group => data.groups.filter(other => other.data_name === group.data_name).length > 1).data_name;
    const duplicates = data.groups.filter(group => group.data_name === duplicateName).sort((a, b) => String(a.id).localeCompare(String(b.id)));
    assert.equal(duplicates.length, 2, 'Test expects exactly two same-name groups');
    await resetFilters(page);
    await page.fill('#searchInput', duplicateName);
    assert.equal(await page.locator('#cards .sample').count(), 2, 'Same-name records remain distinct cards');
    await setDecision(page, String(duplicates[0].id), true, '동명 ID 중 첫 번째만 제외');
    assert.equal(await page.locator(`[data-exclude-id="${duplicates[1].id}"]`).isChecked(), false, 'Checking one same-name ID does not check the other');

    const reportRawBeforePublication = await page.evaluate(key => localStorage.getItem(key), STORAGE_KEY);
    await page.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    await page.locator('#publicationControls').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#reviewPanel').isVisible(), true, 'Review panel is active for publication samples');
    assert.equal(await page.locator('#reportControls').isHidden(), true, 'Report filters are hidden while publication review is active');
    assert.equal(await page.evaluate(key => localStorage.getItem(key), STORAGE_KEY), reportRawBeforePublication, 'Opening publication review does not rewrite report decisions');
    await page.locator('#sourceFilters button').filter({ hasText: '재정보고서' }).click();
    await page.selectOption('#reviewFilter', 'excluded');
    assert.equal(await page.locator(`[data-exclude-id="${duplicates[0].id}"]`).count() > 0, true, 'Excluded report decision survives source switches');
    await page.selectOption('#reviewFilter', 'unselected');
    assert.equal(await page.locator(`[data-exclude-id="${duplicates[0].id}"]`).count(), 0, 'Review filter can hide already excluded records');

    await resetFilters(page);
    assert.equal(await page.locator('#reviewFilter').inputValue(), 'all', 'Filter reset resets review filter');
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Filter reset does not clear choices');

    const budgetGroups = data.groups.filter(group => group.classification?.large === '예산');
    assert.ok(budgetGroups.length > 12, 'Bulk test needs a filtered set spanning more than one page');
    await clearChoices(page, true);
    await page.selectOption('#largeSelect', '예산');
    if (await page.locator('#bulkReason').count()) await page.fill('#bulkReason', '예산 대분류 일괄 제외');
    await openReviewTools(page);
    await page.click('#bulkExclude');
    await page.selectOption('#reviewFilter', 'excluded');
    assert.match(await page.locator('#countline').innerText(), new RegExp(`${budgetGroups.length}개 그룹`), 'Bulk exclude applies to the full filtered result, not only current page');
    const budgetPayload = await storagePayload(page);
    const excludedBudget = budgetPayload.records.filter(record => record.excluded && budgetGroups.some(group => String(group.id) === record.id));
    assert.equal(excludedBudget.length, budgetGroups.length);
    assert.equal(excludedBudget.every(record => record.reason === '예산 대분류 일괄 제외'), true);
    await openReviewTools(page);
    await page.click('#bulkRestore');
    const restored = await storagePayload(page);
    assert.equal(restored.records.filter(record => record.excluded && budgetGroups.some(group => String(group.id) === record.id)).length, 0, 'Bulk restore applies to the full filtered result');

    await resetFilters(page);
    await setDecision(page, String(first.id), true, quotedReason);
    await page.fill('#searchInput', duplicateName);
    await setDecision(page, String(duplicates[0].id), true, '동명 ID 중 첫 번째만 제외');
    await openReviewTools(page);
    const excludedCsvText = await downloadText(page, '#exportExcluded', 'excluded-final.csv');
    let { header, rows } = rowsByHeader(excludedCsvText);
    const idColumn = header.includes('id') ? 'id' : 'group_id';
    assert.ok(header.includes(idColumn));
    const decisionColumn = header.includes('excluded') ? 'excluded' : 'exclusion_decision';
    const reasonColumn = header.includes('reason') ? 'reason' : 'exclusion_reason';
    assert.ok(header.includes(decisionColumn));
    assert.ok(header.includes(reasonColumn));
    assert.ok(header.includes('odt_id'));
    assert.ok(header.includes('data_name'));
    assert.ok(header.includes('classification_path') || ['large','middle','small'].every(name => header.includes(name)));
    assert.deepEqual(rows.map(row => row[idColumn]).sort(), [String(first.id), String(duplicates[0].id)].sort(), 'Final export includes all excluded records irrespective current filters');
    assert.equal(rows.find(row => row[idColumn] === String(first.id))[reasonColumn], quotedReason, 'CSV export preserves quotes/newlines/Korean reasons');

    await resetFilters(page);
    const filteredCsvText = await downloadText(page, '#csvButton', 'current-decisions.csv');
    ({ header, rows } = rowsByHeader(filteredCsvText));
    assert.ok(header.includes('exclusion_decision'));
    assert.ok(header.includes('exclusion_reason'));
    const currentIdColumn = header.includes('id') ? 'id' : 'group_id';
    assert.match(rows.find(row => row[currentIdColumn] === String(first.id)).exclusion_decision, /^(excluded|제외)$/, 'Existing CSV button exports actual current decision');
    assert.equal(rows.find(row => row[currentIdColumn] === String(first.id)).exclusion_reason, quotedReason, 'Existing CSV button exports actual current reason');

    await openReviewTools(page);
    const backupText = await downloadText(page, '#backupReview', 'review-backup.json');
    const backup = JSON.parse(backupText);
    assert.equal(backup.version, 1);
    assert.ok(backup.records.find(record => record.id === String(first.id)).excluded);

    await clearChoices(page, false);
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Clear cancel keeps existing choices');
    await clearChoices(page, true);
    assert.equal(await page.locator('[data-exclude-id]:checked').count(), 0, 'Clear accept resets all choices');

    const importInput = page.locator('#importReview');
    await importInput.setInputFiles({
      name: 'review-backup.json',
      mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify(backup), 'utf8'),
    });
    await page.locator(`[data-exclude-id="${first.id}"]`).waitFor();
    assert.equal(await page.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'JSON backup round-trip restores choices');
    payload = await storagePayload(page);
    payload.records.push({ id: '__unknown_future_id__', excluded: true, reason: '미래 데이터', odt_id: 'UNKNOWN', data_name: '알 수 없음', classification_path: '알 수 없음' });
    await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: STORAGE_KEY, value: payload });
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#reviewPanel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#storageStatus').innerText(), /알 수 없는|unknown|경고|찾을 수 없는|포함되지 않습니다/i, 'Unknown stored IDs are retained with a warning');
    payload = await storagePayload(page);
    assert.ok(payload.records.some(record => record.id === '__unknown_future_id__'), 'Unknown IDs are retained, not dropped');

    const beforeMalformed = await storagePayload(page);
    page.on('dialog', dialog => dialog.accept());
    await page.locator('#importReview').setInputFiles({
      name: 'broken.json',
      mimeType: 'application/json',
      buffer: Buffer.from('{ this is not json', 'utf8'),
    });
    assert.deepEqual(await storagePayload(page), beforeMalformed, 'Malformed JSON import does not mutate current decisions');

    await page.evaluate(({ key, value }) => localStorage.setItem(key, value), { key: STORAGE_KEY, value: '{ corrupted' });
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#reviewPanel').waitFor({ state: 'visible' });
    assert.match(await page.locator('#storageStatus').innerText(), /손상|corrupt|오류|error|읽지 못했습니다/i, 'Corrupted stored payload is surfaced');
    assert.equal(await page.evaluate(key => localStorage.getItem(key), STORAGE_KEY), '{ corrupted', 'Corrupted stored payload is not silently overwritten on load');

    await page.evaluate(key => localStorage.removeItem(key), STORAGE_KEY);
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#reviewPanel').waitFor({ state: 'visible' });
    await page.selectOption('#dataNameSelect', String(first.id));
    await setDecision(page, String(first.id), true, '스크린샷 확인');
    await page.screenshot({ path: path.join(output, 'after-desktop-selected.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator(`[data-exclude-id="${first.id}"]`).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'after-mobile-selected.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Exclusion controls do not create mobile horizontal overflow');

    const noStorage = await browser.newPage({ viewport: { width: 900, height: 900 } });
    await noStorage.addInitScript(key => {
      const memory = new Map();
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
          getItem(name) { return memory.has(name) ? memory.get(name) : null; },
          setItem() { throw new Error('localStorage disabled by test'); },
          removeItem(name) { memory.delete(name); },
          clear() { memory.clear(); },
          key(index) { return Array.from(memory.keys())[index] || null; },
          get length() { return memory.size; },
        },
      });
      window.__reviewStorageKey = key;
    }, STORAGE_KEY);
    await gotoReview(noStorage);
    await noStorage.selectOption('#dataNameSelect', String(first.id));
    await setDecision(noStorage, String(first.id), true, '메모리 상태에서 사용 가능');
    assert.equal(await noStorage.locator(`[data-exclude-id="${first.id}"]`).isChecked(), true, 'Storage-disabled mode remains usable in memory');
    assert.match(await noStorage.locator('#storageStatus').innerText(), /저장|storage|브라우저|localStorage|오류/i, 'Storage-disabled mode warns the reviewer');
    await noStorage.close();

    // Apply the new project decision once to old browsers, without replacing
    // unrelated choices. Subsequent manual changes and imported backups win.
    const migrated = await browser.newPage();
    const oldPayload = {version:1,source:'openfiscal-report-review',records:[
      expectedRecord(first,true,'기존 선택 유지'),
      expectedRecord(byId.get(declaredIds[0]),false,'지정 전 선택'),
    ]};
    await migrated.route('**/report_review_samples.json', route => route.fulfill({
      contentType:'application/json',body:JSON.stringify({...data,exclusion_sets:[]}),
    }));
    await gotoReview(migrated);
    await migrated.evaluate(({key,payload})=>localStorage.setItem(key,JSON.stringify(payload)), {key:STORAGE_KEY,payload:oldPayload});
    await migrated.unroute('**/report_review_samples.json');
    await migrated.reload({waitUntil:'networkidle'});
    assert.match(await migrated.locator('#reviewSummary').innerText(), /제외\s*4/);
    const migratedPayload = await storagePayload(migrated);
    assert.equal(migratedPayload.records.find(r=>r.id===first.id).reason,'기존 선택 유지');
    assert.ok(declaredIds.every(id=>migratedPayload.records.some(r=>r.id===id&&r.excluded)));
    await migrated.selectOption('#dataNameSelect',declaredIds[0]);
    await setDecision(migrated,declaredIds[0],false);
    await migrated.reload({waitUntil:'networkidle'});
    assert.equal((await storagePayload(migrated)).records.find(r=>r.id===declaredIds[0]).excluded,false);
    await migrated.evaluate(()=>{window.confirm=()=>true;});
    await migrated.locator('#importReview').setInputFiles({name:'old-empty-backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({version:1,source:'openfiscal-report-review',records:[]}))});
    await migrated.waitForFunction(key=>JSON.parse(localStorage.getItem(key)).records.length===0,STORAGE_KEY);
    await migrated.reload({waitUntil:'networkidle'});
    assert.match(await migrated.locator('#reviewSummary').innerText(), /제외\s*0/);
    await migrated.close();

    assert.deepEqual(errors, []);
    console.log('PASS: exclusion review persistence, same-name IDs, filters/source switches, bulk all-pages, CSV/JSON export-import, clear/reset, storage failures, corrupted payloads, screenshots');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
