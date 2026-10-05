export interface CatalogRelationSyncResponse {
  etag: string
}

export interface CatalogProductRelationSyncOptions {
  initialEtag: string
  attachmentsChanged: boolean
  replaceAttachments: (etag: string) => Promise<CatalogRelationSyncResponse>
  commitEtag: (etag: string) => void
}

export const syncCatalogProductRelations = async ({
  initialEtag,
  attachmentsChanged,
  replaceAttachments,
  commitEtag,
}: CatalogProductRelationSyncOptions): Promise<string> => {
  let nextEtag = initialEtag
  if (attachmentsChanged) {
    const response = await replaceAttachments(nextEtag)
    nextEtag = response.etag
    commitEtag(nextEtag)
  }
  return nextEtag
}
