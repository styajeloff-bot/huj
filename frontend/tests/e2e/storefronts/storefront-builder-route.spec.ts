import { test, expect } from '@playwright/test'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import { basename, dirname, resolve } from 'node:path'

const frontend = resolve(__dirname, '../../..')

let script: string

test.beforeAll(async () => {
  const bundle = await build({
    stdin: {
      contents: `
        import { createApp, h, ref, defineComponent } from 'vue'

        globalThis.definePageMeta = () => {}

        const currentPath = ref('/workspace/storefronts')
        globalThis.__TEST_ROUTE__ = currentPath

        const NuxtPage = defineComponent({
          name: 'NuxtPage',
          render() {
            return h('div', { id: 'storefront-builder-view' }, [
              h('h1', 'Visual Storefront Builder Mounted'),
              h('button', {
                id: 'btn-back-to-storefronts',
                onClick: () => {
                  currentPath.value = '/workspace/storefronts'
                },
              }, 'Назад к витринам'),
            ])
          },
        })

        import StorefrontsPage from './pages/workspace/storefronts.vue'

        const RootApp = defineComponent({
          setup() {
            return () => h('div', { id: 'app-root' }, [
              h(StorefrontsPage),
            ])
          },
        })

        const app = createApp(RootApp)
        app.component('NuxtPage', NuxtPage)
        app.mount('#app')
      `,
      resolveDir: frontend,
      loader: 'ts',
    },
    bundle: true,
    write: false,
    format: 'iife',
    platform: 'browser',
    plugins: [
      {
        name: 'stub-modules',
        setup(builder) {
          // Stub vue-router
          builder.onResolve({ filter: /^vue-router$/ }, () => ({
            path: resolve(frontend, 'stub-vue-router.ts'),
          }))
          builder.onLoad({ filter: /stub-vue-router\.ts$/ }, () => ({
            contents: `
              import { reactive } from 'vue'
              export const useRoute = () => reactive({
                get path() {
                  return globalThis.__TEST_ROUTE__.value
                },
                params: { id: '41be49e2-c51f-4bce-aa78-1322f90cab30' },
                query: {},
              })
            `,
            loader: 'ts',
            resolveDir: frontend,
          }))

          // Compile vue SFC
          builder.onLoad({ filter: /\.vue$/ }, (args) => {
            let source = readFileSync(args.path, 'utf8')
            // Replace the async dynamic import in storefronts.vue with inline synchronous component for the test environment
            source = source.replace(
              /defineAsyncComponent\(\s*\(\)\s*=>[\s\S]*?\n\)/,
              `defineComponent({
                name: 'AdminStorefrontsPanel',
                render: () => h('div', { id: 'admin-storefronts-panel-view' }, [
                  h('h1', 'Storefronts Admin Panel Active'),
                  h('button', {
                    id: 'btn-open-builder',
                    onClick: () => {
                      window.__TEST_ROUTE__.value = '/workspace/storefronts/41be49e2-c51f-4bce-aa78-1322f90cab30/builder'
                    },
                  }, 'Конструктор витрины'),
                ]),
              })`
            )
            const { descriptor } = parse(source, { filename: args.path })
            const scopeId = `data-v-${basename(args.path, '.vue')}`
            const compiled = compileScript(descriptor, { id: scopeId, inlineTemplate: true })
            return {
              contents: `
                import { h, defineComponent } from 'vue'
                ${compiled.content.replace('export default', 'const component =')}
                component.__scopeId = ${JSON.stringify(scopeId)}
                export default component
              `,
              loader: 'ts',
              resolveDir: dirname(args.path),
            }
          })
        },
      },
    ],
  })

  script = bundle.outputFiles[0].text
})

test.describe('Storefronts page routing (/workspace/storefronts -> builder)', () => {
  test.use({ viewport: { width: 1280, height: 800 } })

  test('renders AdminStorefrontsPanel on /workspace/storefronts', async ({ page }) => {
    await page.setContent('<div id="app"></div>')
    await page.addScriptTag({ content: script })

    await expect(page.locator('#admin-storefronts-panel-view')).toBeVisible()
    await expect(page.locator('#storefront-builder-view')).not.toBeVisible()
  })

  test('switches to NuxtPage builder when navigating to child route /workspace/storefronts/:id/builder and back', async ({ page }) => {
    await page.setContent('<div id="app"></div>')
    await page.addScriptTag({ content: script })

    await expect(page.locator('#admin-storefronts-panel-view')).toBeVisible()

    // Trigger navigation to child route /workspace/storefronts/41be49e2-c51f-4bce-aa78-1322f90cab30/builder
    await page.click('#btn-open-builder')
    await expect(page.locator('#storefront-builder-view')).toBeVisible()
    await expect(page.locator('#admin-storefronts-panel-view')).not.toBeVisible()

    // Click back button to return to storefronts list
    await page.click('#btn-back-to-storefronts')
    await expect(page.locator('#admin-storefronts-panel-view')).toBeVisible()
    await expect(page.locator('#storefront-builder-view')).not.toBeVisible()
  })
})
