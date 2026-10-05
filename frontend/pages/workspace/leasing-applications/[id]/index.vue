<template>
  <div class="max-w-7xl mx-auto">
    <NuxtLink to="/workspace/leasing-applications" class="text-blue-600 hover:text-blue-700 text-sm">
      ← Назад к заявкам
    </NuxtLink>

    <div v-if="loading" class="flex justify-center py-16">
      <div class="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600" />
    </div>

    <div v-else-if="error" class="bg-red-50 border border-red-200 text-red-700 rounded-lg p-4 mt-4">
      {{ error }}
    </div>

    <div v-else-if="state" class="mt-4 space-y-6">
        <!-- 1. Header card -->
        <section class="bg-white rounded-lg shadow-sm p-6">
          <div class="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 class="text-3xl font-bold text-gray-900">
                {{ headerNumber }}
              </h1>
              <ApplicationSourceBadge :source="application.source_type" class="mt-1" />
              <p class="text-sm text-gray-600 mt-1">
                {{ submittedLabel }}
              </p>
            </div>
          </div>

          <dl class="mt-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-4 gap-y-3 text-sm">
            <div>
              <dt class="text-gray-500">Компания</dt>
              <dd class="font-medium text-gray-900">{{ companyName || '—' }}</dd>
            </div>
            <div>
              <dt class="text-gray-500">ИНН</dt>
              <dd class="font-mono text-gray-900">{{ companyInn || '—' }}</dd>
            </div>
          </dl>

          <div class="mt-5 flex flex-wrap items-center gap-3 text-sm" aria-live="polite">
            <span class="text-gray-500">Статус:</span>
            <span
              class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
              :class="statusBadgeClass"
            >
              {{ statusLabel }}
            </span>
            <button
              v-if="canTakeInWork"
              type="button"
              class="btn-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:opacity-50"
              :disabled="takingInWork || working"
              :aria-busy="takingInWork"
              @click="takeInWork"
            >
              {{ takingInWork ? 'Берём в работу…' : 'Взять в работу' }}
            </button>
          </div>
          <p v-if="takeInWorkError" role="alert" class="mt-3 text-sm text-red-700">
            {{ takeInWorkError }}
          </p>
          <p v-if="takeInWorkMessage" role="status" class="mt-3 text-sm text-gray-600">
            {{ takeInWorkMessage }}
          </p>
          <p v-if="!canReview" class="mt-3 text-sm text-gray-600">Заявка доступна только для просмотра.</p>
        </section>

        <ConditionRequests
          v-if="authStore.userRole === 'leasing_company'"
          :api="monetizationApi"
          :application-id="applicationId"
          role="leasing_company"
        />

        <!-- Tabs -->
        <div class="border-b border-gray-200">
          <nav class="-mb-px flex gap-6 overflow-x-auto" aria-label="Tabs">
            <button
              v-for="tab in TABS"
              :key="tab.key"
              type="button"
              class="whitespace-nowrap pb-3 px-1 border-b-2 font-medium text-sm transition-colors"
              :class="activeTab === tab.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </nav>
        </div>

        <!-- Tab: Заявка -->
        <div v-show="activeTab === 'overview'" class="space-y-6">
          <template v-if="hasNormalizedApplicationItems">
            <CommerceApplicationItemsSummary
              v-if="activeApplicationItems.length > 0"
              :items="activeApplicationItems"
              :items-count="applicationItemsCount"
              :total-items-price="applicationItemsPrice"
              show-purpose-regions
            />
            <section v-else class="rounded-lg bg-white p-6 shadow-sm">
              <h2 class="text-lg font-semibold text-gray-900">Техника в заявке</h2>
              <p class="mt-2 text-sm text-gray-500">В заявке нет активных позиций техники.</p>
            </section>
          </template>
          <!-- 3. Vehicles -->
          <section v-else class="bg-white rounded-lg shadow-sm p-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4">
              Автомобили в заявке
            </h2>
            <div v-if="vehicles.length === 0" class="text-sm text-gray-500">
              В заявке нет автомобилей.
            </div>
            <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div
                v-for="v in vehicles"
                :key="v.id as string"
                class="border border-gray-200 rounded-lg p-4 bg-white hover:shadow-md transition-shadow duration-200 relative flex items-start gap-4"
              >
                <NuxtLink
                  v-if="v.detail_url"
                  :to="String(v.detail_url)"
                  class="absolute inset-0 z-10 cursor-pointer"
                  aria-label="Открыть детали"
                />

                <!-- Image -->
                <div class="relative flex-shrink-0 w-32 h-24 bg-gray-100 rounded-lg overflow-hidden">
                  <img
                    v-if="v.images && Array.isArray(v.images) && (v.images as string[]).length > 0"
                    :src="vehicleImageUrl((v.images as string[])[0])"
                    :alt="vehicleTitle(v)"
                    class="w-full h-full object-contain"
                    onerror="this.src='/images/car-placeholder.png'"
                  >
                  <img
                    v-else-if="v.main_image"
                    :src="vehicleImageUrl(v.main_image)"
                    :alt="vehicleTitle(v)"
                    class="w-full h-full object-contain"
                    onerror="this.src='/images/car-placeholder.png'"
                  >
                  <div v-else class="w-full h-full flex items-center justify-center text-gray-400">
                    <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                    </svg>
                  </div>
                </div>

                <!-- Content -->
                <div class="flex-1 min-w-0">
                  <h3 class="text-base font-semibold text-gray-900">
                    {{ vehicleTitle(v) }}
                  </h3>
                  <p class="text-sm text-gray-600 mt-0.5">
                    {{ [(v.modification_name as string | undefined), (v.group_name as string | undefined), (v.vehicle_year as number | undefined)].filter(Boolean).join(' · ') }}
                  </p>

                  <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600">
                    <span v-if="v.color" class="flex items-center gap-1">
                      <span class="w-3 h-3 rounded-full border border-gray-300" :style="{ backgroundColor: v.color as string }" />
                      {{ v.color }}
                    </span>
                    <span v-if="v.quantity">Кол-во: {{ v.quantity }}</span>
                    <span v-if="v.unit_price">Цена: {{ formatMoney(v.unit_price) }}</span>
                    <span v-if="v.total_price" class="font-semibold text-gray-900">Итого: {{ formatMoney(v.total_price) }}</span>
                  </div>

                  <CommerceApplicationItemComment :comment="typeof v.comment === 'string' ? v.comment : null" />
                  <dl class="mt-3 grid grid-cols-1 gap-2 text-sm text-gray-700 sm:grid-cols-2">
                    <div>
                      <dt class="text-gray-500">Цель приобретения</dt>
                      <dd class="font-medium text-gray-900">{{ formatLeasingPurpose(v) }}</dd>
                    </div>
                    <div>
                      <dt class="text-gray-500">Регион</dt>
                      <dd class="font-medium text-gray-900">
                        <VehicleRegionsDisplay :vehicle="v" />
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>
          </section>

          <!-- Запрошенные условия -->
          <section class="bg-white rounded-lg shadow-sm p-6">
            <h2 class="text-lg font-semibold text-gray-900 mb-4">
              Запрошенные условия
            </h2>
            <dl class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3 text-sm">
              <div>
                <dt class="text-gray-500">Сумма заявки</dt>
                <dd class="font-medium text-gray-900">{{ formatMoney(application.total_amount) }}</dd>
              </div>
              <div>
                <dt class="text-gray-500">Аванс (первоначальный взнос)</dt>
                <dd class="font-medium text-gray-900">
                  {{ formatMoney(application.down_payment || (application.total_amount && application.down_payment_percent ? Number(application.total_amount) * Number(application.down_payment_percent) / 100 : null)) }}
                  <span v-if="application.down_payment_percent" class="text-gray-500 font-normal">
                    ({{ application.down_payment_percent }}%)
                  </span>
                </dd>
              </div>
              <div>
                <dt class="text-gray-500">Срок договора</dt>
                <dd class="font-medium text-gray-900">{{ leaseTermLabel }}</dd>
              </div>
              <div>
                <dt class="text-gray-500">Выкупная стоимость</dt>
                <dd class="font-medium text-gray-900">{{ formatMoney(application.buyout_amount) }}</dd>
              </div>
              <div>
                <dt class="text-gray-500">Желаемый ежемесячный платёж</dt>
                <dd class="font-medium text-gray-900">{{ formatMoney(application.monthly_payment) }}</dd>
              </div>
            </dl>
          </section>

          <section class="flex flex-wrap items-center justify-between gap-4 rounded-lg bg-white p-6 shadow-sm">
            <div>
              <h2 class="text-lg font-semibold text-gray-900">Анкета клиента</h2>
              <p class="mt-1 text-sm text-gray-600">Сведения по заявке доступны на отдельной странице.</p>
            </div>
            <NuxtLink
              :to="questionnaireLocation(applicationId, 'leasing', { leasingCompanyId })"
              class="btn-secondary text-sm"
            >
              Открыть анкету
            </NuxtLink>
          </section>

          <!-- Документы (встроены в Заявку) -->
          <section class="bg-white rounded-lg shadow-sm p-6">
            <div class="mb-4 flex items-center justify-between gap-3">
              <h2 class="text-lg font-semibold text-gray-900">
                Прикреплённые документы к заявке
                <span v-if="attachedDocuments.length" class="ml-2 text-sm font-normal text-gray-500">
                  · {{ attachedDocuments.length }}
                </span>
              </h2>
              <div class="flex shrink-0 items-center gap-3">
              <button
                type="button"
                class="btn-secondary text-sm"
                :disabled="attachedDocsLoading"
                @click="fetchAttachedDocuments"
              >
                {{ attachedDocsLoading ? 'Обновляем…' : 'Обновить' }}
              </button>
              <button
                v-if="canRequestDocuments"
                type="button"
                class="btn-secondary text-sm"
                :disabled="working || takingInWork"
                @click="openDocsModal"
              >
                Запросить дополнительные документы
              </button>
              </div>
            </div>
            <p v-if="attachedDocsLoading && attachedDocuments.length" class="mb-3 text-sm text-gray-500" role="status">
              Обновляем список документов…
            </p>
            <p v-if="attachedDocsError && attachedDocuments.length" class="mb-3 text-sm text-red-600" role="alert">
              {{ attachedDocsError }}
            </p>
            <div v-if="attachedDocsLoading && !attachedDocuments.length" class="text-sm text-gray-500">
              Загружаем список документов…
            </div>
            <div v-else-if="attachedDocsError && !attachedDocuments.length" class="text-sm text-red-600" role="alert">
              {{ attachedDocsError }}
            </div>
            <div v-else-if="attachedDocuments.length === 0" class="text-sm text-gray-500">
              Клиент пока ничего не прикрепил.
            </div>
            <ul v-else class="divide-y divide-gray-100">
              <li
                v-for="doc in attachedDocuments"
                :key="doc.id"
                class="py-3 flex items-start justify-between gap-4 flex-wrap"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-baseline gap-2 flex-wrap">
                    <span class="font-medium text-gray-900">{{ doc.display_name }}</span>
                    <span v-if="doc.period_label" class="text-xs font-mono text-gray-500">
                      {{ doc.period_label }}
                    </span>
                  </div>
                  <div class="text-xs text-gray-600 mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                    <span v-if="doc.file_name">{{ doc.file_name }}</span>
                    <span v-if="doc.uploaded_at">
                      Загружен: {{ formatDocDate(doc.uploaded_at) }}
                    </span>
                    <span
                      v-if="doc.leasing_company_status"
                      class="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-medium"
                      :class="docStatusClass(doc.leasing_company_status)"
                    >
                      {{ docStatusLabel(doc.leasing_company_status) }}
                    </span>
                  </div>
                </div>
                <div class="flex items-center gap-3 shrink-0">
                  <button
                    v-if="doc.leasing_company_status === 'pending'"
                    type="button"
                    class="text-xs text-blue-600 hover:text-blue-800 underline"
                    :disabled="approvingDocument"
                    @click="openApproveDocument(doc)"
                  >
                    Принять
                  </button>
                  <a
                    v-if="doc.download_url"
                    :href="documentsApi.downloadUrl(doc.download_url)"
                    target="_blank"
                    class="text-xs text-blue-600 hover:text-blue-800 underline"
                    download
                  >
                    Скачать
                  </a>
                </div>
              </li>
            </ul>
          </section>

          <section class="bg-white rounded-lg shadow-sm p-6">
            <DocumentRequestHistory
              :application-id="applicationId"
              :refresh-key="documentHistoryRefreshKey"
              :leasing-company-id="leasingCompanyId"
            />
          </section>
        </div>

        <!-- Tab: Финотчётность -->
        <div v-show="activeTab === 'financial'">
          <CheckoutCompanyData
            v-if="application?.company_id"
            :company-id="(application.company_id as string)"
          />
          <p v-else class="text-sm text-gray-500">
            У заявки не указана компания.
          </p>
        </div>

        <!-- Tab: КП -->
        <div v-show="activeTab === 'proposal'" class="space-y-6">
          <!-- 4. КП — radio switch + одна активная форма -->
          <section class="bg-white rounded-lg shadow-sm p-3">
            <div role="radiogroup" aria-label="Тип КП" class="flex gap-2 flex-wrap">
              <button
                type="button"
                role="radio"
                :aria-checked="activeKind === 'preliminary'"
                class="px-4 py-2 rounded-md text-sm font-medium border transition-colors"
                :class="activeKind === 'preliminary'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'"
                @click="activeKind = 'preliminary'"
              >
                Предварительное КП
              </button>
              <button
                type="button"
                role="radio"
                :aria-checked="activeKind === 'final'"
                class="px-4 py-2 rounded-md text-sm font-medium border transition-colors"
                :class="activeKind === 'final'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'"
                @click="activeKind = 'final'"
              >
                Итоговое КП
              </button>
            </div>
          </section>

          <LeasingProposalForm
            v-show="activeKind === 'preliminary'"
            :application-id="applicationId"
            kind="preliminary"
            :total-amount="totalAmount"
            :initial-proposal="proposalByKind.preliminary"
            :pdf="proposalByKind.preliminary"
            :pdf-url="api.proposalPdfUrl(applicationId, 'preliminary')"
            :disabled="preliminarySubmitted || !canReview"
            :disabled-reason="preliminaryDisabledReason"
            :submit-disabled-reason="submitDisabledReason"
            @submitted="onProposalSubmitted"
            @upload-pdf="(file, params) => uploadPdf('preliminary', file, params)"
            @remove-pdf="() => removePdf('preliminary')"
            @error="onError"
          />

          <LeasingProposalForm
            v-show="activeKind !== 'preliminary'"
            :application-id="applicationId"
            kind="final"
            :total-amount="totalAmount"
            :initial-proposal="proposalByKind.final"
            :pdf="proposalByKind.final"
            :pdf-url="api.proposalPdfUrl(applicationId, 'final')"
            :disabled="finalSubmitted || !canReview"
            :disabled-reason="finalDisabledReason"
            :submit-disabled-reason="submitDisabledReason"
            @submitted="onProposalSubmitted"
            @upload-pdf="(file, params) => uploadPdf('final', file, params)"
            @remove-pdf="() => removePdf('final')"
            @error="onError"
          />
        </div>

        <!-- Tab: Действия -->
        <div v-show="activeTab === 'actions'" class="space-y-6">
          <!-- 6. Reject / global actions -->
          <section
            v-if="link.status !== 'deal' && (canConfirmDeal || confirmDealDisabledReason || canRequestDocuments || (!finalSubmitted && link.status !== 'rejected'))"
            class="bg-white rounded-lg shadow-sm p-6"
          >
            <h2 class="text-lg font-semibold text-gray-900 mb-3">
              Действия
            </h2>
            <div class="flex flex-wrap gap-3 items-start">
              <div v-if="canConfirmDeal" class="w-full rounded border border-emerald-200 bg-emerald-50 p-4">
                <p class="text-sm text-emerald-900 mb-3">
                  Подтвердите сделку после выбора вашей лизинговой компании клиентом. Действие необратимо.
                </p>
                <button
                  type="button"
                  class="btn-primary bg-emerald-600 hover:bg-emerald-700"
                  :disabled="confirmingDeal"
                  @click="showConfirmDealModal = true"
                >
                  Подтвердить сделку
                </button>
              </div>
              <p v-else-if="confirmDealDisabledReason" class="w-full text-sm text-gray-600">
                {{ confirmDealDisabledReason }}
              </p>
              <button
                v-if="!finalSubmitted && link.status !== 'rejected'"
                type="button"
                class="btn-primary bg-red-600 hover:bg-red-700"
                :disabled="working"
                @click="openRejectModal"
              >
                Отказать
              </button>
            </div>
          </section>

          <section v-if="link.status === 'deal'" class="bg-emerald-50 border border-emerald-200 rounded-lg p-6">
            <h2 class="text-lg font-semibold text-emerald-900">Сделка подтверждена</h2>
            <p class="mt-2 text-sm text-emerald-800">
              Сделка подтверждена лизинговой компанией.
            </p>
          </section>

          <!-- 7. Post-submit summary -->
          <section v-if="finalSubmitted && link.status !== 'deal'" class="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <h2 class="text-lg font-semibold text-blue-900 mb-2">
              Ответ отправлен клиенту
            </h2>
            <p class="text-sm text-blue-800">
              Решение: <strong>{{ actualStatusLabel }}</strong>
            </p>
            <p v-if="link.decision_comment" class="text-sm text-blue-800 mt-2">
              Комментарий: {{ link.decision_comment }}
            </p>

            <div v-if="canIssue" class="mt-4 p-3 bg-white rounded border border-green-200">
              <p class="text-sm text-gray-700 mb-3">
                Клиент принял итоговое КП. Если сделка фактически выполнена — отметьте «Выдано».
              </p>
              <button
                class="btn-primary bg-green-600 hover:bg-green-700"
                :disabled="issuing"
                @click="markIssued"
              >
                <span v-if="issuing">Сохраняем…</span>
                <span v-else>Выдано</span>
              </button>
            </div>
            <div v-else-if="link.status === 'issued'" class="mt-4 p-3 bg-green-50 rounded text-sm text-green-800">
              Заявка выдана клиенту.
            </div>
          </section>
        </div>
      </div>

    <DocumentRequestModal
      :show="showDocsModal"
      :application-id="applicationId"
      @close="showDocsModal = false"
      @success="onDocumentsRequested"
    />

    <Modal
      :show="showConfirmDealModal"
      title="Подтвердить сделку"
      :closable="!confirmingDeal"
      :close-on-overlay="!confirmingDeal"
      :show-footer="true"
      :show-confirm-button="true"
      :show-cancel-button="true"
      cancel-text="Отмена"
      :confirm-text="confirmingDeal ? 'Подтверждаем…' : 'Подтвердить сделку'"
      :confirm-disabled="confirmingDeal"
      @close="showConfirmDealModal = false"
      @confirm="confirmDeal"
    >
      <p class="text-sm text-gray-700">
        После подтверждения сделка будет оформлена. Это действие необратимо.
      </p>
    </Modal>

    <Modal
      :show="Boolean(documentToApprove)"
      title="Принять документ"
      :closable="!approvingDocument"
      :close-on-overlay="!approvingDocument"
      :show-footer="true"
      :show-confirm-button="true"
      :show-cancel-button="true"
      cancel-text="Отмена"
      :confirm-text="approvingDocument ? 'Принимаем…' : 'Принять'"
      :confirm-disabled="approvingDocument"
      @close="closeApproveDocumentModal"
      @confirm="approveAttachedDocument"
    >
      <p class="text-sm text-gray-700">
        Подтвердите принятие документа „{{ documentToApprove?.display_name }}“. После подтверждения его статус для вашей лизинговой компании изменится на „Принят“.
      </p>
    </Modal>

    <!-- Reject modal -->
    <div
      v-if="showRejectModal"
      class="fixed inset-0 bg-gray-900/50 flex items-center justify-center z-50 p-4"
      @click.self="showRejectModal = false"
    >
      <div class="bg-white rounded-lg shadow-xl max-w-lg w-full p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-3">
          Отказать клиенту
        </h3>
        <p class="text-xs text-gray-500 mb-2">
          Комментарий отправится клиенту вместе с отказом.
        </p>
        <textarea
          v-model="rejectComment"
          rows="3"
          placeholder="Причина отказа (обязательно)"
          class="w-full mb-4 px-3 py-2 border border-gray-300 rounded-md text-sm"
        />
        <div class="flex justify-end gap-2">
          <button class="btn-secondary text-sm" @click="showRejectModal = false">
            Отмена
          </button>
          <button
            class="btn-primary text-sm bg-red-600 hover:bg-red-700"
            :disabled="working || !rejectComment.trim()"
            @click="submitReject"
          >
            Отправить отказ
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useQuestionnaireNavigation } from '~/features/questionnaire'
import Modal from '~/components/ui/Modal.vue'
import CheckoutCompanyData from '~/features/checkout/components/CheckoutCompanyData.vue'
import DocumentRequestHistory from '~/features/documents/components/DocumentRequestHistory.vue'
import { createDocumentsApi } from '~/features/documents/api/documentsApi'
import DocumentRequestModal from '~/features/documents/components/DocumentRequestModal.vue'
import LeasingProposalForm from '~/features/leasing/components/LeasingProposalForm.vue'
import VehicleRegionsDisplay from '~/features/applications/components/VehicleRegionsDisplay.vue'
import { formatLeasingPurpose } from '~/features/applications/utils/applicationVehicleDisplay'
import CommerceApplicationItemComment from '~/features/commerce/components/CommerceApplicationItemComment.vue'
import CommerceApplicationItemsSummary from '~/features/commerce/components/CommerceApplicationItemsSummary.vue'
import type { CommerceApplicationItem } from '~/features/commerce/types'
import { getMonthWord } from '~/utils'
import { formatSourcedApplicationNumber } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'
import type {
  LcResponseLink,
  LcResponseState,
  LeasingProposal,
  ProposalParams,
} from '~/features/leasing/api/leasingApi'
import { createLeasingApi } from '~/features/leasing/api/leasingApi'
import { isUuid, type UUID } from '~/types/ids'
import { useAuthStore } from '~/features/auth/store/auth'
import { ConditionRequests, createMonetizationApi } from '~/features/monetization'

