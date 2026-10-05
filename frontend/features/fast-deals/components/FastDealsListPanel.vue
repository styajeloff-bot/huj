<template>
  <section data-testid="fast-deals-list" class="space-y-6">
    <div class="flex items-start justify-between gap-4">
      <div>
        <h2 class="text-xl font-semibold text-gray-900">Регистрация сделки</h2>
        <p class="mt-1 text-sm text-gray-600">
          Сделки, уже согласованные вне платформы между дилером и лизинговой компанией.
        </p>
      </div>
      <button
        v-if="canCreate"
        type="button"
        class="btn-primary shrink-0"
        data-testid="fast-deal-create-button"
        @click="showCreate = true"
      >
        Зарегистрировать сделку
      </button>
    </div>

    <form
      class="card"
      data-testid="fast-deals-filters"
      aria-label="Фильтры списка сделок"
      @submit.prevent="applyFilters"
    >
      <div class="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <div>
          <label :for="fieldId('number')" class="mb-1 block text-sm font-medium text-gray-700">Номер</label>
          <input
            :id="fieldId('number')"
            v-model="filters.number"
            type="search"
            autocomplete="off"
            class="input-field"
            placeholder="DD-… или DL-…"
            @input="debouncedApply"
          >
        </div>
        <div>
          <label :for="fieldId('inn')" class="mb-1 block text-sm font-medium text-gray-700">ИНН клиента</label>
          <input
            :id="fieldId('inn')"
            v-model="filters.client_inn"
            type="search"
            inputmode="numeric"
            autocomplete="off"
            class="input-field"
            placeholder="Например, 7707083893"
            @input="debouncedApply"
          >
        </div>
        <div>
          <label :for="fieldId('client')" class="mb-1 block text-sm font-medium text-gray-700">Компания клиента</label>
          <select :id="fieldId('client')" v-model="filters.client_company_id" class="select-field" @change="applyFilters">
            <option value="">Все клиенты</option>
            <option v-for="company in filterOptions.clients" :key="company.id" :value="company.id">
              {{ companyOptionLabel(company) }}
            </option>
          </select>
        </div>
        <div v-if="showLeasingCompanyFilter">
          <label :for="fieldId('leasing')" class="mb-1 block text-sm font-medium text-gray-700">Лизинговая компания</label>
          <select :id="fieldId('leasing')" v-model="filters.leasing_company_id" class="select-field" @change="applyFilters">
            <option value="">Все лизинговые компании</option>
            <option v-for="company in filterOptions.leasing_companies" :key="company.id" :value="company.id">
              {{ companyOptionLabel(company) }}
            </option>
          </select>
        </div>
        <div v-if="showDealerFilter">
          <label :for="fieldId('dealer')" class="mb-1 block text-sm font-medium text-gray-700">Дилер</label>
          <select :id="fieldId('dealer')" v-model="filters.dealer_company_id" class="select-field" @change="applyFilters">
            <option value="">Все дилеры</option>
            <option v-for="company in filterOptions.dealers" :key="company.id" :value="company.id">
              {{ companyOptionLabel(company) }}
            </option>
          </select>
        </div>
        <div>
          <label :for="fieldId('direction')" class="mb-1 block text-sm font-medium text-gray-700">Направление</label>
          <select :id="fieldId('direction')" v-model="filters.source_type" class="select-field" @change="applyFilters">
            <option value="">Все направления</option>
            <option v-for="option in FAST_DEAL_DIRECTION_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
        <div>
          <label :for="fieldId('status')" class="mb-1 block text-sm font-medium text-gray-700">Статус</label>
          <select :id="fieldId('status')" v-model="filters.status" class="select-field" @change="applyFilters">
            <option value="">Все статусы</option>
            <option v-for="option in FAST_DEAL_STATUS_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
      </div>
      <p v-if="filterOptionsError" class="mt-3 text-xs text-amber-700" role="status">
        Не удалось загрузить списки компаний для фильтров. Остальные фильтры работают.
      </p>
      <div class="mt-4 flex justify-end gap-2">
        <button type="button" class="btn-secondary" data-testid="fast-deals-reset" @click="resetFilters">
          Сбросить
        </button>
        <button type="submit" class="btn-primary">
          Применить
        </button>
      </div>
    </form>

    <div :aria-busy="loading">
      <div
        v-if="forbidden"
        role="alert"
        data-testid="fast-deals-forbidden"
        class="rounded-lg border border-yellow-200 bg-yellow-50 p-6 text-center text-sm text-yellow-800"
      >
        Нет доступа к сделкам этой компании. Обратитесь к администратору компании.
      </div>

      <div
        v-else-if="error"
        role="alert"
        data-testid="fast-deals-error"
        class="rounded-lg border border-red-200 bg-red-50 p-6 text-center"
      >
        <p class="mb-4 text-red-700">{{ error }}</p>
        <button type="button" class="btn-primary" @click="fetchList">Попробовать снова</button>
      </div>

      <div v-else-if="loading && items.length === 0" class="py-12 text-center" role="status">
        <div class="inline-block h-8 w-8 animate-spin rounded-full border-b-2 border-blue-600" />
        <p class="mt-2 text-gray-600">Загружаем сделки…</p>
      </div>

      <div
        v-else-if="items.length === 0"
        data-testid="fast-deals-empty"
        class="rounded-lg border border-gray-200 bg-white py-12 text-center"
      >
        <template v-if="hasActiveFilters">
          <h3 class="mb-2 text-lg font-medium text-gray-900">Сделки не найдены</h3>
          <p class="mb-4 text-gray-600">По заданным фильтрам ничего нет. Измените условия поиска.</p>
          <button type="button" class="btn-secondary" @click="resetFilters">Сбросить фильтры</button>
        </template>
        <template v-else>
          <h3 class="mb-2 text-lg font-medium text-gray-900">Сделок пока нет</h3>
          <p class="text-gray-600">
            {{ canCreate
              ? 'Зарегистрируйте первую сделку, согласованную вне платформы.'
              : 'Здесь появятся сделки, в которых участвует ваша компания.' }}
          </p>
        </template>
      </div>

      <div
        v-else
        class="overflow-x-auto rounded-lg border border-gray-200 bg-white transition-opacity"
        :class="loading ? 'opacity-60' : ''"
      >
        <table class="min-w-full divide-y divide-gray-200 text-sm" data-testid="fast-deals-table">
          <thead class="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th scope="col" class="px-4 py-3 text-left font-medium">Номер</th>
              <th scope="col" class="px-4 py-3 text-left font-medium">Клиент</th>
              <th scope="col" class="px-4 py-3 text-left font-medium">Направление</th>
              <th scope="col" class="px-4 py-3 text-left font-medium">Стороны</th>
              <th scope="col" class="px-4 py-3 text-left font-medium">Статус</th>
              <th scope="col" class="px-4 py-3 text-left font-medium">Ответственные</th>
              <th scope="col" class="px-4 py-3 text-right font-medium"><span class="sr-only">Карточка сделки</span></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 bg-white">
            <tr v-for="deal in items" :key="deal.id" class="align-top hover:bg-gray-50" data-testid="fast-deals-row">
              <td class="px-4 py-3">
                <NuxtLink
                  :to="fastDealRoute(deal.id)"
                  class="whitespace-nowrap font-medium text-blue-600 hover:text-blue-700 hover:underline"
                >
                  {{ deal.display_number }}
                </NuxtLink>
                <div class="mt-0.5 text-xs text-gray-500">{{ formatDateTime(deal.created_at) }}</div>
                <div class="mt-0.5 text-xs text-gray-500">{{ vehiclesSummary(deal) }}</div>
              </td>
              <td class="px-4 py-3">
                <div class="font-medium text-gray-900">{{ deal.client.name }}</div>
                <div v-if="deal.client.inn" class="text-xs text-gray-500">ИНН {{ deal.client.inn }}</div>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-gray-700">
                {{ fastDealDirectionLabel(deal.source_type) }}
              </td>
              <td class="px-4 py-3 text-gray-700">
                <div>Дилер: <span class="font-medium text-gray-900">{{ fastDealParties(deal).dealer }}</span></div>
                <div>ЛК: <span class="font-medium text-gray-900">{{ fastDealParties(deal).leasing }}</span></div>
              </td>
              <td class="px-4 py-3">
                <FastDealStatusBadge :status="deal.status" />
              </td>
              <td class="px-4 py-3 text-gray-700">
                <template v-if="assigneeSummaries(deal).length">
                  <div v-for="assignee in assigneeSummaries(deal)" :key="assignee.key">
                    <span class="text-xs text-gray-500">{{ assignee.roleLabel }}:</span>
                    {{ assignee.name }}
                    <span v-if="assignee.companyName" class="block text-xs text-gray-400">{{ assignee.companyName }}</span>
                  </div>
                </template>
                <span v-else class="text-gray-400">Не назначены</span>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-right">
                <NuxtLink :to="fastDealRoute(deal.id)" class="btn-secondary text-sm">Открыть</NuxtLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="!forbidden && !error && total > 0"
        class="mt-4 flex items-center justify-between gap-4 text-sm text-gray-600"
        data-testid="fast-deals-pagination"
      >
        <span>Найдено: {{ total }}</span>
        <div v-if="pages > 1" class="flex items-center gap-2">
          <button
            type="button"
            class="btn-secondary text-sm disabled:opacity-50"
            :disabled="page <= 1 || loading"
            @click="changePage(page - 1)"
          >
            Назад
          </button>
          <span class="px-2">Страница {{ page }} из {{ pages }}</span>
          <button
            type="button"
            class="btn-secondary text-sm disabled:opacity-50"
            :disabled="page >= pages || loading"
            @click="changePage(page + 1)"
          >
            Вперёд
          </button>
        </div>
      </div>
    </div>

    <FastDealCreateModal v-if="showCreate" @close="showCreate = false" @created="onCreated" />
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import FastDealCreateModal from '~/features/fast-deals/components/FastDealCreateModal.vue'
import FastDealStatusBadge from '~/features/fast-deals/components/FastDealStatusBadge.vue'
import { useFastDealsList } from '~/features/fast-deals/composables/useFastDealsList'
import { assigneeSummaries, fastDealParties } from '~/features/fast-deals/listPresentation'
import { fastDealRoute } from '~/features/fast-deals/routes'
import {
  FAST_DEAL_DIRECTION_OPTIONS,
  FAST_DEAL_STATUS_OPTIONS,
  fastDealDirectionLabel,
  pluralRu,
} from '~/features/fast-deals/status'
import { formatMoney } from '~/features/fast-deals/money'
import type { CompanyBrief, FastDealCard, FastDealListItem } from '~/features/fast-deals/types'

const {
  items,
  total,
  page,
  pages,
  loading,
  error,
  forbidden,
  filters,
  filterOptions,
  filterOptionsError,
  hasActiveFilters,
  canCreate,
  showLeasingCompanyFilter,
  showDealerFilter,
  load,
  fetchList,
  applyFilters,
  debouncedApply,
  resetFilters,
  changePage,
} = useFastDealsList()

const { formatDateTime } = useFormatDate()
const uid = useId()
const fieldId = (name: string) => `${uid}-${name}`
const showCreate = ref(false)

const companyOptionLabel = (company: CompanyBrief): string =>
  company.inn ? `${company.name} (ИНН ${company.inn})` : company.name

const vehiclesSummary = (deal: FastDealListItem): string => {
  if (deal.vehicle_count <= 0) return 'Техника не добавлена'
  const units = pluralRu(deal.vehicle_count, 'единица', 'единицы', 'единиц')
  return `${deal.vehicle_count} ${units} · ${formatMoney(deal.vehicles_total)}`
}

// A just created draft is edited in its own card.
const onCreated = async (deal: FastDealCard) => {
  showCreate.value = false
  await navigateTo(fastDealRoute(deal.id))
}

onMounted(load)
</script>
