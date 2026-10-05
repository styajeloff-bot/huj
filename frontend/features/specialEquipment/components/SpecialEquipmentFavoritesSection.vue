<template>
  <section data-storefront-block="equipment.favorites" class="mt-8 border-t border-storefront-border pt-8 text-storefront-text" aria-labelledby="special-equipment-favorites-title" :aria-busy="shell.favoriteLoading">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.16em] text-storefront-error-text">Каталог транспортных средств и специальной техники</p>
        <h2 id="special-equipment-favorites-title" class="mt-1 text-2xl font-bold tracking-tight text-storefront-title">
          Избранная спецтехника ({{ shell.favoriteCount }})
        </h2>
        <p class="mt-1 text-sm leading-relaxed text-storefront-text-muted">Отдельная подборка — автомобили выше не смешиваются с товарами спецтехники.</p>
      </div>
      <NuxtLink :to="publicRoute('/special-equipment')" class="inline-flex min-h-11 items-center justify-center rounded-lg border border-storefront-border px-4 text-sm font-bold text-storefront-text hover:bg-storefront-secondary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-secondary">
        Открыть каталог
      </NuxtLink>
    </div>

    <div v-if="shell.favoriteLoading && shell.favoriteProducts.length === 0" class="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Загрузка избранной спецтехники">
      <div v-for="index in 3" :key="index" class="h-72 animate-pulse rounded-xl bg-storefront-skeleton motion-reduce:animate-none" />
    </div>

    <div v-else-if="shell.favoriteError && shell.favoriteCount === 0" class="mt-5 rounded-xl border border-storefront-error-border bg-storefront-error p-5" role="alert">
      <ExclamationTriangleIcon class="h-7 w-7 text-storefront-error-icon" aria-hidden="true" />
      <p class="mt-2 font-bold text-storefront-error-text">{{ shell.favoriteError }}</p>
      <button type="button" class="mt-4 min-h-11 rounded-lg border border-storefront-error-border bg-storefront-surface px-4 text-sm font-bold text-storefront-error-text hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus storefront-action-destructive" @click="loadFavorites(true)">
        Повторить
      </button>
    </div>

    <div v-else-if="shell.favoriteCount === 0" class="mt-5 rounded-xl border border-dashed border-storefront-border bg-storefront-background px-6 py-10 text-center">
      <HeartIcon class="mx-auto h-11 w-11 text-storefront-icon-muted" aria-hidden="true" />
      <h3 class="mt-3 text-lg font-bold text-storefront-title">Нет избранной спецтехники</h3>
      <p class="mt-1 text-sm text-storefront-text-muted">Добавляйте модели сердцем на карточке — они появятся в этой секции.</p>
    </div>

    <div v-else class="mt-5">
      <div v-if="shell.favoriteError" class="mb-4 rounded-lg border border-storefront-warning-border bg-storefront-warning px-4 py-3 text-sm text-storefront-warning-text" role="status">
        {{ shell.favoriteError }}
        <button type="button" class="ml-2 font-bold underline underline-offset-2" @click="loadFavorites(true)">Обновить</button>
      </div>

      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <article v-for="product in shell.favoriteProducts" :key="product.id" class="group flex flex-col overflow-hidden rounded-xl border border-storefront-border bg-storefront-surface">
          <component
            :is="specialEquipmentProductLocation(product, publicRoute) ? NuxtLink : 'div'"
            :to="specialEquipmentProductLocation(product, publicRoute) ?? undefined"
            class="relative block aspect-[4/3] overflow-hidden bg-storefront-image focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-storefront-focus"
          >
            <img v-if="imageUrl(product)" :src="imageUrl(product) ?? undefined" :alt="specialEquipmentProductTitle(product)" class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.02] motion-reduce:transition-none" width="480" height="360">
            <span v-else class="grid h-full place-items-center bg-storefront-image text-storefront-text-muted">
              <TruckIcon class="h-12 w-12 text-storefront-icon" aria-hidden="true" />
              <span class="sr-only">Изображение отсутствует</span>
            </span>
          </component>
          <div class="flex flex-1 flex-col p-4">
            <div class="flex flex-1 items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-storefront-link">{{ product.mark.name || 'Марка не указана' }}</p>
                <h3 class="mt-1 text-lg font-bold leading-snug text-storefront-title">
                  <component
                    :is="specialEquipmentProductLocation(product, publicRoute) ? NuxtLink : 'span'"
                    :to="specialEquipmentProductLocation(product, publicRoute) ?? undefined"
                    class="rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus"
                    :class="specialEquipmentProductLocation(product, publicRoute) ? 'hover:text-storefront-link-hover' : ''"
                  >
                    {{ product.title || product.model.name || 'Модель не указана' }}
                  </component>
                </h3>
                <p v-if="product.modification?.name" class="mt-1 line-clamp-2 text-sm text-storefront-text-muted">
                  {{ [product.modification.name, product.trim?.name].filter(Boolean).join(' · ') }}
                </p>
                <p v-else-if="product.superstructure?.name" class="mt-1 line-clamp-2 text-sm text-storefront-text-muted">
                  {{ product.superstructure.name }}
                </p>
              </div>
              <button type="button" class="grid min-h-11 min-w-11 place-items-center rounded-lg text-storefront-error-text hover:bg-storefront-error-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus disabled:cursor-wait disabled:opacity-50 storefront-action-destructive" :disabled="removingIds.has(product.id)" :aria-label="`Удалить ${specialEquipmentProductTitle(product)} из избранного`" @click="removeProduct(product.id)">
                <ArrowPathIcon v-if="removingIds.has(product.id)" class="h-5 w-5 animate-spin motion-reduce:animate-none text-storefront-icon" aria-hidden="true" />
                <HeartIcon v-else class="h-5 w-5 fill-current text-storefront-icon" aria-hidden="true" />
              </button>
            </div>
            <p class="mt-4 border-t border-storefront-border pt-4 text-lg font-bold tabular-nums text-storefront-price">
              {{ specialEquipmentPriceLabel(product) }}
            </p>
            <NuxtLink
              v-if="specialEquipmentProductLocation(product, publicRoute)"
              :to="specialEquipmentProductLocation(product, publicRoute) ?? undefined"
              class="mt-3 inline-flex min-h-11 items-center justify-center rounded-lg bg-storefront-primary px-4 text-sm font-bold text-storefront-primary-foreground hover:bg-storefront-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus focus-visible:ring-offset-2 storefront-action-primary"
            >
              Подробнее
            </NuxtLink>
          </div>
        </article>

        <article v-for="productId in shell.unresolvedFavoriteIds" :key="productId" class="flex min-h-64 flex-col justify-between rounded-xl border border-storefront-warning-border bg-storefront-warning p-5">
          <div>
            <ExclamationTriangleIcon class="h-8 w-8 text-storefront-warning-icon" aria-hidden="true" />
            <h3 class="mt-3 font-bold text-storefront-warning-text">Карточка временно недоступна</h3>
            <p class="mt-2 break-all font-mono text-xs text-storefront-warning-text">{{ productId }}</p>
          </div>
          <button type="button" class="mt-5 min-h-11 rounded-lg border border-storefront-warning-border bg-storefront-surface px-4 text-sm font-bold text-storefront-warning-text hover:bg-storefront-warning-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-storefront-focus" :disabled="removingIds.has(productId)" @click="removeProduct(productId)">
            Удалить из избранного
          </button>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { NuxtLink } from '#components'
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  HeartIcon,
  TruckIcon,
} from '@heroicons/vue/24/outline'
import { useStorefront } from '~/features/storefront'
import type { UUID } from '~/types/ids'
import {
  specialEquipmentProductLocation,
  specialEquipmentProductTitle,
} from '../composables/commerceShellAdapter'
import { specialEquipmentFailureMessage } from '../composables/checkout'
import { toSpecialEquipmentProxyUrl } from '../media'
import { useSpecialEquipmentCommerceShellStore } from '../store/commerceShell'
import type { SpecialEquipmentCommerceProduct } from '../types'
import { specialEquipmentPriceLabel } from '../priceOnRequest'

const shell = useSpecialEquipmentCommerceShellStore()
const { publicRoute } = useStorefront()
const toast = useToast()
const removingIds = ref<Set<UUID>>(new Set())

const imageUrl = (product: SpecialEquipmentCommerceProduct) =>
  toSpecialEquipmentProxyUrl(product.primary_image?.content_url)

const replaceRemoving = (productId: UUID, enabled: boolean) => {
  const next = new Set(removingIds.value)
  if (enabled) next.add(productId)
  else next.delete(productId)
  removingIds.value = next
}

const loadFavorites = async (force = false) => {
  await shell.loadFavorites({ force, resolveGuestProducts: true })
}

const removeProduct = async (productId: UUID) => {
  if (removingIds.value.has(productId)) return
  replaceRemoving(productId, true)
  try {
    await shell.removeFavorite(productId)
    toast.success('Спецтехника удалена из избранного')
  } catch (error: unknown) {
    toast.error(specialEquipmentFailureMessage(error, 'Не удалось удалить технику из избранного'))
  } finally {
    replaceRemoving(productId, false)
  }
}

onMounted(() => loadFavorites())
</script>
