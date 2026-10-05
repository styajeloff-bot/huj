export interface SpecialEquipmentCatalogAsyncDataKeys {
  categoryContext: string
  products: string
  facets: string
}

export const specialEquipmentCatalogAsyncDataKeys = (
  categoryPath: readonly string[],
): SpecialEquipmentCatalogAsyncDataKeys => {
  const scope = categoryPath.length > 0
    ? `category:${categoryPath.map(encodeURIComponent).join('/')}`
    : 'root'

  return {
    categoryContext: `special-equipment-category-context:${scope}`,
    products: `special-equipment-catalog-products:${scope}`,
    facets: `special-equipment-catalog-facets:${scope}`,
  }
}
