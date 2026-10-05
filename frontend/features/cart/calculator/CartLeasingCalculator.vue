<template>
  <div data-storefront-block="client.cart" class="space-y-2">
    <!-- Calculator Form -->
    <form @submit.prevent="calculate" class="space-y-3 sm:space-y-4">
      <div class="space-y-3 sm:space-y-4">
        <div>
          <h3 class="text-sm sm:text-base font-semibold text-[color:var(--storefront-title,#111827)] mb-2 sm:mb-3">
            Параметры расчета
          </h3>
        </div>

        <div class="p-2.5 sm:p-3 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex justify-between items-center gap-2">
            <span class="text-sm sm:text-base font-semibold text-[color:var(--storefront-text,#1f2937)] inline-flex items-center gap-1">
              Стоимость имущества
              <span
                class="inline-flex text-[color:var(--storefront-text-muted,#9ca3af)]"
                title="Эти параметры будут отправлены в лизинговую компанию вместе с заявкой"
              >
                <svg class="text-[color:var(--storefront-icon,inherit)] w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </span>
            </span>
            <span class="text-base sm:text-lg font-bold text-[color:var(--storefront-text,#111827)] tabular-nums">{{ formatPrice(totalAmount) }}</span>
          </div>
        </div>

        <!-- Down Payment -->
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex flex-col space-y-1.5 sm:space-y-2">
            <label class="text-sm sm:text-base font-semibold text-[color:var(--storefront-label,#1f2937)]">
              Первоначальный взнос
            </label>
            <div class="flex space-x-1.5 sm:space-x-2">
              <div
                class="flex items-center bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border-2 border-[color:var(--storefront-border,#e5e7eb)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] transition-colors flex-shrink-0">
                <input v-model.number="downPaymentPercent" @input="updateDownPaymentFromPercent" type="number" :min="minDownPaymentPercent"
                  max="49" step="1" class="storefront-control w-12 sm:w-16 px-1.5 sm:px-2 py-1.5 sm:py-2 rounded-lg focus:outline-none text-xs sm:text-sm font-medium text-center"
                  placeholder="20">
                <span class="px-1 text-[color:var(--storefront-text-muted,#4b5563)] font-medium text-xs sm:text-sm">%</span>
              </div>
              <div
                class="flex-1 flex items-center bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border-2 border-[color:var(--storefront-border,#e5e7eb)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] transition-colors min-w-0">
                <input v-model.number="downPaymentAmount" @input="updateDownPaymentFromAmount" type="number"
                  :min="minDownPayment" :max="props.totalAmount" step="10000"
                  class="storefront-control flex-1 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg focus:outline-none text-xs sm:text-sm font-medium min-w-0"
                  :placeholder="formatPrice(minDownPayment)">
                <span class="px-1.5 sm:px-2 text-[color:var(--storefront-text-muted,#4b5563)] font-medium text-xs sm:text-sm">₽</span>
              </div>
            </div>
          </div>
          <div class="mb-1.5 sm:mb-2 relative group">
            <div class="slider-container">
              <div
                v-if="downPaymentSupportPercent > 0"
                class="slider-support-zone"
                :style="{ width: downPaymentSupportSliderWidth }"
                :title="`${downPaymentSupportPercent}% поддержка первоначального взноса`"
              ></div>
              <input v-model.number="downPaymentPercent" @input="updateDownPaymentFromPercent" type="range" :min="minDownPaymentPercent"
                max="49" step="1" class="storefront-control w-full h-2.5 sm:h-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider" :style="sliderTrackStyle">
            </div>
            <div v-if="downPaymentSupportPercent > 0" class="support-tooltip">
              {{ downPaymentSupportPercent }}% поддержка первоначального взноса
            </div>
          </div>
          <div class="flex justify-between text-[10px] sm:text-xs text-[color:var(--storefront-text-muted,#4b5563)] font-medium">
            <span v-if="downPaymentSupportPercent > 0" class="text-[color:var(--storefront-success-text,#16a34a)] font-bold">{{ downPaymentSupportPercent }}%</span>
            <span v-else>0%</span>
            <span>15%</span>
            <span>20%</span>
            <span>40%</span>
            <span>49%</span>
          </div>
        </div>

        <!-- Lease Term -->
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex flex-col space-y-1.5 sm:space-y-2">
            <label class="text-sm sm:text-base font-semibold text-[color:var(--storefront-label,#1f2937)]">
              Срок договора
            </label>
            <div
              class="flex items-center bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border-2 border-[color:var(--storefront-border,#e5e7eb)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] transition-colors w-fit">
              <input v-model.number="leaseTerm" @change="normalizeLeaseTerm" @keydown.enter.prevent="normalizeLeaseTerm" type="number" min="12" max="84" step="6"
                class="storefront-control w-14 sm:w-20 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg focus:outline-none text-xs sm:text-sm font-medium text-center" placeholder="36">
              <span class="px-1.5 sm:px-2 text-[color:var(--storefront-text-muted,#4b5563)] font-medium text-xs sm:text-sm">{{ getMonthWord(leaseTerm) }}</span>
            </div>
          </div>
          <div class="mb-1.5 sm:mb-2">
            <input v-model.number="leaseTerm" @input="scheduleLeaseTermCalculation" type="range" min="12" max="84" step="6"
              class="storefront-control w-full h-2.5 sm:h-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider">
          </div>
          <div class="flex justify-between text-[10px] sm:text-xs text-[color:var(--storefront-text-muted,#4b5563)] font-medium">
            <span>1 год</span>
            <span>3 года</span>
            <span>5 лет</span>
            <span>7 лет</span>
          </div>
        </div>

        <!-- Buyout Amount -->
        <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)]">
          <div class="flex flex-col space-y-1.5 sm:space-y-2">
            <label class="text-sm sm:text-base font-semibold text-[color:var(--storefront-label,#1f2937)]">
              Выкупная стоимость
            </label>
            <div class="flex space-x-1.5 sm:space-x-2">
              <div
                class="flex items-center bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border-2 border-[color:var(--storefront-border,#e5e7eb)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] transition-colors flex-shrink-0">
                <input v-model.number="buyoutPercent" @input="updateBuyoutFromPercent" type="number" min="0" max="5"
                  step="1" class="storefront-control w-12 sm:w-16 px-1.5 sm:px-2 py-1.5 sm:py-2 rounded-lg focus:outline-none text-xs sm:text-sm font-medium text-center"
                  placeholder="0">
                <span class="px-1 text-[color:var(--storefront-text-muted,#4b5563)] font-medium text-xs sm:text-sm">%</span>
              </div>
              <div
                class="flex-1 flex items-center bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border-2 border-[color:var(--storefront-border,#e5e7eb)] focus-within:border-[color:var(--storefront-input-focus-border,#3b82f6)] transition-colors min-w-0">
                <input v-model.number="buyoutAmount" @input="updateBuyoutFromAmount" type="number" min="0"
                  :max="props.totalAmount" step="10000"
                  class="storefront-control flex-1 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg focus:outline-none text-xs sm:text-sm font-medium min-w-0" placeholder="0">
                <span class="px-1.5 sm:px-2 text-[color:var(--storefront-text-muted,#4b5563)] font-medium text-xs sm:text-sm">₽</span>
              </div>
            </div>
          </div>
          <div class="mb-1.5 sm:mb-2">
            <input v-model.number="buyoutPercent" @input="updateBuyoutFromPercent" type="range" min="0" max="5" step="1"
              class="storefront-control w-full h-2.5 sm:h-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] rounded-lg appearance-none cursor-pointer slider">
          </div>
          <div class="flex justify-between text-[10px] sm:text-xs text-[color:var(--storefront-text-muted,#4b5563)] font-medium">
            <span>0%</span>
            <span>1%</span>
            <span>3%</span>
            <span>5%</span>
          </div>
        </div>
      </div>
    </form>

    <div class="">
      <!-- Collapsible header -->
      <button 
        type="button"
        @click="resultsExpanded = !resultsExpanded"
        class="storefront-action-ghost w-full text-sm sm:text-base font-semibold text-[color:var(--storefront-ghost-foreground,#111827)] mb-2 sm:mb-3 mt-3 sm:mt-4 flex items-center justify-between cursor-pointer hover:text-[color:var(--storefront-ghost-hover-foreground,#374151)] transition-colors"
      >
        <span>Результат расчета</span>
        <svg 
          class="w-4 h-4 sm:w-5 sm:h-5 text-[color:var(--storefront-ghost-icon,#9ca3af)] transition-transform duration-200"
          :class="{ 'rotate-180': resultsExpanded }"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
      </button>

      <div v-if="calculation" class="space-y-2 sm:space-y-3">
        <!-- Two columns when direct support -->
        <template v-if="supportDisplayMode === 'direct' && calculationWithoutDiscount">
          <div class="grid grid-cols-3 gap-x-3 gap-y-1.5 text-sm">
            <div></div>
            <div class="font-medium text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</div>
            <div class="font-medium text-[color:var(--storefront-text-muted,#6b7280)] text-right">С поддержкой</div>
            <div class="text-[color:var(--storefront-text,#374151)]">Ежемесячный платёж</div>
            <div class="font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(calculationWithoutDiscount.monthlyPayment) }}</div>
            <div class="text-right font-bold text-[color:var(--storefront-success-text,#15803d)]">{{ formatPrice(calculation.monthlyPayment) }}</div>
            <div class="text-[color:var(--storefront-text,#374151)]">Первоначальный взнос</div>
            <div>{{ downPaymentPercent }}%</div>
            <div class="text-right">{{ downPaymentPercent }}%</div>
            <div class="text-[color:var(--storefront-text,#374151)]">Сумма договора</div>
            <div class="font-medium">{{ formatPrice(calculationWithoutDiscount.totalCost) }}</div>
            <div class="text-right font-medium text-[color:var(--storefront-success-text,#15803d)]">{{ formatPrice(calculation.totalCost) }}</div>
          </div>
        </template>
        <template v-else>
          <!-- Main result always visible -->
          <div class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
            <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">Ежемесячный платёж</div>
            <div class="text-lg sm:text-xl font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(calculation.monthlyPayment) }}</div>
          </div>

          <!-- Collapsible details -->
          <transition
            enter-active-class="transition-all duration-200 ease-out"
            leave-active-class="transition-all duration-150 ease-in"
            enter-from-class="opacity-0 max-h-0"
            enter-to-class="opacity-100 max-h-[500px]"
            leave-from-class="opacity-100 max-h-[500px]"
            leave-to-class="opacity-0 max-h-0"
          >
            <div v-show="resultsExpanded" class="overflow-hidden">
              <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2.5 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)] shadow-sm">
                <!-- Сравнение "без / с поддержкой" в стиле карточек, как в лендинговом калькуляторе -->
                <div
                  v-if="calculationWithoutDiscount"
                  class="space-y-2 sm:space-y-3"
                >
                  <!-- Ежемесячный платёж -->
                  <div class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)]">
                    <div class="flex justify-between items-center">
                      <div class="text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">Ежемесячный платёж</div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                          {{ formatPrice(calculationWithoutDiscount.monthlyPayment) }}
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-success-text,#15803d)]">
                          {{ formatPrice(calculation.monthlyPayment) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Первоначальный взнос -->
                  <div class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#bfdbfe)]">
                    <div class="flex justify-between items-center">
                      <div class="text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">Первоначальный взнос</div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                          {{ formatPrice(downPaymentAmountWithoutDiscount) }} ({{ downPaymentPercent }}%)
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-text-muted,#2563eb)]">
                          {{ formatPrice(downPaymentAmount) }} ({{ downPaymentPercent }}%)
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Сумма договора -->
                  <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)]">
                    <div class="flex justify-between items-center">
                      <div class="text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">Сумма договора</div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                          {{ formatPrice(calculationWithoutDiscount.totalCost) }}
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-success-text,#15803d)]">
                          {{ formatPrice(calculation.totalCost) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Страхование -->
                  <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)]">
                    <div class="flex justify-between items-center">
                      <div class="text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">Страхование</div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                          {{ formatPrice(insuranceWithoutDiscount) }}
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-text,#111827)]">
                          {{ formatPrice(insuranceWithDiscount) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Возврат НДС -->
                  <div class="bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#a7f3d0)] cursor-pointer hover:bg-[color:rgb(var(--storefront-success-hover-rgb,209_250_229)/var(--tw-bg-opacity,1))] transition-colors"
                       @click.stop="showTooltip('vat')">
                    <div class="flex justify-between items-center">
                      <div class="flex items-center text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">
                        Возврат НДС
                        <svg class="w-3.5 h-3.5 sm:w-4 sm:h-4 ml-1 text-[color:var(--storefront-success-icon,#10b981)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                      </div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-success-text,#047857)]">
                          {{ formatPrice(vatRefundWithoutDiscount) }}
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-success-text,#047857)]">
                          {{ formatPrice(vatRefundWithSupport) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Налог на прибыль -->
                  <div class="bg-[color:rgb(var(--storefront-info-rgb,245_243_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-info-border,#ddd6fe)] cursor-pointer hover:bg-[color:rgb(var(--storefront-info-hover-rgb,237_233_254)/var(--tw-bg-opacity,1))] transition-colors"
                       @click.stop="showTooltip('profit')">
                    <div class="flex justify-between items-center">
                      <div class="flex items-center text-[color:var(--storefront-text,#374151)] text-sm sm:text-base">
                        Налог на прибыль
                        <svg class="w-3.5 h-3.5 sm:w-4 sm:h-4 ml-1 text-[color:var(--storefront-info-icon,#8b5cf6)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                      </div>
                    </div>
                    <div class="mt-1.5 space-y-1 text-xs sm:text-sm">
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">Без поддержки</span>
                        <span class="font-semibold text-[color:var(--storefront-info-text,#6d28d9)]">
                          {{ formatPrice(profitTaxWithoutDiscount) }}
                        </span>
                      </div>
                      <div class="flex justify-between gap-2">
                        <span class="text-[color:var(--storefront-text-muted,#6b7280)]">С поддержкой</span>
                        <span class="font-semibold text-[color:var(--storefront-info-text,#6d28d9)]">
                          {{ formatPrice(profitTaxWithSupport) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Ниже — те же "Учтено в расчёте" блоки, как и раньше -->
                  <div v-if="supportFromApi && totalSupportAmount > 0" class="pt-2 mt-2 border-t border-[color:var(--storefront-border,#e5e7eb)] space-y-1.5">
                    <div class="text-xs sm:text-sm font-medium text-[color:var(--storefront-text-muted,#6b7280)]">Учтено в расчёте:</div>
                    <div v-if="(supportFromApi.down_payment_support || 0) > 0" class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
                      <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm">Поддержка первого взноса</div>
                      <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.down_payment_support) }}</div>
                    </div>
                    <div v-if="(supportFromApi.dealer_commission_support || 0) > 0" class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
                      <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm">Комиссия дилеру (уменьшение счёта)</div>
                      <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.dealer_commission_support) }}</div>
                    </div>
                    <div v-if="(vehicleDiscountSupportAmount || 0) > 0" class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
                      <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm">Поддержка на ТС</div>
                      <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(vehicleDiscountSupportAmount) }}</div>
                    </div>
                    <div v-if="(supportFromApi.interest_support || 0) > 0" class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
                      <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm">Поддержка процентов</div>
                      <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(supportFromApi.interest_support) }}</div>
                    </div>
                  </div>
                </div>

                <!-- Остальные режимы: исходный одноколоночный вид -->
                <div v-else class="space-y-2 sm:space-y-3">
                  <div class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#bfdbfe)] flex justify-between">
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">Первоначальный взнос</div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-text-muted,#2563eb)]">{{ downPaymentPercent }}%</div>
                  </div>

                  <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)] flex justify-between">
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">Сумма договора</div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(calculation.totalCost) }}</div>
                  </div>

                  <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-border,#e5e7eb)] flex justify-between">
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">Страхование</div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-text,#111827)]">{{ formatPrice(Math.round(props.totalAmount * 0.025)) }}</div>
                  </div>

                  <div
                    class="bg-[color:rgb(var(--storefront-success-rgb,236_253_245)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#a7f3d0)] flex justify-between cursor-pointer hover:bg-[color:rgb(var(--storefront-success-hover-rgb,209_250_229)/var(--tw-bg-opacity,1))] transition-colors"
                    @click.stop="showTooltip('vat')"
                  >
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">
                      Возврат НДС
                      <svg class="w-3.5 h-3.5 sm:w-4 sm:h-4 ml-1 text-[color:var(--storefront-success-icon,#10b981)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                      </svg>
                    </div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#059669)]">{{ formatPrice(calculation.vatRefund ?? 0) }}</div>
                  </div>

                  <div
                    class="bg-[color:rgb(var(--storefront-info-rgb,245_243_255)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-info-border,#ddd6fe)] flex justify-between cursor-pointer hover:bg-[color:rgb(var(--storefront-info-hover-rgb,237_233_254)/var(--tw-bg-opacity,1))] transition-colors"
                    @click.stop="showTooltip('profit')"
                  >
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm flex items-center">
                      Налог на прибыль
                      <svg class="w-3.5 h-3.5 sm:w-4 sm:h-4 ml-1 text-[color:var(--storefront-info-icon,#8b5cf6)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                      </svg>
                    </div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-info-text,#7c3aed)]">{{ formatPrice(calculation.profitTaxSavings ?? 0) }}</div>
                  </div>

                  <div v-if="supportDisplayMode === 'refund' && totalDiscount > 0" class="bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] rounded-lg p-2 sm:p-3 border border-[color:var(--storefront-success-border,#bbf7d0)] flex justify-between">
                    <div class="text-[color:var(--storefront-text,#374151)] text-xs sm:text-sm">Учтено в расчёте: поддержка по программе</div>
                    <div class="text-base sm:text-lg font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ formatPrice(totalDiscount) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </template>
      </div>

      <div v-else class="text-center text-[color:var(--storefront-text-muted,#6b7280)] py-4 sm:py-8">
        <svg class="mx-auto h-8 w-8 sm:h-12 sm:w-12 text-[color:var(--storefront-icon,#d1d5db)] mb-2 sm:mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z">
          </path>
        </svg>
        <p class="text-base sm:text-lg font-medium mb-1 sm:mb-2">Заполните параметры для расчета</p>
        <p class="text-xs sm:text-sm text-[color:var(--storefront-text-muted,#9ca3af)]">Укажите Вашу цену</p>
      </div>

      <div v-if="error" class="mt-4 p-3 bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] text-[color:var(--storefront-error-text,#b91c1c)] rounded-lg text-sm">
        <div class="flex items-center">
          <svg class="w-5 h-5 mr-2 text-[color:var(--storefront-error-icon,#ef4444)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          {{ error }}
        </div>
      </div>

      <div class="mt-4 p-3 bg-[color:rgb(var(--storefront-warning-rgb,255_251_235)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fde68a)] text-[color:var(--storefront-text-muted,#4b5563)] rounded-lg text-xs sm:text-sm">
        <div class="flex gap-2">
          <svg class="w-4 h-4 text-[color:var(--storefront-warning-icon,#f59e0b)] flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
          </svg>
          <p>
            <span class="text-[color:var(--storefront-warning-text,#d97706)] font-medium">Расчёт предварительный.</span>
            Актуальный расчет предложит лизинговая компания после подачи заявки.
          </p>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="flex justify-center py-2">
      <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
    </div>

    <!-- Tooltip Modal -->
    <div v-if="tooltipModal" class="fixed inset-0 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/var(--tw-bg-opacity,1))] bg-opacity-50 flex items-end sm:items-center justify-center z-50"
      @click.self="closeTooltip">
      <div
        class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-t-xl sm:rounded-lg shadow-xl max-w-sm w-full sm:mx-4 p-4 transform transition-all duration-300 scale-100">
        <div class="flex justify-between items-start mb-3 sm:mb-4">
          <h3 class="text-sm sm:text-base font-semibold text-[color:var(--storefront-title,#111827)]">{{ currentTooltip.title }}</h3>
          <button @click="closeTooltip" class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] transition-colors">
            <svg class="w-5 h-5 sm:w-6 sm:h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
          </button>
        </div>
        <p class="text-sm sm:text-base text-[color:var(--storefront-text,#374151)] leading-relaxed">{{ currentTooltip.content }}</p>
        <div class="mt-4 sm:mt-6 flex justify-end">
          <button @click="closeTooltip"
            class="storefront-action-primary px-4 py-2 bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-primary-foreground,#ffffff)] text-sm sm:text-base rounded-lg hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] transition-colors">
            Понятно
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getMonthWord } from '~/utils'
import { clearLegacy, useScopedStorage } from '~/features/auth/composables/useScopedStorage'
import { useCartSupportSelection } from '~/features/cart/composables/useCartSupportSelection'
import { useLeasingCalculator } from '~/features/calculator/composables/useLeasingCalculator'
import { calculateDownPaymentSupportPercent } from '~/features/cart/utils/supportPaymentAmounts'
import {
  clampLeaseTermMonths,
  isEligibleLeaseTermMonths,
} from '~/features/cart/calculator/leaseTerm'
import type {
  CartCalculationData,
  CartCalculatorResponse,
  LeasingCalculationResult,
  SupportBreakdown,
  TooltipInfo,
} from '~/features/cart/types'
import type { UUID } from '~/types/ids'

