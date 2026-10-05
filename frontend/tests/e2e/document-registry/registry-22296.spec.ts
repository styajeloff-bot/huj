import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext, type Browser, type Locator, type Page } from '@playwright/test'
import type { ReferenceDocument } from '../../../features/documentRegistry'

interface Fixture { marker: string; base_url: string; storage_states: Record<string, string>; companies: Record<string, { company_id: string; leasing_company_id?: string; name: string }>; catalog: { mark_id: string; model_id: string; brand: string; model: string } }
const enabled = process.env.DOCUMENT_REGISTRY_E2E === '1'
const fixture: Fixture | null = enabled ? JSON.parse(readFileSync(process.env.DOCUMENT_REGISTRY_E2E_FIXTURE ?? '/tmp/carcraft-22296-e2e/manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'document-registry-22296' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) throw new Error('Use the isolated 22296 fixture only')
test.skip(!enabled, 'Requires the real isolated app and DOCUMENT_REGISTRY_E2E_FIXTURE')
const pdf = Buffer.from('%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n')
const upload = (name = 'договор.pdf', buffer = pdf) => ({ name, mimeType: 'application/pdf', buffer })
const date = (days = 0) => { const value = new Date(); value.setUTCDate(value.getUTCDate() + days); return value.toISOString().slice(0, 10) }
async function session(browser: Browser, role: string, width = 1280) {
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: fixture!.storage_states[role], extraHTTPHeaders: { 'X-CSRF-Token': JSON.parse(readFileSync(fixture!.storage_states[role]!, 'utf8')).cookies.find((cookie: { name: string }) => cookie.name === 'csrfToken').value, Origin: fixture!.base_url }, locale: 'ru-RU', timezoneId: 'Europe/Moscow', viewport: { width, height: 1000 } })
  const page = await context.newPage(); const errors: string[] = []; page.on('pageerror', error => errors.push(error.message)); return { context, page, errors }
}
async function create(request: APIRequestContext, metadata: object, groupId?: string) {
  const response = await request.post(`/api/v1/document-registry/${groupId ? `groups/${groupId}/documents` : 'documents'}`, { multipart: { metadata: JSON.stringify(metadata), files: upload() } })
  expect(response.status(), await response.text()).toBe(201); return await response.json() as ReferenceDocument
}
async function saveLinks(page: Page, picker: Locator) {
  const saved = page.waitForResponse(response => response.url().endsWith('/reference-documents') && response.request().method() === 'PATCH')
  await picker.getByRole('button', { name: 'Сохранить связи', exact: true }).click()
  const response = await saved; expect(response.status(), await response.text()).toBe(200)
  await expect(picker.getByRole('button', { name: 'Сохранить связи', exact: true })).toHaveCount(0)
  await expect(picker.getByRole('button', { name: 'Сохранение…', exact: true })).toHaveCount(0)
}
function mainMetadata(name: string, number: string, extra: object = {}) { return { document_type: 'contract', contract_number: number, name, valid_from: date(-10), valid_to: null, participants: { platform_ml: true }, ...extra } }
async function fillForm(dialog: Locator, name: string, number: string) { await dialog.getByLabel('Номер документа', { exact: false }).fill(number); await dialog.getByLabel('Название', { exact: true }).fill(name); await dialog.getByLabel('Действует с', { exact: true }).fill(date()); await dialog.locator('input[type=file]').setInputFiles(upload()) }

