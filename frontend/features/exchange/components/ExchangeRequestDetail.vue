<template>
  <!-- Loading state -->
  <div v-if="loading && !request" class="flex justify-center py-16">
    <div class="animate-spin rounded-full h-10 w-10 border-2 border-gray-200 border-t-blue-600"></div>
  </div>

  <!-- Detail -->
  <div v-else-if="request" class="space-y-5">
    <div v-if="hasCompanySelection && !isDistributor && !canWrite" role="status" class="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      {{ permissionsLoading ? 'Проверяем права выбранной компании…' : permissionsError || 'Данные выбранной компании доступны только для просмотра.' }}
      <button v-if="permissionsError" type="button" class="ml-2 underline" @click="refreshPermissions">Повторить проверку прав</button>
    </div>
    <p v-if="actionError" class="text-sm text-red-700" role="alert">{{ actionError }}</p>
    <!-- Vehicle header -->
    <div class="bg-white rounded-2xl border border-gray-200 overflow-hidden">
      <div class="flex flex-col md:flex-row">
        <!-- Image -->
        <NuxtLink
          to="/special-equipment"
          class="md:w-64 h-48 md:h-auto flex-shrink-0 bg-white border-b md:border-b-0 md:border-r border-gray-100 flex items-center justify-center p-4 hover:bg-gray-50 transition-colors"
        >
          <img
            v-if="firstImage"
            :src="firstImage"
            :alt="vehicleTitle"
            class="max-h-full max-w-full object-contain"
          />
          <svg v-else class="w-16 h-16 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </NuxtLink>

        <!-- Info -->
        <div class="flex-1 p-6 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span :class="statusBadgeClass">{{ statusLabel }}</span>
                <span class="text-xs text-gray-500">Заявка № {{ requestNumber }}</span>
                <span class="text-xs text-gray-400">• {{ formattedCreated }}</span>
              </div>
              <h2 class="text-xl font-bold text-gray-900 truncate">{{ vehicleTitle }}</h2>
              <p v-if="subtitle" class="text-sm text-gray-500 mt-0.5">{{ subtitle }}</p>
            </div>
            <div class="flex-shrink-0 space-y-2 text-right">
              <div class="text-xs text-gray-500">цена в каталоге</div>
              <div
                v-if="hasSupportPriceDiscount"
                class="text-sm text-gray-400 line-through"
              >
                {{ formatPrice(supportPriceBase) }}
              </div>
              <div class="text-xl font-bold text-gray-900">{{ formatPrice(supportUnitPrice) }}</div>
              <div
                v-if="selectedSupportPrograms.length"
                class="flex max-w-md flex-wrap justify-end gap-1.5"
              >
                <SupportBadge
                  v-for="program in selectedSupportPrograms"
                  :key="program.id"
                  :program="program"
                  shape="badge"
                  tooltip-align="right"
                />
              </div>
            </div>
          </div>

          <!-- Key facts: meta → totals → desired -->
          <div class="space-y-2">
            <!-- Group 1: meta -->
            <div class="grid grid-cols-2 gap-2">
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Количество</div>
                <div class="text-sm font-semibold text-gray-900">{{ request.quantity || 1 }} шт.</div>
              </div>
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Срок</div>
                <div class="text-sm font-semibold text-gray-900">
                  {{ request.expiration_at ? formatExchangeDeadline(request.expiration_at) : 'Без срока' }}
                </div>
              </div>
            </div>

            <!-- Group 2: totals -->
            <div class="grid grid-cols-2 gap-2">
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Общая стоимость</div>
                <div class="text-sm font-semibold text-gray-900">{{ formatPrice(totalPrice) }}</div>
              </div>
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Общая желаемая стоимость</div>
                <div class="text-sm font-semibold" :class="hasDesiredDiscount ? 'text-blue-600' : 'text-gray-900'">
                  {{ formatPrice(desiredTotalPrice) }}
                </div>
              </div>
            </div>

            <!-- Group 3: desired per-unit -->
            <div class="grid grid-cols-2 gap-2">
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Желаемая выгода</div>
                <div class="text-sm font-semibold text-gray-900">{{ requestedDiscountLabel }}</div>
              </div>
              <div class="bg-gray-50 rounded-lg px-3 py-2">
                <div class="text-xs text-gray-500">Желаемая цена</div>
                <div class="text-sm font-semibold text-gray-900">{{ requestedPriceLabel }}</div>
              </div>
            </div>
          </div>

          <!-- Actions (LC) -->
          <div v-if="isLc && canWrite" class="flex flex-wrap gap-2">
            <button
              v-if="request.status === 'open'"
              @click="handleOpenArchive"
              class="inline-flex items-center gap-2 px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 text-sm font-medium rounded-lg transition-colors"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              Закрыть заявку
            </button>

            <button
              v-if="request.status === 'deal'"
              @click="handleOpenArchive"
              class="inline-flex items-center gap-2 px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 text-sm font-medium rounded-lg transition-colors"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              В архив
            </button>

            <button
              v-if="['deal', 'archived'].includes(request.status)"
              @click="handleDuplicate"
              :disabled="duplicating"
              class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg shadow-sm transition-colors disabled:opacity-50"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              {{ duplicating ? 'Создание...' : 'Создать повторно' }}
            </button>
          </div>

          <!-- Attached request file (visible to LC & dealer) -->
          <a
            v-if="request.file_url"
            :href="api.downloadUrl(request.file_url)"
            target="_blank"
            class="inline-flex items-center gap-2 px-4 py-2 bg-white hover:bg-gray-50 text-gray-700 border border-gray-300 text-sm font-medium rounded-lg transition-colors self-start"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {{ request.file_name || 'Файл заявки' }}
          </a>
        </div>
      </div>

      <!-- Warehouses strip (LC only — dealers shouldn't see competitors) -->
      <div v-if="(isLc || isDistributor) && warehouses.length > 0" class="px-6 py-4 border-t border-gray-100 bg-gray-50">
        <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
          Дилеры и склады ({{ warehouses.length }})
        </p>
        <div class="flex flex-wrap gap-2">
          <div
            v-for="wh in warehouses"
            :key="wh.id"
            class="inline-flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-xs"
          >
            <svg class="w-3.5 h-3.5 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <div>
              <div v-if="wh.address && wh.city_name" class="text-gray-900 truncate">
                {{ wh.city_name }}, {{ wh.address }}
              </div>
              <div v-else-if="wh.address" class="text-gray-900 truncate">{{ wh.address }}</div>
              <div v-else-if="wh.city_name" class="text-gray-900 truncate">{{ wh.city_name }}</div>
              <div v-if="wh.company_name" class="text-gray-600 truncate">
                {{ wh.company_name }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Comment from LC -->
    <div v-if="leadComment" class="bg-white rounded-2xl border border-gray-200 p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-2">
        Комментарий к заявке
      </h3>
      <p class="text-sm text-gray-700 whitespace-pre-wrap">{{ leadComment }}</p>
    </div>

    <!-- Requested options (dealer view — read-only) -->
    <div v-if="!isLc && !isDistributor && options.length > 0" class="bg-white rounded-2xl border border-gray-200 p-5">
      <h3 class="text-sm font-semibold text-gray-900 mb-3">
        Запрошенные опции
        <span class="text-xs font-normal text-gray-500 ml-1">({{ options.length }})</span>
      </h3>
      <div class="flex flex-wrap gap-1.5">
        <span
          v-for="opt in options"
          :key="opt.id"
          class="inline-flex items-center text-xs px-3 py-1.5 rounded-full border bg-blue-600 border-blue-600 text-white"
        >
          {{ opt.name }}
        </span>
      </div>
    </div>

    <!-- Options filter (LC view) -->
    <div v-if="(isLc || isDistributor) && options.length > 0" class="bg-white rounded-2xl border border-gray-200 p-5">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 class="text-sm font-semibold text-gray-900">Фильтр по опциям</h3>
        </div>
        <div class="flex gap-2 flex-shrink-0">
          <button
            @click="selectAllOptions"
            class="text-xs px-2.5 py-1 rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            Все
          </button>
          <button
            @click="clearOptions"
            class="text-xs px-2.5 py-1 rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            Сбросить
          </button>
        </div>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="opt in options"
          :key="opt.id"
          @click="toggleOption(opt.id)"
          :class="[
            'inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border transition-colors',
            activeOptionIds.includes(opt.id)
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600'
          ]"
        >
          <svg v-if="activeOptionIds.includes(opt.id)" class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
          </svg>
          {{ opt.name }}
        </button>
      </div>
    </div>

    <!-- Bids section -->
    <div class="bg-white rounded-2xl border border-gray-200">
      <div class="flex items-center justify-between px-5 py-4 border-b border-gray-100">
        <h3 class="text-base font-semibold text-gray-900">
          Ставки дилеров
          <span class="text-sm font-normal text-gray-500 ml-1">({{ sortedBids.length }})</span>
        </h3>
        <div v-if="(isLc || isDistributor) && options.length > 0" class="text-xs text-gray-500">
          Сортировка: по совпадению и цене
        </div>
      </div>

      <!-- Dealer: own bid form -->
      <div v-if="!isLc && canWrite && request.status === 'open'" class="p-5 border-b border-gray-100 bg-gray-50 space-y-3">
        <ExchangeBidForm
          :key="`${request.id}:${notificationCompanyId || ''}`"
          :request-id="request.id"
          :can-write="canWrite"
          :request-quantity="request.quantity"
          :existing-bid="myBid"
          @submitted="refreshDetail"
          @failed="reportWriteFailure()"
        />
        <div v-if="myBid && !myBid.is_accepted" class="flex justify-end">
          <button
            type="button"
            :disabled="withdrawing"
            @click="withdrawOwnBid"
            class="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-red-300 text-red-600 hover:bg-red-50 text-sm font-medium rounded-lg transition-colors"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            {{ withdrawing ? 'Отзываем…' : 'Отозвать ставку' }}
          </button>
        </div>
      </div>

      <!-- Bids list -->
      <div v-if="sortedBids.length > 0" class="divide-y divide-gray-100">
        <div
          v-for="bid in sortedBids"
          :key="bid.id"
          :class="[
            'p-5 transition-colors',
            bid.is_accepted ? 'bg-emerald-50/50' : 'hover:bg-gray-50',
          ]"
        >
          <div class="flex flex-col lg:flex-row lg:items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2 mb-2">
                <span class="text-xl font-bold text-gray-900">{{ formatPrice(bid.price) }}</span>
                <span class="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded bg-gray-100 text-gray-700">
                  #{{ bid.rank }}
                </span>
                <span v-if="bid.is_accepted" class="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>
                  {{ isLc || isDistributor ? 'Сделка' : 'Выиграно' }}
                </span>
                <span v-if="bid.is_own" class="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700">
                  Ваша ставка
                </span>
                <span
                  v-if="(isLc || isDistributor) && activeOptionIds.length > 0"
                  :class="[
                    'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full',
                    bidMatchInfo(bid).badgeClass
                  ]"
                >
                  Совпадение: {{ bidMatchInfo(bid).matched }}/{{ activeOptionIds.length }}
                </span>
              </div>

              <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
                <span v-if="(isLc || isDistributor) && bid.dealer_name" class="inline-flex items-center gap-1">
                  <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  {{ bid.dealer_name }}
                </span>
                <span class="inline-flex items-center gap-1">
                  <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h7" />
                  </svg>
                  {{ bid.quantity || 1 }} шт.
                </span>
                <a
                  v-if="bid.bid_file_url && (isLc || isDistributor || bid.is_own)"
                  :href="api.downloadUrl(bid.bid_file_url)"
                  target="_blank"
                  class="inline-flex items-center gap-1 text-blue-600 hover:underline"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414a4 4 0 10-5.656-5.656l-6.415 6.414a6 6 0 108.486 8.486L20.5 13"/>
                  </svg>
                  {{ bid.bid_file_name || 'Файл' }}
                </a>
              </div>

              <!-- Totals per bid -->
              <div class="mt-2 grid grid-cols-2 gap-2 max-w-md">
                <div class="bg-gray-50 rounded-lg px-3 py-1.5">
                  <div class="text-[11px] text-gray-500">Общая стоимость</div>
                  <div class="text-sm font-semibold text-gray-900">{{ formatPrice(bidTotalPrice(bid)) }}</div>
                </div>
                <div class="bg-gray-50 rounded-lg px-3 py-1.5">
                  <div class="text-[11px] text-gray-500">Общая желаемая стоимость</div>
                  <div class="text-sm font-semibold" :class="hasDesiredDiscount ? 'text-blue-600' : 'text-gray-900'">
                    {{ formatPrice(desiredTotalPrice) }}
                  </div>
                </div>
              </div>

              <p v-if="bid.comment && (isLc || isDistributor || bid.is_own)" class="mt-2 text-sm text-gray-700 italic bg-gray-50 px-3 py-2 rounded-lg border border-gray-100">
                "{{ bid.comment }}"
              </p>

              <!-- Bid options -->
              <div v-if="bid.options && bid.options.length > 0" class="mt-3 flex flex-wrap gap-1.5">
                <span
                  v-for="opt in bid.options"
                  :key="opt.id"
                  :class="[
                    'text-xs px-2 py-0.5 rounded',
                    activeOptionIds.includes(opt.id)
                      ? 'bg-emerald-100 text-emerald-700 font-medium'
                      : 'bg-gray-100 text-gray-600'
                  ]"
                >
                  {{ opt.name }}
                </span>
              </div>

              <!-- LC comments on this bid (LC sees all; dealer sees only on own bid) -->
              <div v-if="bid.lc_comments && bid.lc_comments.length > 0 && (isLc || isDistributor || bid.is_own)" class="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
                <div v-for="c in bid.lc_comments" :key="c.id" class="text-sm text-gray-600">
                  <span class="font-medium text-gray-900">{{ c.user_name || 'ЛК' }}:</span>
                  {{ c.comment }}
                  <span class="text-xs text-gray-400 ml-1">
                    {{ formatDateTime(c.created_at) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex flex-col gap-2 flex-shrink-0">
              <!-- LC actions -->
              <template v-if="isLc && canWrite && request.status === 'open'">
                <button
                  @click.stop="handleOpenSelectDealer(bid.id)"
                  :disabled="confirmingDeal"
                  class="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  Выбрать дилера
                </button>
                <button
                  @click.stop="handleOpenCounterOffer(bid.id)"
                  class="inline-flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 text-sm font-medium rounded-lg transition-colors"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Отправить новую цену
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="text-center py-12 text-gray-500">
        <svg class="w-12 h-12 text-gray-300 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p class="text-sm">Пока нет ставок</p>
        <p class="text-xs text-gray-400 mt-1">Дилеры увидят вашу заявку и смогут предложить свою цену</p>
      </div>
    </div>

    <!-- Archive confirmation modal -->
    <div
      v-if="showArchiveConfirm && canWrite"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      @click.self="showArchiveConfirm = false"
    >
      <div class="bg-white rounded-2xl p-6 max-w-sm w-full shadow-xl">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
            <svg class="w-5 h-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h3 class="text-lg font-semibold text-gray-900">В архив?</h3>
        </div>
        <p class="text-sm text-gray-600 mb-5">
          Заявка будет перемещена в архив. Дилеры больше не смогут делать ставки.
          Позже вы сможете создать повторно.
        </p>
        <div class="flex justify-end gap-2">
          <button
            @click="showArchiveConfirm = false"
            class="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Отмена
          </button>
          <button
            @click="handleArchive"
            :disabled="archiving"
            class="px-4 py-2 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
          >
            {{ archiving ? 'Архивация...' : 'В архив' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Select dealer modal -->
    <div
      v-if="showSelectDealerModal && canWrite"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      @click.self="showSelectDealerModal = false"
    >
      <div class="bg-white rounded-2xl p-6 max-w-md w-full shadow-xl">
        <h3 class="text-lg font-semibold text-gray-900 mb-3">Выбрать дилера</h3>
        <p class="text-sm text-gray-600 mb-4">
          Вы выбираете дилера для своей заявки. После выбора дилер получит уведомление, что он выиграл вашу заявку и свяжется с вами для уточнения деталей по договору
        </p>
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Комментарий</label>
          <textarea
            v-model="selectDealerComment"
            rows="3"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            placeholder="Комментарий для дилера..."
          />
        </div>
        <div class="flex justify-end gap-2">
          <button
            @click="showSelectDealerModal = false"
            class="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Закрыть
          </button>
          <button
            @click="handleSelectDealer"
            :disabled="confirmingDeal"
            class="px-4 py-2 text-sm font-medium rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {{ confirmingDeal ? 'Выбор...' : 'Выбрать дилера' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Counter offer modal -->
    <div
      v-if="showCounterOfferModal && canWrite"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      @click.self="showCounterOfferModal = false"
    >
      <div class="bg-white rounded-2xl p-6 max-w-md w-full shadow-xl">
        <h3 class="text-lg font-semibold text-gray-900 mb-3">Отправить новую цену</h3>
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Новая цена</label>
          <input
            v-model="counterOfferPrice"
            type="number"
            min="1"
            step="0.01"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            placeholder="Введите цену..."
          />
        </div>
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Комментарий</label>
          <textarea
            v-model="counterOfferComment"
            rows="3"
            class="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            placeholder="Комментарий для дилера..."
          />
        </div>
        <div class="flex justify-end gap-2">
          <button
            @click="showCounterOfferModal = false"
            class="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Закрыть
          </button>
          <button
            @click="handleSendCounterOffer"
            :disabled="confirmingDeal"
            class="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {{ confirmingDeal ? 'Отправка...' : 'Отправить цену' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bid comment modal (legacy, replaced by inline modals above) -->
  </div>

  <!-- Error / empty -->
  <div v-else class="text-center py-16 bg-white rounded-2xl border border-gray-200">
    <p class="text-sm text-gray-600" role="alert">{{ detailError || 'Заявка недоступна' }}</p>
    <button type="button" class="btn-secondary mt-4" @click="refreshDetail">Повторить загрузку</button>
  </div>
</template>

<script setup lang="ts">
import { formatExchangeDeadline } from '../deadline'
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { createExchangeApi } from '../api/exchangeApi'
import ExchangeBidForm from './ExchangeBidForm.vue'
import ExchangeBidCommentModal from './ExchangeBidCommentModal.vue'
import { provideNotificationCompanyContext } from '~/features/notifications'
import { useApplicationCompanyPermissions } from '~/features/auth/composables/useApplicationCompanyPermissions'
import type { ExchangeBid, ExchangeRequest, ExchangeRequestId } from '../types'
import type { UUID } from '~/types/ids'
import SupportBadge from '~/components/support/SupportBadge.vue'
import { vehicleImageUrl } from '~/utils/vehicleImageUrl'

const props = defineProps<{
  requestId: ExchangeRequestId
  isLc: boolean
  isDistributor?: boolean
  notificationCompanyId?: UUID
}>()

const emit = defineEmits<{ close: [] }>()

const notificationCompanyContext = provideNotificationCompanyContext(() => props.notificationCompanyId)
const api = createExchangeApi(useRuntimeConfig(), notificationCompanyContext)
const detailError = ref('')
const actionError = ref('')
const withdrawing = ref(false)
const loading = ref(false)
const showArchiveConfirm = ref(false)
const archiving = ref(false)
const duplicating = ref(false)
const confirmingDeal = ref(false)
const activeOptionIds = ref<UUID[]>([])
const optionsInitialized = ref(false)

// Select dealer modal state
const showSelectDealerModal = ref(false)
const selectDealerBidId = ref<UUID | null>(null)
const selectDealerComment = ref('')

// Counter offer modal state
const showCounterOfferModal = ref(false)
const counterOfferBidId = ref<UUID | null>(null)
const counterOfferPrice = ref('')
const counterOfferComment = ref('')

const request = ref<ExchangeRequest | null>(null)
const {
  canCreate: companyCanWrite,
  hasSelection: hasCompanySelection,
  loading: permissionsLoading,
  error: permissionsError,
  refresh: refreshPermissions,
} = useApplicationCompanyPermissions(
  () => props.isDistributor ? undefined : props.notificationCompanyId,
  () => true, // Ordinary LC/dealer screens retain their existing role/status policy.
)
const canWrite = computed(() => !props.isDistributor && !!request.value && !loading.value && companyCanWrite.value)
function resetWriteDialogs() {
  showArchiveConfirm.value = false
  showSelectDealerModal.value = false
  selectDealerBidId.value = null
  selectDealerComment.value = ''
  showCounterOfferModal.value = false
  counterOfferBidId.value = null
  counterOfferPrice.value = ''
  counterOfferComment.value = ''
}
watch(canWrite, allowed => { if (!allowed) resetWriteDialogs() }, { flush: 'sync' })
let detailVersion = 0
onBeforeUnmount(() => {
  detailVersion++
  request.value = null
  resetWriteDialogs()
})
const selectedSupportPrograms = computed(() => {
  const requestValue = request.value
  if (!requestValue) return []
  const selectedIds = new Set(requestValue.selected_support_ids)
  return requestValue.support_program_details.filter(program => selectedIds.has(program.id))
})

const firstImage = computed(() => {
  const f = request.value?.images?.[0]
  return f ? vehicleImageUrl(f) : null
})

const vehicleTitle = computed(() => {
  if (!request.value) return ''
  const parts = [request.value.mark_name, request.value.model_name].filter(Boolean)
  return parts.join(' ') || `Автомобиль #${request.value.vehicle_id}`
})

const requestNumber = computed(() => {
  if (!request.value) return ''
  const { batch_number, batch_index, id } = request.value
  if (batch_number && batch_index) return `${batch_number}-${batch_index}`
  return id
})
const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate, formatDateTime } = useFormatDate()

const subtitle = computed(() => {
  if (!request.value) return ''
  const parts = [
    request.value.generation_name,
    request.value.group_name,
    request.value.color,
  ].filter(Boolean)
  return parts.join(' • ')
})

const formattedCreated = computed(() => {
  if (!request.value?.created_at) return ''
  return formatSharedDate(request.value.created_at)
})

const statusLabel = computed(() => {
  const map: Record<string, string> = { open: 'Открыта', deal: 'Сделка', archived: 'Архив' }
  return map[request.value?.status || ''] || ''
})

const statusBadgeClass = computed(() => {
  const base = 'inline-flex items-center text-xs font-medium px-2.5 py-0.5 rounded-full'
  const map: Record<string, string> = {
    open: `${base} bg-emerald-100 text-emerald-700`,
    deal: `${base} bg-blue-100 text-blue-700`,
    archived: `${base} bg-gray-100 text-gray-600`,
  }
  return map[request.value?.status || ''] || `${base} bg-gray-100 text-gray-600`
})

const discountText = computed(() => {
  if (!request.value) return ''
  const { discount_type, discount_value } = request.value
  if (!discount_type || !discount_value) return ''
  switch (discount_type) {
    case 'rubles_off': return `Выгода ${formatPrice(discount_value)}`
    case 'percent_off': return `Выгода ${discount_value}%`
    case 'fixed_price': return `Фикс. цена ${formatPrice(discount_value)}`
    default: return ''
  }
})

const requestedDiscount = computed(() => {
  if (!request.value) return null
  const base = supportUnitPrice.value
  const { discount_type, discount_value } = request.value
  const value = Number(discount_value)
  if (!base || !discount_type || !value) return null
  let rubles = 0
  if (discount_type === 'rubles_off') rubles = value
  else if (discount_type === 'percent_off') rubles = base * value / 100
  else if (discount_type === 'fixed_price') rubles = base - value
  else return null
  if (rubles <= 0) return null
  const percent = (rubles / base) * 100
  const finalPrice = base - rubles
  return { rubles, percent, finalPrice }
})

const requestedDiscountLabel = computed(() => {
  const d = requestedDiscount.value
  if (!d) return '—'
  const percent = d.percent >= 10 ? Math.round(d.percent) : Math.round(d.percent * 10) / 10
  return `${formatPrice(d.rubles)}, ${percent}%`
})

const requestedPriceLabel = computed(() => {
  const d = requestedDiscount.value
  const base = supportUnitPrice.value
  const price = d ? d.finalPrice : base
  return price ? formatPrice(price) : '—'
})

const quantity = computed(() => Number(request.value?.quantity) || 1)
const supportPriceBase = computed(() => (
  Number(request.value?.support_price_base ?? request.value?.discount_price ?? request.value?.base_price) || 0
))
const supportUnitPrice = computed(() => (
  Number(request.value?.support_price_display ?? request.value?.discount_price ?? request.value?.base_price) || 0
))
const hasSupportPriceDiscount = computed(() => (
  Number(request.value?.support_price_amount) > 0 && supportPriceBase.value > supportUnitPrice.value
))
const totalPrice = computed(() => supportUnitPrice.value * quantity.value)
const desiredUnitPrice = computed(() => {
  const d = requestedDiscount.value
  const base = supportUnitPrice.value
  return d ? d.finalPrice : base
})
const desiredTotalPrice = computed(() => desiredUnitPrice.value * quantity.value)
const hasDesiredDiscount = computed(() => !!requestedDiscount.value)

function bidTotalPrice(bid: ExchangeBid) {
  const q = Math.max(1, Number(bid.quantity) || 1)
  return (Number(bid.price) || 0) * q
}

const options = computed(() => request.value?.options || [])
const warehouses = computed(() => request.value?.warehouses || [])
const leadComment = computed(() => {
  const first = (request.value?.dealer_comments || []).find(c => c.comment?.trim())
  return first?.comment || ''
})
const myBid = computed(() => request.value?.bids?.find(b => b.is_own) || null)

const sortedBids = computed(() => {
  const bids = [...(request.value?.bids || [])]
  if ((!props.isLc && !props.isDistributor) || activeOptionIds.value.length === 0) return bids
  return bids.sort((a, b) => {
    const ma = bidMatchInfo(a).matched
    const mb = bidMatchInfo(b).matched
    if (ma !== mb) return mb - ma
    return (a.price || 0) - (b.price || 0)
  })
})

function bidMatchInfo(bid: ExchangeBid) {
  const bidOptionIds = new Set((bid.options || []).map(o => o.id))
  const matched = activeOptionIds.value.filter(id => bidOptionIds.has(id)).length
  const total = activeOptionIds.value.length
  const ratio = total > 0 ? matched / total : 0
  let badgeClass = 'bg-gray-100 text-gray-600'
  if (ratio === 1) badgeClass = 'bg-emerald-100 text-emerald-700'
  else if (ratio >= 0.5) badgeClass = 'bg-amber-100 text-amber-700'
  else if (matched > 0) badgeClass = 'bg-orange-100 text-orange-700'
  else badgeClass = 'bg-red-50 text-red-600'
  return { matched, total, ratio, badgeClass }
}

function toggleOption(id: UUID) {
  const idx = activeOptionIds.value.indexOf(id)
  if (idx >= 0) activeOptionIds.value.splice(idx, 1)
  else activeOptionIds.value.push(id)
}

function selectAllOptions() {
  activeOptionIds.value = options.value.map(o => o.id)
}

function clearOptions() {
  activeOptionIds.value = []
}

function formatPrice(price: number | null | undefined) {
  if (!price) return '—'
  return formatSharedPrice(price)
}

function formatDate(date: string) {
  return formatSharedDate(date)
}

async function refreshDetail() {
  const version = ++detailVersion
  loading.value = true
  detailError.value = ''
  request.value = null
  try {
    const response = props.isDistributor
      ? await api.getDistributorRequestDetail(props.requestId)
      : props.isLc ? await api.getLcRequestDetail(props.requestId) : await api.getDealerRequestDetail(props.requestId)
    if (version !== detailVersion) return
    request.value = response.request
    if (!optionsInitialized.value && options.value.length > 0) {
      activeOptionIds.value = options.value.map(o => o.id)
      optionsInitialized.value = true
    }
  } catch {
    if (version === detailVersion) detailError.value = 'Не удалось загрузить заявку. Возможно, доступ отозван.'
  } finally {
    if (version === detailVersion) loading.value = false
  }
}

async function withdrawOwnBid() {
  if (!canWrite.value || props.isLc || request.value?.status !== 'open' || !myBid.value || myBid.value.is_accepted || withdrawing.value) return
  if (!confirm('Отозвать вашу ставку? Участники заявки получат уведомление.')) return
  const version = detailVersion
  withdrawing.value = true
  actionError.value = ''
  try {
    await api.withdrawBid(myBid.value.id)
    if (version === detailVersion) await refreshDetail()
  } catch {
    if (version === detailVersion) await reportWriteFailure('Не удалось отозвать ставку. Обновите данные.')
  } finally {
    withdrawing.value = false
  }
}

async function reportWriteFailure(message = 'Не удалось сохранить изменения. Проверьте права и обновите данные.') {
  actionError.value = message
  resetWriteDialogs()
  await refreshPermissions()
}

function handleOpenArchive() {
  if (!canWrite.value || !props.isLc || !request.value || !['open', 'deal'].includes(request.value.status)) return
  showArchiveConfirm.value = true
}

async function handleArchive() {
  if (!canWrite.value || !props.isLc || !showArchiveConfirm.value || archiving.value) return
  const version = detailVersion
  archiving.value = true
  try {
    await api.archiveRequest(props.requestId)
    if (version === detailVersion) {
      showArchiveConfirm.value = false
      emit('close')
    }
  } catch {
    if (version === detailVersion) await reportWriteFailure()
  } finally {
    archiving.value = false
  }
}

async function handleDuplicate() {
  if (!canWrite.value || !props.isLc || !request.value || !['deal', 'archived'].includes(request.value.status) || duplicating.value) return
  const version = detailVersion
  duplicating.value = true
  try {
    await api.duplicateRequest(props.requestId)
    if (version === detailVersion) emit('close')
  } catch {
    if (version === detailVersion) await reportWriteFailure()
  } finally {
    duplicating.value = false
  }
}

function handleOpenSelectDealer(bidId: UUID) {
  if (!canWrite.value || !props.isLc || request.value?.status !== 'open' || !request.value.bids?.some(bid => bid.id === bidId)) return
  selectDealerBidId.value = bidId
  selectDealerComment.value = ''
  showSelectDealerModal.value = true
}

async function handleSelectDealer() {
  if (!canWrite.value || !props.isLc || !showSelectDealerModal.value || !selectDealerBidId.value || confirmingDeal.value) return
  const version = detailVersion
  const selectedBidId = selectDealerBidId.value
  const comment = selectDealerComment.value.trim()
  confirmingDeal.value = true
  try {
    await api.confirmDeal(props.requestId, selectedBidId)
    if (version !== detailVersion || !canWrite.value) return
    if (comment) {
      await api.commentOnBid(props.requestId, selectedBidId, comment)
    }
    if (version !== detailVersion) return
    showSelectDealerModal.value = false
    selectDealerBidId.value = null
    await refreshDetail()
  } catch {
    if (version === detailVersion) await reportWriteFailure()
  } finally {
    confirmingDeal.value = false
  }
}

function handleOpenCounterOffer(bidId: UUID) {
  if (!canWrite.value || !props.isLc || request.value?.status !== 'open' || !request.value.bids?.some(bid => bid.id === bidId)) return
  counterOfferBidId.value = bidId
  counterOfferPrice.value = ''
  counterOfferComment.value = ''
  showCounterOfferModal.value = true
}

async function handleSendCounterOffer() {
  if (!canWrite.value || !props.isLc || !showCounterOfferModal.value || !counterOfferBidId.value || confirmingDeal.value) return
  const version = detailVersion
  const price = Number(counterOfferPrice.value)
  if (!price || price <= 0) {
    alert('Введите корректную цену')
    return
  }
  confirmingDeal.value = true
  try {
    await api.counterOffer(counterOfferBidId.value, { price, comment: counterOfferComment.value.trim() || undefined })
    if (version !== detailVersion) return
    showCounterOfferModal.value = false
    counterOfferBidId.value = null
    await refreshDetail()
  } catch {
    if (version === detailVersion) await reportWriteFailure()
  } finally {
    confirmingDeal.value = false
  }
}

watch(() => [props.requestId, props.isLc, props.isDistributor, props.notificationCompanyId] as const, () => {
  resetWriteDialogs()
  actionError.value = ''
  optionsInitialized.value = false
  activeOptionIds.value = []
  void refreshDetail()
}, { immediate: true, flush: 'sync' })
</script>
