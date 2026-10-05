<template>
  <Teleport to="body">
    <div data-storefront-block="client.cart"
      v-if="show"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/0.5)]"
      @click.self="close"
    >
      <div
        class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-xl shadow-xl w-full max-w-[min(48rem,calc(100vw-2rem))] max-h-[90vh] overflow-hidden flex flex-col"
        @click.stop
      >
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Расчет</h2>
          <button
            type="button"
            class="storefront-action-ghost p-2 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] rounded-lg hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
            @click="close"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div class="overflow-y-auto flex-1 p-4 space-y-4">
          <!-- Машина и краткие характеристики (сверху) -->
          <div class="flex gap-4 p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
            <div class="w-24 h-18 sm:w-28 sm:h-20 flex-shrink-0 rounded-lg overflow-hidden bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))]">
              <img
                v-if="vehicleImagePath"
                :src="vehicleImagePath"
                :alt="vehicleTitle"
                class="w-full h-full object-contain"
                onerror="this.src='/images/car-placeholder.png'"
              >
              <div v-else class="w-full h-full flex items-center justify-center text-[color:var(--storefront-text-muted,#9ca3af)]">
                <svg class="text-[color:var(--storefront-icon,inherit)] w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14"/>
                </svg>
              </div>
            </div>
            <div class="min-w-0 flex-1">
              <h3 class="font-semibold text-[color:var(--storefront-title,#111827)]">{{ vehicleTitle }}</h3>
              <div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-[color:var(--storefront-text-muted,#4b5563)]">
                <span v-if="item?.group_name" class="inline-flex whitespace-nowrap">
                  <span class="font-medium">Комплектация:</span>
                  <span class="ml-1">{{ item.group_name }}</span>
                </span>
                <span v-if="item?.vin" class="inline-flex whitespace-nowrap">
                  <span class="font-medium">VIN:</span>
                  <span class="ml-1 font-mono">{{ item.vin }}</span>
                </span>
                <span v-if="item?.color" class="inline-flex whitespace-nowrap">
                  <span class="font-medium">Цвет:</span>
                  <span class="ml-1">{{ item.color }}</span>
                </span>
                <span v-if="item?.year" class="inline-flex whitespace-nowrap">
                  <span class="font-medium">Год:</span>
                  <span class="ml-1">{{ item.year }}</span>
                </span>
              </div>
              <p class="mt-2 text-sm font-medium text-[color:var(--storefront-text,#111827)]">
                Цена за 1 ТС: {{ formatPrice(pricePerUnit) }}
              </p>
            </div>
          </div>

          <SupportProgramSelector
            v-if="hasSupport || availableSupportPrograms.length"
            :programs="availableSupportPrograms"
            :selected-ids="selectedSupportIds"
            :show-bulletins="canSeeSupportBulletins"
            :api-base="String(config.public.apiBase || '')"
            @change="applySupportSelection"
          />

          <!-- Расчёт: 1 ТС — на всю ширину -->
          <div class="p-4 border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] w-full min-w-0">
            <div class="mb-3">
              <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">
                Расчёт (1 ТС)
                <template v-if="hasSupportInCalculation">
                  {{ supportProgramsForVehicle.length > 1 ? ', с учётом мер поддержки' : ', с учётом поддержки' }}
                </template>
              </h4>
            </div>

            <template v-if="loadingCalc1">
              <div class="flex justify-center py-8">
                <div class="animate-spin rounded-full h-8 w-8 border-2 border-[color:var(--storefront-border,#3b82f6)] border-t-transparent"></div>
              </div>
            </template>

            <template v-else-if="calc1">
              <div class="w-full min-w-0">
                <!-- Сравнение с поддержкой: таблица на всю ширину -->
                <template v-if="hasSupportInCalculation && calc1 && calc1WithoutDiscount && horizontalCalcRows?.length">
                  <div class="text-[10px] text-[color:var(--storefront-text-muted,#9ca3af)] px-1 sm:px-2 pt-1 mb-1 leading-tight">
                    Разница: для платежа и суммы договора — красный при положительном, зелёный при отрицательном; для поддержки — наоборот.
                  </div>
                  <div class="text-xs sm:text-sm w-full min-w-0 overflow-x-auto">
                    <div
                      class="grid gap-0 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/0.8)] min-w-[36rem] sm:min-w-0"
                      style="grid-template-columns: minmax(7rem,1.2fr) minmax(5rem,1fr) minmax(5rem,1fr) minmax(4.5rem,0.9fr);"
                    >
                      <div class="font-medium text-[color:var(--storefront-text,#374151)] px-2 py-2"></div>
                      <div class="font-medium text-[color:var(--storefront-text,#1f2937)] px-2 py-2 text-right">Без поддержки</div>
                      <div class="font-medium text-[color:var(--storefront-success-text,#064e3b)] px-2 py-2 text-right bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/0.8)]">
                        С поддержкой
                      </div>
                      <div class="font-medium text-[color:var(--storefront-text,#1f2937)] px-2 py-2 text-right">Разница</div>
                    </div>
                    <div
                      v-for="(row, rIdx) in horizontalCalcRows"
                      :key="rIdx"
                      class="grid gap-0 border-b border-[color:var(--storefront-border,#f3f4f6)] min-w-[36rem] sm:min-w-0"
                      style="grid-template-columns: minmax(7rem,1.2fr) minmax(5rem,1fr) minmax(5rem,1fr) minmax(4.5rem,0.9fr);"
                    >
                      <div class="text-[color:var(--storefront-text,#374151)] px-2 py-2 align-top break-words">{{ row.label }}</div>
                      <div class="text-[color:var(--storefront-text,#111827)] tabular-nums text-right px-2 py-2 align-top">
                        {{ row.without }}
                      </div>
                      <div class="text-[color:var(--storefront-success-text,#064e3b)] tabular-nums text-right px-2 py-2 align-top bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/0.3)]">
                        {{ row.with }}
                      </div>
                      <div
                        class="tabular-nums text-right px-2 py-2 align-top font-medium"
                        :class="row.diffClass"
                      >
                        {{ row.diff }}
                      </div>
                    </div>
                  </div>
                </template>

                <!-- Нет пары «без/с» — упрощённый вид -->
                <template v-else>
                  <div class="p-1 sm:p-3 space-y-2 text-sm w-full">
                    <div class="flex justify-between gap-2">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Ежемесячный платёж</span>
                      <span class="font-semibold text-[color:var(--storefront-text,#111827)] tabular-nums">{{ formatPrice(calc1.monthlyPayment) }}</span>
                    </div>
                    <div class="flex justify-between gap-2">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Аванс по договору</span>
                      <span class="font-medium tabular-nums text-right">{{ simpleAdvanceContract }}</span>
                    </div>
                    <div class="flex justify-between gap-2">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Аванс клиента</span>
                      <span class="font-medium tabular-nums text-right">{{ simpleAdvanceClient }}</span>
                    </div>
                    <div class="flex justify-between gap-2">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Сумма договора</span>
                      <span class="font-medium tabular-nums">{{ formatPrice(calc1.totalCost) }}</span>
                    </div>
                    <template v-if="hasSupportInCalculation && supportFromApi && supportApiAmountPerUnit > 0">
                      <div class="pt-2 mt-2 border-t border-[color:var(--storefront-border,#e5e7eb)] text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)]">Учтено в расчёте:</div>
                      <div v-if="(supportFromApi.vehicle_discount_support || 0) > (supportFromApi.dealer_commission_support || 0)" class="flex justify-between">
                        <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка на ТС</span>
                        <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice((supportFromApi.vehicle_discount_support || 0) - (supportFromApi.dealer_commission_support || 0)) }}</span>
                      </div>
                      <div v-if="(supportFromApi.dealer_commission_support || 0) > 0" class="flex justify-between">
                        <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Комиссия дилеру (уменьш. счёта)</span>
                        <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.dealer_commission_support) }}</span>
                      </div>
                      <div v-if="(supportFromApi.down_payment_support || 0) > 0" class="flex justify-between">
                        <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка первого взноса</span>
                        <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.down_payment_support) }}</span>
                      </div>
                      <div v-if="(supportFromApi.interest_support || 0) > 0" class="flex justify-between">
                        <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка процентов</span>
                        <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.interest_support) }}</span>
                      </div>
                    </template>
                    <div v-else-if="hasSupportInCalculation && hasSupport && supportDisplayAmountPerUnit > 0" class="flex justify-between pt-2 mt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
                      <span class="text-[color:var(--storefront-text-muted,#4b5563)]">{{ supportRowLabel }}</span>
                      <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportDisplayAmountPerUnit) }}</span>
                    </div>
                  </div>
                </template>
              </div>
            </template>
            <template v-else>
              <p class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Заполните параметры в калькуляторе на странице корзины</p>
            </template>
          </div>

          <!-- Итого по N ТС — под расчётом за 1 ТС -->
          <div
            v-if="quantity > 1 && calc1"
            class="mt-2 p-4 border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/0.4)] w-full min-w-0"
          >
            <div class="mb-3">
              <h4 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">
                Расчёт ({{ quantity }} ТС)
                <template v-if="hasSupportInCalculation">
                  {{ supportProgramsForVehicle.length > 1 ? ', с учётом мер поддержки' : ', с учётом поддержки' }}
                </template>
              </h4>
              <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)] mt-1">Итого по всем единицам этой позиции в корзине.</p>
            </div>

            <template v-if="hasSupportInCalculation && calcN && calcNWithoutDiscount && horizontalCalcRowsTotal?.length">
              <div class="text-[10px] text-[color:var(--storefront-text-muted,#9ca3af)] px-1 sm:px-2 pt-1 mb-1 leading-tight">
                Разница: для платежа и суммы договора — красный при положительном, зелёный при отрицательном; для поддержки — наоборот.
              </div>
              <div class="text-xs sm:text-sm w-full min-w-0 overflow-x-auto">
                <div
                  class="grid gap-0 border-b border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/0.8)] min-w-[36rem] sm:min-w-0"
                  style="grid-template-columns: minmax(7rem,1.2fr) minmax(5rem,1fr) minmax(5rem,1fr) minmax(4.5rem,0.9fr);"
                >
                  <div class="font-medium text-[color:var(--storefront-text,#374151)] px-2 py-2"></div>
                  <div class="font-medium text-[color:var(--storefront-text,#1f2937)] px-2 py-2 text-right">Без поддержки</div>
                  <div class="font-medium text-[color:var(--storefront-success-text,#064e3b)] px-2 py-2 text-right bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/0.8)]">
                    С поддержкой
                  </div>
                  <div class="font-medium text-[color:var(--storefront-text,#1f2937)] px-2 py-2 text-right">Разница</div>
                </div>
                <div
                  v-for="(row, rIdx) in horizontalCalcRowsTotal"
                  :key="rIdx"
                  class="grid gap-0 border-b border-[color:var(--storefront-border,#f3f4f6)] min-w-[36rem] sm:min-w-0"
                  style="grid-template-columns: minmax(7rem,1.2fr) minmax(5rem,1fr) minmax(5rem,1fr) minmax(4.5rem,0.9fr);"
                >
                  <div class="text-[color:var(--storefront-text,#374151)] px-2 py-2 align-top break-words">{{ row.label }}</div>
                  <div class="text-[color:var(--storefront-text,#111827)] tabular-nums text-right px-2 py-2 align-top">
                    {{ row.without }}
                  </div>
                  <div class="text-[color:var(--storefront-success-text,#064e3b)] tabular-nums text-right px-2 py-2 align-top bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/0.3)]">
                    {{ row.with }}
                  </div>
                  <div
                    class="tabular-nums text-right px-2 py-2 align-top font-medium"
                    :class="row.diffClass"
                  >
                    {{ row.diff }}
                  </div>
                </div>
              </div>
            </template>

            <template v-else-if="calcN">
              <div class="p-1 sm:p-3 space-y-2 text-sm w-full">
                <div class="flex justify-between gap-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Ежемесячный платёж</span>
                  <span class="font-semibold text-[color:var(--storefront-text,#111827)] tabular-nums">{{ formatPrice(calcN.monthlyPayment) }}</span>
                </div>
                <div class="flex justify-between gap-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Аванс по договору</span>
                  <span class="font-medium tabular-nums text-right">{{ simpleAdvanceContractTotal }}</span>
                </div>
                <div class="flex justify-between gap-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Аванс клиента</span>
                  <span class="font-medium tabular-nums text-right">{{ simpleAdvanceClientTotal }}</span>
                </div>
                <div class="flex justify-between gap-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Сумма договора</span>
                  <span class="font-medium tabular-nums">{{ formatPrice(calcN.totalCost) }}</span>
                </div>
                <template v-if="hasSupportInCalculation && supportFromApiN && (supportFromApiN.vehicle_discount_support || 0) + (supportFromApiN.down_payment_support || 0) + (supportFromApiN.interest_support || 0) > 0">
                  <div class="pt-2 mt-2 border-t border-[color:var(--storefront-border,#e5e7eb)] text-xs font-medium text-[color:var(--storefront-text-muted,#6b7280)]">Учтено в расчёте:</div>
                  <div v-if="(supportFromApiN.vehicle_discount_support || 0) > (supportFromApiN.dealer_commission_support || 0)" class="flex justify-between">
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка на ТС</span>
                    <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApiN.vehicle_discount_support - (supportFromApiN.dealer_commission_support || 0)) }}</span>
                  </div>
                  <div v-if="(supportFromApiN.dealer_commission_support || 0) > 0" class="flex justify-between">
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Комиссия дилеру (уменьш. счёта)</span>
                    <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApiN.dealer_commission_support) }}</span>
                  </div>
                  <div v-if="(supportFromApiN.down_payment_support || 0) > 0" class="flex justify-between">
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка первого взноса</span>
                    <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApiN.down_payment_support) }}</span>
                  </div>
                  <div v-if="(supportFromApiN.interest_support || 0) > 0" class="flex justify-between">
                    <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Поддержка процентов</span>
                    <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApiN.interest_support) }}</span>
                  </div>
                </template>
                <div v-else-if="hasSupportInCalculation && hasSupport && supportDisplayAmountTotal > 0" class="flex justify-between pt-2 mt-2 border-t border-[color:var(--storefront-border,#e5e7eb)]">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">{{ supportRowLabel }}</span>
                  <span class="font-medium text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportDisplayAmountTotal) }}</span>
                </div>
              </div>
            </template>
          </div>

          <!-- Подробные характеристики (раскрываемый блок) -->
          <div class="border border-[color:var(--storefront-border,#e5e7eb)] rounded-lg overflow-hidden">
            <button
              type="button"
              class="storefront-action-ghost w-full flex items-center justify-between p-3 text-left text-sm font-medium text-[color:var(--storefront-ghost-foreground,#374151)] bg-[color:rgb(var(--storefront-ghost-rgb,249_250_251)/var(--tw-bg-opacity,1))] hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,243_244_246)/var(--tw-bg-opacity,1))]"
              @click="detailsExpanded = !detailsExpanded"
            >
              <span>Подробные характеристики</span>
              <svg
                class="w-5 h-5 text-[color:var(--storefront-ghost-icon,#6b7280)] transition-transform"
                :class="{ 'rotate-180': detailsExpanded }"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
              </svg>
            </button>
            <div v-show="detailsExpanded" class="p-3 border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-sm text-[color:var(--storefront-text-muted,#4b5563)] space-y-1">
              <p v-if="item?.mark_name"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Марка:</span> {{ item.mark_name }}</p>
              <p v-if="item?.model_name"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Модель:</span> {{ item.model_name }}</p>
              <p v-if="item?.group_name"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Комплектация:</span> {{ item.group_name }}</p>
              <p v-if="item?.vin"><span class="font-medium text-[color:var(--storefront-text,#374151)]">VIN:</span> {{ item.vin }}</p>
              <p v-if="item?.color"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Цвет:</span> {{ item.color }}</p>
              <p v-if="item?.year"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Год:</span> {{ item.year }}</p>
              <p><span class="font-medium text-[color:var(--storefront-text,#374151)]">Цена за 1 ТС:</span> {{ formatPrice(pricePerUnit) }}</p>
              <p v-if="item?.comment"><span class="font-medium text-[color:var(--storefront-text,#374151)]">Комментарий:</span> {{ item.comment }}</p>
            </div>
          </div>

          <!-- Отправить на почту (форма) -->
          <div v-if="showEmailForm" class="p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] space-y-2">
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)]">Email для отправки</label>
            <input
              v-model="emailToSend"
              type="email"
              placeholder="email@example.com"
              class="storefront-control w-full px-3 py-2 border border-[color:var(--storefront-border,#d1d5db)] rounded-lg text-sm focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:border-[color:var(--storefront-border,#3b82f6)]"
            >
            <div class="flex gap-2">
              <button
                type="button"
                class="storefront-action-ghost px-3 py-1.5 text-sm font-medium text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)]"
                @click="showEmailForm = false"
              >
                Отмена
              </button>
              <button
                type="button"
                class="storefront-action-primary px-3 py-1.5 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] rounded-lg hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:opacity-50"
                :disabled="sendingEmail || !emailToSend"
                @click="sendByEmail"
              >
                {{ sendingEmail ? 'Отправка...' : 'Отправить' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Footer: PDF и Email -->
        <div class="flex flex-wrap items-center gap-2 p-4 border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]">
          <button
            type="button"
            class="storefront-action-ghost px-4 py-2 text-sm font-medium text-[color:var(--storefront-ghost-foreground,#ffffff)] bg-[color:rgb(var(--storefront-ghost-rgb,55_65_81)/var(--tw-bg-opacity,1))] rounded-lg hover:bg-[color:rgb(var(--storefront-ghost-hover-rgb,31_41_55)/var(--tw-bg-opacity,1))] disabled:opacity-50"
            :disabled="generatingPdf"
            @click="downloadPdf"
          >
            {{ generatingPdf ? 'Формирование...' : 'Скачать PDF' }}
          </button>
          <button
            type="button"
            class="storefront-action-ghost px-4 py-2 text-sm font-medium text-[color:var(--storefront-primary-foreground,#2563eb)] border border-[color:var(--storefront-primary-border,#bfdbfe)] rounded-lg hover:bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]"
            @click="showEmailForm = !showEmailForm"
          >
            Отправить на почту
          </button>
        </div>
      </div>
    </div>

  </Teleport>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import { imageBlobToPdfSafeDataUrl } from '~/features/cart/utils/pdfImage'
import {
  calculateAdvanceDifference,
  calculateSupportPaymentAmounts,
  formatSupportPercentDifference,
  supportComparisonRows,
} from '~/features/cart/utils/supportPaymentAmounts'
import { useCartSupportSelection } from '~/features/cart/composables/useCartSupportSelection'
import SupportProgramSelector from '~/components/support/SupportProgramSelector.vue'
import { normalizeSupportPrograms, type SupportBadgeProgram } from '~/types/support'
import type {
  CalculatorParams,
  CartSupportPerProgram,
  CartSupportProgramDetail,
  VehicleCalculationData,
} from '~/features/cart/types'
import type { CommerceCartLine } from '~/features/commerce/cartProjection'
import type { UUID } from '~/types/ids'

const props = defineProps<{
  show: boolean
  item: CommerceCartLine | null
  calculatorParams: CalculatorParams | null
  vehicleCalculationData: VehicleCalculationData | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'support-change'): void
}>()

type SummaryRow = { label: string; value: string }
type CalculationBlock = { title: string; rows: SummaryRow[] }

const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()
const toast = useToast()
const supportSelection = useCartSupportSelection()
const authStore = useAuthStore()

/** Бюллетени поддержки — CarCraft, дистрибьютор, лизинговая компания */
const canSeeSupportBulletins = computed(
  () =>
    authStore.isCarCraftEmployee || authStore.isDistributor || authStore.isLeasingCompany
)

const detailsExpanded = ref(false)
const loadingCalc1 = ref(false)
const generatingPdf = ref(false)
const showEmailForm = ref(false)
const emailToSend = ref('')
const sendingEmail = ref(false)

const vehicleTitle = computed(() => {
  if (!props.item) return ''
  return `${props.item.mark_name || ''} ${props.item.model_name || ''}`.trim()
})

const vehicleImagePath = computed(() => {
  return props.item?.image_url ?? null
})

const vehicleImageUrl = computed(() => {
  const imagePath = vehicleImagePath.value
  if (!imagePath) return null

  if (/^https?:\/\//.test(imagePath)) return imagePath

  const apiBase = String(config.public.apiBase || '').replace(/\/$/, '')
  if (apiBase) return `${apiBase}${imagePath}`

  if (typeof window !== 'undefined') {
    return `${window.location.origin}${imagePath}`
  }

  return imagePath
})

const quantity = computed(() => Math.max(1, Number(props.item?.quantity) || 1))

// Calculation data comes from the parent (CartLeasingCalculator via CartIndexPage).
// The parent makes a single request for all vehicles in the cart.
const calc1 = computed(() => props.vehicleCalculationData?.calculation ?? null)
const calc1WithoutDiscount = computed(() => props.vehicleCalculationData?.calculation_without_support ?? null)
const supportFromApi = computed(() => props.vehicleCalculationData?.support_breakdown ?? null)

// For N units: all monetary values scale linearly with quantity (same rate/term, proportional principal)
const calcN = computed(() => {
  if (!calc1.value || quantity.value <= 1) return null
  const c = calc1.value
  const n = quantity.value
  return {
    monthlyPayment: Math.round(c.monthlyPayment * n),
    totalCost: Math.round(c.totalCost * n),
    totalInterest: Math.round((c.totalInterest || 0) * n),
    vatRefund: Math.round((c.vatRefund || 0) * n),
    profitTaxSavings: Math.round((c.profitTaxSavings || 0) * n),
    totalSavings: Math.round((c.totalSavings || 0) * n),
    buyoutAmount: Math.round((c.buyoutAmount || 0) * n),
    rate: c.rate,
    markup: Math.round((c.markup || 0) * n),
    markupPercent: c.markupPercent
  }
})
const calcNWithoutDiscount = computed(() => {
  if (!calc1WithoutDiscount.value || quantity.value <= 1) return null
  const c = calc1WithoutDiscount.value
  const n = quantity.value
  return {
    monthlyPayment: Math.round(c.monthlyPayment * n),
    totalCost: Math.round(c.totalCost * n),
    totalInterest: Math.round((c.totalInterest || 0) * n),
    vatRefund: Math.round((c.vatRefund || 0) * n),
    profitTaxSavings: Math.round((c.profitTaxSavings || 0) * n),
    totalSavings: Math.round((c.totalSavings || 0) * n),
    buyoutAmount: Math.round((c.buyoutAmount || 0) * n),
    rate: c.rate,
    markup: Math.round((c.markup || 0) * n),
    markupPercent: c.markupPercent
  }
})
const supportFromApiN = computed(() => {
  if (!supportFromApi.value || quantity.value <= 1) return null
  const s = supportFromApi.value
  const n = quantity.value
  return {
    vehicle_discount_support: Math.round((s.vehicle_discount_support || 0) * n),
    dealer_commission_support: Math.round((s.dealer_commission_support || 0) * n),
    down_payment_support: Math.round((s.down_payment_support || 0) * n),
    interest_support: Math.round((s.interest_support || 0) * n)
  }
})

const pricePerUnit = computed(() => {
  if (!props.item) return 0
  return Number(props.item.custom_price) || Number(props.item.discount_price) || Number(props.item.base_price) || 0
})

const supportType = computed(() => props.item?.support_type || null)
const vehicleId = computed(() =>
  props.item?.ref.type === 'vehicle' ? props.item.ref.id : undefined,
)
const supportPerProgramFromApi = ref<CartSupportPerProgram[]>([])
const supportProgramDetailsFromApi = ref<CartSupportProgramDetail[]>([])
const eligibleProgramIdsForVehicle = ref<UUID[]>([])
type SelectedSupportProgramRow = {
  support_program_id: UUID
  type: string | null
  amount?: number
}

const supportProgramsForVehicle = ref<SelectedSupportProgramRow[]>([])
const availableSupportPrograms = computed<SupportBadgeProgram[]>(() => {
  const id = vehicleId.value
  const fromCalculation = supportProgramDetailsFromApi.value.filter(program => (
    program.vehicle_id == null || program.vehicle_id === id
  ))
  return normalizeSupportPrograms([
    ...(props.item?.applicable_support_programs || []),
    ...fromCalculation,
  ])
})
const selectedSupportIds = computed<UUID[]>(() => {
  const id = vehicleId.value
  return id
    ? supportSelection.getSelectionForVehicle(id).selected_support_ids
    : []
})

function supportPaymentAmountsForQuantity(quantity = 1) {
  const support = supportFromApi.value
  return calculateSupportPaymentAmounts({
    unitPrice: pricePerUnit.value,
    quantity,
    downPaymentPercent: downPaymentPercent.value,
    vehicleDiscountSupport: Number(support?.vehicle_discount_support) || 0,
    downPaymentSupport: Number(support?.down_payment_support) || 0,
    interestSupport: Number(support?.interest_support) || 0,
  })
}

// Sync refs from vehicleCalculationData prop when it updates
watch(() => props.vehicleCalculationData, (data) => {
  supportPerProgramFromApi.value = data?.support_per_program ?? []
  supportProgramDetailsFromApi.value = data?.support_program_details ?? []
  const newEligibleIds = data?.eligible_program_ids
  eligibleProgramIdsForVehicle.value = newEligibleIds ?? []
  const id = vehicleId.value
  if (id) {
    supportSelection.ensureProgramsApplied(id, newEligibleIds)
  }
  updateSupportProgramsForVehicle()
}, { immediate: true, deep: false })

/** Есть ли фактически учтённая поддержка в текущем расчёте (по ответу бэкенда, а не по флагу в товаре). */
const hasSupportInCalculation = computed(() => {
  // если бэк вернул breakdown или ненулевую сумму поддержки — считаем, что поддержка есть
  if (supportFromApi.value && supportApiAmountPerUnit.value > 0) return true
  // либо если есть per-program данные с ненулевой суммой по этому ТС
  const id = vehicleId.value
  if (!id) return false
  for (const prog of supportPerProgramFromApi.value || []) {
    const perVeh = prog.per_vehicle?.find((vehicle) => vehicle.vehicle_id === id)
    if (perVeh && Number(perVeh.support_amount) > 0) return true
  }
  return false
})
/**
 * Сумма поддержки по support_params: для value_type=percent — min/max в рублях;
 * для фиксированной суммы — пол min_percent/max_percent от базы; затем clamp к базе.
 */
function computeSupportFromParams(params: Record<string, unknown> | null, baseAmount: number): number {
  if (!params || typeof params !== 'object' || baseAmount <= 0) return 0
  const value = Number(params.value)
  if (value <= 0) return 0
  const valueType = params.value_type === 'percent' ? 'percent' : 'amount'
  let support: number
  if (valueType === 'percent') {
    support = Math.round((baseAmount * value) / 100)
    const minAmount = params.min_amount != null ? Number(params.min_amount) : null
    const maxAmount = params.max_amount != null ? Number(params.max_amount) : null
    if (minAmount != null && support < minAmount) support = minAmount
    if (maxAmount != null && support > maxAmount) support = maxAmount
  } else {
    support = value
    const minPct = params.min_percent != null ? Number(params.min_percent) : null
    const maxPct = params.max_percent != null ? Number(params.max_percent) : null
    const floor = minPct != null ? Math.round((baseAmount * minPct) / 100) : null
    const cap = maxPct != null ? Math.round((baseAmount * maxPct) / 100) : null
    if (floor != null && support < floor) support = floor
    if (cap != null && support > cap) support = cap
  }
  if (support > baseAmount) support = baseAmount
  return Math.max(0, Math.round(support))
}

/** Сумма поддержки на 1 ТС из разницы цен (базовая − цена с учётом поддержки). */
const supportAmountPerUnit = computed(() => {
  if (!props.item) return 0
  const base = Number(props.item.base_price) || 0
  const withSupport = Number(props.item.custom_price) || Number(props.item.discount_price) || 0
  if (withSupport <= 0 || base <= 0 || withSupport >= base) return 0
  return base - withSupport
})

/** База для расчёта поддержки по типу: для поддержки первого взноса — аванс по договору. */
const supportBaseAmountPerUnit = computed(() => {
  const basePrice = Number(props.item?.base_price) || 0
  const pct = downPaymentPercent.value
  if (supportType.value === 'down_payment_compensation') {
    const vehicleDiscount = supportFromApi.value
      ? Number(supportFromApi.value.vehicle_discount_support) || 0
      : 0
    const effectivePrice = Math.max(0, basePrice - vehicleDiscount)
    return Math.round((effectivePrice * pct) / 100)
  }
  return basePrice
})

/** Сумма поддержки на 1 ТС из параметров программы с учётом мин/макс по сумме и проценту. */
const supportAmountFromParamsPerUnit = computed(() => {
  const params = props.item?.support_params
  if (!params || typeof params !== 'object') return 0
  const base = supportBaseAmountPerUnit.value
  if (base <= 0) return 0
  return computeSupportFromParams(params as Record<string, unknown>, base)
})

/** Сумма поддержки из ответа бэкенда (сумма всех компонентов на 1 ТС). */
const supportApiAmountPerUnit = computed(() => {
  const s = supportFromApi.value
  if (!s) return 0
  return (Number(s.vehicle_discount_support) || 0) + (Number(s.down_payment_support) || 0) + (Number(s.interest_support) || 0)
})

/** Итоговая сумма поддержки на 1 ТС для отображения: приоритет — данные с бэкенда, затем клиентский расчёт. */
const supportDisplayAmountPerUnit = computed(() => supportApiAmountPerUnit.value || supportAmountPerUnit.value || supportAmountFromParamsPerUnit.value)
const supportDisplayAmountTotal = computed(() => supportDisplayAmountPerUnit.value * quantity.value)

const hasSupport = computed(() => Boolean(props.item?.has_support))

const supportProgramInfo = computed(() => {
  const info = props.item?.support_program_info
  if (!info || typeof info !== 'object') return null
  return info
})

function formatSupportDate(value: string | null | undefined): string {
  if (value == null) return ''
  const s = value.slice(0, 10)
  if (!s) return ''
  return s
}

function getProgramDetails(programId: UUID): {
  id: UUID
  name: string | null
  bill_of_lading: unknown | null
} | undefined {
  const fromApi = supportProgramDetailsFromApi.value.find((program) => program.id === programId)
  if (fromApi) {
    return {
      id: fromApi.id,
      name: fromApi.name || null,
      bill_of_lading: fromApi.bill_of_lading || null
    }
  }

  // Фоллбек: если по какой-то причине детали не пришли из калькулятора,
  // используем support_program_info из самого товара (хотя там обычно только одна программа).
  const info = props.item?.support_program_info
  if (info && (info.name || info.bill_of_lading)) {
    return {
      id: programId,
      name: info.name || null,
      bill_of_lading: info.bill_of_lading || null
    }
  }

  return undefined
}

type BillOfLadingFile = {
  id?: UUID
  bill_date?: string
  file_name?: string
  file_path?: string
  file_size?: number
}

type BillOfLading = BillOfLadingFile & {
  files?: BillOfLadingFile[]
  comment?: string
}

function getBillOfLadingFiles(programId: UUID): BillOfLadingFile[] {
  const details = getProgramDetails(programId)
  const bol = details?.bill_of_lading as BillOfLading | null | undefined
  if (!bol) return []

  if (Array.isArray(bol.files)) {
    return bol.files.filter((file) => file && (file.file_path || file.file_name || file.bill_date))
  }

  if (bol.file_path || bol.file_name || bol.bill_date) {
    return [bol]
  }

  return []
}

/** Дата бюллетеня (дата проведения) в формате ДД.ММ.ГГГГ */
function formatBillDateRu(value: string | null | undefined): string {
  if (value == null) return ''
  const s = value.slice(0, 10)
  if (!s) return ''
  const parts = s.split('-')
  if (parts.length >= 3) {
    const [y, m, day] = parts
    return `${day}.${m}.${y}`
  }
  return s
}

/** Уникальные даты проведения по бюллетеням программы (для блока «Поддержка для этого ТС»). */
function getBillConductionLineParts(
  programId: UUID
): { label: string; dates: string } | null {
  const files = getBillOfLadingFiles(programId)
  const raw = files
    .map((f) => f.bill_date)
    .filter((date): date is string => Boolean(date))
    .map((date) => date.slice(0, 10))
  const unique = [...new Set(raw)].sort()
  if (unique.length === 0) return null
  const dates = unique.map(formatBillDateRu).join(', ')
  const label = unique.length > 1 ? 'Даты проведения: ' : 'Дата проведения: '
  return { label, dates }
}

function conductForProgram(programId: UUID): Array<{ label: string; dates: string }> {
  const c = getBillConductionLineParts(programId)
  return c ? [c] : []
}

function getBillOfLadingComment(programId: UUID): string {
  const details = getProgramDetails(programId)
  const bol = details?.bill_of_lading as BillOfLading | null | undefined
  if (!bol) return ''

  if (typeof bol.comment === 'string' && bol.comment.trim()) {
    return bol.comment.trim()
  }

  return ''
}

function getBillOfLadingFileUrl(file: { file_path?: string | null }): string | null {
  const path = file?.file_path
  if (!path) return null
  if (/^https?:\/\//.test(path)) return path
  const apiBase = String(config.public.apiBase || '').replace(/\/$/, '')
  return apiBase ? `${apiBase}${path}` : path
}

const isProgramSelected = (programId: UUID): boolean => {
  const id = vehicleId.value
  return Boolean(id && supportSelection.getSelectionForVehicle(id).selected_support_ids.includes(programId))
}

const programCompatibilityError = (programId: UUID): string | null => {
  const id = vehicleId.value
  if (!id || isProgramSelected(programId)) return null
  return supportSelection.compatibilityError(id, programId, availableSupportPrograms.value)
}

function toggleSupport(programId: UUID) {
  const id = vehicleId.value
  if (!id) return
  const error = supportSelection.setProgramEnabled(
    id,
    programId,
    !isProgramSelected(programId),
    availableSupportPrograms.value,
  )
  if (error) return
  updateSupportProgramsForVehicle()
  emit('support-change')
}

function applySupportSelection(selectedIds: UUID[]) {
  const id = vehicleId.value
  if (!id) return
  const error = supportSelection.replacePrograms(
    id,
    selectedIds,
    availableSupportPrograms.value,
  )
  if (error) return
  updateSupportProgramsForVehicle()
  emit('support-change')
}

const supportRowLabel = computed(() => {
  const type = supportType.value
  if (type === 'down_payment_compensation') return 'Поддержка первого взноса'
  if (type === 'vehicle_discount_dealer_compensation') return 'Поддержка на ТС'
  if (type === 'leasing_interest_compensation') return 'Поддержка процентов'
  if (type === 'vehicle_discount_dealer_invoice') return 'Поддержка на ТС'
  return 'Поддержка по программе'
})

const getSupportTypeLabel = (type: string | null | undefined) => {
  const labels: Record<string, string> = {
    down_payment_compensation: 'Поддержка первого взноса',
    vehicle_discount_dealer_compensation: 'Поддержка на ТС (поддержка дилеру)',
    vehicle_discount_dealer_invoice: 'Поддержка на ТС (уменьшение счёта)',
    leasing_interest_compensation: 'Поддержка процентов по лизингу'
  }
  if (!type) return 'Поддержка'
  return labels[type] || type
}

function updateSupportProgramsForVehicle() {
  const id = vehicleId.value
  if (!id) {
    supportProgramsForVehicle.value = []
    return
  }

  const sel = supportSelection.getSelectionForVehicle(id)
  const selectedIds = Array.isArray(sel.selected_support_ids) ? sel.selected_support_ids : []
  const programsFromApi = supportPerProgramFromApi.value || []

  supportProgramsForVehicle.value = selectedIds.map((pid) => {
    const prog = programsFromApi.find((program) => program.support_program_id === pid)
    const perVeh = prog?.per_vehicle?.find((vehicle) => vehicle.vehicle_id === id)
    return {
      support_program_id: pid,
      type: prog?.type ?? null,
      amount: perVeh ? Number(perVeh.support_amount) || 0 : undefined
    }
  })
}

const getSelectedSupportRow = (
  programId: UUID,
): SelectedSupportProgramRow | undefined => (
  supportProgramsForVehicle.value.find(
    program => program.support_program_id === programId,
  )
)

const downPaymentPercent = computed(() => props.calculatorParams?.down_payment_percent ?? 20)

function formatProgramPeriod(programId: UUID): string {
  const fromApi = supportProgramDetailsFromApi.value.find((program) => program.id === programId)
  const start = fromApi?.starts_at
  const end = fromApi?.ends_at
  if (!start && !end) return ''
  const fmt = (d: string | null | undefined) => {
    if (!d) return ''
    const s = d.slice(0, 10)
    const parts = s.split('-')
    if (parts.length >= 3) {
      const [y, m, day] = parts
      return `${day}.${m}.${y}`
    }
    return s
  }
  if (start && !end) return 'Бессрочный'
  if (!start && end) return `до ${fmt(end)}`
  return `${fmt(start)} — ${fmt(end)}`
}

type HorizontalCalcRow = {
  label: string
  without: string
  with: string
  diff: string
  diffClass: string
}

function diffMoneyClass(delta: number): string {
  if (delta === 0) return 'text-[color:var(--storefront-text,#1f2937)]'
  return delta > 0 ? 'text-[color:var(--storefront-error-text,#dc2626)]' : 'text-[color:var(--storefront-success-text,#16a34a)]'
}

function formatDiffRubles(delta: number): { text: string; diffClass: string } {
  if (delta === 0) return { text: '—', diffClass: 'text-[color:var(--storefront-text,#1f2937)]' }
  const sign = delta > 0 ? '+' : '−'
  const abs = Math.abs(Math.round(delta))
  return {
    text: `${sign}${formatPrice(abs)}`,
    diffClass: diffMoneyClass(delta)
  }
}

function formatAdvanceDifference(
  withoutAmount: number,
  withAmount: number,
  withoutPercent: number,
  withPercent: number,
): { text: string; diffClass: string } {
  const difference = calculateAdvanceDifference(
    withoutAmount,
    withAmount,
    withoutPercent,
    withPercent,
  )
  const amount = difference.amountDelta === 0
    ? ''
    : formatDiffRubles(difference.amountDelta).text
  const percentDifference = formatSupportPercentDifference(
    difference.percentDelta,
  )
  const percent = percentDifference.text === '—'
    ? ''
    : percentDifference.text
  if (!amount && !percent) {
    return { text: '—', diffClass: 'text-[color:var(--storefront-text,#1f2937)]' }
  }
  return {
    text: amount && percent ? `${amount} (${percent})` : amount || percent,
    diffClass: difference.amountDelta === 0
      ? percentDifference.diffClass
      : diffMoneyClass(difference.amountDelta),
  }
}

function buildSupportComparisonRows(
  support: Parameters<typeof supportComparisonRows>[0],
): HorizontalCalcRow[] {
  return supportComparisonRows(support).map(row => ({
    label: row.label,
    without: '—',
    with: formatPrice(row.amount),
    diff: `+${formatPrice(row.amount)}`,
    diffClass: 'text-[color:var(--storefront-success-text,#16a34a)]',
  }))
}

const horizontalCalcRows = computed((): HorizontalCalcRow[] | null => {
  if (!hasSupportInCalculation.value || !calc1.value || !calc1WithoutDiscount.value) return null
  const wo = calc1WithoutDiscount.value
  const w = calc1.value
  const s = supportFromApi.value
  const amounts = supportPaymentAmountsForQuantity()
  if (!s || amounts.baseTotal <= 0) return null

  const baseDownWo = amounts.contractDownPayment
  const pctWo = downPaymentPercent.value
  const baseDownWith = Number.isFinite(Number(s.contract_down_payment))
    ? Number(s.contract_down_payment)
    : amounts.contractDownPayment
  const pctWith = amounts.contractDownPaymentPercent
  const effDownV = Number.isFinite(Number(s.client_down_payment))
    ? Number(s.client_down_payment)
    : amounts.clientDownPayment
  const pctClient = amounts.clientDownPaymentPercent
  const propertyWithout = amounts.baseTotal
  const propertyWith = amounts.effectiveTotal
  const dProperty = formatDiffRubles(propertyWith - propertyWithout)

  const dMonthly = formatDiffRubles(w.monthlyPayment - wo.monthlyPayment)
  const dContractAdv = formatAdvanceDifference(baseDownWo, baseDownWith, pctWo, pctWith)
  const dClientAdv = formatAdvanceDifference(baseDownWo, effDownV, pctWo, pctClient)
  const dTotal = formatDiffRubles(w.totalCost - wo.totalCost)

  return [
    {
      label: 'Ежемесячный платёж',
      without: formatPrice(wo.monthlyPayment),
      with: formatPrice(w.monthlyPayment),
      diff: dMonthly.text,
      diffClass: dMonthly.diffClass
    },
    {
      label: 'Аванс по договору',
      without: `${formatPrice(baseDownWo)} (${pctWo}%)`,
      with: `${formatPrice(baseDownWith)} (${pctWith}%)`,
      diff: dContractAdv.text,
      diffClass: dContractAdv.diffClass
    },
    {
      label: 'Аванс клиента',
      without: `${formatPrice(baseDownWo)} (${pctWo}%)`,
      with: `${formatPrice(effDownV)} (${pctClient}%)`,
      diff: dClientAdv.text,
      diffClass: dClientAdv.diffClass
    },
    ...buildSupportComparisonRows(s),
    {
      label: 'Стоимость имущества',
      without: formatPrice(propertyWithout),
      with: formatPrice(propertyWith),
      diff: dProperty.text,
      diffClass: dProperty.diffClass
    },
    {
      label: 'Сумма договора',
      without: formatPrice(wo.totalCost),
      with: formatPrice(w.totalCost),
      diff: dTotal.text,
      diffClass: dTotal.diffClass
    }
  ]
})

/** Та же таблица, но итоги по quantity > 1 (все ТС этой позиции) */
const horizontalCalcRowsTotal = computed((): HorizontalCalcRow[] | null => {
  const n = quantity.value
  if (n <= 1) return null
  if (!hasSupportInCalculation.value || !calcN.value || !calcNWithoutDiscount.value) return null
  const wo = calcNWithoutDiscount.value
  const w = calcN.value
  const s = supportFromApiN.value
  const amounts = supportPaymentAmountsForQuantity(n)
  if (!s || amounts.baseTotal <= 0) return null

  const baseDownWo = amounts.contractDownPayment
  const pctWo = downPaymentPercent.value
  const baseDownWith = amounts.contractDownPayment
  const pctWith = amounts.contractDownPaymentPercent
  const effDownV = amounts.clientDownPayment
  const pctClient = amounts.clientDownPaymentPercent
  const propertyWithout = amounts.baseTotal
  const propertyWith = amounts.effectiveTotal
  const dProperty = formatDiffRubles(propertyWith - propertyWithout)

  const dMonthly = formatDiffRubles(w.monthlyPayment - wo.monthlyPayment)
  const dContractAdv = formatAdvanceDifference(baseDownWo, baseDownWith, pctWo, pctWith)
  const dClientAdv = formatAdvanceDifference(baseDownWo, effDownV, pctWo, pctClient)
  const dTotal = formatDiffRubles(w.totalCost - wo.totalCost)

  return [
    {
      label: 'Ежемесячный платёж',
      without: formatPrice(wo.monthlyPayment),
      with: formatPrice(w.monthlyPayment),
      diff: dMonthly.text,
      diffClass: dMonthly.diffClass
    },
    {
      label: 'Аванс по договору',
      without: `${formatPrice(baseDownWo)} (${pctWo}%)`,
      with: `${formatPrice(baseDownWith)} (${pctWith}%)`,
      diff: dContractAdv.text,
      diffClass: dContractAdv.diffClass
    },
    {
      label: 'Аванс клиента',
      without: `${formatPrice(baseDownWo)} (${pctWo}%)`,
      with: `${formatPrice(effDownV)} (${pctClient}%)`,
      diff: dClientAdv.text,
      diffClass: dClientAdv.diffClass
    },
    ...buildSupportComparisonRows(s),
    {
      label: 'Стоимость имущества',
      without: formatPrice(propertyWithout),
      with: formatPrice(propertyWith),
      diff: dProperty.text,
      diffClass: dProperty.diffClass
    },
    {
      label: 'Сумма договора',
      without: formatPrice(wo.totalCost),
      with: formatPrice(w.totalCost),
      diff: dTotal.text,
      diffClass: dTotal.diffClass
    }
  ]
})

const simpleAdvanceContract = computed(() => {
  if (!calc1.value || !props.item) return '—'
  const amounts = supportPaymentAmountsForQuantity()
  if (amounts.baseTotal <= 0) return '—'
  return `${formatPrice(amounts.contractDownPayment)} (${amounts.contractDownPaymentPercent}%)`
})

const simpleAdvanceClient = computed(() => {
  if (!calc1.value || !props.item) return '—'
  if (!supportFromApi.value) return simpleAdvanceContract.value
  const amounts = supportPaymentAmountsForQuantity()
  return `${formatPrice(amounts.clientDownPayment)} (${amounts.clientDownPaymentPercent}%)`
})

const simpleAdvanceContractTotal = computed(() => {
  if (!calcN.value || !props.item || quantity.value <= 1) return '—'
  const amounts = supportPaymentAmountsForQuantity(quantity.value)
  if (amounts.baseTotal <= 0) return '—'
  return `${formatPrice(amounts.contractDownPayment)} (${amounts.contractDownPaymentPercent}%)`
})

const simpleAdvanceClientTotal = computed(() => {
  if (!calcN.value || !props.item || quantity.value <= 1) return '—'
  if (!supportFromApi.value) return simpleAdvanceContractTotal.value
  const amounts = supportPaymentAmountsForQuantity(quantity.value)
  return `${formatPrice(amounts.clientDownPayment)} (${amounts.clientDownPaymentPercent}%)`
})
const leaseTerm = computed(() => props.calculatorParams?.lease_term_months ?? 36)
const buyoutPercent = computed(() => props.calculatorParams?.buyout_percent ?? 0)

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function buildSummaryData() {
  const details: SummaryRow[] = []

  if (props.item?.mark_name) details.push({ label: 'Марка', value: String(props.item.mark_name) })
  if (props.item?.model_name) details.push({ label: 'Модель', value: String(props.item.model_name) })
  if (props.item?.group_name) details.push({ label: 'Комплектация', value: String(props.item.group_name) })
  if (props.item?.vin) details.push({ label: 'VIN', value: String(props.item.vin) })
  if (props.item?.color) details.push({ label: 'Цвет', value: String(props.item.color) })
  if (props.item?.year) details.push({ label: 'Год', value: String(props.item.year) })

  details.push({ label: 'Цена за 1 ТС', value: formatPrice(pricePerUnit.value) })

  if (props.item?.comment) {
    details.push({ label: 'Комментарий', value: String(props.item.comment) })
  }

  const rowsFromHorizontal = horizontalCalcRows.value?.length
    ? horizontalCalcRows.value.map((row) => ({
        label: row.label,
        value: `без: ${row.without}; с: ${row.with}; разница: ${row.diff}`
      }))
    : null

  const rows1 = calc1.value
    ? rowsFromHorizontal
      ? rowsFromHorizontal
      : hasSupportInCalculation.value && calc1WithoutDiscount.value
        ? [
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Ежемесячный платёж (без поддержки)' : 'Ежемесячный платёж (без поддержки)',
              value: formatPrice(calc1WithoutDiscount.value.monthlyPayment)
            },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Ежемесячный платёж (с поддержкой)' : 'Ежемесячный платёж (с поддержкой)',
              value: formatPrice(calc1.value.monthlyPayment)
            },
            { label: 'Первоначальный взнос', value: `${downPaymentPercent.value}%` },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Сумма договора (без поддержки)' : 'Сумма договора (без поддержки)',
              value: formatPrice(calc1WithoutDiscount.value.totalCost)
            },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Сумма договора (с поддержкой)' : 'Сумма договора (с поддержкой)',
              value: formatPrice(calc1.value.totalCost)
            }
          ]
        : [
            { label: 'Ежемесячный платёж', value: formatPrice(calc1.value.monthlyPayment) },
            { label: 'Первоначальный взнос', value: `${downPaymentPercent.value}%` },
            { label: 'Сумма договора', value: formatPrice(calc1.value.totalCost) },
            ...(supportFromApi.value && supportApiAmountPerUnit.value > 0
              ? [
                  ...((supportFromApi.value.vehicle_discount_support || 0) > (supportFromApi.value.dealer_commission_support || 0) ? [{ label: 'Поддержка на ТС', value: formatPrice((supportFromApi.value.vehicle_discount_support || 0) - (supportFromApi.value.dealer_commission_support || 0)) }] : []),
                  ...((supportFromApi.value.dealer_commission_support || 0) > 0 ? [{ label: 'Комиссия дилеру', value: formatPrice(supportFromApi.value.dealer_commission_support) }] : []),
                  ...((supportFromApi.value.down_payment_support || 0) > 0 ? [{ label: 'Поддержка первого взноса', value: formatPrice(supportFromApi.value.down_payment_support) }] : []),
                  ...((supportFromApi.value.interest_support || 0) > 0 ? [{ label: 'Поддержка процентов', value: formatPrice(supportFromApi.value.interest_support) }] : []),
                ]
              : hasSupportInCalculation.value && supportDisplayAmountPerUnit.value > 0
                ? [{ label: supportRowLabel.value, value: formatPrice(supportDisplayAmountPerUnit.value) }]
                : [])
          ]
    : [{ label: 'Статус', value: 'Нет данных расчета' }]

  const calculations: CalculationBlock[] = [{ title: 'Расчёт (1 ТС)', rows: rows1 }]

  if (quantity.value > 1) {
    const rowsFromHorizontalTotal = horizontalCalcRowsTotal.value?.length
      ? horizontalCalcRowsTotal.value.map((row) => ({
          label: row.label,
          value: `без: ${row.without}; с: ${row.with}; разница: ${row.diff}`
        }))
      : null

    if (rowsFromHorizontalTotal) {
      calculations.push({ title: `Расчёт (${quantity.value} ТС)`, rows: rowsFromHorizontalTotal })
    } else if (calcN.value) {
      const rowsN = hasSupportInCalculation.value && calcNWithoutDiscount.value
        ? [
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Ежемесячный платёж (без поддержки)' : 'Ежемесячный платёж (без поддержки)',
              value: formatPrice(calcNWithoutDiscount.value.monthlyPayment)
            },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Ежемесячный платёж (с поддержкой)' : 'Ежемесячный платёж (с поддержкой)',
              value: formatPrice(calcN.value.monthlyPayment)
            },
            { label: 'Первоначальный взнос', value: `${downPaymentPercent.value}%` },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Сумма договора (без поддержки)' : 'Сумма договора (без поддержки)',
              value: formatPrice(calcNWithoutDiscount.value.totalCost)
            },
            {
              label: supportProgramsForVehicle.value.length > 1 ? 'Сумма договора (с поддержкой)' : 'Сумма договора (с поддержкой)',
              value: formatPrice(calcN.value.totalCost)
            }
          ]
        : [
            { label: 'Ежемесячный платёж', value: formatPrice(calcN.value.monthlyPayment) },
            { label: 'Первоначальный взнос', value: `${downPaymentPercent.value}%` },
            { label: 'Сумма договора', value: formatPrice(calcN.value.totalCost) },
            ...(supportFromApiN.value && ((supportFromApiN.value.vehicle_discount_support || 0) + (supportFromApiN.value.down_payment_support || 0) + (supportFromApiN.value.interest_support || 0)) > 0
              ? [
                  ...((supportFromApiN.value.vehicle_discount_support || 0) > (supportFromApiN.value.dealer_commission_support || 0) ? [{ label: 'Поддержка на ТС', value: formatPrice(supportFromApiN.value.vehicle_discount_support - (supportFromApiN.value.dealer_commission_support || 0)) }] : []),
                  ...((supportFromApiN.value.dealer_commission_support || 0) > 0 ? [{ label: 'Комиссия дилеру', value: formatPrice(supportFromApiN.value.dealer_commission_support) }] : []),
                  ...((supportFromApiN.value.down_payment_support || 0) > 0 ? [{ label: 'Поддержка первого взноса', value: formatPrice(supportFromApiN.value.down_payment_support) }] : []),
                  ...((supportFromApiN.value.interest_support || 0) > 0 ? [{ label: 'Поддержка процентов', value: formatPrice(supportFromApiN.value.interest_support) }] : []),
                ]
              : hasSupportInCalculation.value && supportDisplayAmountTotal.value > 0
                ? [{ label: supportRowLabel.value, value: formatPrice(supportDisplayAmountTotal.value) }]
                : [])
          ]
      calculations.push({ title: `Расчёт (${quantity.value} ТС)`, rows: rowsN })
    }
  }

  return {
    title: 'Расчет',
    vehicleTitle: vehicleTitle.value,
    imageUrl: vehicleImageUrl.value,
    priceLine: `Цена за 1 ТС: ${formatPrice(pricePerUnit.value)}`,
    leaseTerm: `${leaseTerm.value} мес.`,
    buyoutPercent: `${buyoutPercent.value}%`,
    calculations,
    details
  }
}

