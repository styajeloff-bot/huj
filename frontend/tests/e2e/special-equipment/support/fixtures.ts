import { existsSync, readFileSync } from 'node:fs'
import { exec } from 'node:child_process'
import { resolve } from 'node:path'
import { promisify } from 'node:util'

export const E2E_FIXTURE_MANIFEST_ENV = 'E2E_FIXTURE_MANIFEST' as const
export const E2E_FIXTURE_RESET_COMMAND_ENV = 'E2E_FIXTURE_RESET_COMMAND' as const
export const E2E_EMPLOYEE_STORAGE_STATE_ENV = 'E2E_EMPLOYEE_STORAGE_STATE' as const
export const E2E_CLIENT_STORAGE_STATE_ENV = 'E2E_CLIENT_STORAGE_STATE' as const

export const E2E_CATEGORY_KEYS = [
  'root',
  'emptyRoot',
  'dagParentA',
  'dagParentB',
  'shared',
  'siblingA',
  'siblingB',
  'attachmentRoot',
  'attachmentChild',
  'attachmentDescendant',
  'leaf',
  'count25',
] as const

export const E2E_PRODUCT_KEYS = [
  'representative',
  'equivalent',
  'nonEquivalent',
  'usedMileage',
  'usedHours',
  'onOrder',
  'noVin',
  'attachmentStandalone',
  'attachmentCompatible',
  'kitWithMod',
  'kitWithoutMod',
  'unpublishedAvailable',
  'publishedUnavailable',
  'trimAbsEsp',
  'trimAbsOnly',
  'trimSafetyNone',
] as const

export type E2ECategoryKey = typeof E2E_CATEGORY_KEYS[number]
export type E2EProductKey = typeof E2E_PRODUCT_KEYS[number]
export type JsonRecord = Record<string, unknown>

export interface E2EFixtureCategory extends JsonRecord {
  id: string
  code: string
  name: string
  slug: string
  path: string[]
  parent_ids: string[]
  is_attachment_category: boolean
}

export interface E2EFixtureProduct extends JsonRecord {
  id: string
  code?: string
  name?: string
  title?: string
  published_at: string | null
}

export interface E2EModelShowcaseModel extends JsonRecord {
  id: string
  name: string
  mark_id: string
  complectation_id: string
  price: string
  min_price: string
  discount_price: string
  category: string
  body_type: string
  volume: string
  horse_power: string
  time_to_100: string
}

export interface E2EModelShowcase extends JsonRecord {
  storefront: JsonRecord & { id: string; slug: string }
  mixed_storefront: JsonRecord & { id: string; slug: string }
  logical_mark: JsonRecord & { id: string; ids: string[]; name: string }
  mixed_logical_mark: JsonRecord & { id: string; ids: string[]; name: string }
  models: Record<'alpha' | 'beta', E2EModelShowcaseModel>
  mixed_model: E2EModelShowcaseModel
  vehicles: JsonRecord
  mixed_vehicle: JsonRecord
  image_filename: string
}

export interface E2EFixtureManifest extends JsonRecord {
  schema_version: 1
  namespace: string
  prefix: string
  auth: JsonRecord
  companies: JsonRecord
  categories: Record<E2ECategoryKey, E2EFixtureCategory>
  marks: JsonRecord
  models: JsonRecord
  model_showcase: E2EModelShowcase
  modifications: JsonRecord
  trims: JsonRecord
  attribute_groups: JsonRecord
  attributes: JsonRecord
  options: JsonRecord
  products: Record<E2EProductKey, E2EFixtureProduct>
  fingerprint_probes: Record<string, E2EFixtureProduct>
  relations: JsonRecord
  cart: JsonRecord
  imports: JsonRecord
  counts: JsonRecord
}

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requireRecord = (record: JsonRecord, key: string, context: string): JsonRecord => {
  const value = record[key]
  if (!isRecord(value)) throw new Error(`${context}.${key} must be an object`)
  return value
}

const requireString = (record: JsonRecord, key: string, context: string): string => {
  const value = record[key]
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`${context}.${key} must be a non-empty string`)
  }
  return value
}

const requireStringArray = (record: JsonRecord, key: string, context: string): string[] => {
  const value = record[key]
  if (!Array.isArray(value) || !value.every(item => typeof item === 'string')) {
    throw new Error(`${context}.${key} must be an array of strings`)
  }
  return value
}

const parseCategory = (value: unknown, key: E2ECategoryKey): E2EFixtureCategory => {
  if (!isRecord(value)) throw new Error(`manifest.categories.${key} must be an object`)
  const context = `manifest.categories.${key}`
  if (typeof value.is_attachment_category !== 'boolean') {
    throw new Error(`${context}.is_attachment_category must be a boolean`)
  }
  return {
    ...value,
    id: requireString(value, 'id', context),
    code: requireString(value, 'code', context),
    name: requireString(value, 'name', context),
    slug: requireString(value, 'slug', context),
    path: requireStringArray(value, 'path', context),
    parent_ids: requireStringArray(value, 'parent_ids', context),
    is_attachment_category: value.is_attachment_category,
  }
}