const { debounce } = useLodash()

const props = withDefaults(defineProps<{
  totalAmount: number
  /** Special-equipment lines and vehicle options outside authoritative vehicle prices. */
  additionalAmount?: number
  totalDiscount?: number
  /** 'direct' = show two columns (without/with discount), 'refund' = add support row */
  supportDisplayMode?: string | null
  selectedVehicles?: UUID[]
  vehiclePriceOverrides?: Record<UUID, number>
  vehicleQuantities?: Record<UUID, number>
}>(), {
  totalDiscount: 0,
  vehiclePriceOverrides: () => ({}),
  vehicleQuantities: () => ({})
})

const emit = defineEmits<{
  (e: 'calculation-change', calculation: CartCalculationData | null): void
}>()

const config = useRuntimeConfig()
const { formatPrice } = useFormatPrice()
const calculator = useLeasingCalculator()
const supportSelection = useCartSupportSelection()

const calculatorStorage = useScopedStorage<{
  downPaymentPercent: number
  leaseTerm: number
  buyoutPercent: number
}>('cart-calculator-state')
clearLegacy('cart-calculator-state')

const MAX_DOWN_PAYMENT_PERCENT = 49
const minDownPaymentPercent = computed(() => 0)
const clampDownPaymentPercent = (percent: number) =>
  Math.min(
    MAX_DOWN_PAYMENT_PERCENT,
    Math.max(minDownPaymentPercent.value, percent),
  )

