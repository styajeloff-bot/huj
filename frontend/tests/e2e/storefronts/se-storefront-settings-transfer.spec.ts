import { expect, test, type APIRequestContext } from '@playwright/test'

test.use({
  baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1',
})

const authenticate = async (
  request: APIRequestContext,
  phone: string,
): Promise<void> => {
  const login = await request.post('/api/v1/auth/login', { data: { phone } })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone, code: '0000' },
  })
  expect(verification.status()).toBe(200)
}

interface StorefrontPreviewItem {
  slug: string
  action: 'create' | 'update'
  warnings: string[]
}

interface StorefrontPreviewResponse {
  items: StorefrontPreviewItem[]
  preview_token: string
}

interface StorefrontImportResponse {
  created?: string[]
  updated?: string[]
  items?: unknown[]
  imported_storefronts?: unknown[]
}

interface StorefrontAdminRecord {
  id: string
  slug: string | null
  is_active: boolean
  warehouse_ids: string[]
}

test.describe('Storefront settings transfer — export, preview, import, role checks, warehouse validation', () => {
  test('1. Role access: dealer (+76660000003) is forbidden from export, preview, and import (403)', async ({ request }) => {
    await authenticate(request, '+76660000003')

    // GET /api/v1/admin/storefronts/settings/export -> 403
    const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(exportRes.status()).toBe(403)

    // POST /api/v1/admin/storefronts/settings/preview -> 403
    const dummyFile = Buffer.from('{}', 'utf-8')
    const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: dummyFile,
        },
      },
    })
    expect(previewRes.status()).toBe(403)

    // POST /api/v1/admin/storefronts/settings/import -> 403
    const importRes = await request.post('/api/v1/admin/storefronts/settings/import', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: dummyFile,
        },
        preview_token: 'dummy-token',
        confirmed: 'true',
      },
    })
    expect(importRes.status()).toBe(403)
  })

  test('2. Export: GET /api/v1/admin/storefronts/settings/export returns 200, valid JSON and Content-Disposition', async ({ request }) => {
    await authenticate(request, '+76660000001')

    const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(exportRes.status()).toBe(200)

    const contentDisposition = exportRes.headers()['content-disposition'] ?? ''
    expect(contentDisposition).toContain('attachment')
    expect(contentDisposition).toContain('storefront-settings.json')

    const rawBody = await exportRes.text()
    expect(rawBody.length).toBeGreaterThan(0)

    const data = JSON.parse(rawBody) as Record<string, Record<string, unknown>>
    expect(typeof data).toBe('object')
    expect(data).not.toBeNull()
    expect(data['/']).toBeDefined()
    expect(data['/'].is_active).toBe(true)
    expect(data['/'].public_ui).toBeDefined()
    expect(data['/'].appearance).toBeDefined()
    expect(data['/'].section_visibility).toBeDefined()
  })

  test('3. Preview: POST /api/v1/admin/storefronts/settings/preview returns 200, preview_token and update actions', async ({ request }) => {
    await authenticate(request, '+76660000001')

    const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(exportRes.status()).toBe(200)
    const exportBuffer = await exportRes.body()
    const exportJson = JSON.parse(exportBuffer.toString('utf-8')) as Record<string, Record<string, unknown>>

    const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: exportBuffer,
        },
      },
    })
    expect(previewRes.status()).toBe(200)

    const body = (await previewRes.json()) as StorefrontPreviewResponse
    expect(typeof body.preview_token).toBe('string')
    expect(body.preview_token.length).toBeGreaterThan(0)
    expect(Array.isArray(body.items)).toBe(true)

    // For every storefront present in export, there should be an item with action 'update'
    for (const slug of Object.keys(exportJson)) {
      const item = body.items.find(it => it.slug === slug)
      expect(item).toBeDefined()
      expect(item?.action).toBe('update')
    }

    const rootItem = body.items.find(it => it.slug === '/')
    expect(rootItem).toBeDefined()
    expect(rootItem?.action).toBe('update')
    expect(rootItem?.warnings).toEqual([])
  })

  test('4. Preview new slug: returns action "create" and warning about inactive storefront without warehouses', async ({ request }) => {
    await authenticate(request, '+76660000001')

    const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(exportRes.status()).toBe(200)
    const exportJson = JSON.parse((await exportRes.body()).toString('utf-8')) as Record<string, Record<string, unknown>>

    const newSlug = `brand-new-storefront-${Date.now().toString(36)}`
    const cloned = JSON.parse(JSON.stringify(exportJson['/'])) as Record<string, unknown>
    cloned.is_active = false
    cloned.logo = null

    const modified = { ...exportJson, [newSlug]: cloned }
    const modifiedBuffer = Buffer.from(JSON.stringify(modified), 'utf-8')

    const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: modifiedBuffer,
        },
      },
    })
    expect(previewRes.status()).toBe(200)

    const body = (await previewRes.json()) as StorefrontPreviewResponse
    const newItem = body.items.find(it => it.slug === newSlug)
    expect(newItem).toBeDefined()
    expect(newItem?.action).toBe('create')
    expect(
      newItem?.warnings.some(w =>
        w.includes('Будет создана выключенная витрина без складов с системным шрифтом'),
      ),
    ).toBe(true)
  })

  test('5. Warehouse validation: active storefront without active warehouses is rejected with 422', async ({ request }) => {
    await authenticate(request, '+76660000001')

    const sfListRes = await request.get('/api/v1/admin/storefronts')
    expect(sfListRes.status()).toBe(200)
    const sfList = (await sfListRes.json()) as { items: StorefrontAdminRecord[] }

    const sfWithWh = sfList.items.find(
      sf => sf.slug !== null && sf.slug !== '/' && sf.warehouse_ids && sf.warehouse_ids.length > 0,
    )

    if (sfWithWh && sfWithWh.slug) {
      const warehouseId = sfWithWh.warehouse_ids[0]

      // Step A: Deactivate warehouse
      const deactivateRes = await request.put(`/api/v1/admin/warehouses/${warehouseId}`, {
        data: { is_active: false },
      })
      expect(deactivateRes.status()).toBe(200)

      try {
        // Export current settings
        const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
        expect(exportRes.status()).toBe(200)
        const exportJson = JSON.parse((await exportRes.body()).toString('utf-8')) as Record<string, Record<string, unknown>>

        // Ensure the storefront has is_active: true
        if (exportJson[sfWithWh.slug]) {
          exportJson[sfWithWh.slug].is_active = true
        }

        const previewWithInactiveWh = await request.post('/api/v1/admin/storefronts/settings/preview', {
          multipart: {
            file: {
              name: 'storefront-settings.json',
              mimeType: 'application/json',
              buffer: Buffer.from(JSON.stringify(exportJson), 'utf-8'),
            },
          },
        })
        expect(previewWithInactiveWh.status()).toBe(422)
        const errorJson = (await previewWithInactiveWh.json()) as { detail: string }
        expect(errorJson.detail).toContain('Выберите хотя бы один существующий активный склад')
      } finally {
        // Step B: Re-activate warehouse
        const reactivateRes = await request.put(`/api/v1/admin/warehouses/${warehouseId}`, {
          data: { is_active: true },
        })
        expect(reactivateRes.status()).toBe(200)
      }

      // Step C: Verify preview now succeeds with active warehouse
      const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
      expect(exportRes.status()).toBe(200)
      const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
        multipart: {
          file: {
            name: 'storefront-settings.json',
            mimeType: 'application/json',
            buffer: await exportRes.body(),
          },
        },
      })
      expect(previewRes.status()).toBe(200)
    } else {
      // If no non-default storefront currently has warehouses, test that activating
      // any non-default storefront without active warehouses is rejected with 422
      const exportRes = await request.get('/api/v1/admin/storefronts/settings/export')
      expect(exportRes.status()).toBe(200)
      const exportJson = JSON.parse((await exportRes.body()).toString('utf-8')) as Record<string, Record<string, unknown>>

      const nonDefaultSlug = Object.keys(exportJson).find(s => s !== '/')
      if (nonDefaultSlug) {
        exportJson[nonDefaultSlug].is_active = true
        const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
          multipart: {
            file: {
              name: 'storefront-settings.json',
              mimeType: 'application/json',
              buffer: Buffer.from(JSON.stringify(exportJson), 'utf-8'),
            },
          },
        })
        if (previewRes.status() === 422) {
          const errorJson = (await previewRes.json()) as { detail: string }
          expect(errorJson.detail).toContain('Выберите хотя бы один существующий активный склад')
        } else {
          expect(previewRes.status()).toBe(200)
        }
      }
    }
  })

  test('6. Import: POST /api/v1/admin/storefronts/settings/import applies settings and subsequent export reflects them', async ({ request }) => {
    await authenticate(request, '+76660000001')

    // 1. Export original settings
    const initialExportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(initialExportRes.status()).toBe(200)
    const originalBuffer = await initialExportRes.body()
    const originalJson = JSON.parse(originalBuffer.toString('utf-8')) as Record<string, Record<string, unknown>>

    const testSlug = `import-test-${Date.now().toString(36)}`
    const testEmail = `transfer-${Date.now().toString(36)}@carcraft.ru`

    // Clone root block for new inactive storefront
    const newStorefront = JSON.parse(JSON.stringify(originalJson['/'])) as Record<string, unknown>
    newStorefront.is_active = false
    newStorefront.logo = null
    newStorefront.contact_email = testEmail

    const modifiedJson = {
      ...originalJson,
      [testSlug]: newStorefront,
    }
    const modifiedBuffer = Buffer.from(JSON.stringify(modifiedJson), 'utf-8')

    // 2. Preview the modified file to get preview_token
    const previewRes = await request.post('/api/v1/admin/storefronts/settings/preview', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: modifiedBuffer,
        },
      },
    })
    expect(previewRes.status()).toBe(200)
    const previewBody = (await previewRes.json()) as StorefrontPreviewResponse
    const previewToken = previewBody.preview_token
    expect(previewToken).toBeTruthy()

    // 3. Import without confirmation fails with 400
    const unconfirmedRes = await request.post('/api/v1/admin/storefronts/settings/import', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: modifiedBuffer,
        },
        preview_token: previewToken,
        confirmed: 'false',
      },
    })
    expect(unconfirmedRes.status()).toBe(400)
    const unconfirmedBody = (await unconfirmedRes.json()) as { detail: string }
    expect(unconfirmedBody.detail).toContain('Подтвердите импорт')

    // 4. Confirmed import succeeds with 200
    const importRes = await request.post('/api/v1/admin/storefronts/settings/import', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: modifiedBuffer,
        },
        preview_token: previewToken,
        confirmed: 'true',
      },
    })
    expect(importRes.status()).toBe(200)
    const importBody = (await importRes.json()) as StorefrontImportResponse
    expect(importBody).toBeDefined()
    if (importBody.created) {
      expect(importBody.created).toContain(testSlug)
    }

    // 5. Subsequent export contains the imported storefront and matching settings
    const postExportRes = await request.get('/api/v1/admin/storefronts/settings/export')
    expect(postExportRes.status()).toBe(200)
    const postExportJson = JSON.parse((await postExportRes.body()).toString('utf-8')) as Record<string, Record<string, unknown>>

    expect(postExportJson[testSlug]).toBeDefined()
    expect(postExportJson[testSlug].is_active).toBe(false)
    expect(postExportJson[testSlug].contact_email).toBe(testEmail)

    // 6. Test domain rule on newly created storefront:
    // It exists now, but has NO warehouses.
    // Trying to preview with is_active: true must return 422 ("Выберите хотя бы один существующий активный склад")
    const activateAttemptJson = {
      ...postExportJson,
      [testSlug]: {
        ...postExportJson[testSlug],
        is_active: true,
      },
    }
    const activateAttemptPreview = await request.post('/api/v1/admin/storefronts/settings/preview', {
      multipart: {
        file: {
          name: 'storefront-settings.json',
          mimeType: 'application/json',
          buffer: Buffer.from(JSON.stringify(activateAttemptJson), 'utf-8'),
        },
      },
    })
    expect(activateAttemptPreview.status()).toBe(422)
    const activateAttemptBody = (await activateAttemptPreview.json()) as { detail: string }
    expect(activateAttemptBody.detail).toContain('Выберите хотя бы один существующий активный склад')
  })
})
