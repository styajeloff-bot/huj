import { expect, test, type Locator } from '@playwright/test'
import { parse as parseTemplate, type ElementNode, type RootNode, type TemplateChildNode } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import { build } from 'esbuild'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import ts from 'typescript'

// Same actual-Vue/Tailwind seam as theme-gallery-footer: the whole footer, the
// header's exact logo link (including its reserved-size container), and the
// admin's exact logo fieldset plus its real versioned URL computation. Auth,
// routing and data are fixture adapters; no upload or storage is exercised.
const frontend = resolve(__dirname, '../../..')
const load = createRequire(resolve(frontend, 'package.json'))
const headerPath = resolve(frontend, 'components/TheHeader.vue')
const footerPath = resolve(frontend, 'components/TheFooter.vue')
const adminPath = resolve(frontend, 'features/admin/storefronts/components/AdminStorefrontsPanel.vue')
const headerSource = readFileSync(headerPath, 'utf8')
const footerSource = readFileSync(footerPath, 'utf8')
const adminSource = readFileSync(adminPath, 'utf8')

function elements(source: string): ElementNode[] {
  const result: ElementNode[] = []
  const visit = (node: RootNode | TemplateChildNode) => {
    if (node.type === 1) result.push(node)
    if (node.type === 0 || node.type === 1) node.children.forEach(visit)
  }
  visit(parseTemplate(source))
  return result
}

