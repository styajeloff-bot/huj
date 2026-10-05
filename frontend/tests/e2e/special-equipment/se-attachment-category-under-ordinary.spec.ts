import { randomUUID } from 'node:crypto'
import { expect, test, type APIResponse } from '@playwright/test'
import { getE2EFixtureManifest, resetE2EFixture, type JsonRecord } from './support/fixtures'

const ADMIN_API = '/api/v1/admin/special-equipment'
const PUBLIC_API = '/api/v1/special-equipment'

const json = async (response: APIResponse): Promise<JsonRecord> => {
  if (!response.ok()) {
    const errorBody = await response.text()
    expect(response.ok(), `${response.status()} ${response.url()} -> ${errorBody}`).toBeTruthy()
  }
  return response.json() as Promise<JsonRecord>
}

const uniqueDigits = (): string => String(Date.now()).slice(-8)

test.describe('Special Equipment — Attachment Category Under Ordinary (specs/task_2026-09-28_21-45-54_MSK.md)', () => {
  test.use({
    storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE,
    actionTimeout: 120_000,
  })

  test.beforeEach(async () => {
    test.setTimeout(600_000)
    await resetE2EFixture()
  })

  test('Boundary edge: attachment category under ordinary does not inherit rules, card limits or pollute ordinary products', async ({ request }) => {
    const fixture = getE2EFixtureManifest()
    const tag = uniqueDigits()

    // 1. Create 5 attributes for Ordinary category O
    const oAttrs: JsonRecord[] = []
    for (let i = 1; i <= 5; i++) {
      const code = `attr_o_${tag}_${i}`
      const created = await json(await request.post(`${ADMIN_API}/attributes`, {
        headers: { 'Idempotency-Key': randomUUID() },
        data: {
          code,
          name: `Характеристика O${i} ${tag}`,
          data_type: 'text',
          filter_kind: 'search',
          is_active: true,
        },
      }))
      oAttrs.push(created)
    }

    // 2. Create 3 attributes for Attachment category A
    const aAttrs: JsonRecord[] = []
    for (let i = 1; i <= 3; i++) {
      const code = `attr_a_${tag}_${i}`
      const created = await json(await request.post(`${ADMIN_API}/attributes`, {
        headers: { 'Idempotency-Key': randomUUID() },
        data: {
          code,
          name: `Характеристика A${i} ${tag}`,
          data_type: 'text',
          filter_kind: 'search',
          is_active: true,
        },
      }))
      aAttrs.push(created)
    }

    // 3. Create Ordinary Category O
    const catO = await json(await request.post(`${ADMIN_API}/categories`, {
      headers: { 'Idempotency-Key': randomUUID() },
      data: {
        code: `cat_o_${tag}`,
        name: `Обычная категория ${tag}`,
        usage_metric: 'engine_hours',
        is_attachment_category: false,
        is_active: true,
        parent_ids: [],
        attribute_links: oAttrs.map((attr, idx) => ({
          attribute_id: attr.id,
          is_required: false,
          is_visible: true,
          sort_order: idx + 1,
        })),
      },
    }))

    // 4. Create Attachment Category A
    const catA = await json(await request.post(`${ADMIN_API}/categories`, {
      headers: { 'Idempotency-Key': randomUUID() },
      data: {
        code: `cat_a_${tag}`,
        name: `Надстройки ${tag}`,
        usage_metric: 'engine_hours',
        is_attachment_category: true,
        is_active: true,
        parent_ids: [],
        attribute_links: aAttrs.map((attr, idx) => ({
          attribute_id: attr.id,
          is_required: false,
          is_visible: true,
          sort_order: idx + 1,
        })),
      },
    }))

    // 5. Card attribute limit check: Link O as parent of A (5 + 3 = 8 > 6 attributes)
    // Because O -> A is a boundary edge, card attribute limits must NOT be exceeded!
    const catAGet = await request.get(`${ADMIN_API}/categories/${String(catA.id)}`)
    const catAEtag = catAGet.headers().etag
    expect(catAEtag).toBeTruthy()

    const reparentResponse = await request.put(`${ADMIN_API}/categories/${String(catA.id)}/parents`, {
      headers: { 'If-Match': catAEtag! },
      data: {
        parent_ids: [catO.id],
      },
    })
    expect(reparentResponse.ok(), `Reparenting failed: ${reparentResponse.status()}`).toBeTruthy()
    const catAUpdated = await json(reparentResponse)
    expect(catAUpdated.parent_ids).toContain(catO.id)

    // 6. Admin API check: effective_attribute_links for Category A does NOT contain O's attributes
    const catAFresh = await json(await request.get(`${ADMIN_API}/categories/${String(catA.id)}`))
    const effectiveLinks = catAFresh.effective_attribute_links as Array<{ attribute_id: string }>
    const oAttrIds = new Set(oAttrs.map(a => String(a.id)))
    const leakedOAttrs = effectiveLinks.filter(link => oAttrIds.has(String(link.attribute_id)))
    expect(leakedOAttrs).toHaveLength(0)

    // 7. Create or patch a product in category A
    // Use existing standalone attachment product from fixture and move it to catA
    const standaloneGet = await request.get(`${ADMIN_API}/products/${fixture.products.attachmentStandalone.id}`)
    const standaloneEtag = standaloneGet.headers().etag
    expect(standaloneEtag).toBeTruthy()

    await json(await request.patch(`${ADMIN_API}/products/${fixture.products.attachmentStandalone.id}`, {
      headers: { 'If-Match': standaloneEtag! },
      data: {
        category_ids: [catA.id],
      },
    }))

    // 8. Public Catalog / Filtering checks
    // 8a. GET /api/v1/special-equipment/products?category_path={catO.slug} does NOT return product T
    const prodOResponse = await json(await request.get(`${PUBLIC_API}/products`, {
      params: { category_path: String(catO.slug) },
    }))
    const oItems = (prodOResponse.items || []) as Array<{ id: string }>
    expect(oItems.some(item => item.id === fixture.products.attachmentStandalone.id)).toBeFalsy()

    // 8b. GET /api/v1/special-equipment/products?category_path={catO.slug}/{catA.slug} DOES return product T
    const prodAResponse = await json(await request.get(`${PUBLIC_API}/products`, {
      params: { category_path: `${catO.slug}/${catA.slug}` },
    }))
    const aItems = (prodAResponse.items || []) as Array<{ id: string }>
    expect(aItems.some(item => item.id === fixture.products.attachmentStandalone.id)).toBeTruthy()

    // 8c. GET /api/v1/special-equipment/facets?category_path={catO.slug} does NOT contain A's attributes
    const facetsO = await json(await request.get(`${PUBLIC_API}/facets`, {
      params: { category_path: String(catO.slug) },
    }))
    const aAttrIds = new Set(aAttrs.map(a => String(a.id)))
    const facetsAttributes = ((facetsO.attributes || facetsO.attribute_groups) || []) as Array<{ id?: string, attributes?: Array<{ id: string }> }>
    const extractedIds = new Set<string>()
    for (const item of facetsAttributes) {
      if (item.id) extractedIds.add(String(item.id))
      if (Array.isArray(item.attributes)) {
        for (const sub of item.attributes) {
          if (sub.id) extractedIds.add(String(sub.id))
        }
      }
    }
    expect([...aAttrIds].some(attrId => extractedIds.has(attrId))).toBeFalsy()

    // 8d. GET /api/v1/special-equipment/categories:
    // O's product_count does NOT count A's products;
    // placements / child_ids contains O -> A edge for navigation.
    const categoriesTree = await json(await request.get(`${PUBLIC_API}/categories`))
    const allCategories = (categoriesTree.items || []) as Array<{ id: string, child_ids: string[], product_count: number }>
    const placements = (categoriesTree.placements || []) as Array<{ parent_id: string, category_id: string }>

    const oInTree = allCategories.find(c => c.id === catO.id)
    const aInTree = allCategories.find(c => c.id === catA.id)
    expect(oInTree?.product_count).toBe(0)
    expect(aInTree?.product_count).toBeGreaterThanOrEqual(1)

    const oToAPlacement = placements.find(p => p.parent_id === catO.id && p.category_id === catA.id)
    const oHasAInChildIds = oInTree?.child_ids?.includes(String(catA.id))
    expect(Boolean(oToAPlacement || oHasAInChildIds), 'Navigation must retain boundary edge O -> A').toBeTruthy()
  })
})
