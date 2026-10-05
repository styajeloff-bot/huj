import {
  productModel,
  type SpecialEquipmentCommerceProduct,
  type SpecialEquipmentProductCard,
} from '../types'

/**
 * Normalizes a public catalog product for guest favorites/cart persistence.
 * Authenticated commerce endpoints already return this compact projection.
 */
export const toSpecialEquipmentCommerceProduct = (
  product: SpecialEquipmentProductCard,
): SpecialEquipmentCommerceProduct => {
  const model = productModel(product)
  return {
    id: product.id,
    slug: product.slug,
    title: product.title ?? null,
    detail_url: product.detail_url,
    mark: {
      id: model.mark.id,
      name: model.mark.name,
    },
    model: {
      id: model.id,
      name: model.name,
    },
    modification: product.modification
      ? {
          id: product.modification.id,
          name: product.modification.name,
        }
      : null,
    superstructure: product.superstructure ?? null,
    trim: product.trim
    ? {
        id: product.trim.id,
        name: product.trim.name,
      }
    : null,
  manufacture_year: product.manufacture_year,
  body_color: product.body_color
    ? {
        id: product.body_color.id,
        name: product.body_color.name,
      }
    : null,
  price: product.price,
  base_price: product.base_price,
  special_price: product.special_price,
  price_on_request: product.price_on_request,
  price_from: product.price_from,
  currency_code: product.currency_code,
  sale_status: product.sale_status,
  primary_image: product.primary_image
    ? {
        id: product.primary_image.id,
        content_url: product.primary_image.content_url,
      }
    : null,
  capabilities: product.capabilities,
  available_count: product.available_count,
}
}


