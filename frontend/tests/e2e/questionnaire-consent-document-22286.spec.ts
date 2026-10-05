import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { createHash } from 'node:crypto'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const manifestPath = path.join(runtime, 'consent-document-manifest.json')
interface Manifest { application_id: string; signature_request_id: string; field: string; sha256: string; filename: string; lc_a: string }
const fixture: Manifest | null = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'

test.describe('22286 existing SOPD from questionnaire', () => {
  test.setTimeout(90_000)
  test.skip(!fixture, 'Run consent_document_acceptance.py to prepare isolated real files')

  test('LC opens and downloads the existing SOPD from its questionnaire', async ({ browser }) => {
    const role = 'lc_a'
    const context = await browser.newContext({ storageState: path.join(runtime, `${role}.storage.json`), baseURL, viewport: { width: 1440, height: 1000 } })
    const serverErrors: string[] = []
    context.on('response', response => { if (new URL(response.url()).pathname.startsWith('/api/v1/') && response.status() >= 500) serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`) })
    try {
      const page = await context.newPage()
      await page.goto(`/workspace/leasing-applications/${fixture!.application_id}?leasing_company_id=${fixture!.lc_a}`)
      await page.getByRole('link', { name: 'Открыть анкету', exact: true }).click()
      await expect(page).toHaveURL(new RegExp(`/workspace/questionnaire/${fixture!.application_id}\\?`))
      const section = page.getByTestId('application-questionnaire')
      await expect(section).toBeVisible({ timeout: 30_000 })
      const consent = section.locator('dt').filter({ hasText: /^Согласие на обработку персональных данных$/ }).locator('..')
      await expect(consent).toContainText('СОПД от ')
      await expect(consent).not.toContainText('СОПД №')
      const open = consent.getByRole('link', { name: 'Открыть СОПД', exact: true })
      await expect(open).toHaveAttribute('href', new RegExp(`/questionnaire/${fixture!.application_id}/consents/${fixture!.signature_request_id}/content\\?`))
      const popupPromise = page.waitForEvent('popup')
      await open.click()
      const popup = await popupPromise
      await popup.waitForLoadState('domcontentloaded')
      await expect(popup.locator('img')).toBeVisible()
      expect(await popup.locator('img').evaluate(image => (image as HTMLImageElement).naturalWidth)).toBe(1)
      await popup.close()
      const downloadPromise = page.waitForEvent('download')
      await consent.getByRole('link', { name: 'Скачать СОПД', exact: true }).click()
      const download = await downloadPromise
      expect(download.suggestedFilename()).toBe(fixture!.filename)
      const destination = path.join(runtime, `consent-document-${role}.png`)
      await download.saveAs(destination)
      expect(createHash('sha256').update(fs.readFileSync(destination)).digest('hex')).toBe(fixture!.sha256)
      await page.screenshot({ path: path.join(runtime, `consent-document-${role}-links.png`), fullPage: true })
      expect(serverErrors).toEqual([])
    } finally { await context.close() }
  })
})
