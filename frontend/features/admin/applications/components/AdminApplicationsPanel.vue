<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-semibold text-gray-900">
        Распределение заявок
      </h2>

      <div class="flex gap-2">
        <button @click="exportCsv" class="btn-secondary text-sm">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
          </svg>
          Выгрузить CSV
        </button>
        <label class="btn-secondary text-sm cursor-pointer">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12"></path>
          </svg>
          Загрузить CSV
          <input type="file" accept=".csv" class="hidden" @change="importCsv">
        </label>
      </div>


    </div>

    <ImportProgress
      :uploading="csvImport.uploading.value"
      :finished="csvImport.finished.value"
      :status="csvImport.status.value"
      :filename="csvImport.filename.value"
      :progress="csvImport.progress.value"
      :rows-total="csvImport.rowsTotal.value"
      :rows-done="csvImport.rowsDone.value"
      :errors-count="csvImport.errorsCount.value"
      :error-sample="csvImport.errorSample.value"
      :error-message="csvImport.errorMessage.value"
    />

    <!-- Quick filters -->
    <div class="flex flex-wrap gap-2 mb-4">
      <button 
        @click="setQuickFilter('')"
        :class="filters.status === '' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'"
        class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors"
      >
        Все заявки
      </button>
      <button
        @click="setQuickFilter('active')"
        :disabled="filters.kind === 'fast_deal'"
        :class="filters.status === 'active' ? 'bg-blue-600 text-white' : 'bg-blue-100 text-blue-800 hover:bg-blue-200'"
        class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      >
        Активные
      </button>
      <button 
        @click="setQuickFilter('rejected')"
        :disabled="filters.kind === 'fast_deal'"
        :class="filters.status === 'rejected' ? 'bg-red-600 text-white' : 'bg-red-100 text-red-800 hover:bg-red-200'"
        class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      >
        Отклонены
      </button>
      <button 
        @click="setQuickFilter('issued')"
        :disabled="filters.kind === 'fast_deal'"
        :class="filters.status === 'issued' ? 'bg-green-600 text-white' : 'bg-green-100 text-green-800 hover:bg-green-200'"
        class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
      >
        Выданы
      </button>
    </div>

    <!-- Filters -->
    <div class="card mb-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Статус</label>
          <select v-model="filters.status" @change="fetchApplications" :disabled="filters.kind === 'fast_deal'" class="select-field">
            <option value="">Все статусы</option>
            <option value="active">Активная</option>
            <option value="rejected">Отклонена</option>
            <option value="issued">Выдана</option>
          </select>
          <p v-if="statusFilterHint" class="mt-1 text-xs text-gray-500" data-testid="application-status-hint">{{ statusFilterHint }}</p>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Поиск</label>
          <input 
            v-model="filters.search" 
            @input="debouncedSearch"
            type="text" 
            placeholder="Номер заявки, имя, email, ИНН..."
            class="input-field"
          >
        </div>
        <div class="flex items-end">
          <button @click="fetchApplications" class="btn-secondary">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            Обновить
          </button>
        </div>
      </div>
      <ApplicationKindFilter v-model="filters.kind" class="mt-4 max-w-xs" @update:model-value="applyFilters" />
      <ApplicationSourceFilter v-model="filters.sources" class="mt-4" @update:model-value="applyFilters" />
    </div>

    <div v-if="linkedApplicationId" class="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4" aria-live="polite">
      <div class="flex items-center justify-between gap-4">
        <p class="text-sm text-blue-900">{{ linkedDetailState?.loading ? 'Загружаем заявку из уведомления…' : 'Заявка из уведомления показана первой, независимо от фильтров списка.' }}</p>
        <button type="button" class="btn-secondary text-sm" @click="closeLinkedApplication">Закрыть переход</button>
      </div>
      <p v-if="linkedDetailState?.error" class="mt-2 text-sm text-red-700">{{ linkedDetailState.error }}</p>
      <button v-if="linkedDetailState?.error" type="button" class="mt-2 btn-secondary text-sm" @click="fetchApplicationDetails(linkedApplicationId)">Повторить загрузку</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      <p class="mt-2 text-gray-600">Загружаем заявки...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-8">
      <p class="text-red-600 mb-4">{{ error }}</p>
      <button @click="fetchApplications" class="btn-primary">Попробовать снова</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="visibleApplications.length === 0" class="text-center py-12">
      <svg class="mx-auto h-12 w-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z">
        </path>
      </svg>
      <h3 class="text-lg font-medium text-gray-900 mb-2">Заявок не найдено</h3>
      <p class="text-gray-600">Попробуйте изменить фильтры поиска</p>
    </div>

    <!-- Applications list -->
    <div v-else class="space-y-4">
      <template v-for="app in visibleApplications" :key="app.id">
      <FastDealApplicationRow v-if="isFastDealRow(app)" :deal="app" />
      <div
        v-else
        class="card hover:shadow-lg transition-shadow"
        :class="app.status === 'active' ? 'border-l-4 border-l-blue-500' : ''"
      >
        <div class="flex items-start justify-between mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">
              Заявка {{ formatApplicationNumber(app) }}
            </h3>
            <ApplicationSourceBadge :source="app.source_type" class="mt-1" />
            <p class="text-sm text-gray-600">
              {{ app.name }} | {{ app.phone || 'Телефон не указан' }}
              <span v-if="app.company_name"> | {{ app.company_name }}</span>
              <span v-if="app.company_inn"> (ИНН: {{ app.company_inn }})</span>
            </p>
            <p v-if="app.created_at" class="text-xs text-gray-400 mt-0.5">
              Создана: {{ formatDateTime(app.created_at) }}
            </p>
          </div>
          <span 
            class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
            :class="getStatusClasses(app.status)"
          >
            {{ getStatusText(app.status) }}
          </span>
        </div>

        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div>
            <div class="text-sm text-gray-500">Стоимость ТС</div>
            <div class="font-medium">{{ formatPrice(app.total_items_price || app.total_vehicles_price || app.total_amount || 0) }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">Кол-во ТС</div>
            <div class="font-medium">{{ app.items_count || app.vehicles_count || 0 }}</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">Аванс</div>
            <div class="font-medium">{{ app.down_payment_percent || 0 }}%</div>
          </div>
          <div>
            <div class="text-sm text-gray-500">Срок</div>
            <div class="font-medium">{{ app.lease_term_months || 0 }} мес.</div>
          </div>
        </div>

        <!-- Leasing companies -->
        <div v-if="app.selected_companies_info && app.selected_companies_info.length > 0" class="mb-4">
          <div class="text-sm text-gray-500 mb-2">Лизинговые компании:</div>
          <div class="flex flex-wrap gap-2">
            <span 
              v-for="company in app.selected_companies_info" 
              :key="company.company_id"
              class="inline-flex px-2 py-1 text-xs bg-green-100 text-green-800 rounded-full font-medium"
            >
              {{ company.company_name }}
            </span>
          </div>
        </div>
        <div v-else class="mb-4">
          <span class="inline-flex px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded-full font-medium">
            Лизинговые компании не назначены
          </span>
        </div>

        <!-- Actions -->
        <div class="flex flex-wrap gap-2 pt-4 border-t border-gray-200">
          <NuxtLink :to="questionnaireLocation(app.id, 'applications')" class="btn-secondary text-sm">
            Открыть анкету
          </NuxtLink>
          <button
            type="button"
            @click="toggleDetails(app)"
            :disabled="detailStates[app.id]?.loading"
            class="btn-secondary text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg
              class="w-4 h-4 mr-1 transition-transform"
              :class="detailStates[app.id]?.expanded ? 'rotate-180' : ''"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
            {{ detailStates[app.id]?.expanded ? 'Свернуть' : 'Подробнее' }}
          </button>
          <button
            type="button"
            @click="openLeasingModal(app)"
            :class="hasLeasingCompanies(app) ? 'btn-secondary' : 'btn-primary'"
            class="text-sm disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canAssignLeasingCompanies(app)"
            :aria-describedby="!canAssignLeasingCompanies(app) ? `leasing-assignment-reason-${app.id}` : undefined"
          >
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
            </svg>
            Выбрать лизинговую компанию
          </button>
          <p
            v-if="!canAssignLeasingCompanies(app)"
            :id="`leasing-assignment-reason-${app.id}`"
            class="basis-full text-sm font-medium text-amber-800"
          >
            Сначала дилер должен выставить цену для всех позиций
          </p>
          <button 
            @click="openVehiclesModal(app)" 
            class="btn-secondary text-sm"
          >
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"></path>
            </svg>
            Управление ТС
          </button>
        </div>

        <div
          v-if="detailStates[app.id]?.expanded"
          class="mt-4 border-t border-gray-200 pt-4"
        >
          <div v-if="detailStates[app.id]?.loading" class="flex items-center gap-2 rounded-md bg-gray-50 px-3 py-3 text-sm text-gray-600">
            <span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-b-transparent"></span>
            Загружаем детали заявки...
          </div>

          <div v-else-if="detailStates[app.id]?.error" class="rounded-md border border-red-200 bg-red-50 px-3 py-3">
            <p class="text-sm text-red-700">{{ detailStates[app.id]?.error }}</p>
            <button
              type="button"
              @click="fetchApplicationDetails(app.id)"
              class="mt-2 text-sm font-medium text-red-700 underline underline-offset-2 hover:text-red-800"
            >
              Повторить
            </button>
          </div>

          <template v-else-if="detailStates[app.id]?.data">
            <div class="rounded-md border border-gray-200 bg-gray-50 p-4">
              <h4 class="mb-3 text-sm font-semibold text-gray-900">Сводка заявки</h4>
              <ApplicationSourceBadge :source="detailStates[app.id]?.data?.application.source_type" class="mb-3" />
              <div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <div class="text-xs text-gray-500">Номер</div>
                  <div class="font-medium text-gray-900">{{ formatApplicationNumber(detailStates[app.id]?.data?.application) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Клиент</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.name) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Email</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.email) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Телефон</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.phone) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Компания</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.company_name) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">ИНН</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.company_inn) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Статус</div>
                  <div class="font-medium text-gray-900">{{ getStatusText(detailStates[app.id]?.data?.application.status || '') }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Этап</div>
                  <div class="font-medium text-gray-900">{{ detailValue(detailStates[app.id]?.data?.application.current_stage) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Сумма</div>
                  <div class="font-medium text-gray-900">{{ formatNullablePrice(detailStates[app.id]?.data?.application.total_amount) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Стоимость ТС</div>
                  <div class="font-medium text-gray-900">{{ formatNullablePrice(detailStates[app.id]?.data?.application.total_items_price || detailStates[app.id]?.data?.application.total_vehicles_price) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Аванс</div>
                  <div class="font-medium text-gray-900">
                    {{ formatNullablePrice(detailStates[app.id]?.data?.application.down_payment) }}
                    <span class="text-gray-500">({{ formatNullablePercent(detailStates[app.id]?.data?.application.down_payment_percent) }})</span>
                  </div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Ежемесячный платёж</div>
                  <div class="font-medium text-gray-900">{{ formatNullablePrice(detailStates[app.id]?.data?.application.monthly_payment) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Срок</div>
                  <div class="font-medium text-gray-900">{{ formatNullableMonths(detailStates[app.id]?.data?.application.lease_term_months) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">ТС</div>
                  <div class="font-medium text-gray-900">{{ detailStates[app.id]?.data?.application.items_count || detailStates[app.id]?.data?.application.vehicles_count || 0 }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Создана</div>
                  <div class="font-medium text-gray-900">{{ formatNullableDate(detailStates[app.id]?.data?.application.created_at) }}</div>
                </div>
                <div>
                  <div class="text-xs text-gray-500">Обновлена</div>
                  <div class="font-medium text-gray-900">{{ formatNullableDate(detailStates[app.id]?.data?.application.updated_at) }}</div>
                </div>
              </div>
            </div>

            <CommerceApplicationItemsSummary
              v-if="detailStates[app.id]?.items.length"
              class="mt-4"
              :items="detailStates[app.id]?.items || []"
              :items-count="detailStates[app.id]?.itemsCount"
              :total-items-price="detailStates[app.id]?.totalItemsPrice"
            />

            <section class="mt-4 rounded-lg border border-gray-200 bg-white p-4" :aria-labelledby="`price-history-title-${app.id}`">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h4 :id="`price-history-title-${app.id}`" class="text-sm font-semibold text-gray-900">История изменения цен</h4>
                  <p class="mt-1 text-sm text-gray-500">Изменения стоимости позиций дилером · {{ detailStates[app.id]?.priceHistoryTotal ?? 0 }}</p>
                </div>
                <button
                  type="button"
                  class="btn-secondary text-sm disabled:cursor-wait disabled:opacity-50"
                  :disabled="detailStates[app.id]?.priceHistoryLoading"
                  @click="fetchPriceHistory(app.id)"
                >
                  Обновить
                </button>
              </div>
              <div v-if="detailStates[app.id]?.priceHistoryLoading" class="mt-4 rounded-md bg-gray-50 px-3 py-3 text-sm text-gray-600" aria-live="polite">
                Загружаем историю цен…
              </div>
              <div v-else-if="detailStates[app.id]?.priceHistoryError" class="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-3" role="alert">
                <p class="text-sm text-red-700">{{ detailStates[app.id]?.priceHistoryError }}</p>
                <button type="button" class="mt-2 text-sm font-semibold text-red-700 underline" @click="fetchPriceHistory(app.id)">Повторить</button>
              </div>
              <div v-else-if="!detailStates[app.id]?.priceHistory.length" class="mt-4 rounded-md bg-gray-50 px-3 py-3 text-sm text-gray-600">
                Цена позиций ещё не изменялась.
              </div>
              <div v-else class="mt-4 overflow-x-auto rounded-md border border-gray-200">
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                  <thead class="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th class="px-3 py-2 text-left font-medium">Позиция</th>
                      <th class="px-3 py-2 text-right font-medium">Было</th>
                      <th class="px-3 py-2 text-right font-medium">Стало</th>
                      <th class="px-3 py-2 text-left font-medium">Изменил</th>
                      <th class="px-3 py-2 text-left font-medium">Дата</th>
                      <th class="px-3 py-2 text-left font-medium">Источник</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-200 bg-white">
                    <tr v-for="change in detailStates[app.id]?.priceHistory" :key="change.id">
                      <td class="px-3 py-2 font-medium text-gray-900">{{ change.item_title || change.item_id }}</td>
                      <td class="px-3 py-2 text-right tabular-nums text-gray-700">{{ formatHistoryPrice(change.old_price) }}</td>
                      <td class="px-3 py-2 text-right font-semibold tabular-nums text-gray-950">{{ formatHistoryPrice(change.new_price) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ change.changed_by_name || change.changed_by }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullableDate(change.changed_at) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ priceHistorySourceLabel(change.source) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <div class="mt-4">
              <h4 class="mb-2 text-sm font-semibold text-gray-900">Заявки в лизинговые компании</h4>
              <div
                v-if="detailStates[app.id]?.data?.leasing_company_applications.length === 0"
                class="rounded-md border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-600"
              >
                Заявки в лизинговые компании не найдены.
              </div>
              <div v-else class="overflow-x-auto rounded-md border border-gray-200">
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                  <thead class="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th class="px-3 py-2 text-left font-medium">ЛК</th>
                      <th class="px-3 py-2 text-left font-medium">ИНН</th>
                      <th class="px-3 py-2 text-left font-medium">Статус</th>
                      <th class="px-3 py-2 text-left font-medium">Комментарий</th>
                      <th class="px-3 py-2 text-left font-medium">PDF</th>
                      <th class="px-3 py-2 text-left font-medium">Отправлена</th>
                      <th class="px-3 py-2 text-left font-medium">Обновлена</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-200 bg-white">
                    <tr
                      v-for="lca in detailStates[app.id]?.data?.leasing_company_applications"
                      :key="lca.id"
                    >
                      <td class="px-3 py-2 font-medium text-gray-900">{{ detailValue(lca.leasing_company?.name) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(lca.leasing_company?.inn) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(lca.status) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(lca.decision_comment || lca.review_notes) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(lca.response_pdf_file_name) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullableDate(lca.submitted_at) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullableDate(lca.updated_at) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div
              v-for="lca in detailStates[app.id]?.data?.leasing_company_applications"
              :key="`proposals-${lca.id}`"
              class="mt-4"
            >
              <h4 class="mb-2 text-sm font-semibold text-gray-900">
                Предложения: {{ detailValue(lca.leasing_company?.name, 'ЛК не указана') }}
              </h4>
              <div
                v-if="!lca.proposals || lca.proposals.length === 0"
                class="rounded-md border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-600"
              >
                Предложения по этой ЛК не найдены.
              </div>
              <div v-else class="overflow-x-auto rounded-md border border-gray-200">
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                  <thead class="bg-gray-50 text-xs uppercase text-gray-500">
                    <tr>
                      <th class="px-3 py-2 text-left font-medium">Тип</th>
                      <th class="px-3 py-2 text-left font-medium">Позиция</th>
                      <th class="px-3 py-2 text-left font-medium">Сумма</th>
                      <th class="px-3 py-2 text-left font-medium">Аванс</th>
                      <th class="px-3 py-2 text-left font-medium">Срок</th>
                      <th class="px-3 py-2 text-left font-medium">Платёж</th>
                      <th class="px-3 py-2 text-left font-medium">Ставка</th>
                      <th class="px-3 py-2 text-left font-medium">Решение клиента</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-200 bg-white">
                    <tr
                      v-for="proposal in lca.proposals"
                      :key="proposal.id"
                    >
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(proposal.kind) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(proposal.position) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullablePrice(proposal.total_amount) }}</td>
                      <td class="px-3 py-2 text-gray-700">
                        {{ formatNullablePrice(proposal.down_payment) }}
                        <span class="text-gray-500">({{ formatNullablePercent(proposal.down_payment_percent) }})</span>
                      </td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullableMonths(proposal.lease_term_months) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullablePrice(proposal.monthly_payment) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ formatNullablePercent(proposal.rate) }}</td>
                      <td class="px-3 py-2 text-gray-700">{{ detailValue(proposal.client_decision_action) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>

          <div v-else class="rounded-md border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-600">
            Детали заявки не загружены.
          </div>
        </div>
      </div>
      </template>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="flex justify-center mt-6 space-x-2">
        <button 
          @click="changePage(currentPage - 1)" 
          :disabled="currentPage === 1"
          class="btn-secondary text-sm disabled:opacity-50"
        >
          Назад
        </button>
        <span class="px-4 py-2 text-sm text-gray-600">
          Страница {{ currentPage }} из {{ totalPages }}
        </span>
        <button 
          @click="changePage(currentPage + 1)" 
          :disabled="currentPage === totalPages"
          class="btn-secondary text-sm disabled:opacity-50"
        >
          Вперед
        </button>
      </div>
    </div>

    <!-- Leasing Companies Modal -->
    <LeasingCompaniesModal
      v-if="showLeasingModal && selectedApplication"
      :application="selectedApplication"
      @close="showLeasingModal = false"
      @saved="onLeasingSaved"
    />

    <!-- Vehicles Management Modal -->
    <VehicleManagementModal
      v-if="showVehiclesModal && selectedApplication"
      :application="selectedApplication"
      @close="showVehiclesModal = false"
      @saved="onVehiclesSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { isUuid } from '~/types/ids'
import { useQuestionnaireNavigation } from '~/features/questionnaire'
import type {
  AdminApplication,
  AdminApplicationDetailResponse,
  AdminApplicationVehiclePriceItem,
  AdminApplicationPriceChange,
  AdminApplicationPriceChangesResponse,
} from '~/types/admin'
import CommerceApplicationItemsSummary from '~/features/commerce/components/CommerceApplicationItemsSummary.vue'
import type { CommerceApplicationItem, CommerceMoney } from '~/features/commerce/types'
import { formatCommerceMoney } from '~/features/commerce/money'
import { formatSourcedApplicationNumber as formatApplicationNumber, type SiteApplicationSourceType } from '~/features/applications/sourceType'
import ApplicationSourceBadge from '~/features/applications/components/ApplicationSourceBadge.vue'
import ApplicationSourceFilter from '~/features/applications/components/ApplicationSourceFilter.vue'
import ApplicationKindFilter from '~/features/fast-deals/components/ApplicationKindFilter.vue'
import FastDealApplicationRow from '~/features/fast-deals/components/FastDealApplicationRow.vue'
import { isFastDealRow, ordinaryRows, type ApplicationListKind } from '~/features/fast-deals/mergedList'
import type { FastDealListItem } from '~/features/fast-deals/types'
import VehicleManagementModal from '~/features/admin/vehicles/components/VehicleManagementModal.vue'
import LeasingCompaniesModal from '~/features/admin/users/components/LeasingCompaniesModal.vue'
import ImportProgress from '~/features/admin/shared/components/ImportProgress.vue'
import { useCsvImport } from '~/features/admin/shared/composables/useCsvImport'
import { createDetailRequestCoordinator } from '~/features/admin/applications/detailRequestCoordinator'

const config = useRuntimeConfig()
const { questionnaireLocation } = useQuestionnaireNavigation()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const csvImport = useCsvImport()

/** The list holds ordinary applications and fast deals (`kind: 'fast_deal'`) in one order. */
type AdminListRow = AdminApplication | FastDealListItem

const applications = ref<AdminListRow[]>([])
const loading = ref(true)
const error = ref('')
const currentPage = ref(1)
const totalPages = ref(1)
const total = ref(0)

const filters = reactive({
  status: '', // Show all applications by default
  search: '',
  sources: [] as SiteApplicationSourceType[],
  kind: '' as ApplicationListKind | '',
})

// An ordinary status excludes fast deals on the server; while only fast deals are listed the
// ordinary status filter is not sent at all.
const statusFilterHint = computed(() => {
  if (filters.kind === 'fast_deal') return 'Статус быстрой регистрации выбирается в разделе «Регистрация сделки».'
  if (filters.status && filters.kind === '') return 'При выборе статуса показываются только обычные заявки, быстрые регистрации скрыты.'
  return ''
})

const showLeasingModal = ref(false)
const showVehiclesModal = ref(false)
const selectedApplication = ref<AdminApplication | null>(null)

interface ApplicationDetailState {
  expanded: boolean
  loading: boolean
  error: string
  data: AdminApplicationDetailResponse | null
  items: CommerceApplicationItem[]
  itemsCount: number | null
  totalItemsPrice: CommerceMoney | null
  priceHistoryLoading: boolean
  priceHistoryError: string
  priceHistory: AdminApplicationPriceChange[]
  priceHistoryTotal: number
}

const detailStates = reactive<Record<string, ApplicationDetailState>>({})
const detailRequestCoordinator = createDetailRequestCoordinator()
const linkedApplicationId = computed(() => isUuid(route.query.application) ? route.query.application : null)
const visibleApplications = computed(() => {
  const linked = linkedApplicationId.value ? detailStates[linkedApplicationId.value]?.data?.application : null
  return linked ? [linked, ...applications.value.filter(app => app.id !== linked.id)] : applications.value
})
const linkedDetailState = computed(() => linkedApplicationId.value ? detailStates[linkedApplicationId.value] : null)
const closeLinkedApplication = async () => {
  const query = { ...route.query }
  delete query.application
  await router.replace({ query })
}

const { formatPrice } = useFormatPrice()
const { formatDateTime } = useFormatDate()

const ensureDetailState = (applicationId: string) => {
  if (!detailStates[applicationId]) {
    detailStates[applicationId] = {
      expanded: false,
      loading: false,
      error: '',
      data: null,
      items: [],
      itemsCount: null,
      totalItemsPrice: null,
      priceHistoryLoading: false,
      priceHistoryError: '',
      priceHistory: [],
      priceHistoryTotal: 0,
    }
  }

  return detailStates[applicationId]
}

const toCommerceMoney = (value: number | string | null | undefined): CommerceMoney | null => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null
  return String(value)
}

const toCommerceVehicleItem = (item: AdminApplicationVehiclePriceItem): CommerceApplicationItem => ({
  type: 'vehicle',
  id: item.id,
  item_id: item.item_id ?? null,
  title: item.title || 'Автомобиль',
  image_url: item.image_url ?? null,
  detail_url: item.detail_url ?? null,
  quantity: item.quantity > 0 ? item.quantity : 1,
  unit_price: toCommerceMoney(item.unit_price ?? item.catalog_price),
  total_price: toCommerceMoney(item.total_price),
  catalog_price: toCommerceMoney(item.catalog_price ?? item.unit_price),
  show_catalog_price: item.show_catalog_price ?? true,
  discount_type: item.discount_type ?? null,
  discount_value: toCommerceMoney(item.discount_value),
  discount_amount: toCommerceMoney(item.discount_amount),
  markup_type: item.markup_type ?? null,
  markup_value: toCommerceMoney(item.markup_value),
  markup_amount: toCommerceMoney(item.markup_amount),
  final_price: toCommerceMoney(item.final_price ?? item.unit_price),
  dealer_comment: item.dealer_comment ?? null,
  currency_code: item.currency_code || 'RUB',
  status: item.status ?? null,
  snapshot: item.snapshot ?? null,
})

// Debounced search
let searchTimeout: ReturnType<typeof setTimeout> | null = null
const debouncedSearch = () => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    currentPage.value = 1
    fetchApplications()
  }, 500)
}

const fetchApplications = async () => {
  loading.value = true
  error.value = ''

  try {
    const params = new URLSearchParams({
      page: currentPage.value.toString(),
      limit: '20'
    })
    
    if (filters.status && filters.kind !== 'fast_deal') params.append('status', filters.status)
    if (filters.search) params.append('search', filters.search)
    if (filters.sources.length) params.append('source_type', filters.sources.join(','))
    if (filters.kind) params.append('kind', filters.kind)

    const response = await $fetch(`/api/v1/admin/applications?${params}`, {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const data = response as { applications: AdminListRow[]; pagination: { page: number; limit: number; total: number; pages: number } }
    applications.value = data.applications
    totalPages.value = data.pagination.pages
    total.value = data.pagination.total
  } catch (err: unknown) {
    const e = err as { data?: { error?: string } }
    error.value = e.data?.error || 'Ошибка при загрузке заявок'
    console.error('Error fetching applications:', err)
  } finally {
    loading.value = false
  }
}

const fetchApplicationDetails = async (applicationId: string) => {
  const state = ensureDetailState(applicationId)
  state.loading = true
  state.error = ''

  await detailRequestCoordinator.run(
    applicationId,
    async () => {
      const detail = await $fetch<AdminApplicationDetailResponse>('/api/v1/admin/applications/' + applicationId, {
        baseURL: config.public.apiBase,
        credentials: 'include',
      })
      return detail
    },
    {
      onSuccess: (detail) => {
        state.data = detail
        state.items = detail.application.items
          ?? (detail.application.vehicle_price_items || []).map(toCommerceVehicleItem)
        state.itemsCount = detail.application.items_count ?? null
        state.totalItemsPrice = toCommerceMoney(detail.application.total_items_price ?? detail.application.total_amount)
        const listApplication = ordinaryRows<AdminApplication>(applications.value).find(app => app.id === applicationId)
        if (listApplication) {
          listApplication.pending_price_items_count = detail.application.pending_price_items_count ?? 0
          listApplication.can_assign_leasing_companies = detail.application.can_assign_leasing_companies ?? true
        }
        void fetchPriceHistory(applicationId)
      },
      onError: (err) => {
        const e = err as { data?: { detail?: string; error?: string } }
        state.error = e.data?.detail || e.data?.error || 'Ошибка при загрузке деталей заявки'
        console.error('Error fetching application details:', err)
      },
      onSettled: () => {
        state.loading = false
      }
    }
  )
}

const invalidateApplicationDetails = (applicationId?: string) => {
  if (applicationId) {
    detailRequestCoordinator.invalidate(applicationId)
    const state = detailStates[applicationId]
    if (state) {
      state.data = null
      state.error = ''
      state.loading = false
    }
    return
  }

  for (const id of Object.keys(detailStates)) {
    detailRequestCoordinator.invalidate(id)
    delete detailStates[id]
  }
}

const refreshExpandedDetails = (applicationId: string | undefined) => {
  if (!applicationId) return
  const state = detailStates[applicationId]
  invalidateApplicationDetails(applicationId)
  if (state?.expanded) void fetchApplicationDetails(applicationId)
}

const toggleDetails = async (app: AdminApplication) => {
  const state = ensureDetailState(app.id)

  if (state.expanded) {
    state.expanded = false
    return
  }

  state.expanded = true

  if (!state.data && !state.loading) {
    await fetchApplicationDetails(app.id)
  }
}

const changePage = (page: number) => {
  if (page < 1 || page > totalPages.value) return
  currentPage.value = page
  fetchApplications()
}

const getStatusClasses = (status: string) => {
  const classes: Record<string, string> = {
    active: 'bg-blue-100 text-blue-800',
    rejected: 'bg-red-100 text-red-800',
    issued: 'bg-green-100 text-green-800'
  }
  return classes[status] || 'bg-gray-100 text-gray-800'
}

const getStatusText = (status: string) => {
  const texts: Record<string, string> = {
    active: 'Активная',
    rejected: 'Отклонена',
    issued: 'Выдана'
  }
  return texts[status] || 'Неизвестно'
}

const hasLeasingCompanies = (app: AdminApplication) => {
  return app.selected_companies_info && app.selected_companies_info.length > 0
}

const canAssignLeasingCompanies = (app: AdminApplication): boolean =>
  app.can_assign_leasing_companies !== false && (app.pending_price_items_count ?? 0) === 0

const applyFilters = () => {
  currentPage.value = 1
  fetchApplications()
}

const setQuickFilter = (status: string) => {
  filters.status = status
  currentPage.value = 1
  fetchApplications()
}

const detailValue = (value: string | number | null | undefined, fallback = '—') => {
  if (value === null || value === undefined || value === '') return fallback
  return value
}

const formatNullablePrice = (value: number | null | undefined) => {
  return typeof value === 'number' ? formatPrice(value) : '—'
}

const formatNullablePercent = (value: number | null | undefined) => {
  return typeof value === 'number' ? `${value}%` : '—'
}

const formatNullableMonths = (value: number | null | undefined) => {
  return typeof value === 'number' ? `${value} мес.` : '—'
}

const formatNullableDate = (value: string | null | undefined) => {
  return value ? formatDateTime(value) : '—'
}

const formatHistoryPrice = (value: string | null): string =>
  value === null ? '—' : formatCommerceMoney(value)

const priceHistorySourceLabel = (source: string): string => ({
  dealer_ui: 'Кабинет дилера',
  api: 'API',
})[source] ?? source

const fetchPriceHistory = async (applicationId: string): Promise<void> => {
  const state = ensureDetailState(applicationId)
  state.priceHistoryLoading = true
  state.priceHistoryError = ''
  try {
    const response = await $fetch<AdminApplicationPriceChangesResponse>(
      `/api/v1/admin/applications/${applicationId}/price-changes`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include',
        query: { limit: 50, offset: 0 },
      },
    )
    state.priceHistory = response.items
    state.priceHistoryTotal = response.total
  } catch (err: unknown) {
    const payload = err as { data?: { detail?: string; error?: string } }
    state.priceHistoryError = payload.data?.detail
      || payload.data?.error
      || 'Не удалось загрузить историю изменения цен'
  } finally {
    state.priceHistoryLoading = false
  }
}

const openLeasingModal = (app: AdminApplication) => {
  if (!canAssignLeasingCompanies(app)) return
  selectedApplication.value = app
  showLeasingModal.value = true
}

const openVehiclesModal = (app: AdminApplication) => {
  selectedApplication.value = app
  showVehiclesModal.value = true
}

const onLeasingSaved = () => {
  const applicationId = selectedApplication.value?.id
  showLeasingModal.value = false
  fetchApplications()
  refreshExpandedDetails(applicationId)
  toast.success('Лизинговые компании назначены')
}

const onVehiclesSaved = () => {
  const applicationId = selectedApplication.value?.id
  fetchApplications()
  refreshExpandedDetails(applicationId)
  toast.success('Изменения сохранены')
}

const exportCsv = async () => {
  // The export is the ordinary applications export; fast deals are not part of it.
  const params = new URLSearchParams({ format: 'csv', kind: 'application' })
  if (filters.status) params.append('status', filters.status)
  if (filters.search) params.append('search', filters.search)
  if (filters.sources.length) params.append('source_type', filters.sources.join(','))

  try {
    const response = await fetch(`${config.public.apiBase}/api/v1/admin/applications?${params}`, {
      credentials: 'include'
    })
    if (!response.ok) throw new Error('Export failed')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `applications_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Export error:', err)
    toast.error('Ошибка при экспорте')
  }
}

const importCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  const job = await csvImport.upload('/api/v1/admin/applications/import', file)
  input.value = ''
  if (job?.status !== 'done') return

  invalidateApplicationDetails()
  await fetchApplications()
}

watch(linkedApplicationId, async id => {
  if (!id) return
  ensureDetailState(id).expanded = true
  await fetchApplicationDetails(id)
}, { immediate: true })

onMounted(() => {
  fetchApplications()
})
</script>