const loadCalculatorState = () => {
  if (process.client) {
    const state = calculatorStorage.get()
    if (state) {
      const storedDownPaymentPercent = Number(state.downPaymentPercent)
      return {
        downPaymentPercent: Number.isFinite(storedDownPaymentPercent)
          ? clampDownPaymentPercent(storedDownPaymentPercent)
          : 20,
        leaseTerm: state.leaseTerm || 36,
        buyoutPercent: state.buyoutPercent || 0,
      }
    }
  }
  return {
    downPaymentPercent: 20,
    leaseTerm: 36,
    buyoutPercent: 0,
  }
}

const saveCalculatorState = () => {
  if (process.client) {
    calculatorStorage.set({
      downPaymentPercent: downPaymentPercent.value,
      leaseTerm: leaseTerm.value,
      buyoutPercent: buyoutPercent.value,
    })
  }
}

const initialState = loadCalculatorState()

const downPaymentPercent = ref(initialState.downPaymentPercent)
const downPaymentAmount = ref(0)
const leaseTerm = ref(initialState.leaseTerm)
const buyoutPercent = ref(initialState.buyoutPercent)
const buyoutAmount = ref(0)
const tooltipModal = ref<boolean | null>(null)
const currentTooltip = ref<TooltipInfo>({ title: '', content: '' })
const resultsExpanded = ref(false)
const calculationWithoutDiscount = ref<LeasingCalculationResult | null>(null)

