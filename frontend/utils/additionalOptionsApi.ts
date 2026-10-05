type RuntimeConfig = ReturnType<typeof useRuntimeConfig>

export interface AdditionalEquipmentCatalogItem {
  equipment_code: string
  equipment_display_name: string
}

export interface AdditionalServiceCatalogItem {
  service_code: string
  service_display_name: string
}

export interface AdditionalEquipmentCatalogResponse {
  items?: AdditionalEquipmentCatalogItem[]
}

export interface AdditionalServiceCatalogResponse {
  items?: AdditionalServiceCatalogItem[]
}

export const createAdditionalOptionsApi = (config: RuntimeConfig) => {
  const request = <T>(url: string) =>
    $fetch<T>(url, {
      baseURL: config.public.apiBase,
      credentials: 'include',
    })

  return {
    getEquipments: () =>
      request<AdditionalEquipmentCatalogResponse>('/api/v1/equipments'),

    getServices: () =>
      request<AdditionalServiceCatalogResponse>('/api/v1/services'),
  }
}
