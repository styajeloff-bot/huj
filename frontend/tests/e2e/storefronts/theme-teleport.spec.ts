import { test, expect } from '@playwright/test'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Compile the actual shared Modal and theme, without an API/server fixture.
// The only adapter supplies Nuxt's Vue auto-imports and the feature public seam.
const frontend = resolve(__dirname, '../../..')
let fixture: string
test.beforeAll(async () => {
  const result = await build({
    stdin: { contents: `
      import { createApp, h, ref } from 'vue'
      import Modal from './components/ui/Modal.vue'
      import { buildStorefrontTheme, serializeStorefrontThemeVariables } from './features/storefront/theme'
      import { createDefaultStorefrontAppearance } from './features/storefront/appearance'
      const appearance = createDefaultStorefrontAppearance()
      window.updateTheme = (overrides, active = true) => {
        appearance.color_overrides = overrides
        const theme = buildStorefrontTheme(appearance)
        document.body.classList.toggle('storefront-theme', active)
        document.body.style.cssText = active ? serializeStorefrontThemeVariables(theme.variables) : ''
        document.querySelector('#theme').textContent = active ? theme.scopeCss : ''
        return theme
      }
      window.previewModalTitle = () => buildStorefrontTheme(appearance, { block: 'shared.modal', parent: 'client.checkout' }).blocks['shared.modal']['--storefront-title']
      window.updateTheme({ 'client.checkout.title': '#123456' })
      const show = ref(Boolean(window.initialModal))
      window.openModal = () => { show.value = true }
      createApp({ setup: () => () => h('section', { 'data-storefront-block': 'client.checkout' }, [
        h(Modal, { show: show.value, title: 'Actual shared modal' }, {
          default: () => h('form', { 'data-storefront-block': 'shared.form', id: 'nested-form' }, 'Form')
        })
      ]) }).mount('#app')
    `, resolveDir: frontend, loader: 'ts' },
    bundle: true, write: false, format: 'iife', platform: 'browser',
    alias: { '~': frontend },
    define: { 'import.meta.client': 'true', 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true', __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false' },
    plugins: [{ name: 'actual-modal', setup(builder) {
      builder.onLoad({ filter: /Modal\.vue$/ }, args => {
        const { descriptor } = parse(readFileSync(args.path, 'utf8'), { filename: args.path })
        const compiled = compileScript(descriptor, { id: 'modal-theme-test', inlineTemplate: true })
        return { contents: `import { ref, computed, watch, onBeforeUnmount, nextTick, useId } from 'vue';\n${compiled.content}`, loader: 'ts', resolveDir: resolve(frontend, 'components/ui') }
      })
      builder.onResolve({ filter: /^~\/features\/storefront$/ }, () => ({ path: 'storefront-public-seam', namespace: 'test' }))
      builder.onLoad({ filter: /.*/, namespace: 'test' }, () => ({ contents: `export { useStorefrontTeleportContext } from './features/storefront/composables/useStorefrontTeleportContext'`, loader: 'ts', resolveDir: frontend }))
    } }],
  })
  fixture = result.outputFiles[0]!.text
})

test.beforeEach(async ({ page }) => {
  await page.setContent('<html><head><style id="theme"></style></head><body><div id="app"></div></body></html>')
  await page.addScriptTag({ content: fixture })
})

test('actual parent colors cross Teleport, with explicit modal/form choices and reset', async ({ page }) => {
  await page.evaluate('window.openModal()')
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  const color = () => dialog.evaluate(element => getComputedStyle(element).getPropertyValue('--storefront-title').trim())
  await expect.poll(color).toBe('#123456')
  expect(await color()).toBe(await page.evaluate('window.previewModalTitle()'))
  expect(await dialog.evaluate(element => !document.querySelector('#app')!.contains(element))).toBe(true)

  await page.evaluate(`window.updateTheme({ 'client.checkout.title': '#123456', 'shared.modal.title': '#654321', 'shared.form.title': '#AABBCC' })`)
  await expect.poll(color).toBe('#654321')
  expect(await color()).toBe(await page.evaluate('window.previewModalTitle()'))
  await expect.poll(() => page.locator('#nested-form').evaluate(element => getComputedStyle(element).getPropertyValue('--storefront-title').trim())).toBe('#AABBCC')

  await page.evaluate(`window.updateTheme({ 'client.checkout.title': '#112233' })`)
  await expect.poll(color).toBe('#112233')
  expect(await color()).toBe(await page.evaluate('window.previewModalTitle()'))
  await expect.poll(() => page.locator('#nested-form').evaluate(element => getComputedStyle(element).getPropertyValue('--storefront-title').trim())).toBe('#112233')
})

test('an initially open modal crosses to body without losing its theme or becoming inert', async ({ page }) => {
  await page.goto('about:blank')
  await page.setContent('<html><head><style id="theme"></style></head><body><div id="app"></div></body></html>')
  await page.evaluate('window.initialModal = true')
  await page.addScriptTag({ content: fixture })
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await expect.poll(() => dialog.evaluate(element => getComputedStyle(element).getPropertyValue('--storefront-title').trim())).toBe('#123456')
  expect(await dialog.evaluate(element => element.closest('[inert]') === null)).toBe(true)
  expect(await dialog.evaluate(element => !document.querySelector('#app')!.contains(element))).toBe(true)
})

test('removing the public theme clears inherited colors from an open workspace modal', async ({ page }) => {
  await page.evaluate('window.openModal()')
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.evaluate('window.updateTheme({}, false)')
  await expect.poll(() => page.getByRole('dialog').evaluate(element => getComputedStyle(element).getPropertyValue('--storefront-title').trim())).toBe('')
})