definePageMeta({ layout: 'workspace', middleware: ['auth', 'require-workspace'], key: route => route.fullPath })

const route = useRoute()
const { questionnaireLocation } = useQuestionnaireNavigation()
const config = useRuntimeConfig()
const authStore = useAuthStore()
const monetizationApi = createMonetizationApi(config, () => route.query.notification_company_id, () => route.query.leasing_company_id)
const leasingCompanyId = computed(() => isUuid(route.query.leasing_company_id) ? route.query.leasing_company_id : undefined)
const api = createLeasingApi(config, () => route.query.leasing_company_id)
const documentsApi = createDocumentsApi(config, () => leasingCompanyId.value)
const toast = useToast()

const applicationId = computed<UUID>(() => String(route.params.id))

const state = ref<LcResponseState | null>(null)
const loading = ref(true)
const error = ref('')
const working = ref(false)
const takingInWork = ref(false)
const takeInWorkError = ref('')
const takeInWorkMessage = ref('')

const showDocsModal = ref(false)
const documentHistoryRefreshKey = ref(0)

const showRejectModal = ref(false)
const rejectComment = ref('')

const issuing = ref(false)
const showConfirmDealModal = ref(false)
const confirmingDeal = ref(false)

const activeKind = ref<'preliminary' | 'final'>('preliminary')