const calculation = computed(() => calculator.calculation.value)
const specialOffer = computed(() => calculator.specialOffer.value)
const supportFromApi = computed(() => calculator.support.value)
const loading = computed(() => calculator.loading.value)
const error = computed(() => calculator.error.value)

const totalSupportAmount = computed(() => {
  const s = supportFromApi.value
  if (!s) return 0
  return (s.vehicle_discount_support || 0) + (s.down_payment_support || 0) + (s.interest_support || 0)
})

// Для сравнений "без / с поддержкой": базовая сумма без выгоды/поддержки
const totalAmountWithoutDiscount = computed(() => {
  const amount = Number(props.totalAmount) || 0
  const discount = Math.max(0, Number(props.totalDiscount) || 0)
  if (amount <= 0) return 0
  return amount + discount
})

const downPaymentAmountWithoutDiscount = computed(() => {
  const base = totalAmountWithoutDiscount.value
  if (base <= 0) return 0
  const percent = Number(downPaymentPercent.value) || 0
  return Math.round(base * percent / 100)
})

const insuranceWithDiscount = computed(() => {
  const amount = Number(props.totalAmount) || 0
  if (amount <= 0) return 0
  return Math.round(amount * 0.025)
})

const insuranceWithoutDiscount = computed(() => {
  const base = totalAmountWithoutDiscount.value
  if (base <= 0) return 0
  return Math.round(base * 0.025)
})

