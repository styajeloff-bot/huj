<template>
  <div data-storefront-block="client.cabinet">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">Компенсации</h2>
        <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)] mt-1">
          Реестр компенсаций по сделкам с учетом ролевой видимости.
        </p>
      </div>
    </div>

    <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] mb-6">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Статус</label>
          <select v-model="filters.status" class="storefront-control select-field" @change="applyFilters">
            <option value="">Все статусы</option>
            <option value="under_review">На рассмотрении</option>
            <option value="accepted">Принято</option>
            <option value="rejected">Отказано</option>
            <option value="paid">Оплачено</option>
            <option value="overdue">Просрочено</option>
            <option value="cancelled">Отменено</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Источник</label>
          <select v-model="filters.source" class="storefront-control select-field" @change="applyFilters">
            <option value="">Все источники</option>
            <option value="platform">Платформа</option>
            <option value="exchange">Биржа</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Заявка</label>
          <input
            v-model="filters.application_query"
            type="text"
            class="storefront-control input-field"
            placeholder="Номер заявки или UUID"
            @change="applyFilters"
            @keyup.enter="applyFilters"
          />
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Поиск по номеру заявки в таблице или UUID заявки.</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Поддержка</label>
          <input
            v-model="filters.support_query"
            type="text"
            class="storefront-control input-field"
            placeholder="Название программы или UUID"
            @change="applyFilters"
            @keyup.enter="applyFilters"
          />
          <p class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
            Поиск по названию применённой поддержки, UUID применения или UUID программы.
          </p>
        </div>

        <div v-if="showParticipantFilters">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Кто платит</label>
          <select v-model="filters.payer" class="storefront-control select-field" @change="applyFilters">
            <option value="">Все</option>
            <option v-for="item in payerOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>

        <div v-if="showParticipantFilters">
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Кому платит</label>
          <select v-model="filters.recipient" class="storefront-control select-field" @change="applyFilters">
            <option value="">Все</option>
            <option v-for="item in recipientOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Срок с</label>
          <input
            v-model="filters.due_date_from"
            type="date"
            class="storefront-control input-field"
            @change="applyFilters"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-1">Срок по</label>
          <input
            v-model="filters.due_date_to"
            type="date"
            class="storefront-control input-field"
            @change="applyFilters"
          />
        </div>

        <div>
          <SearchableDropdown
            v-model="visibleColumns"
            label="Колонки таблицы"
            placeholder="Выберите колонки"
            :items="columnOptions"
            label-key="label"
            value-key="id"
            search-placeholder="Найти колонку..."
            multiple
            @update:modelValue="saveVisibleColumns"
          />
        </div>
      </div>
      <div class="mt-4 flex flex-col sm:flex-row sm:items-center sm:justify-end gap-2">
        <button type="button" class="btn-secondary" @click="resetFilters">
          Сбросить
        </button>
        <button type="button" class="btn-primary" @click="applyFilters">
          Применить фильтры
        </button>
      </div>
    </div>

    <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
      <div v-if="loading" class="text-center py-8">
        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
        <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем компенсации...</p>
      </div>

      <div v-else-if="error" class="text-center py-8 px-4">
        <p class="text-[color:var(--storefront-error-text,#dc2626)] mb-4">{{ error }}</p>
        <button class="btn-primary" @click="fetchCompensations">Попробовать снова</button>
      </div>

      <div v-else-if="compensations.length === 0" class="text-center py-8 px-4">
        <p class="text-[color:var(--storefront-text-muted,#4b5563)]">Компенсации не найдены</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
          <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
            <tr>
              <th v-if="col('application')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Заявка</th>
              <th v-if="col('source')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Источник</th>
              <th v-if="col('support')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Поддержка</th>
              <th v-if="col('payer')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Кто платит</th>
              <th v-if="col('recipient')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Кому платит</th>
              <th v-if="col('base')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">База</th>
              <th v-if="col('amount')" class="px-4 py-3 text-right text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Сумма</th>
              <th v-if="col('documents')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Документы</th>
              <th v-if="col('status')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Статус</th>
              <th v-if="col('dueDate')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Срок</th>
              <th v-if="col('paidAt')" class="px-4 py-3 text-left text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase">Дата оплаты</th>
              <th
                v-if="col('actions') && showActionsColumn"
                class="px-4 py-3 text-right text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)] uppercase"
              >
                Действия
              </th>
            </tr>
          </thead>
          <tbody class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] divide-y divide-[color:var(--storefront-border,#e5e7eb)]">
            <tr v-for="compensation in compensations" :key="compensation.id" class="hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
              <td v-if="col('application')" class="px-4 py-3 text-sm">
                <NuxtLink
                  v-if="canOpenApplicationLink(compensation)"
                  :to="compensation.source === 'exchange'
                    ? `/workspace/exchange?request=${compensation.exchange_request_id}`
                    : `/application/${compensation.application_id}`"
                  class="text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1e40af)] hover:underline"
                >
                  {{ applicationDisplayNumber(compensation) }}
                </NuxtLink>
                <span v-else :class="applicationDisplayNumber(compensation) !== '—' ? 'text-[color:var(--storefront-text,#374151)]' : 'text-[color:var(--storefront-text-muted,#9ca3af)]'">
                  {{ applicationDisplayNumber(compensation) }}
                </span>
              </td>
              <td v-if="col('source')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ sourceLabel(compensation.source) }}
              </td>
              <td v-if="col('support')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                <div class="font-medium text-[color:var(--storefront-text,#111827)]">
                  {{ compensation.applied_support_name || 'Применённая поддержка' }}
                </div>
                <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]" :title="compensation.applied_support_id">
                  Применение: {{ shortUuid(compensation.applied_support_id) }}
                </div>
                <div
                  v-if="compensation.support_program_id"
                  class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]"
                  :title="compensation.support_program_id"
                >
                  Программа: {{ shortUuid(compensation.support_program_id) }}
                </div>
              </td>
              <td v-if="col('payer')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ payerLabel(compensation.payer) }}
              </td>
              <td v-if="col('recipient')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ recipientLabel(compensation.recipient) }}
              </td>
              <td v-if="col('base')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ baseLabel(compensation.calculation_base) }}
              </td>
              <td v-if="col('amount')" class="px-4 py-3 text-sm text-right font-medium">
                {{ formatRub(compensation.amount) }} р.
              </td>
              <td v-if="col('documents')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                <div v-if="compensation.documents?.length" class="space-y-1">
                  <div
                    v-for="(document, index) in compensation.documents"
                    :key="documentKey(document, index)"
                  >
                    <a
                      v-if="documentLink(document)"
                      :href="documentLink(document)"
                      target="_blank"
                      rel="noopener"
                      class="text-[color:var(--storefront-link,#2563eb)] hover:text-[color:var(--storefront-link-hover,#1e40af)] hover:underline"
                    >
                      {{ documentLabel(document) }}
                    </a>
                    <span v-else>{{ documentLabel(document) }}</span>
                  </div>
                </div>
                <span v-else class="text-[color:var(--storefront-text-muted,#9ca3af)]">—</span>
              </td>
              <td v-if="col('status')" class="px-4 py-3">
                <span
                  class="inline-flex px-2 py-1 text-xs font-semibold rounded-full"
                  :class="statusClass(compensation.status)"
                >
                  {{ statusLabel(compensation.status) }}
                </span>
              </td>
              <td v-if="col('dueDate')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ formatDate(compensation.due_date) }}
              </td>
              <td v-if="col('paidAt')" class="px-4 py-3 text-sm text-[color:var(--storefront-text,#374151)]">
                {{ formatDate(compensation.paid_at) }}
              </td>
              <td v-if="col('actions') && showActionsColumn" class="px-4 py-3 text-right text-sm space-x-2">
                <button
                  v-if="canReview(compensation)"
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1e40af)]"
                  @click="openReviewDialog(compensation, 'accepted')"
                >
                  Акцептовать
                </button>
                <button
                  v-if="canReview(compensation)"
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)]"
                  @click="openReviewDialog(compensation, 'rejected')"
                >
                  Отказать
                </button>
                <button
                  v-if="canMarkPaid(compensation)"
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#16a34a)] hover:text-[color:var(--storefront-ghost-hover-foreground,#166534)]"
                  @click="openPaidDialog(compensation)"
                >
                  Оплатить
                </button>
                <button
                  v-if="canCancelCompensation && (compensation.status === 'under_review' || compensation.status === 'accepted' || compensation.status === 'overdue')"
                  type="button"
                  class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#dc2626)] hover:text-[color:var(--storefront-ghost-hover-foreground,#991b1b)]"
                  @click="openCancelDialog(compensation)"
                >
                  Отменить
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pagination.pages > 1" class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] px-6 py-3 border-t">
        <div class="flex items-center justify-between">
          <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Показаны
            {{ (pagination.page - 1) * pagination.limit + 1 }}–{{ Math.min(pagination.page * pagination.limit, pagination.total) }}
            из {{ pagination.total }}
          </div>
          <div class="flex space-x-2">
            <button
              class="btn-secondary disabled:opacity-50"
              :disabled="pagination.page <= 1"
              @click="changePage(pagination.page - 1)"
            >
              Предыдущая
            </button>
            <button
              class="btn-secondary disabled:opacity-50"
              :disabled="pagination.page >= pagination.pages"
              @click="changePage(pagination.page + 1)"
            >
              Следующая
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showReviewDialog && compensationToReview"
      class="fixed inset-0 z-50 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] flex items-center justify-center p-4"
      @click.self="closeReviewDialog"
    >
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">
          {{ reviewForm.status === 'accepted' ? 'Акцептовать компенсацию' : 'Отказать по компенсации' }}
        </h3>
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-4">
          Компенсация #{{ compensationToReview.id }}, сумма {{ formatRub(compensationToReview.amount) }} р.
        </p>
        <div class="space-y-3 mb-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Комментарий</label>
            <textarea v-model="reviewForm.reason" class="storefront-control input-field text-sm min-h-[80px]" placeholder="Необязательно" />
          </div>
          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">
              Файл подтверждения
            </label>
            <input
              type="file"
              class="storefront-control block w-full text-sm text-[color:var(--storefront-text-muted,#4b5563)] file:mr-4 file:rounded-lg file:border-0 file:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]"
              :accept="documentAccept"
              :disabled="reviewLoading"
              @change="onReviewFileChange"
            />
            <p v-if="reviewFile" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ reviewFile.name }}
            </p>
          </div>
        </div>
        <div v-if="reviewError" class="mb-4 p-3 rounded border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
          {{ reviewError }}
        </div>
        <div class="flex justify-end gap-3">
          <button type="button" class="btn-secondary" :disabled="reviewLoading" @click="closeReviewDialog">
            Отмена
          </button>
          <button type="button" class="btn-primary" :disabled="reviewLoading" @click="submitReview">
            {{ reviewLoading ? 'Сохраняем...' : 'Подтвердить' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showPaidDialog && compensationToPay"
      class="fixed inset-0 z-50 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] flex items-center justify-center p-4"
      @click.self="closePaidDialog"
    >
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-2">Отметить оплату</h3>
        <p class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mb-4">
          Компенсация #{{ compensationToPay.id }}, сумма {{ formatRub(compensationToPay.amount) }} р.
          Требуется хотя бы один подтверждающий документ.
        </p>
        <div class="space-y-3 mb-4">
          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">
              Подтверждающий документ *
            </label>
            <input
              type="file"
              class="storefront-control block w-full text-sm text-[color:var(--storefront-text-muted,#4b5563)] file:mr-4 file:rounded-lg file:border-0 file:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]"
              :accept="documentAccept"
              :disabled="paidLoading"
              @change="onPaidFileChange"
            />
            <p v-if="paidFile" class="mt-1 text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              {{ paidFile.name }}
            </p>
          </div>
          <div>
            <label class="block text-xs font-medium text-[color:var(--storefront-label,#4b5563)] mb-1">Дата оплаты</label>
            <input v-model="paidForm.paidDate" type="date" class="storefront-control input-field text-sm" />
          </div>
        </div>
        <div
          v-if="paidError"
          class="mb-4 p-3 rounded border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-sm text-[color:var(--storefront-error-text,#b91c1c)]"
        >
          {{ paidError }}
        </div>
        <div class="flex justify-end gap-3">
          <button type="button" class="btn-secondary" :disabled="paidLoading" @click="closePaidDialog">
            Отмена
          </button>
          <button type="button" class="btn-primary" :disabled="paidLoading" @click="submitPaid">
            {{ paidLoading ? 'Сохраняем...' : 'Подтвердить' }}
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="showCancelDialog && compensationToCancel"
      class="fixed inset-0 z-50 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)] flex items-center justify-center p-4"
      @click.self="closeCancelDialog"
    >
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">Отменить компенсацию</h3>
        <p class="text-sm text-[color:var(--storefront-text,#374151)] mb-4">
          Вы уверены, что хотите отменить компенсацию #{{ compensationToCancel.id }}?
        </p>
        <div
          v-if="cancelError"
          class="mb-4 p-3 rounded border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] text-sm text-[color:var(--storefront-error-text,#b91c1c)]"
        >
          {{ cancelError }}
        </div>
        <div class="flex justify-end gap-3">
          <button class="btn-secondary" :disabled="cancelLoading" @click="closeCancelDialog">
            Отмена
          </button>
          <button class="storefront-action-destructive btn-danger" :disabled="cancelLoading" @click="cancelCompensation">
            {{ cancelLoading ? 'Отменяем...' : 'Отменить' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { createCompensationApi, type CompensationDocument, type CompensationFilters, type CompensationPayer, type CompensationRecipient, type CompensationRecord, type CompensationSource, type CompensationStatus } from '../api/compensationApi'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import { useAuthStore } from '~/features/auth/store/auth'
import SearchableDropdown from '~/components/ui/SearchableDropdown.vue'
import type { UUID } from '~/types/ids'

interface SelectOption<T extends string> {
  value: T
  label: string
}

const config = useRuntimeConfig()
const authStore = useAuthStore()
const api = createCompensationApi(config)
const documentAccept = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.xls,.xlsx'

const payerOptions: SelectOption<CompensationPayer>[] = [
  { value: 'distributor', label: 'Дистрибьютор' },
  { value: 'dealer', label: 'Дилер' },
  { value: 'carcraft', label: 'CarCraft' },
  { value: 'minpromtorg', label: 'Минпромторг' },
  { value: 'client', label: 'Клиент' }
]

const recipientOptions: SelectOption<CompensationRecipient>[] = [
  { value: 'leasing_company', label: 'Лизинговая компания' },
  { value: 'dealer', label: 'Дилер' },
  { value: 'carcraft', label: 'CarCraft' },
  { value: 'client', label: 'Клиент' }
]

const COLUMNS_KEY = 'compensation-registry-visible-columns'
const ALL_COLS = [
  'application',
  'source',
  'support',
  'payer',
  'recipient',
  'base',
  'amount',
  'documents',
  'status',
  'dueDate',
  'paidAt',
  'actions'
] as const
type CompensationColumnId = typeof ALL_COLS[number]

const columnOptions: Array<{ id: CompensationColumnId; label: string }> = [
  { id: 'application', label: 'Заявка' },
  { id: 'source', label: 'Источник' },
  { id: 'support', label: 'Поддержка' },
  { id: 'payer', label: 'Кто платит' },
  { id: 'recipient', label: 'Кому платит' },
  { id: 'base', label: 'База' },
  { id: 'amount', label: 'Сумма' },
  { id: 'documents', label: 'Документы' },
  { id: 'status', label: 'Статус' },
  { id: 'dueDate', label: 'Срок' },
  { id: 'paidAt', label: 'Дата оплаты' },
  { id: 'actions', label: 'Действия' }
]

const columnsStorage = useScopedStorage<CompensationColumnId[]>(COLUMNS_KEY)
clearLegacy(COLUMNS_KEY)

const normalizeColumns = (columns: unknown): CompensationColumnId[] => {
  if (!Array.isArray(columns)) return [...ALL_COLS]
  const filtered = columns.filter((id): id is CompensationColumnId =>
    ALL_COLS.includes(id as CompensationColumnId)
  )
  return filtered.length > 0 ? filtered : [...ALL_COLS]
}

const loadVisibleColumns = (): CompensationColumnId[] => {
  if (process.client) return normalizeColumns(columnsStorage.get())
  return [...ALL_COLS]
}

const visibleColumns = ref<CompensationColumnId[]>(loadVisibleColumns())

const saveVisibleColumns = (): void => {
  if (!process.client) return
  const columns = normalizeColumns(visibleColumns.value)
  if (columns.length !== visibleColumns.value.length) {
    visibleColumns.value = columns
  }
  columnsStorage.set(columns)
}

const col = (id: CompensationColumnId): boolean => visibleColumns.value.includes(id)

const compensations = ref<CompensationRecord[]>([])
const loading = ref(true)
const error = ref('')
const showCancelDialog = ref(false)
const cancelLoading = ref(false)
const cancelError = ref('')
const compensationToCancel = ref<CompensationRecord | null>(null)

const showPaidDialog = ref(false)
const paidLoading = ref(false)
const paidError = ref('')
const compensationToPay = ref<CompensationRecord | null>(null)
const paidForm = ref({
  paidDate: ''
})
const paidFile = ref<File | null>(null)
const showReviewDialog = ref(false)
const reviewLoading = ref(false)
const reviewError = ref('')
const compensationToReview = ref<CompensationRecord | null>(null)
const reviewForm = ref<{
  status: 'accepted' | 'rejected'
  reason: string
}>({
  status: 'accepted',
  reason: ''
})
const reviewFile = ref<File | null>(null)

const pagination = ref({
  page: 1,
  limit: 50,
  total: 0,
  pages: 0
})

const filters = ref<CompensationFilters>({
  status: '',
  payer: '',
  recipient: '',
  source: '',
  application_query: '',
  support_query: '',
  due_date_from: '',
  due_date_to: ''
})

const canCancelCompensation = computed(() => authStore.isCarCraftEmployee)
const showParticipantFilters = computed(() => authStore.isCarCraftEmployee)

const PAYER_ROLES = new Set(['distributor', 'dealer', 'carcraft', 'minpromtorg', 'client'])

const canMarkPaid = (row: CompensationRecord): boolean => {
  if (row.status !== 'accepted' && row.status !== 'overdue') return false
  const role = authStore.userRole
  if (authStore.isCarCraftEmployee) return true
  return role != null && role === row.payer
}

const canReview = (row: CompensationRecord): boolean => {
  if (row.status !== 'under_review') return false
  const role = authStore.userRole
  if (authStore.isCarCraftEmployee) return true
  return role != null && role === row.payer
}

/** Колонка нужна сотруднику CarCraft (отмена / оплата) или роли, которая может быть плательщиком. */
const showActionsColumn = computed(
  () => authStore.isCarCraftEmployee || (authStore.userRole != null && PAYER_ROLES.has(authStore.userRole))
)

const applicationDisplayNumber = (row: CompensationRecord): string => (
  row.source === 'exchange'
    ? row.exchange_request_display_number || row.exchange_request_id || '—'
    : row.application_display_number || '—'
)

const canOpenApplicationLink = (row: CompensationRecord): boolean => {
  if (row.source === 'exchange') {
    return Boolean(row.exchange_request_id && (authStore.isLeasingCompany || authStore.isDealer))
  }
  if (!row.application_id || authStore.isDealer) return false
  return authStore.isCarCraftEmployee || authStore.isDistributor || authStore.isClient || authStore.isLeasingCompany
}

const sourceLabel = (source: CompensationSource): string => source === 'exchange' ? 'Биржа' : 'Платформа'

const payerLabel = (value: CompensationPayer): string =>
  payerOptions.find((item) => item.value === value)?.label || value

const recipientLabel = (value: CompensationRecipient): string =>
  recipientOptions.find((item) => item.value === value)?.label || value

const baseLabel = (value: CompensationRecord['calculation_base']): string => {
  const labels: Record<CompensationRecord['calculation_base'], string> = {
    base_price: 'РРЦ',
    special_price: 'Специальная цена',
    dealer_cost: 'Себестоимость',
    application_price: 'Цена в заявке',
    down_payment: 'Первый взнос',
    support_amount: 'Сумма поддержки'
  }
  return labels[value]
}

const statusLabel = (value: CompensationStatus | string): string => {
  const labels: Record<CompensationStatus, string> = {
    under_review: 'На рассмотрении',
    accepted: 'Принято',
    rejected: 'Отказано',
    paid: 'Оплачено',
    overdue: 'Просрочено',
    cancelled: 'Отменено'
  }
  return labels[value as CompensationStatus] || value
}

const statusClass = (value: CompensationStatus | string): string => {
  const classes: Record<CompensationStatus, string> = {
    under_review: 'bg-[color:rgb(var(--storefront-warning-rgb,254_249_195)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#854d0e)]',
    accepted: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]',
    rejected: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]',
    paid: 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]',
    overdue: 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]',
    cancelled: 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
  }
  return classes[value as CompensationStatus] || 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1f2937)]'
}

