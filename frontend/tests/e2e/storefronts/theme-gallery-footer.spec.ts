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

// There is no separate CarGallery.vue: compile the exact gallery/CTA template
// nodes from the car page, its actual class computation and useImageCarousel.
// TheFooter is compiled whole. Only data, Nuxt routing/auto-imports and the
// read-only storefront/visibility seams are adapted; no API lifecycle is run.
const frontend = resolve(__dirname, '../../..')
const require = createRequire(resolve(frontend, 'package.json'))
const carPath = resolve(frontend, 'pages/cars/[id].vue')
const footerPath = resolve(frontend, 'components/TheFooter.vue')
let carSource = readFileSync(carPath, 'utf8')
let footerSource = readFileSync(footerPath, 'utf8')
// Disposable mutation proves these checks reject the old visible color leaks.
if (process.env.E2E_GALLERY_FOOTER_THEME_MUTATION === 'legacy-colors') {
  carSource = carSource.replaceAll('border-storefront-selected-border', 'border-storefront-border')
  footerSource = footerSource.replaceAll('--storefront-link,', '--storefront-text,')
}
const photo = readFileSync(resolve(frontend, 'public/images/hero-car.png'))
const logo = readFileSync(resolve(frontend, 'public/images/logo.png'))
const palette = {
  'cars.gallery.image_background': '#E1D2C3',
  'cars.gallery.border': '#334455',
  'cars.gallery.selected.border': '#D51E79',
  'cars.gallery.secondary_action.icon': '#1267A4',
  'cars.detail.actions.action.background': '#225577',
  'cars.detail.actions.action.text': '#F1E2D3',
  'cars.detail.actions.action.icon': '#D42378',
  'cars.detail.actions.action.hover.background': '#336688',
  'cars.detail.actions.action.hover.text': '#C1D2E3',
  'cars.detail.actions.action.hover.icon': '#12A567',
  'cars.detail.actions.action.disabled.background': '#C4B5A6',
  'cars.detail.actions.action.disabled.text': '#412345',
  'cars.detail.actions.action.disabled.icon': '#93651A',
  'footer.background': '#132435',
  'footer.text': '#ABCDEF',
  'footer.link.text': '#E6B37A',
  'footer.link.hover.text': '#5DB8D4',
  'footer.icon': '#B14EC7',
}

function elements(source: string): ElementNode[] {
  const result: ElementNode[] = []
  const visit = (node: RootNode | TemplateChildNode) => {
    if (node.type === 1) result.push(node)
    if (node.type === 0 || node.type === 1) node.children.forEach(visit)
  }
  visit(parseTemplate(source))
  return result
}