const activeTab = ref<'overview' | 'financial' | 'proposal' | 'actions'>('overview')

const TABS = [
  { key: 'overview', label: 'Заявка' },
  { key: 'financial', label: 'Финотчётность' },
  { key: 'proposal', label: 'КП' },
  { key: 'actions', label: 'Действия' },
] as const

const link = computed<LcResponseLink>(() => state.value?.link ?? ({} as LcResponseLink))
const canReview = computed(() => state.value?.can_review === true)
const canTakeInWork = computed(() => canReview.value && link.value.status === 'submitted')
const submitDisabledReason = computed(() => {
  if (!canReview.value) return 'Нет прав на изменение заявки этой ЛК.'
  if (link.value.status === 'submitted') return 'Сначала возьмите заявку в работу'
  if (takingInWork.value || working.value) return 'Дождитесь завершения текущего действия.'
  return ''
})
const application = computed<NonNullable<LcResponseState['application']>>(
  () => state.value?.application ?? {},
)

const proposals = computed<LeasingProposal[]>(() => state.value?.proposals ?? [])
const proposalByKind = computed(() => ({
  preliminary: proposals.value.find((p) => p.kind === 'preliminary') ?? null,
  final: proposals.value.find((p) => p.kind === 'final') ?? null,
}))

const finalSubmitted = computed(() => {
  const s = link.value.status
  return Boolean(link.value.submitted_at) || s === 'approved' || s === 'rejected' || s === 'issued' || s === 'closed' || s === 'deal'
})
const preliminarySubmitted = computed(() => {
  // Preliminary form is locked once the LC has either moved past prescoring or
  // submitted the final response.
  const s = link.value.status
  return finalSubmitted.value || s === 'prescoring' || s === 'approved_scoring' || s === 'approved_scoring_another_cond'
})