for (const width of [768, 1280, 1920]) test(`real registry create, child, version, table, export and delete at ${width}px`, async ({ browser }) => {
  test.setTimeout(120_000)
  const { context, page, errors } = await session(browser, 'admin', width)
  const key = randomUUID().slice(0, 8); const name = `UI-${width}-${key}`; const number = `UI-${key}`
  await page.goto('/workspace/document-registry'); await expect(page.locator('.dr-workspace').getByRole('heading', { name: 'Справочник документов', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Добавить документ', exact: true }).click()
  let dialog = page.getByRole('dialog').last()
  await fillForm(dialog, name, number); await dialog.getByRole('group', { name: 'Участники связки' }).getByLabel('Платформа МЛ').check()
  const created = page.waitForResponse(response => response.url().endsWith('/document-registry/documents') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); const root = await (await created).json() as { id: string; group_id: string }
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByPlaceholder('Поиск документов').fill(name)
  await expect(page.locator('.dr-group')).toHaveCount(1)
  const group = page.locator('.dr-group').filter({ hasText: name }); await expect(group).toHaveCount(1)
  await group.getByRole('button', { name: '+ Документ в связку', exact: true }).click(); dialog = page.getByRole('dialog').last()
  await fillForm(dialog, `${name}-акт`, `${number}-A`); await dialog.getByRole('combobox', { name: 'Тип документа', exact: true }).selectOption('act'); await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await group.getByRole('button', { name: /Показать ещё 1/ }).click(); await expect(group.getByRole('tab', { name: 'Акт (1)', exact: true })).toBeVisible()
  const child = group.locator('.dr-document').filter({ hasText: `${name}-акт` }); await expect(child).toHaveCount(1)
  await expect(child.getByRole('button', { name: 'Новая версия', exact: true })).toHaveCount(0); await child.getByRole('button', { name: 'Редактировать', exact: true }).click(); dialog = page.getByRole('dialog').last(); await dialog.locator('input[type=file]').setInputFiles(upload('версия-2.pdf')); await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(child).toContainText('Версия 2'); await child.getByRole('button', { name: 'История версий (2)', exact: true }).click(); await expect(page.getByRole('dialog').last()).toContainText('Версия 1'); await page.getByRole('dialog').last().getByRole('button', { name: 'Закрыть', exact: true }).click()
  await child.getByRole('button', { name: 'Деактивировать', exact: true }).click(); await expect(child.locator('.dr-status')).toHaveText('Деактивирован'); await child.getByRole('button', { name: 'Активировать', exact: true }).click(); await expect(child.locator('.dr-status')).toHaveText('Действует')
  await group.screenshot({ path: `/tmp/carcraft-22296-e2e/registry-card-${width}.png` }); await page.locator('.dr-header').scrollIntoViewIfNeeded(); await page.screenshot({ path: `/tmp/carcraft-22296-e2e/registry-${width}.png`, fullPage: true })
  await group.locator(`[data-document-id="${root.id}"]`).getByRole('button', { name: 'Редактировать', exact: true }).click(); dialog = page.getByRole('dialog').last(); await expect(dialog.getByLabel('Номер документа', { exact: false })).toBeDisabled(); await dialog.getByRole('button', { name: 'Отмена', exact: true }).click()
  await page.getByRole('button', { name: 'Таблица', exact: true }).click(); await expect(page.locator('.dr-table tbody tr')).toHaveCount(1); await expect(page.locator('.dr-table')).toContainText(`${number}-A`)
  await page.locator('.dr-table').getByRole('link').click(); await expect(page.getByRole('dialog')).toContainText(`${name}-акт`); await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).click()
  const downloaded = page.waitForEvent('download'); await page.getByRole('button', { name: 'Скачать Excel', exact: true }).click(); expect((await downloaded).suggestedFilename()).toBe('Справочник документов.xlsx')
  await page.getByRole('button', { name: 'Карточки', exact: true }).click(); await group.locator(`[data-document-id="${root.id}"]`).getByRole('button', { name: 'Удалить', exact: true }).click(); dialog = page.getByRole('dialog'); await expect(dialog).toContainText('Документов будет удалено: 2'); await dialog.getByRole('button', { name: 'Удалить', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0); await expect(page.locator('.dr-group')).toHaveCount(0)
  expect(errors).toEqual([]); await context.close()
})

test('partner sees only related child; concealed main stays absent from cards, table, history and file API', async ({ browser }) => {
  test.setTimeout(90_000)
  const admin = await session(browser, 'admin'); const key = randomUUID().slice(0, 8)
  const main = await create(admin.context.request, mainMetadata(`Скрытый-${key}`, `HIDE-${key}`, { participants: { dealer_company_ids: [fixture!.companies.dealer!.company_id] } }))
  const child = await create(admin.context.request, { document_type: 'act', contract_number: `VISIBLE-${key}`, name: `Доступный-${key}`, valid_from: date(), related_companies: { dealer_company_ids: [fixture!.companies.dealer2!.company_id] } }, main.group_id)
  const outsider = await session(browser, 'outsider'); const page = outsider.page
  await page.goto(`/workspace/document-registry?document=${child.id}`); await expect(page.getByRole('dialog')).toContainText(child.name); await expect(page.getByRole('button', { name: 'Добавить документ', exact: true })).toHaveCount(0); await expect(page.getByRole('dialog').getByRole('button', { name: 'Редактировать', exact: true })).toHaveCount(0)
  await page.getByRole('dialog').getByRole('button', { name: 'Закрыть', exact: true }).click(); await page.getByPlaceholder('Поиск документов').fill(child.name); await expect(page.locator('.dr-group')).toHaveCount(1); await expect(page.locator('.dr-group')).not.toContainText(main.name)
  await page.getByRole('button', { name: 'Таблица', exact: true }).click(); await expect(page.locator('.dr-table')).toContainText(child.name); await expect(page.locator('.dr-table')).not.toContainText(main.name)
  for (const path of [`/documents/${main.id}`, `/documents/${main.id}/versions`, `/files/${main.current_version.files[0]!.id}/download`]) expect((await outsider.context.request.get('/api/v1/document-registry' + path)).status()).toBe(404)
  expect((await outsider.context.request.patch(`/api/v1/document-registry/documents/${child.id}/activation`, { data: { active: false } })).status()).toBe(403)
  const response = await admin.context.request.get(`/api/v1/document-registry/documents/${main.id}/monetization-usages`); const impact = await response.json() as { fingerprint: string }; expect((await admin.context.request.delete(`/api/v1/document-registry/documents/${main.id}`, { headers: { 'If-Match': impact.fingerprint } })).status()).toBe(204)
  expect(outsider.errors).toEqual([]); await outsider.context.close(); await admin.context.close()
})

test('monetization selects current links and uploads into an expired-only group without copying files', async ({ browser }) => {
  test.setTimeout(120_000)
  const { context, page, errors } = await session(browser, 'admin'); const key = randomUUID().slice(0, 8)
  const participants = { leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id], dealer_company_ids: [fixture!.companies.dealer!.company_id] }
  const expired = await create(context.request, mainMetadata(`Истёкший-${key}`, `EXPIRED-${key}`, { participants, valid_from: date(-40), valid_to: date(-1) }))
  const future = await create(context.request, mainMetadata(`Будущий-${key}`, `FUTURE-${key}`, { participants, valid_from: date(10) }))
  const created = await context.request.post('/api/v1/admin/monetization/programs', { data: { name: `Условие-UI-${key}`, status: 'inactive', leasing_company_id: fixture!.companies.leasing!.leasing_company_id, dealer_company_id: fixture!.companies.dealer!.company_id, period_start: date(), sources: [{ source_type: 'platform', expenses: [{ local_id: 'expense', participant_type: 'leasing', base_type: 'property_value', calc_type: 'percent', value: '1' }], incomes: [] }] } })
  expect(created.status(), await created.text()).toBe(201); const program = await created.json() as { id: string; name: string }
  await page.goto('/workspace/monetization'); await page.locator('.programs-table tbody tr').filter({ hasText: program.name }).getByRole('button', { name: 'Карточка', exact: true }).click(); const picker = page.locator('.dr-picker')
  const registryTab = picker.getByRole('tab', { name: 'Из справочника документов', exact: true })
  const uploadTab = picker.getByRole('tab', { name: 'Загрузить новый файл', exact: true })
  await expect(picker.getByRole('heading', { name: 'Приложить договор', exact: true })).toBeVisible()
  await expect(registryTab).toHaveAttribute('aria-selected', 'true'); await expect(picker).toContainText(future.name); await expect(picker).not.toContainText(expired.name)
  await expect(picker.getByRole('button', { name: 'Выбрать из справочника', exact: true })).toHaveCount(0); await expect(page.getByRole('dialog')).toHaveCount(0)
  const futureRow = picker.locator(`[data-document-id="${future.id}"]`)
  await expect(futureRow.getByRole('checkbox')).not.toBeChecked()
  for (const width of [768, 1280]) {
    await page.setViewportSize({ width, height: 1000 }); await picker.scrollIntoViewIfNeeded()
    await picker.screenshot({ path: `/tmp/carcraft-22296-e2e/monetization-picker-unselected-${width}.png` })
  }
  await futureRow.getByRole('checkbox').check(); await expect(futureRow).toHaveAttribute('data-selected', 'true')
  const fileDownload = page.waitForEvent('download'); await futureRow.getByRole('button', { name: 'договор.pdf', exact: true }).click(); expect((await fileDownload).suggestedFilename()).toBe('договор.pdf'); await expect(futureRow.getByRole('checkbox')).toBeChecked()
  for (const width of [768, 1280, 1920]) {
    await page.setViewportSize({ width, height: 1000 }); await picker.scrollIntoViewIfNeeded()
    await expect(futureRow.getByRole('button', { name: 'договор.pdf', exact: true })).toBeVisible()
    await picker.screenshot({ path: `/tmp/carcraft-22296-e2e/monetization-picker-${width}.png` })
  }
  await page.setViewportSize({ width: 1280, height: 1000 }); await saveLinks(page, picker)
  await registryTab.focus(); await registryTab.press('ArrowRight'); await expect(uploadTab).toBeFocused(); await expect(uploadTab).toHaveAttribute('aria-selected', 'true')
  await uploadTab.press('Home'); await expect(registryTab).toBeFocused(); await registryTab.press('End'); await expect(uploadTab).toBeFocused()
  for (const width of [768, 1280]) {
    await page.setViewportSize({ width, height: 1000 }); await picker.scrollIntoViewIfNeeded()
    await picker.screenshot({ path: `/tmp/carcraft-22296-e2e/monetization-picker-upload-${width}.png` })
  }
  await picker.getByRole('button', { name: 'Загрузить документ', exact: true }).click(); let dialog = page.getByRole('dialog'); await expect(dialog.getByRole('combobox', { name: 'Связка', exact: true }).locator(`option[value="${expired.group_id}"]`)).toContainText(expired.name); await dialog.getByRole('combobox', { name: 'Связка', exact: true }).selectOption(expired.group_id); await dialog.getByRole('button', { name: 'Продолжить', exact: true }).click(); dialog = page.getByRole('dialog'); await expect(dialog).toContainText('Отмена условий монетизации не удалит его'); await fillForm(dialog, `Новый-${key}`, `NEW-${key}`); await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0); await expect(registryTab).toHaveAttribute('aria-selected', 'true'); await expect(picker.locator('.contract-row').filter({ hasText: `Новый-${key}` }).getByRole('checkbox')).toBeChecked(); await saveLinks(page, picker)
  const deactivated = await context.request.patch(`/api/v1/document-registry/documents/${future.id}/activation`, { data: { active: false } }); expect(deactivated.status()).toBe(200)
  await page.reload(); await page.locator('.programs-table tbody tr').filter({ hasText: program.name }).getByRole('button', { name: 'Карточка', exact: true }).click()
  await expect(futureRow).toContainText('Деактивирован'); await expect(futureRow.getByRole('checkbox')).toBeChecked(); await futureRow.getByRole('checkbox').uncheck(); await picker.getByRole('button', { name: 'Отменить изменения', exact: true }).click(); await expect(futureRow.getByRole('checkbox')).toBeChecked()
  const reader = await session(browser, 'leasing'); await reader.page.goto('/workspace/monetization'); await reader.page.locator('.programs-table tbody tr').filter({ hasText: program.name }).getByRole('button', { name: 'Карточка', exact: true }).click()
  const readonlyPicker = reader.page.locator('.dr-picker'); await expect(readonlyPicker).toContainText(future.name); await expect(readonlyPicker).toContainText(`Новый-${key}`); await expect(readonlyPicker.getByRole('checkbox')).toHaveCount(0); await expect(readonlyPicker.getByRole('tab')).toHaveCount(0); await expect(readonlyPicker).not.toContainText(expired.name); expect(reader.errors).toEqual([]); await reader.context.close()
  const reactivated = await context.request.patch(`/api/v1/document-registry/documents/${future.id}/activation`, { data: { active: true } }); expect(reactivated.status()).toBe(200)
  const links = await context.request.get(`/api/v1/admin/monetization/programs/${program.id}/reference-documents`); const result = await links.json() as { items: { id: string; group_id: string; name: string }[] }; expect(result.items.map(item => item.name).sort()).toEqual([future.name, `Новый-${key}`].sort()); expect(result.items.find(item => item.name === `Новый-${key}`)?.group_id).toBe(expired.group_id)
  await page.goto(`/workspace/document-registry?document=${expired.id}`); await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click(); dialog = page.getByRole('dialog').last(); await expect(dialog).toContainText(program.name); await dialog.getByRole('button', { name: 'Удалить', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0)
  const remaining = await (await context.request.get(`/api/v1/admin/monetization/programs/${program.id}/reference-documents`)).json() as { items: { id: string }[] }; expect(remaining.items.map(item => item.id)).toEqual([future.id]); expect((await context.request.get(`/api/v1/admin/monetization/programs/${program.id}`)).status()).toBe(200)
  expect(errors).toEqual([]); await context.close()
})

test('company search remains interactive inside the modal and accepts multiple leasing companies', async ({ browser }) => {
  test.setTimeout(90_000)
  const { context, page, errors } = await session(browser, 'admin'); const key = randomUUID().slice(0, 8)
  await page.goto('/workspace/document-registry'); await page.getByRole('button', { name: 'Добавить документ', exact: true }).click(); const dialog = page.getByRole('dialog')
  await fillForm(dialog, `Компании-${key}`, `COMPANY-${key}`)
  const fieldset = dialog.getByRole('group', { name: 'Участники связки', exact: true }); const picker = fieldset.locator('.dr-company-picker').filter({ hasText: 'Лизинговые компании' })
  for (const alias of ['leasing', 'leasing2']) {
    await picker.getByRole('button', { name: 'Название или ИНН', exact: true }).click(); await dialog.locator('.shadow-xl input').fill(fixture!.companies[alias]!.name)
    await dialog.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + fixture!.companies[alias]!.name + ' ·') }).click(); await expect(picker.locator('.dr-tag').filter({ hasText: fixture!.companies[alias]!.name })).toBeVisible()
  }
  const saved = page.waitForResponse(response => response.url().endsWith('/document-registry/documents') && response.request().method() === 'POST'); await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); const response = await saved; expect(response.status(), await response.text()).toBe(201); const document = await response.json() as { id: string }
  await expect(page.getByRole('dialog')).toHaveCount(0); const reader = await session(browser, 'leasing2'); await reader.page.goto(`/workspace/document-registry?document=${document.id}`); await expect(reader.page.getByRole('dialog')).toContainText(`Компании-${key}`); expect(reader.errors).toEqual([]); await reader.context.close()
  expect(errors).toEqual([]); await context.close()
})

