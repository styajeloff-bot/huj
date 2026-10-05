import type {
  CatalogProduct,
  CatalogProductAttachmentLink,
} from './types'
import { normalizeCatalogProductRelations } from './productRelations'

export function appendCatalogProductRelations(
  kind: 'attachments',
  existing: readonly CatalogProductAttachmentLink[],
  products: readonly CatalogProduct[],
): CatalogProductAttachmentLink[] {
  const seen = new Set(existing.map(item => item.attachment_product_id))
  const items: Array<CatalogProductAttachmentLink> = [...existing]

  for (const product of products) {
    if (seen.has(product.id)) continue
    seen.add(product.id)
    const position = items.length
    items.push({ attachment_product_id: product.id, position, product })
  }

  return normalizeCatalogProductRelations(items)
}