function close() {
  emit('close')
}

async function getVehicleImageDataUrl() {
  const imageUrl = vehicleImageUrl.value
  if (!imageUrl) return null

  try {
    const response = await fetch(imageUrl, { credentials: 'include' })
    if (!response.ok) return null

    const blob = await response.blob()
    return await imageBlobToPdfSafeDataUrl(blob)
  } catch (error) {
    console.error('Image load error:', error)
    return null
  }
}

async function downloadPdf() {
  generatingPdf.value = true
  try {
    const pdfMake = await import('pdfmake/build/pdfmake')
    const pdfFonts = await import('pdfmake/build/vfs_fonts')
    const pdfMakeInstance = pdfMake.default || pdfMake
    if (pdfFonts.pdfMake?.vfs) pdfMakeInstance.vfs = pdfFonts.pdfMake.vfs
    else if (pdfFonts.default) pdfMakeInstance.vfs = pdfFonts.default
    else throw new Error('Шрифты PDF не загружены')

    const summary = buildSummaryData()
    const imageDataUrl = await getVehicleImageDataUrl()
    const content: any[] = [
      { text: summary.title, style: 'header', alignment: 'center' },
      { text: '\n' },
      {
        columns: [
          imageDataUrl
            ? { image: imageDataUrl, fit: [140, 90], margin: [0, 0, 12, 0] }
            : { text: '', width: 0 },
          {
            width: '*',
            stack: [
              { text: summary.vehicleTitle || 'Автомобиль', style: 'subheader' },
              { text: summary.priceLine, style: 'normal' },
              { text: `Срок договора: ${summary.leaseTerm}`, style: 'normal' },
              { text: `Выкупная стоимость: ${summary.buyoutPercent}`, style: 'normal' }
            ]
          }
        ]
      },
      { text: '\n' }
    ]

    for (const block of summary.calculations) {
      content.push({ text: block.title, style: 'sectionHeader' })
      for (const row of block.rows) {
        content.push({
          columns: [
            { text: row.label, style: 'label' },
            { text: row.value, style: 'value', alignment: 'right' }
          ],
          margin: [0, 0, 0, 4]
        })
      }
      content.push({ text: '\n' })
    }

    content.push({ text: 'Подробные характеристики', style: 'sectionHeader' })
    for (const row of summary.details) {
      content.push({
        columns: [
          { text: row.label, style: 'label' },
          { text: row.value, style: 'value', alignment: 'right' }
        ],
        margin: [0, 0, 0, 4]
      })
    }

    const doc = pdfMakeInstance.createPdf({
      pageSize: 'A4',
      pageMargins: [36, 36, 36, 36],
      content,
      styles: {
        header: { fontSize: 18, bold: true, margin: [0, 0, 0, 10] },
        subheader: { fontSize: 13, bold: true, margin: [0, 0, 0, 6] },
        sectionHeader: { fontSize: 12, bold: true, margin: [0, 8, 0, 6] },
        normal: { fontSize: 10, margin: [0, 0, 0, 3] },
        label: { fontSize: 10, color: '#374151' },
        value: { fontSize: 10, bold: true, color: '#111827' }
      },
      defaultStyle: {
        fontSize: 10
      }
    })

    doc.getBlob((blob: Blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `raschet-${(props.item?.mark_name || 'vehicle').replace(/\s+/g, '-')}-${Date.now()}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    })
  } catch (e) {
    console.error('PDF error:', e)
    toast?.error?.('Не удалось сформировать PDF')
  } finally {
    generatingPdf.value = false
  }
}

function buildEmailText() {
  const summary = buildSummaryData()
  const lines: string[] = [
    `${summary.title}: ${summary.vehicleTitle}`,
    '',
    summary.priceLine,
    `Срок договора: ${summary.leaseTerm}`,
    `Выкупная стоимость: ${summary.buyoutPercent}`,
    ''
  ]

  for (const block of summary.calculations) {
    lines.push(`${block.title}:`)
    for (const row of block.rows) {
      lines.push(`${row.label}: ${row.value}`)
    }
    lines.push('')
  }

  lines.push('Подробные характеристики:')
  for (const row of summary.details) {
    lines.push(`${row.label}: ${row.value}`)
  }

  if (summary.imageUrl) {
    lines.push('', `Фото: ${summary.imageUrl}`)
  }

  return lines.join('\n')
}

function buildEmailHtml() {
  const summary = buildSummaryData()

  const calculationsHtml = summary.calculations
    .map((block) => {
      const rows = block.rows
        .map((row) => `
          <tr>
            <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
            <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
          </tr>
        `)
        .join('')

      return `
        <div style="margin: 0 0 16px 0; padding: 12px; border: 1px solid #e5e7eb; border-radius: 10px;">
          <div style="font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 8px;">${escapeHtml(block.title)}</div>
          <table style="width: 100%; border-collapse: collapse;">${rows}</table>
        </div>
      `
    })
    .join('')

  const detailsRows = summary.details
    .map((row) => `
      <tr>
        <td style="padding: 6px 0; color: #4b5563;">${escapeHtml(row.label)}</td>
        <td style="padding: 6px 0; color: #111827; font-weight: 600; text-align: right;">${escapeHtml(row.value)}</td>
      </tr>
    `)
    .join('')

  const imageHtml = summary.imageUrl
    ? `<img src="${escapeHtml(summary.imageUrl)}" alt="${escapeHtml(summary.vehicleTitle)}" style="width: 100%; max-width: 240px; border-radius: 10px; display: block; margin: 0 auto 12px auto; object-fit: contain; background: #f3f4f6;" />`
    : ''

  return `
    <div style="font-family: Arial, sans-serif; max-width: 680px; margin: 0 auto; color: #111827; background: #ffffff;">
      <div style="padding: 18px; border: 1px solid #e5e7eb; border-radius: 12px;">
        <h2 style="margin: 0 0 14px 0; font-size: 20px; text-align: center;">${escapeHtml(summary.title)}</h2>
        ${imageHtml}
        <div style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">${escapeHtml(summary.vehicleTitle)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">${escapeHtml(summary.priceLine)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 4px;">Срок договора: ${escapeHtml(summary.leaseTerm)}</div>
        <div style="font-size: 14px; color: #374151; margin-bottom: 14px;">Выкупная стоимость: ${escapeHtml(summary.buyoutPercent)}</div>

        ${calculationsHtml}

        <div style="margin-top: 4px; padding: 12px; border: 1px solid #e5e7eb; border-radius: 10px;">
          <div style="font-size: 14px; font-weight: 600; color: #111827; margin-bottom: 8px;">Подробные характеристики</div>
          <table style="width: 100%; border-collapse: collapse;">
            ${detailsRows}
          </table>
        </div>
      </div>
    </div>
  `
}

async function sendByEmail() {
  if (!emailToSend.value) return
  sendingEmail.value = true

  try {
    const text = buildEmailText()
    const html = buildEmailHtml()

    await $fetch('/api/v1/calculator/send-calculation-email', {
      method: 'POST',
      body: {
        to: emailToSend.value,
        subject: `Расчет лизинга: ${vehicleTitle.value}`,
        text,
        html
      },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    showEmailForm.value = false
    emailToSend.value = ''
    toast?.success?.('Расчет отправлен на указанный email')
  } catch (e: any) {
    console.error('Send email error:', e)
    toast?.error?.(e?.data?.error || 'Не удалось отправить письмо')
  } finally {
    sendingEmail.value = false
  }
}

watch(
  () => [props.show, props.item] as const,
  ([show, item]) => {
    if (show && item) {
      updateSupportProgramsForVehicle()
    }
  },
  { immediate: true }
)
</script>