const vatRefundWithSupport = computed(() => {
  return calculation.value?.vatRefund ?? 0
})

const vatRefundWithoutDiscount = computed(() => {
  return calculationWithoutDiscount.value?.vatRefund ?? 0
})

const profitTaxWithSupport = computed(() => {
  return calculation.value?.profitTaxSavings ?? 0
})

const profitTaxWithoutDiscount = computed(() => {
  return calculationWithoutDiscount.value?.profitTaxSavings ?? 0
})

/** Поддержка на ТС без части поддержки, направленной дилеру. */
const vehicleDiscountSupportAmount = computed(() => {
  const s = supportFromApi.value
  if (!s) return 0
  const total = s.vehicle_discount_support || 0
  const dealerCommission = s.dealer_commission_support || 0
  return Math.max(0, total - dealerCommission)
})

const downPaymentSupportPercent = computed(() => {
  const supportBase = supportFromApi.value?.effective_total || props.totalAmount
  return calculateDownPaymentSupportPercent(
    supportFromApi.value?.down_payment_support || 0,
    supportBase,
  )
})

const downPaymentSupportSliderWidth = computed(() => {
  const percent = downPaymentSupportPercent.value
  if (percent <= 0) return '0%'
  return `${(percent / 49) * 100}%`
})

const sliderTrackStyle = computed(() => {
  const percent = downPaymentSupportPercent.value
  if (percent <= 0) return {}
  const gradientStop = (percent / 49) * 100
  return {
    '--down-payment-support-stop': `${gradientStop}%`
  }
})