// Once the preliminary КП is sent, default the active tab
// to "final" so the LC lands on the form they can still edit.
watch(preliminarySubmitted, (locked) => {
  if (locked && activeKind.value === 'preliminary') {
    activeKind.value = 'final'
  }
})

const preliminaryDisabledReason = computed(() => {
  if (!canReview.value) return 'Заявка доступна только для просмотра.'
  if (!preliminarySubmitted.value) return ''
  if (['prescoring', 'approved_scoring', 'approved_scoring_another_cond'].includes(link.value.status)) return 'Предварительный расчёт уже отправлен клиенту.'
  return 'Ответ отправлен клиенту.'
})
const finalDisabledReason = computed(() =>
  !canReview.value ? 'Заявка доступна только для просмотра.' : finalSubmitted.value ? 'Ответ отправлен клиенту.' : '',
)

const vehicles = computed<Record<string, unknown>[]>(() => {
  const raw = (application.value as Record<string, unknown>)?.vehicles
  return Array.isArray(raw) ? (raw as Record<string, unknown>[]) : []
})
const historicalApplicationItemStatuses = new Set(['removed', 'replaced', 'rejected'])
const hasNormalizedApplicationItems = computed(() => Array.isArray(application.value.items))
const applicationItems = computed<CommerceApplicationItem[]>(() => {
  const raw = application.value.items
  return Array.isArray(raw) ? raw as CommerceApplicationItem[] : []
})
const activeApplicationItems = computed(() => applicationItems.value.filter((item) => !item.status || !historicalApplicationItemStatuses.has(item.status)))
const applicationItemsCount = computed(() => typeof application.value.items_count === 'number' ? application.value.items_count : null)
const applicationItemsPrice = computed(() => typeof application.value.total_items_price === 'string' ? application.value.total_items_price : null)
const totalAmount = computed<number>(() => {
  const v = application.value.total_amount
  return typeof v === 'number' ? v : Number(v) || 0
})
const leaseTermLabel = computed(() => {
  const v = application.value.lease_term_months
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n) || n <= 0) return '—'
  return `${n} ${getMonthWord(n)}`
})

