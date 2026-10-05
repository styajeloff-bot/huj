import { test, expect, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

const artifacts = process.env.E2E_STOREFRONT_THEME_ARTIFACT_DIR || resolve('../artifacts/e2e/storefront-theme')
const enabled = Boolean(process.env.E2E_STOREFRONT_THEME_ARTIFACT_DIR)
const manifest = enabled ? JSON.parse(readFileSync(resolve(artifacts, 'manifest.json'), 'utf8')) : { storefront: '', page: '' }
const admin = enabled ? JSON.parse(readFileSync(resolve(artifacts, 'admin.storage.json'), 'utf8')) : { cookies: [], origins: [] }
const client = enabled ? JSON.parse(readFileSync(resolve(artifacts, 'client.storage.json'), 'utf8')) : { cookies: [], origins: [] }
const endpoint = `/api/v1/admin/storefronts/${manifest.storefront}/pages/${manifest.page}`
const palette = ['#9B245C', '#F4E4C9', '#D8E7ED', '#173B52']
const rgb = ['rgb(155, 36, 92)', 'rgb(244, 228, 201)', 'rgb(216, 231, 237)', 'rgb(23, 59, 82)']
const calculator = (page: Page) => page.getByRole('heading', { name: 'E2E Palette Calculator' }).locator('xpath=../..')

async function checkPalette(page: Page) {
  await expect(page.locator('.storefront-page-renderer')).toHaveCSS('background-color', rgb[1])
  await expect(calculator(page)).toHaveCSS('background-color', rgb[2])
  await expect(page.getByRole('heading', { name: 'E2E Palette Calculator' })).toHaveCSS('color', rgb[3])
  await expect(calculator(page).getByRole('button', { name: 'Подать заявку' })).toHaveCSS('background-color', rgb[0])
  await expect(page.getByText('E2E explicit override', { exact: true })).toHaveCSS('color', 'rgb(90, 34, 136)')
}

async function saveAndPublish(page: Page, settings: Record<string, unknown>, sections?: unknown[]) {
  const current = await (await page.request.get(endpoint)).json()
  const draft = { ...current.draft_layout, settings, ...(sections ? { sections } : {}) }
  const saved = await page.request.put(`${endpoint}/draft`, { data: { expected_version: current.version, draft_layout: draft } })
  expect(saved.ok()).toBeTruthy()
  const version = (await saved.json()).version
  const published = await page.request.post(`${endpoint}/publish`, { data: { expected_version: version } })
  expect(published.ok()).toBeTruthy()
}

test.describe('Real storefront page palette', () => {
  test.skip(!enabled, 'Requires scripts/e2e/storefront-theme/run.sh isolated fixtures')
  test.use({ storageState: admin })
  test.beforeEach(async ({ page }) => {
    const sections = [{ id: randomUUID(), name: 'E2E Palette', layout_type: 'container', columns: [{ id: randomUUID(), width: 12, widgets: [
      { id: randomUUID(), type: 'leasing_calculator', props: { title: 'E2E Palette Calculator', subtitle: 'Theme preview', show_apply_button: true } },
      { id: randomUUID(), type: 'rich_text', props: { html_content: '<p>E2E explicit override</p>' }, styles: { text_color: '#5A2288', background_color: '#EDDDAA' } },
    ] }] }]
    await saveAndPublish(page, {}, sections)
  })
  test('builder preview, save/reload, draft isolation, undo/redo and publish at desktop widths', async ({ page, context }) => {
    test.setTimeout(90_000)
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`/workspace/storefronts/${manifest.storefront}/builder`)
    await page.locator('header select').selectOption(manifest.page)
    await expect(calculator(page)).toBeVisible()
    await page.getByRole('button', { name: 'Глобальный стиль', exact: true }).click()
    const inputs = page.locator('aside input[type=color]')
    await expect(inputs.first()).toHaveValue('#247a49')
    for (let index = 0; index < palette.length; index++) {
      await inputs.nth(index).fill(palette[index])
    }
    await checkPalette(page)
    await page.screenshot({ path: resolve(artifacts, "builder-palette.png"), fullPage: true })
    await page.getByTitle('Отменить действие (Ctrl+Z / Cmd+Z)').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { name: 'E2E Palette Calculator' })).not.toHaveCSS('color', rgb[3])
    await page.getByTitle('Повторить действие (Ctrl+Shift+Z / Cmd+Shift+Z)').focus()
    await page.keyboard.press('Enter')
    await checkPalette(page)
    const publicBefore = await (await page.request.get('/api/v1/storefront/pages/about')).json()
    const savedResponse = page.waitForResponse(res => res.url().endsWith('/draft') && res.request().method() === 'PUT')
    await page.getByRole('button', { name: 'Сохранить черновик', exact: true }).click()
    expect((await savedResponse).ok()).toBeTruthy()
    await page.reload()
    await page.locator('header select').selectOption(manifest.page)
    await expect(calculator(page)).toBeVisible()
    await checkPalette(page)
    const publicAfterDraft = await (await page.request.get('/api/v1/storefront/pages/about')).json()
    expect(publicAfterDraft.layout).toEqual(publicBefore.layout)
    expect(publicAfterDraft.published_at).toEqual(publicBefore.published_at)
    const publicPage = await context.newPage()
    publicPage.on('pageerror', error => errors.push(error.message))
    await publicPage.goto('/about')
    await expect(calculator(publicPage).getByRole('button', { name: 'Подать заявку' })).toHaveCSS('background-color', 'rgb(36, 122, 73)')
    const headerPrimary = await publicPage.locator('header').first().evaluate(el => getComputedStyle(el).getPropertyValue('--storefront-primary'))
    await page.getByRole('button', { name: 'Опубликовать', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Опубликовать витрину?' })).toBeVisible()
    const publish = page.waitForResponse(res => res.url().endsWith('/publish') && res.request().method() === 'POST')
    await page.getByRole('button', { name: 'Да, опубликовать', exact: true }).click()
    expect((await publish).ok()).toBeTruthy()
    for (const width of [1440, 768]) {
      await publicPage.setViewportSize({ width, height: 1000 })
      await publicPage.reload()
      await checkPalette(publicPage)
      await publicPage.screenshot({ path: resolve(artifacts, `public-palette-${width}.png`), fullPage: true })
      expect(await publicPage.locator('header').first().evaluate(el => getComputedStyle(el).getPropertyValue('--storefront-primary'))).toEqual(headerPrimary)
      const ranges = calculator(publicPage).locator('input[type=range]')
      await expect(ranges).toHaveCount(3)
      for (const range of await ranges.all()) {
        await expect(range).toBeVisible()
        const styles = await range.evaluate(el => ({ background: getComputedStyle(el).backgroundColor, height: el.getBoundingClientRect().height, thumb: getComputedStyle(el, '::-webkit-slider-thumb').backgroundColor }))
        expect(styles.background).not.toBe('rgba(0, 0, 0, 0)')
        expect(styles.background).not.toBe(rgb[2])
        expect(styles.height).toBeGreaterThanOrEqual(8)
      }
      await ranges.first().hover()
      await ranges.first().screenshot({ path: resolve(artifacts, `range-hover-${width}.png`) })
      const number = calculator(publicPage).locator('input[type=number]').first()
      const oldValue = await number.inputValue()
      await ranges.first().focus()
      await ranges.first().press('ArrowRight')
      await expect(number).not.toHaveValue(oldValue)
      const focused = await ranges.first().evaluate(el => ({ outline: getComputedStyle(el).outlineStyle, shadow: getComputedStyle(el).boxShadow }))
      expect(focused.outline !== 'none' || focused.shadow !== 'none').toBeTruthy()
    }
    await publicPage.goto('/')
    await expect(publicPage.locator('header').first()).toBeVisible()
    expect(await publicPage.locator('header').first().evaluate(el => getComputedStyle(el).getPropertyValue('--storefront-primary'))).toEqual(headerPrimary)
    expect(errors).toEqual([])
  })

  test('all widget types inherit palette and retain explicit section/column colors', async ({ page }) => {
    const widget = (type: string, props: Record<string, unknown>, styles?: Record<string, unknown>) => ({ id: randomUUID(), type, props, styles })
    const section = { id: randomUUID(), name: 'Widget palette coverage', layout_type: 'container', styles: { background_color: '#EEDDAA' }, columns: [{ id: randomUUID(), width: 12, styles: { background_color: '#CCEEDD' }, widgets: [
      widget('hero_banner', { title: 'E2E Hero', cta_text: 'Hero CTA', cta_link: '/about' }),
      widget('cta_strip', { title: 'E2E CTA', button_text: 'CTA action', button_link: '/about', background_style: 'primary' }),
      widget('features_grid', { title: 'E2E Features', items: [{ icon: 'clock', title: 'E2E Feature card', description: 'Card description' }] }),
      widget('lead_form', { title: 'E2E Form', show_phone: true, submit_button_text: 'E2E Form submit' }),
      widget('product_showcase', { title: 'E2E Catalog', item_count: 2 }),
      widget('partners_carousel', { title: 'E2E Partners', items: [{ name: 'E2E partner', logo_url: '/favicon.ico' }] }),
      widget('faq_accordion', { title: 'E2E FAQ', items: [{ question: 'E2E question', answer: 'E2E answer' }], open_first: true }),
      widget('contacts_block', { title: 'E2E Contacts', show_phone: true, phone: '+70000000000' }),
      widget('spacer_divider', { height_px: 24, show_divider: true, divider_color: '#672DA1' }),
      widget('spacer_divider', { height_px: 24, show_divider: true }),
    ] }] }
    await saveAndPublish(page, Object.fromEntries(['primary_color', 'background_color', 'surface_color', 'text_color'].map((key, index) => [key, palette[index]])), [section])
    await page.goto('/about')
    await expect(page.locator(`[data-section-id="${section.id}"]`)).toHaveCSS('background-color', 'rgb(238, 221, 170)')
    await expect(page.locator(`[data-column-id="${section.columns[0].id}"]`)).toHaveCSS('background-color', 'rgb(204, 238, 221)')
    const byType = (type: string) => page.locator(`[data-widget-id="${section.columns[0].widgets.find(item => item.type === type)!.id}"]`)
    for (const type of ['hero_banner', 'cta_strip']) {
      await expect(byType(type).locator('.storefront-builder-widget')).toHaveCSS('background-color', rgb[0])
    }
    for (const title of ['E2E Features', 'E2E Form', 'E2E Catalog', 'E2E Partners', 'E2E FAQ', 'E2E Contacts']) {
      await expect(page.getByRole('heading', { name: title, exact: true })).toHaveCSS('color', rgb[3])
    }
    await expect(page.getByRole('heading', { name: 'E2E Feature card' }).locator('..')).toHaveCSS('background-color', 'rgb(204, 238, 221)')
    await expect(page.locator('[data-widget=lead_form]')).toHaveCSS('background-color', 'rgb(204, 238, 221)')
    await expect(page.getByRole('button', { name: 'E2E Form submit', exact: true })).toHaveCSS('background-color', rgb[0])
    await expect(byType('product_showcase').getByRole('link', { name: 'Все предложения' })).toHaveCSS('color', rgb[0])
    await expect(byType('faq_accordion').getByRole('button', { name: 'E2E question' }).locator('xpath=../..')).toHaveCSS('background-color', 'rgb(204, 238, 221)')
    await expect(byType('spacer_divider').locator('[style*="border"]')).toHaveCSS('border-top-color', 'rgb(103, 45, 161)')
    const defaultDivider = section.columns[0].widgets.filter(item => item.type === 'spacer_divider')[1]
    const defaultDividerElement = page.locator(`[data-widget-id="${defaultDivider.id}"] [style*="border"]`)
    const expectedBorder = await defaultDividerElement.evaluate(el => {
      const probe = document.createElement('span')
      probe.style.color = 'var(--storefront-border)'
      el.appendChild(probe)
      const color = getComputedStyle(probe).color
      probe.remove()
      return color
    })
    expect(await defaultDividerElement.evaluate(el => getComputedStyle(el).borderTopColor)).toBe(expectedBorder)
    await page.screenshot({ path: resolve(artifacts, 'all-widgets-palette.png'), fullPage: true })
  })

  test('invalid/missing colors inherit storefront and empty page uses fallback', async ({ page }) => {
    await saveAndPublish(page, { primary_color: 'invalid', background_color: '', text_color: 'url(javascript:alert(1))' })
    await page.goto('/about')
    await expect(calculator(page)).toHaveCSS('background-color', 'rgb(227, 234, 220)')
    await expect(page.locator('.storefront-page-renderer')).toHaveCSS('background-color', 'rgb(242, 244, 239)')
    await expect(page.getByRole('heading', { name: 'E2E Palette Calculator' })).toHaveCSS('color', 'rgb(38, 59, 49)')
    await expect(calculator(page).getByRole('button', { name: 'Подать заявку' })).toHaveCSS('background-color', 'rgb(36, 122, 73)')
    const builderPage = await page.context().newPage()
    await builderPage.goto(`/workspace/storefronts/${manifest.storefront}/builder`)
    await builderPage.locator('header select').selectOption(manifest.page)
    await builderPage.getByRole('button', { name: 'Глобальный стиль', exact: true }).click()
    await expect(builderPage.locator('aside input[type=color]').first()).toHaveValue('#247a49')
    await saveAndPublish(page, { primary_color: '#ABC', background_color: '#FEF' })
    expect((await (await page.request.get('/api/v1/storefront/pages/about')).json()).layout.settings.primary_color).toBe('#ABC')
    await page.reload()
    await expect(calculator(page).getByRole('button', { name: 'Подать заявку' })).toHaveCSS('background-color', 'rgb(170, 187, 204)')
    await expect(page.locator('.storefront-page-renderer')).toHaveCSS('background-color', 'rgb(255, 238, 255)')
    await builderPage.reload()
    await builderPage.locator('header select').selectOption(manifest.page)
    await builderPage.getByRole('button', { name: 'Глобальный стиль', exact: true }).click()
    await expect(builderPage.locator('aside input[type=color]').first()).toHaveValue('#aabbcc')
    await expect(builderPage.locator('aside input[type=color]').nth(1)).toHaveValue('#ffeeff')
    await builderPage.close()
    await saveAndPublish(page, { primary_color: palette[0], background_color: palette[1] }, [])
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Наша миссия' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'E2E Palette Calculator' })).toHaveCount(0)
    await expect(page.locator('.storefront-page-renderer')).not.toHaveCSS('background-color', rgb[1])
  })

  test('existing write authorization, layout validation and stale version errors', async ({ page, playwright, baseURL }) => {
    const anonymous = await playwright.request.newContext({ baseURL, storageState: { cookies: [], origins: [] } })
    const restricted = await playwright.request.newContext({ baseURL, storageState: client })
    expect((await anonymous.get(endpoint)).status()).toBe(401)
    expect((await restricted.get(endpoint)).status()).toBe(403)
    const current = await (await page.request.get(endpoint)).json()
    const draft = { expected_version: current.version, draft_layout: current.draft_layout }
    expect((await anonymous.put(`${endpoint}/draft`, { data: draft })).status()).toBe(401)
    expect((await restricted.put(`${endpoint}/draft`, { data: draft })).status()).toBe(403)
    expect((await page.request.put(`${endpoint}/draft`, { data: { ...draft, expected_version: 0 } })).status()).toBe(422)
    expect((await page.request.post(`${endpoint}/publish`, { data: { expected_version: current.version + 100 } })).status()).toBe(409)
    expect((await page.request.put(`${endpoint}/draft`, { data: { ...draft, expected_version: current.version + 100 } })).status()).toBe(409)
    await anonymous.dispose()
    await restricted.dispose()
  })
})
