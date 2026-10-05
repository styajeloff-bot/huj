import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const manifestPath = path.join(runtime, 'manifest.json')
interface ManagementFixture {
  application_id: string
  requisites_name: string
  document_title: string
  document_id: string
  empty_pending_request_id: string
}
interface Manifest {
  management_company?: ManagementFixture
  companies: Record<string, { leasing_company_id?: string }>
}
const manifest: Manifest | null = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null
const fixture = manifest?.management_company
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'

test.describe('22286 management company requisites and scoped documents', () => {
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(90_000)
  test.skip(!manifest, 'Run the isolated 22286 API fixtures first')
  test.beforeAll(() => { expect(fixture, 'management_company_acceptance.py fixture is required').toBeDefined() })

  for (const role of ['lc_a', 'lc_b']) {
    test(role + ' sees requisites and only its available document at 768px', async ({ browser }) => {
      const context = await browser.newContext({
        storageState: path.join(runtime, role + '.storage.json'), baseURL,
        viewport: { width: 768, height: 1000 }
      })
      const serverErrors: string[] = []
      context.on('response', response => {
        if (new URL(response.url()).pathname.startsWith('/api/v1/') && response.status() >= 500) {
          serverErrors.push(response.status() + ' ' + new URL(response.url()).pathname)
        }
      })
      try {
        const page = await context.newPage()
        const companyId = manifest!.companies[role].leasing_company_id!
        await page.goto('/workspace/questionnaire/' + fixture!.application_id + '?source=leasing&leasing_company_id=' + companyId)
        const section = page.getByTestId('application-questionnaire')
        await expect(section).toBeVisible({ timeout: 30_000 })
        const row = section.locator('dt').filter({ hasText: /^Сведения об управляющей компании$/ }).locator('..')
        await expect(row).toContainText('Реквизиты управляющей компании')
        await expect(row).toContainText(fixture!.requisites_name)
        if (role === 'lc_a') {
          await expect(row).toContainText('Файл приложен: ' + fixture!.document_title)
          const open = row.getByRole('link', { name: 'Открыть ' + fixture!.document_title, exact: true })
          await expect(open).toHaveAttribute('href', new RegExp('/documents/' + fixture!.document_id + '/content'))
          const downloadPromise = page.waitForEvent('download')
          await row.getByRole('link', { name: 'Скачать', exact: true }).click()
          const download = await downloadPromise
          const destination = path.join(runtime, 'management-company-lc-a.pdf')
          await download.saveAs(destination)
          expect(fs.readFileSync(destination).subarray(0, 5).toString()).toBe('%PDF-')
        } else {
          await expect(row).toContainText('Документ об управляющей компании не предоставлен')
          await expect(row).not.toContainText(fixture!.document_title)
          await expect(row.getByRole('link')).toHaveCount(0)
        }
        await page.reload()
        await expect(row).toContainText(fixture!.requisites_name)
        await expect(row).toContainText(role === 'lc_a'
          ? 'Файл приложен: ' + fixture!.document_title
          : 'Документ об управляющей компании не предоставлен')
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
        await row.screenshot({ path: path.join(runtime, 'management-company-' + role + '.png') })
        expect(serverErrors).toEqual([])
      } finally {
        await context.close()
      }
    })
  }

  test('client can answer the management-company request without a file and keep requisites', async ({ browser }) => {
    expect(fixture!.empty_pending_request_id).toBeTruthy()
    const context = await browser.newContext({
      storageState: path.join(runtime, 'client.storage.json'), baseURL,
      viewport: { width: 768, height: 1000 }
    })
    const serverErrors: string[] = []
    context.on('response', response => {
      if (new URL(response.url()).pathname.startsWith('/api/v1/') && response.status() >= 500) {
        serverErrors.push(response.status() + ' ' + new URL(response.url()).pathname)
      }
    })
    try {
      const page = await context.newPage()
      await page.goto('/application/' + fixture!.application_id)
      await page.getByRole('button', { name: 'Ответить на запрос', exact: true }).click({ timeout: 30_000 })
      const dialog = page.getByRole('dialog')
      await expect(dialog.getByText('(необязательно)', { exact: true })).toBeVisible()
      await dialog.getByRole('button', { name: 'Отправить', exact: true }).click()
      await expect(dialog).toHaveCount(0)
      const current = async () => {
        const response = await page.request.get('/api/v1/questionnaire/' + fixture!.application_id)
        expect(response.ok()).toBeTruthy()
        return (await response.json()).questionnaire.management_company_details
      }
      await expect.poll(async () => (await current()).status).toBe('not_provided')
      const saved = await current()
      expect(saved.file_name).toBeNull()
      expect(saved.documents).toEqual([])
      expect(JSON.stringify(saved.requisites)).toContain(fixture!.requisites_name)
      const response = await page.request.get('/api/v1/applications/' + fixture!.application_id + '/document-requests')
      expect(response.ok()).toBeTruthy()
      const history = await response.json() as { batches: Array<{ items: Array<{ id: string; status: string; attachments?: unknown[] }> }> }
      expect(history.batches.flatMap(batch => batch.items).find(item => item.id === fixture!.empty_pending_request_id))
        .toMatchObject({ status: 'provided', attachments: [] })
      await page.reload()
      await expect(page.getByRole('button', { name: 'Ответить на запрос', exact: true })).toHaveCount(0)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
      expect(serverErrors).toEqual([])
    } finally {
      await context.close()
    }
  })
})