const headerNumber = computed(() => {
  const dn = formatSourcedApplicationNumber(application.value)
  return `Заявка ${dn}`
})
const companyName = computed(() => {
  const c = (application.value.company as Record<string, unknown> | undefined)
  return (c?.name as string) || (application.value.company_name as string) || ''
})
const companyInn = computed(() => {
  const c = (application.value.company as Record<string, unknown> | undefined)
  return (c?.inn as string) || (application.value.company_inn as string) || ''
})
const leasingCompanyName = computed(
  () => state.value?.application?.leasing_company_name as string ?? '',
)

const accountingPdfUrl = computed(() => api.accountingPdfUrl(applicationId.value))
const { formatPrice } = useFormatPrice()
const { formatDateTime } = useFormatDate()

const submittedLabel = computed(() => {
  if (!link.value.submitted_at) return 'Черновик ответа — клиент не видит изменения до отправки.'
  return `Отправлено ${formatDateTime(link.value.submitted_at)}`
})

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  submitted: { label: 'Подана', cls: 'bg-blue-100 text-blue-800' },
  under_review: { label: 'На рассмотрении', cls: 'bg-yellow-100 text-yellow-800' },
  documents_required: { label: 'Запрошены документы', cls: 'bg-amber-100 text-amber-800' },
  under_review_with_docs: { label: 'На рассмотрении с документами', cls: 'bg-blue-100 text-blue-800' },
  approved_scoring: { label: 'Скоринг одобрен', cls: 'bg-sky-100 text-sky-800' },
  approved_scoring_another_cond: { label: 'Скоринг одобрен с другими условиями', cls: 'bg-sky-100 text-sky-800' },
  approved_final: { label: 'Финально одобрено', cls: 'bg-green-100 text-green-800' },
  approved_final_another_cond: { label: 'Финально одобрено с другими условиями', cls: 'bg-green-100 text-green-800' },
  document_request: { label: 'Запрошены документы', cls: 'bg-amber-100 text-amber-800' },
  prescoring: { label: 'Предварительно одобрено', cls: 'bg-sky-100 text-sky-800' },
  approved: { label: 'Одобрено', cls: 'bg-green-100 text-green-800' },
  rejected: { label: 'Отказано', cls: 'bg-red-100 text-red-800' },
  closed: { label: 'Клиент отказался', cls: 'bg-gray-200 text-gray-800' },
  issued: { label: 'Выдано', cls: 'bg-emerald-100 text-emerald-800' },
  deal: { label: 'Сделка подтверждена', cls: 'bg-emerald-100 text-emerald-800' },
  selected_lc: { label: 'Выбрана ЛК', cls: 'bg-purple-100 text-purple-800' },
}
const statusLabel = computed(
  () => {
    const displayStatus = link.value.display_status ?? link.value.status
    return STATUS_LABELS[displayStatus ?? '']?.label || displayStatus || '—'
  },
)
const actualStatusLabel = computed(
  () => STATUS_LABELS[link.value.status ?? '']?.label || link.value.status || '—',
)
const statusBadgeClass = computed(
  () => STATUS_LABELS[link.value.display_status ?? link.value.status ?? '']?.cls || 'bg-gray-100 text-gray-700',
)

