export interface CatalogCreateMediaCheckpoint<TResource> {
  resource: TResource
  etag: string
}

interface ConditionalResource<TResource> {
  data: TResource
  etag: string
}

/**
 * Create an aggregate once, then keep its identity while resumable media
 * endpoints advance the ETag. A media failure leaves the latest checkpoint in
 * the caller, so the next submit starts at the unfinished upload.
 */
export const resumeCatalogCreateMedia = async <TResource>({
  checkpoint,
  idempotencyKey,
  create,
  syncMedia,
  commit,
}: {
  checkpoint: CatalogCreateMediaCheckpoint<TResource> | null
  idempotencyKey: string
  create: (idempotencyKey: string) => Promise<ConditionalResource<TResource>>
  syncMedia: (
    resource: TResource,
    etag: string,
    onProgress: (etag: string) => void,
  ) => Promise<string>
  commit: (checkpoint: CatalogCreateMediaCheckpoint<TResource>) => void
}): Promise<CatalogCreateMediaCheckpoint<TResource>> => {
  let current = checkpoint
  if (!current) {
    const created = await create(idempotencyKey)
    current = { resource: created.data, etag: created.etag }
    commit(current)
  }

  const resource = current.resource
  const commitProgress = (etag: string) => {
    current = { resource, etag }
    commit(current)
  }
  const etag = await syncMedia(resource, current.etag, commitProgress)
  const completed = { resource, etag }
  commit(completed)
  return completed
}