const formatRub = (value: number | null | undefined): string => {
  if (value == null) return '0'
  return new Intl.NumberFormat('ru-RU').format(Math.round(Number(value)))
}

const documentLabel = (document: CompensationDocument): string =>
  document.name || document.file_name || 'Документ'

const documentLink = (document: CompensationDocument): string =>
  String(document.path || '')

const documentKey = (document: CompensationDocument, index: number): string =>
  String(document.id || document.path || document.name || index)

const shortUuid = (value: UUID | null | undefined): string => {
  if (!value) return '—'
  const normalized = String(value)
  return normalized.length > 12
    ? `${normalized.slice(0, 8)}…${normalized.slice(-4)}`
    : normalized
}

const formatDate = (value: string | null): string => {
  if (!value) return '—'

  const parsed = new Date(value)
  if (!Number.isNaN(parsed.getTime())) {
    return parsed.toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    })
  }

  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}.${match[2]}.${match[1]}` : String(value)
}

const applyFilters = async (): Promise<void> => {
  pagination.value.page = 1
  await fetchCompensations()
}

const resetFilters = async (): Promise<void> => {
  filters.value = {
    status: '',
    payer: '',
    recipient: '',
    source: '',
    application_query: '',
    support_query: '',
    due_date_from: '',
    due_date_to: ''
  }
  pagination.value.page = 1
  await fetchCompensations()
}

const fetchCompensations = async (): Promise<void> => {
  loading.value = true
  error.value = ''

  if (
    filters.value.due_date_from &&
    filters.value.due_date_to &&
    filters.value.due_date_from > filters.value.due_date_to
  ) {
    error.value = 'Срок "с" не может быть позже срока "по"'
    loading.value = false
    return
  }

  try {
    const response = await api.list({
      ...filters.value,
      page: String(pagination.value.page),
      limit: String(pagination.value.limit)
    })
    compensations.value = response.compensations || []
    const nextPagination = response.pagination || pagination.value
    pagination.value = {
      ...nextPagination,
      pages: nextPagination.pages ?? nextPagination.total_pages ?? 0
    }
  } catch (err: unknown) {
    error.value = extractErrorMessage(err, 'Ошибка при загрузке компенсаций')
  } finally {
    loading.value = false
  }
}

const changePage = async (page: number): Promise<void> => {
  pagination.value.page = page
  await fetchCompensations()
}

const todayIsoDate = (): string => {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const openPaidDialog = (compensation: CompensationRecord): void => {
  compensationToPay.value = compensation
  paidForm.value = { paidDate: todayIsoDate() }
  paidFile.value = null
  paidError.value = ''
  showPaidDialog.value = true
}

const openReviewDialog = (compensation: CompensationRecord, status: 'accepted' | 'rejected'): void => {
  compensationToReview.value = compensation
  reviewForm.value = { status, reason: '' }
  reviewFile.value = null
  reviewError.value = ''
  showReviewDialog.value = true
}

const closeReviewDialog = (): void => {
  showReviewDialog.value = false
  compensationToReview.value = null
  reviewFile.value = null
  reviewError.value = ''
}

const submitReview = async (): Promise<void> => {
  if (!compensationToReview.value) return
  reviewLoading.value = true
  reviewError.value = ''
  try {
    let documents: CompensationDocument[] | null = null
    if (reviewFile.value) {
      const response = await api.uploadDocument(
        compensationToReview.value.id,
        reviewFile.value,
        reviewForm.value.status === 'accepted' ? 'acceptance' : 'rejection'
      )
      documents = [response.document]
    }
    await api.updateStatus(compensationToReview.value.id, {
      status: reviewForm.value.status,
      reason: reviewForm.value.reason.trim() || null,
      documents
    })
    closeReviewDialog()
    await fetchCompensations()
  } catch (err: unknown) {
    reviewError.value = extractErrorMessage(err, 'Не удалось обновить статус')
  } finally {
    reviewLoading.value = false
  }
}

const closePaidDialog = (): void => {
  showPaidDialog.value = false
  compensationToPay.value = null
  paidFile.value = null
  paidError.value = ''
}

const submitPaid = async (): Promise<void> => {
  if (!compensationToPay.value) return
  if (!paidFile.value) {
    paidError.value = 'Загрузите подтверждающий документ'
    return
  }

  paidLoading.value = true
  paidError.value = ''
  try {
    const dateStr = paidForm.value.paidDate || todayIsoDate()
    const paidAt = new Date(`${dateStr}T12:00:00`).toISOString()
    const response = await api.uploadDocument(
      compensationToPay.value.id,
      paidFile.value,
      'payment'
    )
    await api.updateStatus(compensationToPay.value.id, {
      status: 'paid',
      documents: [
        ...(compensationToPay.value.documents || []),
        response.document
      ],
      paid_at: paidAt
    })
    closePaidDialog()
    await fetchCompensations()
  } catch (err: unknown) {
    paidError.value = extractErrorMessage(err, 'Не удалось отметить оплату')
  } finally {
    paidLoading.value = false
  }
}

const onReviewFileChange = (event: Event): void => {
  reviewFile.value = selectedFileFromEvent(event)
}

const onPaidFileChange = (event: Event): void => {
  paidFile.value = selectedFileFromEvent(event)
}

const selectedFileFromEvent = (event: Event): File | null => {
  const input = event.target as HTMLInputElement | null
  return input?.files?.[0] || null
}

const openCancelDialog = (compensation: CompensationRecord): void => {
  compensationToCancel.value = compensation
  cancelError.value = ''
  showCancelDialog.value = true
}

const closeCancelDialog = (): void => {
  showCancelDialog.value = false
  compensationToCancel.value = null
  cancelError.value = ''
}

const cancelCompensation = async (): Promise<void> => {
  if (!compensationToCancel.value) return

  cancelLoading.value = true
  cancelError.value = ''
  try {
    await api.updateStatus(compensationToCancel.value.id, { status: 'cancelled' })
    closeCancelDialog()
    await fetchCompensations()
  } catch (err: unknown) {
    cancelError.value = extractErrorMessage(err, 'Не удалось отменить компенсацию')
  } finally {
    cancelLoading.value = false
  }
}

const extractErrorMessage = (err: unknown, fallback: string): string => {
  if (typeof err === 'object' && err !== null) {
    const maybeData = (err as { data?: { detail?: string; error?: string } }).data
    if (maybeData?.detail) return maybeData.detail
    if (maybeData?.error) return maybeData.error
  }
  return fallback
}

onMounted(() => {
  fetchCompensations()
})
</script>