const parseProduct = (value: unknown, key: E2EProductKey): E2EFixtureProduct => {
  if (!isRecord(value)) throw new Error(`manifest.products.${key} must be an object`)
  return {
    ...value,
    id: requireString(value, 'id', `manifest.products.${key}`),
    published_at: typeof value.published_at === 'string' ? value.published_at : null,
  }
}

const parseFingerprintProbes = (value: unknown): Record<string, E2EFixtureProduct> => {
  if (!isRecord(value)) throw new Error('manifest.fingerprint_probes must be an object')
  const entries = Object.entries(value).map(([key, probe]) => {
    if (!isRecord(probe)) throw new Error(`manifest.fingerprint_probes.${key} must be an object`)
    return [key, {
      ...probe,
      id: requireString(probe, 'id', `manifest.fingerprint_probes.${key}`),
      published_at: typeof probe.published_at === 'string' ? probe.published_at : null,
    } satisfies E2EFixtureProduct]
  })
  if (entries.length === 0) throw new Error('manifest.fingerprint_probes must not be empty')
  return Object.fromEntries(entries)
}

const parseModelShowcaseModel = (
  value: unknown,
  context: string,
): E2EModelShowcaseModel => {
  if (!isRecord(value)) throw new Error(`${context} must be an object`)
  return {
    ...value,
    id: requireString(value, 'id', context),
    name: requireString(value, 'name', context),
    mark_id: requireString(value, 'mark_id', context),
    complectation_id: requireString(value, 'complectation_id', context),
    price: requireString(value, 'price', context),
    min_price: requireString(value, 'min_price', context),
    discount_price: requireString(value, 'discount_price', context),
    category: requireString(value, 'category', context),
    body_type: requireString(value, 'body_type', context),
    volume: requireString(value, 'volume', context),
    horse_power: requireString(value, 'horse_power', context),
    time_to_100: requireString(value, 'time_to_100', context),
  }
}

const parseModelShowcase = (value: unknown): E2EModelShowcase => {
  if (!isRecord(value)) throw new Error('manifest.model_showcase must be an object')
  const storefront = requireRecord(value, 'storefront', 'manifest.model_showcase')
  const mixedStorefront = requireRecord(value, 'mixed_storefront', 'manifest.model_showcase')
  const logicalMark = requireRecord(value, 'logical_mark', 'manifest.model_showcase')
  const mixedLogicalMark = requireRecord(value, 'mixed_logical_mark', 'manifest.model_showcase')
  const models = requireRecord(value, 'models', 'manifest.model_showcase')
  return {
    ...value,
    storefront: {
      ...storefront,
      id: requireString(storefront, 'id', 'manifest.model_showcase.storefront'),
      slug: requireString(storefront, 'slug', 'manifest.model_showcase.storefront'),
    },
    mixed_storefront: {
      ...mixedStorefront,
      id: requireString(mixedStorefront, 'id', 'manifest.model_showcase.mixed_storefront'),
      slug: requireString(mixedStorefront, 'slug', 'manifest.model_showcase.mixed_storefront'),
    },
    logical_mark: {
      ...logicalMark,
      id: requireString(logicalMark, 'id', 'manifest.model_showcase.logical_mark'),
      ids: requireStringArray(logicalMark, 'ids', 'manifest.model_showcase.logical_mark'),
      name: requireString(logicalMark, 'name', 'manifest.model_showcase.logical_mark'),
    },
    mixed_logical_mark: {
      ...mixedLogicalMark,
      id: requireString(mixedLogicalMark, 'id', 'manifest.model_showcase.mixed_logical_mark'),
      ids: requireStringArray(mixedLogicalMark, 'ids', 'manifest.model_showcase.mixed_logical_mark'),
      name: requireString(mixedLogicalMark, 'name', 'manifest.model_showcase.mixed_logical_mark'),
    },
    models: {
      alpha: parseModelShowcaseModel(models.alpha, 'manifest.model_showcase.models.alpha'),
      beta: parseModelShowcaseModel(models.beta, 'manifest.model_showcase.models.beta'),
    },
    mixed_model: parseModelShowcaseModel(
      value.mixed_model,
      'manifest.model_showcase.mixed_model',
    ),
    vehicles: requireRecord(value, 'vehicles', 'manifest.model_showcase'),
    mixed_vehicle: requireRecord(value, 'mixed_vehicle', 'manifest.model_showcase'),
    image_filename: requireString(value, 'image_filename', 'manifest.model_showcase'),
  }
}