const DOCUMENT_REQUEST_ALLOWED_STATUSES = new Set([
  'under_review',
  'documents_required',
  'under_review_with_docs',
  'approved_scoring',
  'approved_scoring_another_cond',
])
const canRequestDocuments = computed(() =>
  canReview.value && DOCUMENT_REQUEST_ALLOWED_STATUSES.has(link.value.status),
)

const canIssue = computed(() => {
  if (link.value.status !== 'approved') return false
  return proposals.value.some(
    (p) =>
      ((p as unknown as Record<string, unknown>).kind as string) === 'final'
      && ((p as unknown as Record<string, unknown>).client_decision_action as string) === 'accepted',
  )
})

const canConfirmDeal = computed(() => state.value?.can_confirm_deal === true)
const confirmDealDisabledReason = computed(() => state.value?.confirm_deal_disabled_reason ?? '')

const formatMoney = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return String(value)
  return formatPrice(n)
}
const vehicleDetailId = (vehicle: Record<string, unknown>): UUID | null => {
  const id = vehicle.vehicle_id
  return isUuid(id) ? id : null
}
const vehicleTitle = (v: Record<string, unknown>): string => {
  const parts = [v.mark_name, v.model_name, v.modification_name, v.year].filter(Boolean)
  if (parts.length) return parts.join(' ')
  return typeof v.id === 'string' ? `Авто #${v.id}` : 'Автомобиль'
}

