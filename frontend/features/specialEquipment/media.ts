/**
 * Special-equipment media is private object storage and must be delivered only
 * by the FastAPI proxy. Rejecting anything else prevents an accidental backend
 * DTO regression from exposing a bucket URL in the browser.
 */
export const toSpecialEquipmentProxyUrl = (value: string | null | undefined): string | null => {
  if (typeof value !== 'string') return null
  const isPublicProxy = value.startsWith('/api/v1/special-equipment/')
  const isManagementProxy = value.startsWith('/api/v1/admin/special-equipment/')
  return isPublicProxy || isManagementProxy ? value : null
}