export const parseE2EFixtureManifest = (value: unknown): E2EFixtureManifest => {
  if (!isRecord(value)) throw new Error('E2E fixture manifest must be a JSON object')
  if (value.schema_version !== 1) throw new Error('E2E fixture manifest schema_version must be 1')

  const categoriesRecord = requireRecord(value, 'categories', 'manifest')
  const productsRecord = requireRecord(value, 'products', 'manifest')
  const categories = Object.fromEntries(E2E_CATEGORY_KEYS.map(key => [key, parseCategory(categoriesRecord[key], key)])) as Record<E2ECategoryKey, E2EFixtureCategory>
  const products = Object.fromEntries(E2E_PRODUCT_KEYS.map(key => [key, parseProduct(productsRecord[key], key)])) as Record<E2EProductKey, E2EFixtureProduct>

  return {
    ...value,
    schema_version: 1,
    namespace: requireString(value, 'namespace', 'manifest'),
    prefix: requireString(value, 'prefix', 'manifest'),
    auth: requireRecord(value, 'auth', 'manifest'),
    companies: requireRecord(value, 'companies', 'manifest'),
    categories,
    marks: requireRecord(value, 'marks', 'manifest'),
    models: requireRecord(value, 'models', 'manifest'),
    model_showcase: parseModelShowcase(value.model_showcase),
    modifications: requireRecord(value, 'modifications', 'manifest'),
    trims: requireRecord(value, 'trims', 'manifest'),
    attribute_groups: requireRecord(value, 'attribute_groups', 'manifest'),
    attributes: requireRecord(value, 'attributes', 'manifest'),
    options: requireRecord(value, 'options', 'manifest'),
    products,
    fingerprint_probes: parseFingerprintProbes(value.fingerprint_probes),
    relations: requireRecord(value, 'relations', 'manifest'),
    cart: requireRecord(value, 'cart', 'manifest'),
    imports: requireRecord(value, 'imports', 'manifest'),
    counts: requireRecord(value, 'counts', 'manifest'),
  }
}

export const resolveE2EFixtureManifestSource = (source?: string): string => {
  const raw = source ?? process.env[E2E_FIXTURE_MANIFEST_ENV]
  if (!raw?.trim()) {
    throw new Error(`${E2E_FIXTURE_MANIFEST_ENV} must contain a manifest JSON path or JSON object`)
  }
  const trimmed = raw.trim()
  if (trimmed.startsWith('{')) return trimmed

  const manifestPath = resolve(trimmed)
  if (!existsSync(manifestPath)) throw new Error(`E2E fixture manifest not found: ${manifestPath}`)
  return readFileSync(manifestPath, 'utf8')
}

export const loadE2EFixtureManifest = (source?: string): E2EFixtureManifest => {
  const rawJson = resolveE2EFixtureManifestSource(source)
  try {
    return parseE2EFixtureManifest(JSON.parse(rawJson) as unknown)
  }
  catch (error) {
    if (error instanceof SyntaxError) throw new Error(`Invalid E2E fixture manifest JSON: ${error.message}`)
    throw error
  }
}

let cachedManifest: E2EFixtureManifest | undefined

export const getE2EFixtureManifest = (): E2EFixtureManifest => {
  cachedManifest ??= loadE2EFixtureManifest()
  return cachedManifest
}

export const clearE2EFixtureManifestCache = (): void => {
  cachedManifest = undefined
}

const execAsync = promisify(exec)

export const resetE2EFixture = async (): Promise<E2EFixtureManifest> => {
  const command = process.env[E2E_FIXTURE_RESET_COMMAND_ENV]?.trim()
  if (!command) throw new Error(`${E2E_FIXTURE_RESET_COMMAND_ENV} must contain the runner-owned reset command`)
  await execAsync(command, {
    cwd: process.cwd(),
    env: process.env,
    maxBuffer: 10 * 1024 * 1024,
  })
  clearE2EFixtureManifestCache()
  return getE2EFixtureManifest()
}

export const requireStorageStatePath = (role: 'employee' | 'client'): string => {
  const key = role === 'employee' ? E2E_EMPLOYEE_STORAGE_STATE_ENV : E2E_CLIENT_STORAGE_STATE_ENV
  const storageStatePath = process.env[key]?.trim()
  if (!storageStatePath) throw new Error(`${key} must contain a Playwright storage-state path`)
  const absolutePath = resolve(storageStatePath)
  if (!existsSync(absolutePath)) throw new Error(`${key} not found: ${absolutePath}`)
  return absolutePath
}

export const fixtureProductLabel = (product: E2EFixtureProduct): string => {
  const label = product.name ?? product.title ?? product.code
  if (!label) throw new Error(`Fixture product ${product.id} must expose name, title, or code for UI assertions`)
  return label
}