const fetchState = async () => {
  // Refreshing metadata must not unmount a form with an unsaved quote/PDF.
  if (!state.value) loading.value = true
  error.value = ''
  try {
    state.value = await api.getResponseState(applicationId.value)
  } catch (err: unknown) {
    const message = (err as { data?: { detail?: string } }).data?.detail || 'Не удалось загрузить ответ'
    if (state.value) toast.error(message)
    else error.value = message
  } finally {
    loading.value = false
  }
  // Documents block — independent of the response state, so failures don't
  // break the rest of the LC cabinet.
  fetchAttachedDocuments()
}

const takeInWork = async () => {
  if (!canTakeInWork.value || takingInWork.value || working.value) return
  takingInWork.value = true
  takeInWorkError.value = ''
  takeInWorkMessage.value = ''
  try {
    const result = await api.takeInWork(applicationId.value)
    // Use the returned current status, including retries handled by another
    // employee. Do not invent under_review or discard the local draft.
    if (state.value) state.value.link = { ...state.value.link, status: result.lca_status }
    takeInWorkMessage.value = result.message
    try {
      state.value = await api.getResponseState(applicationId.value)
    } catch {
      takeInWorkError.value = 'Статус получен, но не удалось обновить карточку. Введённый расчёт сохранён на экране.'
    }
  } catch (err: unknown) {
    takeInWorkError.value = (err as { data?: { detail?: string } }).data?.detail || 'Не удалось взять заявку в работу. Повторите попытку.'
  } finally {
    takingInWork.value = false
  }
}

interface AttachedDocument {
  id: UUID
  document_type: string
  display_name: string
  period_label: string | null
  file_name: string | null
  file_size: number | null
  uploaded_at: string | null
  status: string | null
  leasing_company_status: string | null
  download_url: string | null
}

const attachedDocuments = ref<AttachedDocument[]>([])
const attachedDocsLoading = ref(false)
const attachedDocsError = ref('')
const documentToApprove = ref<AttachedDocument | null>(null)
const approvingDocument = ref(false)

const fetchAttachedDocuments = async () => {
  attachedDocsLoading.value = true
  attachedDocsError.value = ''
  try {
    const resp = await api.getApplicationDocuments(applicationId.value) as unknown as { documents: AttachedDocument[] }
    attachedDocuments.value = resp.documents || []
  } catch (err: unknown) {
    attachedDocsError.value =
      (err as { data?: { detail?: string } }).data?.detail
      || 'Не удалось загрузить документы заявки.'
  } finally {
    attachedDocsLoading.value = false
  }
}

const formatDocDate = (raw: string | null): string => {
  if (!raw) return ''
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return ''
  return formatDateTime(d)
}

const DOC_STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  approved: { label: 'Принят', cls: 'bg-green-100 text-green-800' },
  rejected: { label: 'Отклонён', cls: 'bg-red-100 text-red-800' },
  pending: { label: 'На проверке', cls: 'bg-yellow-100 text-yellow-800' },
  revision_requested: { label: 'Запрошена правка', cls: 'bg-amber-100 text-amber-800' },
}
const docStatusLabel = (status: string | null): string => {
  if (!status) return ''
  return DOC_STATUS_LABELS[status]?.label || status
}
const docStatusClass = (status: string | null): string => {
  if (!status) return ''
  return DOC_STATUS_LABELS[status]?.cls || 'bg-gray-100 text-gray-700'
}