test('upload inside a new monetization draft saves the registry document even when the draft is cancelled', async ({ browser }) => {
  test.setTimeout(90_000)
  const { context, page, errors } = await session(browser, 'admin'); const key = randomUUID().slice(0, 8)
  await page.goto('/workspace/monetization'); await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click(); const editor = page.locator('.program-editor')
  await editor.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..').getByRole('button').click(); await page.getByPlaceholder('Название или ИНН', { exact: true }).fill(fixture!.companies.leasing!.name); await page.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + fixture!.companies.leasing!.name + ' ·') }).click()
  await expect(editor.getByRole('tab', { name: 'Из справочника документов', exact: true })).toHaveAttribute('aria-selected', 'true')
  await editor.getByRole('tab', { name: 'Загрузить новый файл', exact: true }).click()
  await editor.getByRole('button', { name: 'Загрузить документ', exact: true }).click(); let dialog = page.getByRole('dialog'); await dialog.getByRole('button', { name: 'Продолжить', exact: true }).click(); dialog = page.getByRole('dialog'); await expect(dialog).toContainText('Отмена условий монетизации не удалит его'); await fillForm(dialog, `Черновик-${key}`, `DRAFT-${key}`)
  const saved = page.waitForResponse(response => response.url().endsWith('/document-registry/documents') && response.request().method() === 'POST'); await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click(); const response = await saved; expect(response.status(), await response.text()).toBe(201); const document = await response.json() as { id: string }
  await expect(page.getByRole('dialog')).toHaveCount(0); await expect(editor).toBeVisible(); await expect(editor.getByRole('tab', { name: 'Из справочника документов', exact: true })).toHaveAttribute('aria-selected', 'true'); await expect(editor.locator('.contract-row[data-selected=true]').filter({ hasText: `Черновик-${key}` }).getByRole('checkbox')).toBeChecked(); await editor.getByRole('button', { name: 'Отмена', exact: true }).click(); await expect(editor).toHaveCount(0); expect((await context.request.get(`/api/v1/document-registry/documents/${document.id}`)).status()).toBe(200)
  expect(errors).toEqual([]); await context.close()
})