function logoFragments(): string {
  const header = parse(headerSource, { filename: headerPath }).descriptor
  const admin = parse(adminSource, { filename: adminPath }).descriptor
  const logoLink = elements(header.template!.content).find(node => node.tag === 'NuxtLink' && node.loc.source.includes(':src="logo_url"'))
  const fieldset = elements(admin.template!.content).find(node => node.tag === 'fieldset' && node.loc.source.includes(':src="displayedLogoUrl"'))
  const script = ts.createSourceFile(adminPath, admin.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const preview = script.statements.filter(ts.isVariableStatement)
    .flatMap(statement => [...statement.declarationList.declarations])
    .find(declaration => declaration.name.getText(script) === 'displayedLogoUrl')
  if (!logoLink || !fieldset || !preview) throw new Error('Actual header/admin logo extraction no longer matches the components')
  return `<script setup lang="ts">
    import { computed, ref } from 'vue'
    import { logo_url, selected } from 'logo-fixture-data'
    const storefrontLabel = 'Оригинальный логотип'
    const publicRoute = path => path
    const public_ui = { home_page_key: 'home' }
    const pageTitle = () => 'Главная'
    const logoInput = ref(null)
    const saving = false
    const selectLogo = () => { throw new Error('This read-only fixture does not upload files') }
    const removeLogo = () => { throw new Error('This read-only fixture does not delete files') }
    const ${preview.getText(script)}
  </script><template>
    <section id="actual-header-logo">${logoLink.loc.source}</section>
    <section id="actual-admin-logo">${fieldset.loc.source}</section>
  </template>`
}

declare global {
  interface Window {
    setLogoQualityFixture: (url: string) => void
    replaceAdminLogoFixture: (url: string, version: number, inherited?: boolean) => void
  }
}

let fixture: string
let css: string
let unexpectedRequests: string[]
let browserErrors: string[]

test.beforeAll(async () => {
  css = (await postcss([tailwindcss({
    ...load('./tailwind.config.js'),
    content: [{ raw: [headerSource, footerSource, adminSource].join('\n'), extension: 'vue' }],
  })]).process(readFileSync(resolve(frontend, 'assets/css/main.css'), 'utf8'), {
    from: resolve(frontend, 'assets/css/main.css'),
  })).css
  const result = await build({
    stdin: { contents: `
      import { createApp, defineComponent, h } from 'vue'
      import LogoFragments from 'actual-logo-fragments'
      import TheFooter from './components/TheFooter.vue'
      import { logo_url, selected } from 'logo-fixture-data'
      import { buildStorefrontTheme, serializeStorefrontThemeVariables } from './features/storefront/theme'
      import { createDefaultStorefrontAppearance } from './features/storefront/appearance'
      const theme = buildStorefrontTheme(createDefaultStorefrontAppearance())
      document.body.classList.add('storefront-theme')
      document.body.style.cssText = serializeStorefrontThemeVariables(theme.variables)
      document.querySelector('#theme').textContent = theme.scopeCss
      window.setLogoQualityFixture = url => {
        logo_url.value = url
        selected.value = { logo_url: url, effective_logo_url: url, version: 1 }
      }
      window.replaceAdminLogoFixture = (url, version, inherited = false) => {
        selected.value = { logo_url: inherited ? null : url, effective_logo_url: url, version }
      }
      const app = createApp({ setup: () => () => h('main', [h(LogoFragments), h(TheFooter)]) })
      app.component('NuxtLink', defineComponent({
        props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()),
      }))
      app.mount('#app')
    `, resolveDir: frontend, loader: 'ts' },
    bundle: true, write: false, format: 'iife', platform: 'browser',
    alias: { '~': frontend },
    define: {
      'import.meta.client': 'true', 'process.env.NODE_ENV': '"test"', __VUE_OPTIONS_API__: 'true',
      __VUE_PROD_DEVTOOLS__: 'false', __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: 'false',
    },
    plugins: [{ name: 'actual-logo-components', setup(builder) {
      builder.onResolve({ filter: /^actual-logo-fragments$/ }, () => ({ path: 'logo-fragments', namespace: 'logo-component' }))
      builder.onLoad({ filter: /.*/, namespace: 'logo-component' }, () => ({
        contents: compileScript(parse(logoFragments(), { filename: 'ActualLogoFragments.vue' }).descriptor, {
          id: 'actual-logo-fragments', inlineTemplate: true,
        }).content, loader: 'ts', resolveDir: frontend,
      }))
      builder.onLoad({ filter: /TheFooter\.vue$/ }, args => ({
        contents: `import { computed } from 'vue';\n` + compileScript(parse(footerSource, { filename: args.path }).descriptor, {
          id: 'actual-quality-footer', inlineTemplate: true,
        }).content, loader: 'ts', resolveDir: dirname(args.path),
      }))
      builder.onResolve({ filter: /^(?:logo-fixture-data|~\/features\/(?:storefront|sectionVisibility\/store\/sectionVisibility))$/ }, () => ({ path: 'logo-data', namespace: 'logo-data' }))
      builder.onLoad({ filter: /.*/, namespace: 'logo-data' }, () => ({
        contents: `
          import { ref } from 'vue'
          export const logo_url = ref('/logo-original.png')
          export const selected = ref({ logo_url: logo_url.value, effective_logo_url: logo_url.value, version: 1 })
          export const useSectionVisibilityStore = () => ({ isSectionVisible: () => true })
          export const useStorefront = () => ({
            logo_url, contact_email: ref('fixture@example.test'), contact_phone: ref('+7 495 123-45-67'),
            contact_phone_href: ref('+74951234567'), slug: ref('quality'), public_ui: ref({ home_page_key: 'home' }),
            pageTitle: () => 'Каталог', publicRoute: path => '/quality' + path,
          })
        `, loader: 'ts', resolveDir: frontend,
      }))
    } }],
  })
  fixture = result.outputFiles[0]!.text
})

test.beforeEach(async ({ page }) => {
  unexpectedRequests = []
  browserErrors = []
  page.on('pageerror', error => browserErrors.push(error.message))
  // Deterministic raster test inputs, not a transformed copy of a user asset.
  const images = await page.evaluate(() => Object.fromEntries([
      ['original', 505, 384], ['wide', 1200, 100], ['small', 24, 20], ['exif', 240, 360],
  ].map(([name, width, height]) => {
    const canvas = document.createElement('canvas')
    canvas.width = Number(width)
    canvas.height = Number(height)
    const context = canvas.getContext('2d')!
    context.fillStyle = '#B58461'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.fillStyle = '#183A52'
    for (let x = 0; x < canvas.width; x += 2) context.fillRect(x, 0, 1, canvas.height)
    return [name, canvas.toDataURL(name === 'exif' ? 'image/jpeg' : 'image/png').split(',')[1]]
  })))
  // JPEG APP1: little-endian TIFF with the single EXIF Orientation=6 tag.
  // The raster remains 240x360; the browser should expose it as 360x240.
  const orientation6 = Buffer.from('ffe1002245786966000049492a0008000000010012010300010000000600000000000000', 'hex')
  const jpeg = Buffer.from(images.exif, 'base64')
  const orientedJpeg = Buffer.concat([jpeg.subarray(0, 2), orientation6, jpeg.subarray(2)])
  let releaseImages!: () => void
  const imagesReady = new Promise<void>(resolve => { releaseImages = resolve })
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.origin === 'http://theme-logo.test') {
      if (url.pathname === '/') {
        await route.fulfill({ contentType: 'text/html', body: '<html><head><style id="theme"></style></head><body><div id="app"></div></body></html>' })
        return
      }
      const name = /^\/logo-(original|wide|small|exif)\.(?:png|jpg)$/.exec(url.pathname)?.[1]
      if (name) {
        await imagesReady
        const body = images[url.searchParams.get('v') === '2' ? 'wide' : name]
        await route.fulfill({ contentType: name === 'exif' ? 'image/jpeg' : 'image/png', body: name === 'exif' ? orientedJpeg : Buffer.from(body, 'base64') })
        return
      }
    }
    unexpectedRequests.push(`${request.method()} ${url.origin}${url.pathname}`)
    await route.abort('blockedbyclient')
  })
  await page.goto('http://theme-logo.test/')
  await page.addStyleTag({ content: css })
  await page.addScriptTag({ content: fixture })
  const slots = page.locator('#actual-header-logo a, #actual-admin-logo img').last()
  await expect(slots).toBeAttached()
  const headerBefore = await page.locator('#actual-header-logo a').boundingBox()
  expect(headerBefore?.height).toBe(50)
  releaseImages()
  await expect.poll(() => page.locator('#actual-header-logo img').evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(505)
  expect(await page.locator('#actual-header-logo a').boundingBox()).toEqual(headerBefore)
})