function carFragment(): string {
  const descriptor = parse(carSource, { filename: carPath }).descriptor
  const nodes = elements(descriptor.template!.content)
  const gallery = nodes.find(node => node.props.some(prop => prop.type === 6 &&
    prop.name === 'data-storefront-block' && prop.value?.content === 'cars.gallery'))
  const button = nodes.find(node => node.tag === 'button' && node.props.some(prop => prop.type === 7 &&
    prop.name === 'on' && prop.arg?.type === 4 && prop.arg.content === 'click' && prop.exp?.loc.source === 'toggleCart'))
  const script = ts.createSourceFile(carPath, descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const classes = script.statements.filter(ts.isVariableStatement)
    .flatMap(statement => [...statement.declarationList.declarations])
    .find(declaration => declaration.name.getText(script) === 'cartButtonClass')
  if (!gallery || !button || !classes) throw new Error('Actual car gallery/CTA extraction no longer matches the page')
  return `<script setup lang="ts">
    import { computed, ref } from 'vue'
    import { useImageCarousel } from './features/cars/composables/useImageCarousel'
    const car = { mark_name: 'AURUS', model_name: 'Senat', is_restyle: false }
    const carImages = ref(['/photo-1.png', '/photo-2.png'])
    const { currentImageIndex, previousImage, nextImage, handleTouchStart, handleTouchMove, handleTouchEnd } = useImageCarousel(carImages)
    const cartLoading = ref(false)
    const canUseCart = ref(true)
    const inCart = ref(false)
    const toggleCart = () => { inCart.value = !inCart.value }
    const ${classes.getText(script)}
    window.setGalleryCartLoading = value => { cartLoading.value = value }
  </script><template>
    <section data-storefront-block="cars.detail" class="max-w-2xl mx-auto p-4">
      ${gallery.loc.source}
      <div data-storefront-block="cars.detail.actions" class="flex mt-4">${button.loc.source}</div>
    </section>
  </template>`
}

let fixture: string
let css: string
let unexpectedRequests: string[]
let browserErrors: string[]

test.beforeAll(async () => {
  css = (await postcss([tailwindcss({
    ...require('./tailwind.config.js'),
    content: [{ raw: `${carSource}\n${footerSource}`, extension: 'vue' }],
  })]).process(readFileSync(resolve(frontend, 'assets/css/main.css'), 'utf8'), {
    from: resolve(frontend, 'assets/css/main.css'),
  })).css
  const result = await build({
    stdin: { contents: `
      import { createApp, defineComponent, h } from 'vue'
      import CarFragment from 'actual-car-fragment'
      import TheFooter from './components/TheFooter.vue'
      import { buildStorefrontTheme, serializeStorefrontThemeVariables } from './features/storefront/theme'
      import { createDefaultStorefrontAppearance } from './features/storefront/appearance'
      import { validateStorefrontColorOverrides } from './features/storefront/colorRegistry'
      const appearance = createDefaultStorefrontAppearance()
      window.setGalleryFooterTheme = overrides => {
        const errors = validateStorefrontColorOverrides(overrides)
        if (Object.keys(errors).length) throw new Error(JSON.stringify(errors))
        appearance.color_overrides = overrides
        const theme = buildStorefrontTheme(appearance)
        document.body.classList.add('storefront-theme')
        document.body.style.cssText = serializeStorefrontThemeVariables(theme.variables)
        document.querySelector('#theme').textContent = theme.scopeCss
      }
      const app = createApp({ setup: () => () => h('main', [h(CarFragment), h(TheFooter)]) })
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
    plugins: [{ name: 'actual-gallery-footer', setup(builder) {
      builder.onResolve({ filter: /^actual-car-fragment$/ }, () => ({ path: 'car-fragment', namespace: 'car-test' }))
      builder.onLoad({ filter: /.*/, namespace: 'car-test' }, () => ({
        contents: compileScript(parse(carFragment(), { filename: 'CarFragment.vue' }).descriptor, {
          id: 'actual-car-fragment', inlineTemplate: true,
        }).content, loader: 'ts', resolveDir: frontend,
      }))
      builder.onLoad({ filter: /TheFooter\.vue$/ }, args => ({
        contents: `import { computed } from 'vue';\n` + compileScript(parse(footerSource, { filename: args.path }).descriptor, {
          id: 'actual-footer', inlineTemplate: true,
        }).content, loader: 'ts', resolveDir: dirname(args.path),
      }))
      builder.onLoad({ filter: /useImageCarousel\.ts$/ }, args => ({
        contents: `import { ref, onMounted, onUnmounted } from 'vue';\n${readFileSync(args.path, 'utf8')}`,
        loader: 'ts', resolveDir: dirname(args.path),
      }))
      builder.onResolve({ filter: /^~\/features\/(?:storefront|sectionVisibility\/store\/sectionVisibility)$/ }, args => ({
        path: args.path, namespace: 'footer-data',
      }))
      builder.onLoad({ filter: /.*/, namespace: 'footer-data' }, () => ({
        contents: `
          import { ref } from 'vue'
          export const useSectionVisibilityStore = () => ({ isSectionVisible: () => true })
          export const useStorefront = () => ({
            contact_email: ref('fixture@example.test'), contact_phone: ref('+7 495 123-45-67'),
            contact_phone_href: ref('+74951234567'), logo_url: ref('/custom-logo.png'), slug: ref('aurus'),
            public_ui: ref({ home_page_key: 'home' }), pageTitle: () => 'Каталог', publicRoute: path => '/aurus' + path,
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
  await page.route('**/*', async route => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'GET' && url.origin === 'http://theme-gallery.test') {
      if (url.pathname === '/') {
        await route.fulfill({ contentType: 'text/html', body: '<html><head><style id="theme"></style></head><body><div id="app"></div></body></html>' })
        return
      }
      if (['/photo-1.png', '/photo-2.png', '/custom-logo.png'].includes(url.pathname)) {
        await route.fulfill({ contentType: 'image/png', body: url.pathname === '/custom-logo.png' ? logo : photo })
        return
      }
    }
    unexpectedRequests.push(`${request.method()} ${url.origin}${url.pathname}`)
    await route.abort('blockedbyclient')
  })
  await page.goto('http://theme-gallery.test/')
  await page.addStyleTag({ content: css })
  await page.addScriptTag({ content: fixture })
  await page.evaluate(`window.setGalleryFooterTheme(${JSON.stringify(palette)})`)
  await expect(page.locator('[data-storefront-block="cars.gallery"]')).toBeVisible()
})

test.afterEach(() => {
  expect(unexpectedRequests).toEqual([])
  expect(browserErrors).toEqual([])
})

const rgb = (hex: string) => `rgb(${[1, 3, 5].map(index => Number.parseInt(hex.slice(index, index + 2), 16)).join(', ')})`
const style = (target: Locator, property: string) => target.evaluate((node, name) => getComputedStyle(node).getPropertyValue(name), property)
const expectColor = (target: Locator, property: string, hex: string) => expect.poll(() => style(target, property)).toBe(rgb(hex))

test('actual gallery selection paints visible thumbnail borders and rings after click and keyboard navigation', async ({ page }) => {
  const gallery = page.locator('[data-storefront-block="cars.gallery"]')
  const thumbnails = gallery.locator('button').filter({ has: page.locator('img') })
  await expect(thumbnails).toHaveCount(2)
  const first = thumbnails.nth(0)
  const second = thumbnails.nth(1)
  await expectColor(first, 'border-top-color', palette['cars.gallery.selected.border'])
  expect(await style(first, 'border-top-width')).toBe('2px')
  await expect.poll(() => style(first, 'box-shadow')).toContain(rgb(palette['cars.gallery.selected.border']))
  await expectColor(second, 'border-top-color', palette['cars.gallery.border'])
  await second.click()
  await page.mouse.move(0, 0)
  await expectColor(second, 'border-top-color', palette['cars.gallery.selected.border'])
  await expect.poll(() => style(second, 'box-shadow')).toContain(rgb(palette['cars.gallery.selected.border']))
  await expectColor(first, 'border-top-color', palette['cars.gallery.border'])
  await expect.poll(() => style(first, 'box-shadow')).not.toContain(rgb(palette['cars.gallery.selected.border']))
  await page.keyboard.press('ArrowLeft')
  await expectColor(first, 'border-top-color', palette['cars.gallery.selected.border'])
  await expectColor(second, 'border-top-color', palette['cars.gallery.border'])
  const arrows = gallery.locator('button svg path')
  await expect(arrows).toHaveCount(2)
  for (const arrow of await arrows.all()) await expectColor(arrow, 'stroke', palette['cars.gallery.secondary_action.icon'])
})

test('actual car CTA keeps nested SVG stroke and loading fill independent of text in normal, hover and disabled states', async ({ page }) => {
  const button = page.locator('[data-storefront-block="cars.detail.actions"] button')
  await expectColor(button, 'background-color', palette['cars.detail.actions.action.background'])
  await expectColor(button, 'color', palette['cars.detail.actions.action.text'])
  await expect(button.locator('svg path')).toHaveCount(2)
  for (const path of await button.locator('svg path').all()) {
    await expectColor(path, 'stroke', palette['cars.detail.actions.action.icon'])
    expect(await style(path, 'fill')).toBe('none')
  }
  await button.hover()
  await expectColor(button, 'background-color', palette['cars.detail.actions.action.hover.background'])
  await expectColor(button, 'color', palette['cars.detail.actions.action.hover.text'])
  await expectColor(button.locator('svg path').first(), 'stroke', palette['cars.detail.actions.action.hover.icon'])
  await page.evaluate('window.setGalleryCartLoading(true)')
  await expect(button).toBeDisabled()
  await expect(button).toContainText('Обновляем...')
  await expectColor(button, 'background-color', palette['cars.detail.actions.action.disabled.background'])
  await expectColor(button, 'color', palette['cars.detail.actions.action.disabled.text'])
  await expectColor(button.locator('svg path'), 'fill', palette['cars.detail.actions.action.disabled.icon'])
  await expectColor(button.locator('svg circle'), 'stroke', palette['cars.detail.actions.action.disabled.icon'])
})

test('all six actual footer links share independently configured normal/hover colors while contact icons keep their own color', async ({ page }) => {
  const footer = page.locator('footer')
  const links = footer.locator('a')
  await expect(links).toHaveCount(6)
  await expectColor(footer, 'background-color', palette['footer.background'])
  await expectColor(footer.locator('p'), 'color', palette['footer.text'])
  for (const link of await links.all()) {
    await page.mouse.move(0, 0)
    await expectColor(link, 'color', palette['footer.link.text'])
    await link.hover()
    await expectColor(link, 'color', palette['footer.link.hover.text'])
    for (const path of await footer.locator('svg path').all()) await expectColor(path, 'stroke', palette['footer.icon'])
  }
})

for (const width of [768, 1024, 1440]) {
  test(`actual photos and custom footer logo remain unfiltered after theme changes at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 })
    const images = page.locator('[data-storefront-block="cars.gallery"] img, footer img')
    await expect(images).toHaveCount(5)
    const checkImages = async () => {
      expect(await images.evaluateAll(nodes => nodes.map(node => node.getAttribute('src'))))
        .toEqual(['/photo-1.png', '/photo-2.png', '/photo-1.png', '/photo-2.png', '/custom-logo.png'])
      for (const image of await images.all()) {
        await expect.poll(() => image.evaluate(node => (node as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
        expect(await style(image, 'filter')).toBe('none')
        expect(await style(image, 'mix-blend-mode')).toBe('normal')
        expect(await image.evaluate(node => {
          const effects: string[] = []
          for (let parent = node.parentElement; parent; parent = parent.parentElement) {
            const computed = getComputedStyle(parent)
            if (computed.filter !== 'none' || computed.mixBlendMode !== 'normal') effects.push(parent.tagName)
          }
          return effects
        })).toEqual([])
      }
      expect(await page.locator('footer img').getAttribute('src')).toBe('/custom-logo.png')
      const box = await page.locator('footer img').boundingBox()
      expect(box!.height).toBeGreaterThan(0)
      expect(box!.height).toBeLessThanOrEqual(50)
    }
    await checkImages()
    const changed = { ...palette, 'cars.gallery.image_background': '#AABBCC', 'footer.background': '#BBDDFF', 'footer.text': '#660044' }
    await page.evaluate(`window.setGalleryFooterTheme(${JSON.stringify(changed)})`)
    await expectColor(page.locator('[data-storefront-block="cars.gallery"] > div').first(), 'background-color', '#AABBCC')
    await expectColor(page.locator('footer'), 'background-color', '#BBDDFF')
    await checkImages()
  })
}