test('all edits create snapshots; restoring a version refreshes the registry and linked monetization', async ({ browser }) => {
  test.setTimeout(120_000)
  const { context, page, errors } = await session(browser, 'admin')
  const key = randomUUID().slice(0, 8); const name = `Версии-${key}`
  const document = await create(context.request, mainMetadata(name, `VERSIONS-${key}`, {
    participants: { leasing_company_ids: [fixture!.companies.leasing!.leasing_company_id], dealer_company_ids: [fixture!.companies.dealer!.company_id] },
    valid_to: date(60),
  }))
  const created = await context.request.post('/api/v1/admin/monetization/programs', { data: {
    name: `Версии-условие-${key}`, status: 'inactive', leasing_company_id: fixture!.companies.leasing!.leasing_company_id,
    dealer_company_id: fixture!.companies.dealer!.company_id, period_start: date(), reference_document_ids: [document.id],
    sources: [{ source_type: 'platform', expenses: [{ local_id: 'expense', participant_type: 'leasing', base_type: 'property_value', calc_type: 'percent', value: '1' }], incomes: [] }],
  } })
  expect(created.status(), await created.text()).toBe(201)
  const program = await created.json() as { id: string; name: string }
  async function saveVersion(dialog: Locator) {
    const pending = page.waitForResponse(response => response.url().endsWith(`/documents/${document.id}/versions`) && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click()
    const response = await pending; expect(response.status(), await response.text()).toBe(201)
    await expect(page.getByRole('dialog')).toHaveCount(1)
    return await response.json() as ReferenceDocument
  }
  async function restore(history: Locator, version: number, versionId: string) {
    const row = history.locator(`[data-version-number="${version}"]`)
    const pending = page.waitForResponse(response => response.url().endsWith(`/versions/${versionId}/activate`) && response.request().method() === 'POST')
    await row.getByRole('button', { name: 'Сделать текущей', exact: true }).click()
    const response = await pending; expect(response.status(), await response.text()).toBe(200)
    await expect(row.locator('.dr-main-badge')).toHaveText('Текущая')
    await expect(history.getByRole('status')).toHaveCount(0)
    return await response.json() as ReferenceDocument
  }
  await page.goto(`/workspace/document-registry?document=${document.id}`)
  const detail = page.getByRole('dialog').first().locator('.dr-document')
  await detail.getByRole('button', { name: 'Редактировать', exact: true }).click()
  let dialog = page.getByRole('dialog').last()
  await expect(dialog).toContainText('Сохранение создаст новую версию')
  await expect(dialog.getByLabel('Номер документа', { exact: false })).toBeDisabled()
  await expect(dialog.getByRole('combobox', { name: 'Тип документа', exact: true })).toBeDisabled()
  await expect(dialog.getByRole('group', { name: 'Участники связки', exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('list', { name: 'Сохранённые файлы', exact: true })).toContainText('договор.pdf')
  await dialog.getByLabel('Название', { exact: true }).fill(name + '-v2')
  await dialog.getByLabel('Действует с', { exact: true }).fill(date(-40))
  await dialog.getByLabel('Действует по', { exact: false }).fill(date(-1))
  const related = dialog.getByRole('group', { name: 'Связанные компании', exact: true }).locator('.dr-company-picker').filter({ hasText: 'Лизинговые компании' })
  await related.getByRole('button', { name: 'Название или ИНН', exact: true }).click()
  await dialog.locator('.shadow-xl input').fill(fixture!.companies.leasing2!.name)
  await dialog.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + fixture!.companies.leasing2!.name + ' ·') }).click()
  await expect(dialog.locator('.shadow-xl input')).toHaveCount(0)
  await dialog.screenshot({ path: '/tmp/carcraft-22296-e2e/registry-version-editor.png' })
  const v2 = await saveVersion(dialog)
  expect(v2.current_version.version_number).toBe(2); expect(v2.version_count).toBe(2)
  expect(v2.current_version.files.map(file => file.name)).toEqual(['договор.pdf'])
  expect(v2.related_companies.leasing_company_ids).toEqual([fixture!.companies.leasing2!.leasing_company_id])
  await expect(detail).toContainText(name + '-v2'); await expect(detail.locator('.dr-status')).toHaveText('Истёк')
  const oldFile = await context.request.get(document.current_version.files[0]!.download_url)
  expect(oldFile.status()).toBe(200); expect(await oldFile.body()).toEqual(pdf)

  await detail.getByRole('button', { name: 'Редактировать', exact: true }).click(); dialog = page.getByRole('dialog').last()
  await dialog.getByLabel('Название', { exact: true }).fill(name + '-v3')
  await dialog.getByLabel('Действует с', { exact: true }).fill(date())
  await dialog.getByLabel('Действует по', { exact: false }).fill(date(60))
  await dialog.getByRole('button', { name: 'Убрать файл договор.pdf', exact: true }).click()
  await dialog.getByRole('button', { name: 'Сохранить документ', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Выберите от 1 до 10')
  const replacementPdf = Buffer.concat([pdf, Buffer.from('\n% distinct replacement bytes ' + key + '\n')])
  await dialog.locator('input[type=file]').setInputFiles(upload('версия-3.pdf', replacementPdf))
  const v3 = await saveVersion(dialog)
  expect(v3.current_version.version_number).toBe(3); expect(v3.current_version.files.map(file => file.name)).toEqual(['версия-3.pdf'])
  await detail.getByRole('button', { name: 'Деактивировать', exact: true }).click(); await expect(detail.locator('.dr-status')).toHaveText('Деактивирован')
  await detail.getByRole('button', { name: 'История версий (3)', exact: true }).click(); dialog = page.getByRole('dialog').last()
  await expect(dialog.locator('[data-version-number="1"]')).toContainText(name)
  await expect(dialog.locator('[data-version-number="1"]')).not.toContainText(name + '-v2')
  await expect(dialog.locator('[data-version-number="1"]')).not.toContainText(fixture!.companies.leasing2!.name)
  await expect(dialog.locator('[data-version-number="2"]')).toContainText(name + '-v2')
  await expect(dialog.locator('[data-version-number="2"]')).toContainText(fixture!.companies.leasing2!.name)
  await expect(dialog.locator('[data-version-number="2"]')).toContainText('договор.pdf')
  await expect(dialog.locator('[data-version-number="3"]')).toContainText('версия-3.pdf')
  await expect(dialog.locator('.version-backfilled')).toHaveCount(0)
  const restored = await restore(dialog, 1, document.current_version.id)
  expect(restored.active).toBe(false); expect(restored.name).toBe(name); expect(restored.related_companies.leasing_company_ids).toEqual([])
  for (const [version, filename, contents] of [[1, 'договор.pdf', pdf], [3, 'версия-3.pdf', replacementPdf]] as const) {
    const fileResponse = page.waitForResponse(response => response.url().includes('/document-registry/files/') && response.url().includes('/download'))
    const download = page.waitForEvent('download')
    await dialog.locator(`[data-version-number="${version}"]`).getByRole('button', { name: filename, exact: true }).click()
    const response = await fileResponse; expect(response.status()).toBe(200)
    expect(await response.body()).toEqual(contents)
    expect((await download).suggestedFilename()).toBe(filename)
  }
  expect(replacementPdf.equals(pdf)).toBe(false)
  await dialog.screenshot({ path: '/tmp/carcraft-22296-e2e/registry-version-history.png' })
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click()
  await expect(detail).toContainText('Версия 1'); await expect(detail.locator('.dr-status')).toHaveText('Деактивирован')
  await detail.getByRole('button', { name: 'Редактировать', exact: true }).click(); dialog = page.getByRole('dialog').last()
  await expect(dialog.getByLabel('Название', { exact: true })).toHaveValue(name)
  await expect(dialog.getByRole('list', { name: 'Сохранённые файлы', exact: true })).toContainText('договор.pdf')
  await dialog.getByLabel('Название', { exact: true }).fill(name + '-v4')
  const v4 = await saveVersion(dialog)
  expect(v4.current_version.version_number).toBe(4); expect(v4.version_count).toBe(4); expect(v4.active).toBe(false)
  await detail.getByRole('button', { name: 'Активировать', exact: true }).click(); await expect(detail.locator('.dr-status')).toHaveText('Действует')

  await page.goto('/workspace/monetization')
  await page.locator('.programs-table tbody tr').filter({ hasText: program.name }).getByRole('button', { name: 'Карточка', exact: true }).click()
  const picker = page.locator('.dr-picker'); const linkedRow = picker.locator(`[data-document-id="${document.id}"]`)
  await expect(linkedRow).toContainText(name + '-v4'); await expect(linkedRow.getByRole('checkbox')).toBeChecked()
  await linkedRow.getByRole('button', { name: 'История версий', exact: true }).click(); dialog = page.getByRole('dialog')
  const restoredV2 = await restore(dialog, 2, v2.current_version.id)
  expect(restoredV2.status).toBe('expired'); expect(restoredV2.current_version.version_number).toBe(2)
  await dialog.getByRole('button', { name: 'Закрыть', exact: true }).click(); await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(linkedRow).toContainText(name + '-v2'); await expect(linkedRow).toContainText('Истёк'); await expect(linkedRow.getByRole('checkbox')).toBeChecked()
  await expect(linkedRow.getByRole('button', { name: 'договор.pdf', exact: true })).toBeVisible()
  await expect(picker.getByRole('button', { name: 'Сохранить связи', exact: true })).toHaveCount(0)
  const links = await (await context.request.get(`/api/v1/admin/monetization/programs/${program.id}/reference-documents`)).json() as { items: ReferenceDocument[] }
  expect(links.items.map(item => item.id)).toEqual([document.id]); expect(links.items[0]!.current_version.id).toBe(v2.current_version.id)
  const candidates = await (await context.request.post('/api/v1/document-registry/monetization-candidates', { data: { program_id: program.id } })).json() as { items: ReferenceDocument[] }
  expect(candidates.items.map(item => item.id)).not.toContain(document.id)

  const reader = await session(browser, 'dealer')
  await reader.page.goto(`/workspace/document-registry?document=${document.id}`)
  await expect(reader.page.getByRole('button', { name: 'Редактировать', exact: true })).toHaveCount(0)
  await reader.page.getByRole('dialog').getByRole('button', { name: 'История версий (4)', exact: true }).click()
  await expect(reader.page.getByRole('dialog').last().locator('[data-version-number="2"] .dr-main-badge')).toHaveText('Текущая')
  await expect(reader.page.getByRole('button', { name: 'Сделать текущей', exact: true })).toHaveCount(0)
  const denied = await reader.context.request.post(`/api/v1/document-registry/documents/${document.id}/versions/${document.current_version.id}/activate`, { data: { expected_current_version_id: v2.current_version.id } })
  expect(denied.status()).toBe(403)
  expect(reader.errors).toEqual([]); await reader.context.close()
  expect(errors).toEqual([]); await context.close()
})