const openApproveDocument = (document: AttachedDocument) => {
  if (document.leasing_company_status !== 'pending' || approvingDocument.value) return
  documentToApprove.value = document
}
const closeApproveDocumentModal = () => {
  if (!approvingDocument.value) documentToApprove.value = null
}
const approveAttachedDocument = async () => {
  const document = documentToApprove.value
  if (!document || approvingDocument.value) return
  approvingDocument.value = true
  try {
    await api.approveApplicationDocument(applicationId.value, document.id)
    documentToApprove.value = null
    toast.success('Документ принят')
  } catch (err: unknown) {
    const detail = (err as { data?: { detail?: string } }).data?.detail
    toast.error(detail || 'Не удалось принять документ. Список документов обновлён.')
  } finally {
    await fetchAttachedDocuments()
    approvingDocument.value = false
  }
}

const onError = (msg: string) => toast.error(msg)
const onProposalSubmitted = async () => {
  toast.success('Расчёт отправлен клиенту')
  await fetchState()
}

const updateProposalPdfMeta = (
  kind: 'preliminary' | 'final',
  pdf: { file_name: string; file_size: number; uploaded_at: string } | null,
) => {
  const proposal = proposals.value.find(item => item.kind === kind)
  if (!proposal) return
  proposal.pdf_file_name = pdf?.file_name ?? null
  proposal.pdf_size = pdf?.file_size ?? null
  proposal.pdf_uploaded_at = pdf?.uploaded_at ?? null
}

const uploadPdf = async (kind: 'preliminary' | 'final', file: File, params: ProposalParams) => {
  working.value = true
  try {
    const savedProposal = await api.upsertProposal(applicationId.value, kind, params)
    if (state.value) {
      state.value.proposals = [
        ...state.value.proposals.filter(item => item.kind !== kind),
        savedProposal,
      ]
    }
    const uploadedPdf = await api.uploadProposalPdf(applicationId.value, kind, file)
    updateProposalPdfMeta(kind, uploadedPdf)
  } catch (err: unknown) {
    onError((err as { data?: { detail?: string }; message?: string })?.data?.detail || 'Не удалось загрузить PDF')
  } finally {
    working.value = false
  }
}

const removePdf = async (kind: 'preliminary' | 'final') => {
  working.value = true
  try {
    await api.removeProposalPdf(applicationId.value, kind)
    updateProposalPdfMeta(kind, null)
  } catch (err: unknown) {
    onError((err as { data?: { detail?: string }; message?: string })?.data?.detail || 'Не удалось удалить PDF')
  } finally {
    working.value = false
  }
}

const openDocsModal = () => {
  if (!canRequestDocuments.value || working.value || takingInWork.value) return
  showDocsModal.value = true
}
const onDocumentsRequested = async () => {
  showDocsModal.value = false
  documentHistoryRefreshKey.value += 1
  toast.success('Запрос документов отправлен')
  await fetchState()
}

const openRejectModal = () => {
  rejectComment.value = link.value.decision_comment ?? ''
  showRejectModal.value = true
}
const submitReject = async () => {
  const comment = rejectComment.value.trim()
  if (!comment) {
    toast.error('Укажите причину отказа')
    return
  }
  if (!confirm('Отправить отказ клиенту? После отправки изменения недоступны.')) return
  working.value = true
  try {
    await api.submitDecision(applicationId.value, 'reject', comment, 'final')
    showRejectModal.value = false
    await fetchState()
  } catch (err: unknown) {
    toast.error((err as { data?: { detail?: string } }).data?.detail || 'Не удалось отправить отказ')
  } finally {
    working.value = false
  }
}

const markIssued = async () => {
  if (!window.confirm('Отметить заявку как Выдано? Действие необратимо.')) return
  issuing.value = true
  try {
    await api.issueApplication(applicationId.value)
    await fetchState()
  } catch (err: unknown) {
    const apiErr = err as { data?: { detail?: string }; message?: string }
    alert('Не удалось отметить выдачу: ' + (apiErr.data?.detail || apiErr.message))
  } finally {
    issuing.value = false
  }
}

const confirmDeal = async () => {
  confirmingDeal.value = true
  try {
    const response = await api.confirmDeal(applicationId.value)
    if (state.value) {
      state.value = {
        ...state.value,
        link: { ...state.value.link, status: response.status },
        can_confirm_deal: false,
        confirm_deal_disabled_reason: null,
      }
    }
    showConfirmDealModal.value = false
    await fetchState()
    toast.success('Сделка подтверждена')
  } catch (err: unknown) {
    toast.error((err as { data?: { detail?: string } }).data?.detail || 'Не удалось подтвердить сделку')
  } finally {
    confirmingDeal.value = false
  }
}

onMounted(fetchState)
</script>