const minDownPayment = computed(() => {
  const amount = Number(props.totalAmount) || 0
  return Math.ceil(amount * minDownPaymentPercent.value / 100)
})
const maxDownPayment = computed(() => {
  const amount = Number(props.totalAmount) || 0
  return Math.ceil(amount * 1.0)
})
const maxBuyoutAmount = computed(() => {
  const amount = Number(props.totalAmount) || 0
  const downPayment = Number(downPaymentAmount.value) || 0
  return Math.max(0, amount - downPayment)
})

const canCalculate = computed(() => {
  const amount = Number(props.totalAmount) || 0
  const downPayment = Number(downPaymentAmount.value) || 0
  return amount > 0 &&
    downPayment >= minDownPayment.value &&
    downPayment <= maxDownPayment.value &&
    isEligibleLeaseTermMonths(leaseTerm.value)
})

// Methods


const updateDownPaymentFromPercent = () => {
  const amount = Number(props.totalAmount) || 0
  const inputPercent = Number(downPaymentPercent.value) || 0

  const percent = clampDownPaymentPercent(inputPercent)
  downPaymentPercent.value = percent
  downPaymentAmount.value = Math.round(amount * percent / 100)
  if (canCalculate.value) {
    debouncedCalculate()
  }
}

const updateDownPaymentFromAmount = () => {
  const amount = Number(props.totalAmount) || 0
  const downPayment = Number(downPaymentAmount.value) || 0

  if (downPayment >= minDownPayment.value && downPayment <= maxDownPayment.value && amount > 0) {
    const percent = clampDownPaymentPercent(
      Math.round((downPayment / amount) * 100),
    )
    downPaymentPercent.value = percent
    downPaymentAmount.value = Math.round(amount * percent / 100)
    debouncedCalculate()
  }
}

const validateAmount = () => {
  let amount = Number(downPaymentAmount.value) || 0
  if (amount > maxDownPayment.value) {
    downPaymentAmount.value = maxDownPayment.value
  } else if (amount < minDownPayment.value) {
    downPaymentAmount.value = minDownPayment.value
  }
  updateDownPaymentFromAmount()
}

const updateBuyoutFromPercent = () => {
  const percent = Number(buyoutPercent.value) || 0
  const loanAmount = maxBuyoutAmount.value

  if (percent >= 0 && percent <= 5) {
    buyoutAmount.value = Math.round(loanAmount * percent / 100)
    debouncedCalculate()
  }
}

const updateBuyoutFromAmount = () => {
  const amount = Number(buyoutAmount.value) || 0
  const loanAmount = maxBuyoutAmount.value

  if (amount >= 0 && amount <= loanAmount && loanAmount > 0) {
    buyoutPercent.value = Math.round((amount / loanAmount) * 100)
    debouncedCalculate()
  }
}

const validateBuyoutAmount = () => {
  let amount = Number(buyoutAmount.value) || 0
  if (amount > maxBuyoutAmount.value) {
    buyoutAmount.value = maxBuyoutAmount.value
  } else if (amount < 0) {
    buyoutAmount.value = 0
  }
  updateBuyoutFromAmount()
}

