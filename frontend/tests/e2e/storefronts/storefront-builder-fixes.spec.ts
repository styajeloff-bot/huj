import { test, expect } from '@playwright/test'
import { slugify } from '../../../features/storefrontBuilder/utils/slugify'
import { RESERVED_STOREFRONT_SLUGS, isReservedRouteSlug } from '../../../features/storefront/routeManifest'

test.describe('Storefront Builder Fixes - Unit & Functional Checks', () => {
  test('slugify correctly transliterates Russian, removes special characters, and formats slug', () => {
    expect(slugify('Спецпредложение')).toBe('specpredlozhenie')
    expect(slugify('Акции и скидки на грузовики')).toBe('akcii-i-skidki-na-gruzoviki')
    expect(slugify('Тест  ---  пробелы !!! & знаки')).toBe('test-probely-znaki')
    expect(slugify('English Title 2026')).toBe('english-title-2026')
    expect(slugify('Юрист & Консультация (№1)')).toBe('yurist-konsultaciya-1')
  })

  test('reserved slugs protect system routes from being overridden by custom pages', () => {
    expect(isReservedRouteSlug('workspace')).toBe(true)
    expect(isReservedRouteSlug('admin')).toBe(true)
    expect(isReservedRouteSlug('about')).toBe(true)
    expect(isReservedRouteSlug('cart')).toBe(true)
    expect(isReservedRouteSlug('auth')).toBe(true)
    expect(isReservedRouteSlug('special-equipment')).toBe(true)
    expect(isReservedRouteSlug('my-custom-promo-page')).toBe(false)
    expect(RESERVED_STOREFRONT_SLUGS).toContain('workspace')
  })

  test('StorefrontBuilderCanvas template contains min-h-0, overflow-y-auto and previewMode condition', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const canvasCode = fs.readFileSync(
      path.resolve(__dirname, '../../../features/storefrontBuilder/components/StorefrontBuilderCanvas.vue'),
      'utf8'
    )
    expect(canvasCode).toContain('min-h-0')
    expect(canvasCode).toContain('overflow-y-auto')
    expect(canvasCode).toContain('!builderStore.previewMode')
  })

  test('StorefrontBuilderSidebar contains Header tab configuration', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const sidebarCode = fs.readFileSync(
      path.resolve(__dirname, '../../../features/storefrontBuilder/components/StorefrontBuilderSidebar.vue'),
      'utf8'
    )
    expect(sidebarCode).toContain("key: 'header'")
    expect(sidebarCode).toContain('Шапка')
    expect(sidebarCode).toContain('builderStore.saveHeaderSettings')
  })

  test('StorefrontBuilderTopBar renders all available pages in select', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const topBarCode = fs.readFileSync(
      path.resolve(__dirname, '../../../features/storefrontBuilder/components/StorefrontBuilderTopBar.vue'),
      'utf8'
    )
    expect(topBarCode).toContain('v-for="page in builderStore.availablePages"')
    expect(topBarCode).toContain('+ Создать страницу…')
    expect(topBarCode).toContain('handlePageSelect')
  })

  test('StorefrontBuilder page creation handles errors and displays error banner', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const builderPageCode = fs.readFileSync(
      path.resolve(__dirname, '../../../pages/workspace/storefronts/[id]/builder.vue'),
      'utf8'
    )
    expect(builderPageCode).toContain('createPageError')
    expect(builderPageCode).toContain('role="alert"')
    expect(builderPageCode).toContain('route.query.page')
  })

  test('AdminStorefrontsPanel displays custom pages in visibility tab with builder links', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const panelCode = fs.readFileSync(
      path.resolve(__dirname, '../../../features/admin/storefronts/components/AdminStorefrontsPanel.vue'),
      'utf8'
    )
    expect(panelCode).toContain('customPages')
    expect(panelCode).toContain('В конструктор')
    expect(panelCode).toContain('Создать страницу в конструкторе')
    expect(panelCode).toContain('savePublicUi')
  })

  test('AdminSectionVisibilityPanel includes custom storefront pages in public scope', () => {
    const fs = require('node:fs')
    const path = require('node:path')
    const visibilityCode = fs.readFileSync(
      path.resolve(__dirname, '../../../features/sectionVisibility/AdminSectionVisibilityPanel.vue'),
      'utf8'
    )
    expect(visibilityCode).toContain('storefrontPages')
    expect(visibilityCode).toContain('customStorefrontPages')
    expect(visibilityCode).toContain('isCurrentHomePage')
  })
})

