/* Run against a local docs/ server; use an already installed Playwright. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/report_review_samples.json')));
const publications = JSON.parse(fs.readFileSync(path.join(root, 'docs/data/publication_review_samples.json')));
const base = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:8765/type-examples/';
const output = path.join(root, '.omx/state/classification-review');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true, executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.locator('#cards .sample').first().waitFor();
    assert.equal(await page.locator('#cards .sample').count(), 12);
    assert.match(await page.locator('#countline').innerText(), /60개 그룹.*7,262건/);
    assert.equal(await page.locator('#cards .status.unreviewed').count(), 12);
    await page.screenshot({ path: path.join(output, 'after-desktop.png') });

    await page.selectOption('#largeSelect', '예산');
    await page.selectOption('#middleSelect', '정부예산기금안');
    await page.selectOption('#smallSelect', '추가경정예산안');
    assert.equal(await page.locator('#cards .sample').count(), 4);
    assert.equal(await page.locator('#largeSelect option').count(), 8, 'Parents must not be restricted by children');
    const target = data.groups.find(g => g.data_name === '추가경정예산안 첨부서류');
    await page.selectOption('#dataNameSelect', target.id);
    assert.equal(await page.locator('#cards .sample').count(), 1);
    assert.equal(await page.locator('#cards h3').innerText(), target.data_name);
    const downloadPromise = page.waitForEvent('download');
    await page.click('#csvButton');
    const download = await downloadPromise;
    await download.saveAs(path.join(output, 'filtered-review.csv'));
    const csv = fs.readFileSync(path.join(output, 'filtered-review.csv'), 'utf8');
    assert.equal(csv.trim().split('\n').length, 2);
    assert.match(csv, /exclusion_decision.*exclusion_reason/);
    assert.ok(csv.includes(target.odt_id));
    assert.ok(csv.includes('"예산","정부예산기금안","추가경정예산안"'));
    assert.ok(csv.trim().endsWith(',"",""'));

    await page.locator('#cards .preview').first().scrollIntoViewIfNeeded();
    await page.locator('#cards .preview').first().click();
    assert.equal(await page.locator('#viewer').evaluate(e => e.open), true);
    await page.waitForFunction(() => document.querySelector('#viewer img').naturalWidth > 0);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#viewer').evaluate(e => e.open), false);
    assert.equal(await page.evaluate(() => document.activeElement.classList.contains('preview')), true);
    await page.locator('#cards [data-document-index="1"]').click();
    assert.equal(await page.locator('#cards [data-document-index="1"]').getAttribute('aria-pressed'), 'true');
    assert.equal(await page.evaluate(() => document.activeElement.dataset.documentIndex), '1');

    await page.selectOption('#largeSelect', '결산');
    assert.equal(await page.locator('#middleSelect').inputValue(), '__ALL__');
    assert.equal(await page.locator('#smallSelect').inputValue(), '__ALL__');
    assert.equal(await page.locator('#dataNameSelect').inputValue(), '__ALL__');
    await page.selectOption('#largeSelect', '지방재정');
    await page.selectOption('#middleSelect', '__EMPTY__');
    await page.selectOption('#smallSelect', '__EMPTY__');
    assert.equal(await page.locator('#cards .sample').count(), 3);
    assert.equal(await page.locator('#cards .preview').count() > 0, true);
    assert.match(await page.locator('#cards').innerText(), /ZIP/);
    assert.equal(await page.locator('#cards a[href*="openfiscaldata"]').count(), 3);

    await page.click('#resetButton');
    await page.fill('#searchInput', '성과평가관련 지침');
    assert.equal(await page.locator('#cards .sample').count(), 2, 'Same name with different IDs must remain separate');
    await page.click('#resetButton');
    await page.selectOption('#largeSelect', '성과관리');
    await page.selectOption('#middleSelect', '성과평가관련 지침');
    const names = await page.locator('#dataNameSelect option').allTextContents();
    assert.equal(names.length, 3);
    assert.notEqual(names[1], names[2]);

    const single = data.groups.find(g => g.years.length === 1 && g.documents.length);
    await page.click('#resetButton');
    await page.selectOption('#dataNameSelect', single.id);
    assert.ok((await page.locator('#cards .meta').first().innerText()).includes(`연도 ${single.years[0]} ·`));
    await page.fill('#searchInput', 'no-such-report-7654321');
    assert.equal(await page.locator('#cards .sample').count(), 0);
    assert.equal(await page.locator('#empty').isVisible(), true);
    assert.match(await page.locator('#countline').innerText(), /0–0/);

    await page.click('#resetButton');
    await page.locator('#pager button').filter({ hasText: /^다음$/ }).click();
    assert.match(await page.locator('#countline').innerText(), /13–24/);
    await page.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    assert.equal(await page.locator('#reportControls').isVisible(), false);
    assert.equal(await page.locator('#publicationControls').isVisible(), true);
    assert.equal(await page.locator('#reviewPanel').isVisible(), true);
    assert.equal(await page.locator('#cards .sample').count(), 12, 'Publication review groups are paginated');
    assert.match(await page.locator('#countline').innerText(), /15개|1–12/);
    const pubTarget = publications.groups.find(group => group.documents?.length || group.sample?.documents?.length) || publications.groups[0];
    await page.selectOption('#publicationTypeSelect', String(pubTarget.id));
    assert.equal(await page.locator('#cards .sample').count(), 1);
    assert.ok((await page.locator('#cards').innerText()).includes(pubTarget.data_name));
    await page.click('#publicationReset');
    await page.locator('#sourceFilters button').filter({ hasText: '재정보고서' }).click();
    await page.click('#resetButton');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(output, 'after-mobile.png') });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'No mobile horizontal overflow');
    await page.locator('.review-methods summary').click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Expanded source details must wrap');
    await page.locator('.review-methods summary').click();
    await page.locator('#reportControls').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'after-mobile-filters.png') });
    await page.selectOption('#largeSelect', '예산');
    await page.selectOption('#middleSelect', '정부예산기금안');
    await page.selectOption('#smallSelect', '추가경정예산안');
    await page.locator('#cards').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'after-mobile-cards.png') });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.locator('#reportControls').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, 'after-desktop-filtered.png') });
    assert.deepEqual(errors, []);

    const failed = await browser.newPage();
    await failed.route('**/report_review_samples.json', route => route.fulfill({ status: 503, body: 'unavailable' }));
    await failed.goto(base, { waitUntil: 'networkidle' });
    assert.match(await failed.locator('#cards').innerText(), /불러오지 못했습니다/);
    assert.equal(await failed.locator('#csvButton').isDisabled(), true);
    await failed.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    await failed.locator('#publicationControls').waitFor({ state: 'visible' });
    assert.ok(await failed.locator('#cards .sample').count() > 0, 'Independent publication view survives report load failure');

    const failedPublications = await browser.newPage();
    await failedPublications.route('**/publication_review_samples.json', route => route.fulfill({ status: 503, body: 'unavailable' }));
    await failedPublications.goto(base, { waitUntil: 'networkidle' });
    await failedPublications.locator('#cards .sample').first().waitFor();
    assert.ok(await failedPublications.locator('#cards .sample').count() > 0, 'Independent report view survives publication load failure');
    await failedPublications.locator('#sourceFilters button').filter({ hasText: '재정간행물' }).click();
    assert.match(await failedPublications.locator('#cards').innerText(), /불러오지 못했습니다/);
    await failedPublications.close();
    console.log('PASS: cascades, absent levels, duplicate names, CSV, previews/dialog, tabs, empty/search/reset, pagination, publications, mobile and fetch errors');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