const normalizeLeaseTerm = () => {
  leaseTerm.value = clampLeaseTermMonths(leaseTerm.value)
  if (!canCalculate.value) {
    debouncedCalculate.cancel()
    resetCalculation()
    return
  }
  debouncedCalculate()
}

const scheduleLeaseTermCalculation = () => {
  if (canCalculate.value) {
    debouncedCalculate()
  }
}

const selectedVehicleIds = computed<UUID[]>(() => props.selectedVehicles || [])

const resetCalculation = () => {
  calculator.reset()
  calculationWithoutDiscount.value = null
  emit('calculation-change', null)
}

const calculate = async (): Promise<boolean> => {
  if (!canCalculate.value) {
    resetCalculation()
    return false
  }

  resetCalculation()

  try {
    // Собираем выбранную поддержку по каждому ТС отдельно
    const selectedSupport: Record<UUID, UUID[]> = {}
    for (const vehicleId of selectedVehicleIds.value) {
      const sel = supportSelection.getSelectionForVehicle(vehicleId)
      const selectedProgramIds = Array.from(
        new Set(sel.selected_support_ids)
      ).sort((a, b) => a.localeCompare(b))
      selectedSupport[vehicleId] = selectedProgramIds
    }

    const calculationData: {
      total_amount: number
      additional_amount?: number
      down_payment: number
      down_payment_percent: number
      lease_term_months: number
      buyout_amount?: number
      vehicle_ids: UUID[]
      vehicle_price_overrides?: Record<UUID, number>
      vehicle_quantities?: Record<UUID, number>
      selected_support: Record<UUID, UUID[]>
    } = {
      total_amount: props.totalAmount,
      ...(props.additionalAmount === undefined
        ? {}
        : { additional_amount: props.additionalAmount }),
      down_payment: downPaymentAmount.value,
      down_payment_percent: clampDownPaymentPercent(Number(downPaymentPercent.value)),
      lease_term_months: Number(leaseTerm.value),
      buyout_amount: buyoutAmount.value,
      vehicle_ids: selectedVehicleIds.value,
      vehicle_price_overrides: props.vehiclePriceOverrides,
      vehicle_quantities: props.vehicleQuantities,
      selected_support: selectedSupport
    }

    const response = await calculator.calculate(calculationData) as CartCalculatorResponse | null
    if (!response?.calculation) return false

    // "Без выгоды/поддержки" берём из ответа бэкенда,
    // но только если реально есть применяемые программы поддержки
    const s = response.support
    const supportSum =
      (s?.vehicle_discount_support || 0) +
      (s?.down_payment_support || 0) +
      (s?.interest_support || 0)
    const supportPerProgram = response.support_per_program
    const supportPerVehicle = response.support_per_vehicle
    const hasPrograms =
      (Array.isArray(supportPerProgram) && supportPerProgram.length > 0) ||
      (Array.isArray(supportPerVehicle) && supportPerVehicle.length > 0)

    const calcWithoutSupport = response.calculation_without_support
    if (supportSum > 0 && hasPrograms && calcWithoutSupport?.calculation) {
      calculationWithoutDiscount.value = calcWithoutSupport.calculation
    } else {
      calculationWithoutDiscount.value = null
    }

    emit('calculation-change', {
      total_amount: props.totalAmount,
      ...(props.additionalAmount === undefined
        ? {}
        : { additional_amount: props.additionalAmount }),
      down_payment: downPaymentAmount.value,
      down_payment_percent: downPaymentPercent.value,
      lease_term_months: leaseTerm.value,
      buyout_amount: buyoutAmount.value,
      buyout_percent: buyoutPercent.value,
      vehicle_ids: selectedVehicleIds.value,
      vehicle_price_overrides: props.vehiclePriceOverrides,
      vehicle_quantities: props.vehicleQuantities,
      calculation: response.calculation ?? null,
      support: response.support ?? null,
      calculations_per_vehicle: response.calculations_per_vehicle ?? [],
      selected_support: selectedSupport,
      support_per_vehicle: response.support_per_vehicle ?? [],
      support_per_program: response.support_per_program ?? [],
      support_program_details: response.support_program_details ?? [],
      eligible_support_program_ids_by_vehicle: response.eligible_support_program_ids_by_vehicle ?? []
    })
    return true
  } catch (err) {
    console.error('Calculation error:', err)
    return false
  }
}

// Позволяет родительским компонентам принудительно пересчитать калькулятор без перемонтирования
const recalculate = () => {
  debouncedCalculate.cancel()
  return calculate()
}

defineExpose({
  recalculate
})

// Debounced version of calculate - waits 500ms after last input change
const debouncedCalculate = debounce(() => {
  calculate()
}, 500)

watch(() => props.totalAmount, (newAmount) => {
  const amount = Number(newAmount) || 0
  if (amount <= 0) {
    debouncedCalculate.cancel()
    downPaymentAmount.value = 0
    buyoutAmount.value = 0
    resetCalculation()
    return
  }

  const percent = Number(downPaymentPercent.value) || 20
  downPaymentAmount.value = Math.round(amount * percent / 100)

  const loanAmount = amount - downPaymentAmount.value
  if (loanAmount > 0 && buyoutPercent.value > 0) {
    buyoutAmount.value = Math.round(loanAmount * buyoutPercent.value / 100)
  } else if (buyoutAmount.value > loanAmount) {
    buyoutAmount.value = 0
    buyoutPercent.value = 0
  }

  debouncedCalculate()
}, { immediate: true })