test.afterEach(() => {
  expect(unexpectedRequests).toEqual([])
  expect(browserErrors).toEqual([])
})

const metrics = (logo: Locator) => logo.evaluate(node => {
  const image = node as HTMLImageElement
  const bounds = image.getBoundingClientRect()
  const container = image.parentElement!.getBoundingClientRect()
  const style = getComputedStyle(image)
  const effects: string[] = []
  for (let parent: Element | null = image; parent; parent = parent.parentElement) {
    const computed = getComputedStyle(parent)
    if (computed.filter !== 'none' || computed.mixBlendMode !== 'normal') effects.push(parent.tagName)
  }
  return {
    naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
    width: bounds.width, height: bounds.height, containerWidth: container.width,
    objectFit: style.objectFit, maxHeight: style.maxHeight, effects,
  }
})

for (const dpr of [1, 2]) {
  test.describe(`original logo at DPR ${dpr}`, () => {
    test.use({ deviceScaleFactor: dpr })
    for (const width of [768, 1024, 1440]) {
      test(`actual header, footer and admin preview preserve natural pixels and proportional bounds at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 })
        expect(await page.evaluate(() => window.devicePixelRatio)).toBe(dpr)
        const logos = page.locator('#actual-header-logo img, #actual-admin-logo img, footer img')
        await expect(logos).toHaveCount(3)
        for (const logo of await logos.all()) {
          await expect.poll(() => logo.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(505)
          const value = await metrics(logo)
          expect(value.naturalHeight).toBe(384)
          // Chromium lays out replaced elements on a 1/64 CSS-pixel grid.
          expect(value.height).toBeCloseTo(50, 1)
          expect(value.height).toBeLessThanOrEqual(50)
          expect(value.width).toBeCloseTo(65.7552, 1)
          expect(value.objectFit).toBe('contain')
          expect(value.maxHeight).toBe('50px')
          expect(value.effects).toEqual([])
        }
        await page.evaluate(() => window.setLogoQualityFixture('/logo-wide.png'))
        for (const logo of await logos.all()) {
          await expect.poll(() => logo.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(1200)
          const value = await metrics(logo)
          expect(value.naturalHeight).toBe(100)
          expect(value.width).toBeLessThanOrEqual(value.containerWidth)
          expect(value.height).toBeLessThanOrEqual(50)
          expect(value.width / value.height).toBeCloseTo(12, 1)
          expect(value.effects).toEqual([])
        }
        await page.evaluate(() => window.setLogoQualityFixture('/logo-small.png'))
        for (const logo of await logos.all()) {
          await expect.poll(() => logo.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(24)
          const value = await metrics(logo)
          expect([value.naturalWidth, value.naturalHeight, value.width, value.height]).toEqual([24, 20, 24, 20])
          expect(value.effects).toEqual([])
        }
      })
    }
    test('the browser honors original JPEG EXIF orientation without stretching or exceeding 50 CSS pixels', async ({ page }) => {
      await page.evaluate(() => window.setLogoQualityFixture('/logo-exif.jpg'))
      for (const logo of await page.locator('#actual-header-logo img, #actual-admin-logo img, footer img').all()) {
        await expect.poll(() => logo.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(360)
        const value = await metrics(logo)
        expect(value.naturalHeight).toBe(240)
        expect(value.width).toBeCloseTo(75, 1)
        expect(value.height).toBeCloseTo(50, 1)
        expect(value.height).toBeLessThanOrEqual(50)
        expect(value.objectFit).toBe('contain')
        expect(value.effects).toEqual([])
      }
    })
    test('the actual admin URL computation reloads a replacement and supports inherited originals', async ({ page }) => {
      const preview = page.locator('#actual-admin-logo img')
      await expect(preview).toHaveAttribute('src', '/logo-original.png?v=1')
      await expect(page.locator('#actual-admin-logo')).toContainText('Исходный файл сохраняется без изменения качества и разрешения')
      await page.evaluate(() => window.replaceAdminLogoFixture('/logo-original.png', 2))
      await expect(preview).toHaveAttribute('src', '/logo-original.png?v=2')
      await expect.poll(() => preview.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(1200)
      await page.evaluate(() => window.replaceAdminLogoFixture('/logo-small.png', 3, true))
      await expect(preview).toHaveAttribute('src', '/logo-small.png?v=3')
      await expect(preview).toHaveAttribute('alt', 'Логотип, унаследованный от основной витрины')
      await expect.poll(() => preview.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBe(24)
    })
  })
}
