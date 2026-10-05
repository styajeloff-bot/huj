import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext, type Browser } from '@playwright/test'
import type { ReferenceDocument } from '../../../features/documentRegistry'

interface Fixture { marker: string; base_url: string; storage_states: Record<string, string>; companies: Record<string, { company_id: string }> }
const enabled = process.env.DOCUMENT_REGISTRY_E2E === '1'
const fixture: Fixture | null = enabled ? JSON.parse(readFileSync(process.env.DOCUMENT_REGISTRY_E2E_FIXTURE ?? '/tmp/carcraft-22296-e2e/manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'document-registry-22296' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) throw new Error('Use the isolated 22296 fixture only')
test.skip(!enabled, 'Requires the isolated document registry fixture')
const pdf = Buffer.from('%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n')
async function session(browser: Browser, role: string) {
  const path = fixture!.storage_states[role]!
  const csrf = JSON.parse(readFileSync(path, 'utf8')).cookies.find((cookie: { name: string }) => cookie.name === 'csrfToken').value
  return browser.newContext({ baseURL: fixture!.base_url, storageState: path, extraHTTPHeaders: { Origin: fixture!.base_url, 'X-CSRF-Token': csrf }, locale: 'ru-RU', timezoneId: 'Europe/Moscow', viewport: { width: 1280, height: 1000 } })
}
async function create(request: APIRequestContext, name: string, groupId?: string, extra: object = {}) {
  const response = await request.post(`/api/v1/document-registry/${groupId ? `groups/${groupId}/documents` : 'documents'}`, { multipart: { metadata: JSON.stringify({ document_type: 'contract', contract_number: randomUUID(), name, valid_from: '2026-01-01', ...(groupId ? {} : { participants: { platform_ml: true } }), ...extra }), files: { name: 'contract.pdf', mimeType: 'application/pdf', buffer: pdf } } })
  expect(response.status(), await response.text()).toBe(201)
  return await response.json() as ReferenceDocument
}
async function remove(request: APIRequestContext, id: string) {
  const impact = await (await request.get(`/api/v1/document-registry/documents/${id}/monetization-usages`)).json() as { fingerprint: string }
  expect((await request.delete(`/api/v1/document-registry/documents/${id}`, { headers: { 'If-Match': impact.fingerprint } })).status()).toBe(204)
}

test('expanded group tabs count only displayed child documents, never the main or file versions', async ({ browser }) => {
  const context = await session(browser, 'admin'); const page = await context.newPage(); const name = 'Count-' + randomUUID().slice(0, 8)
  const main = await create(context.request, name); const child = await create(context.request, name + '-child', main.group_id)
  const act = await create(context.request, name + '-act', main.group_id, { document_type: 'act' })
  try {
    const version = await context.request.post(`/api/v1/document-registry/documents/${child.id}/versions`, { multipart: { metadata: JSON.stringify({ expected_current_version_id: child.current_version.id, name: child.name, related_companies: { platform_ml: false, leasing_company_ids: [], dealer_company_ids: [], distributor_company_ids: [] }, valid_from: '2026-01-01', valid_to: null, retained_file_ids: [] }), files: { name: 'v2.pdf', mimeType: 'application/pdf', buffer: pdf } } })
    expect(version.status(), await version.text()).toBe(201)
    await page.goto('/workspace/document-registry'); await page.getByPlaceholder('Поиск документов').fill(name)
    await expect(page.locator('.dr-group')).toHaveCount(1)
    const group = page.locator('.dr-group').filter({ hasText: name }); await expect(group).toHaveCount(1)
    await group.getByRole('button', { name: /Показать ещё 2/ }).click()
    await expect(group.locator('.dr-document')).toHaveCount(3)
    const response = await context.request.get(`/api/v1/document-registry/groups/${main.group_id}/documents`)
    const rows = await response.json() as { items: { id: string; is_main: boolean; current_version: { version_number: number } }[] }
    expect(new Set(rows.items.map(item => item.id)).size).toBe(3)
    expect(rows.items.filter(item => !item.is_main)).toHaveLength(2)
    await expect(group.getByRole('tab', { name: /^Все / })).toHaveText('Все (2)')
    await expect(group.getByRole('tab', { name: /^Договор / })).toHaveText('Договор (1)')
    await group.getByRole('tab', { name: /^Договор / }).click()
    await expect(group.locator('.dr-document').filter({ hasText: name + '-child' })).toContainText('Версия 2')
    await expect(group.getByRole('tab', { name: 'Договор (1)', exact: true })).toHaveAttribute('aria-selected', 'true')
    const panel = group.getByRole('tabpanel')
    await expect(panel.locator('[data-document-id]')).toHaveCount(1)
    expect(await panel.locator('[data-document-id]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id')))).toEqual([child.id])
    await group.getByRole('tab', { name: 'Акт (1)', exact: true }).click()
    await expect(panel.locator('[data-document-id]')).toHaveCount(1)
    expect(await panel.locator('[data-document-id]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id')))).toEqual([act.id])
    await group.getByRole('tab', { name: 'Счёт (0)', exact: true }).click()
    await expect(panel).toContainText('Дочерних документов этого типа нет.')
    await expect(panel.locator('[data-document-id]')).toHaveCount(0)
    await expect(group.locator(':scope > [data-document-id]')).toHaveAttribute('data-document-id', main.id)
    await group.getByRole('tab', { name: 'Все (2)', exact: true }).click()
    await expect(panel.locator('[data-document-id]')).toHaveCount(2)
    expect((await panel.locator('[data-document-id]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-document-id')))).sort()).toEqual([child.id, act.id].sort())
    await page.screenshot({ path: process.env.DOCUMENT_REGISTRY_COUNTER_SCREENSHOT ?? '/tmp/carcraft-22296-e2e/group-counter-fixed.png', fullPage: true })
  } finally { await remove(context.request, main.id); await context.close() }
})

test('child-only partner does not lose one count for an inaccessible main document', async ({ browser }) => {
  const admin = await session(browser, 'admin'); const reader = await session(browser, 'outsider'); const page = await reader.newPage(); const name = 'Count-ACL-' + randomUUID().slice(0, 8)
  const main = await create(admin.request, name + '-private', undefined, { participants: { dealer_company_ids: [fixture!.companies.dealer!.company_id] } })
  await create(admin.request, name + '-visible', main.group_id, { related_companies: { dealer_company_ids: [fixture!.companies.dealer2!.company_id] } })
  try {
    await page.goto('/workspace/document-registry'); await page.getByPlaceholder('Поиск документов').fill(name)
    const group = page.locator('.dr-group'); await expect(group).toHaveCount(1); await expect(group).not.toContainText(name + '-private')
    await expect(group.locator('.dr-document')).toHaveCount(1)
    await expect(group.getByRole('tab', { name: 'Все (1)', exact: true })).toBeVisible()
    await expect(group.getByRole('tab', { name: 'Договор (1)', exact: true })).toBeVisible()
  } finally { await remove(admin.request, main.id); await reader.close(); await admin.close() }
})