watch(() => props.additionalAmount, () => {
  debouncedCalculate()
})

watch(() => props.vehiclePriceOverrides, () => {
  debouncedCalculate()
}, { deep: true })

watch(() => props.vehicleQuantities, () => {
  debouncedCalculate()
}, { deep: true })

watch(downPaymentAmount, () => {
  const loanAmount = maxBuyoutAmount.value
  if (buyoutAmount.value > loanAmount) {
    buyoutAmount.value = Math.min(buyoutAmount.value, Math.max(0, loanAmount))
    if (loanAmount > 0) {
      buyoutPercent.value = Math.round((buyoutAmount.value / loanAmount) * 100)
    } else {
      buyoutPercent.value = 0
    }
  }
})

watch(buyoutAmount, () => {
  debouncedCalculate()
})

// Methods
const showTooltip = (type: string) => {
  const tooltips: Record<string, TooltipInfo> = {
    vat: {
      title: 'Возврат НДС',
      content: 'Компания может принять к вычету НДС, включенный в лизинговые платежи. Сумму рассчитывает калькулятор по действующей ставке.'
    },
    profit: {
      title: 'Снижение налога на прибыль',
      content: 'Приобретая транспортное средство в лизинг, компания имеет право на вычет НДС, включенного в лизинговой платеж. Так как покупка оформляется как аренда с правом выкупа, организация, помимо прочего, снижает налог на прибыль, поскольку выплаты по факту являются расходом организации.'
    }
  }

  currentTooltip.value = tooltips[type] || { title: '', content: '' }
  tooltipModal.value = true
}

const closeTooltip = () => {
  tooltipModal.value = false
  currentTooltip.value = { title: '', content: '' }
}

watch([downPaymentPercent, leaseTerm, buyoutPercent], () => {
  saveCalculatorState()
})

onMounted(() => {
  const amount = Number(props.totalAmount) || 0
  if (amount > 0) {
    const percent = Number(downPaymentPercent.value) || 20
    downPaymentAmount.value = Math.round(amount * percent / 100)

    const loanAmount = amount - downPaymentAmount.value
    if (loanAmount > 0 && buyoutPercent.value > 0) {
      buyoutAmount.value = Math.round(loanAmount * buyoutPercent.value / 100)
    }

    if (canCalculate.value) {
      debouncedCalculate()
    }
  }
})

onBeforeUnmount(() => {
  debouncedCalculate.cancel()
  calculator.reset()
})
</script>

<style scoped>
.slider-container {
  position: relative;
  width: 100%;
}

.slider-support-zone {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  height: 10px;
  background: linear-gradient(to right, var(--storefront-success,#22c55e), var(--storefront-success,#4ade80));
  border-radius: 5px 0 0 5px;
  z-index: 1;
  pointer-events: none;
}

.support-tooltip {
  position: absolute;
  left: 0;
  bottom: 100%;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--storefront-success,#166534);
  color: var(--storefront-text,white);
  font-size: 12px;
  border-radius: 6px;
  white-space: nowrap;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  z-index: 10;
}

.support-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 12px;
  border: 5px solid transparent;
  border-top-color: var(--storefront-success-border,#166534);
}

.group:hover .support-tooltip {
  opacity: 1;
  visibility: visible;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  height: 24px;
  width: 24px;
  border-radius: 50%;
  background: var(--storefront-surface,#ffffff);
  cursor: pointer;
  box-shadow: 0 4px 8px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.15);
  border: 3px solid var(--storefront-primary,#3b82f6);
  transition: all 0.2s ease;
  position: relative;
  z-index: 2;
}

.slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 12px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.2);
}

.slider::-moz-range-thumb {
  height: 24px;
  width: 24px;
  border-radius: 50%;
  background: var(--storefront-surface,#ffffff);
  cursor: pointer;
  border: 3px solid var(--storefront-primary,#3b82f6);
  box-shadow: 0 4px 8px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.15);
  transition: all 0.2s ease;
  position: relative;
  z-index: 2;
}

.slider::-moz-range-thumb:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 12px rgb(var(--storefront-shadow-rgb,0 0 0) / 0.2);
}

.slider::-webkit-slider-track {
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) var(--down-payment-support-stop, 0%), var(--storefront-surface,#f3f4f6) var(--down-payment-support-stop, 0%), var(--storefront-surface,#f3f4f6) 100%);
  height: 10px;
  border-radius: 5px;
  border: 1px solid var(--storefront-border,#e5e7eb);
}

.slider::-moz-range-track {
  background: linear-gradient(to right, var(--storefront-success,#22c55e) 0%, var(--storefront-success,#22c55e) var(--down-payment-support-stop, 0%), var(--storefront-surface,#f3f4f6) var(--down-payment-support-stop, 0%), var(--storefront-surface,#f3f4f6) 100%);
  height: 10px;
  border-radius: 5px;
  border: 1px solid var(--storefront-border,#e5e7eb);
}

</style>
