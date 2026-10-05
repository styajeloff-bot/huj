<template>
  <section data-storefront-block="client.checkout" class="space-y-5">
    <section
      v-if="showApprovalTable"
      class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-5 shadow-sm sm:p-6"
    >
      <div class="mb-4 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div class="flex items-start gap-2">
          <div>
            <h2 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">{{ approvalTableTitle }}</h2>
            <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
              Лучшие КП лизинговых компаний по условиям заявки.
            </p>
          </div>
          <div class="relative group">
            <span class="mt-0.5 inline-flex h-5 w-5 cursor-help select-none items-center justify-center rounded-full border border-[color:var(--storefront-border,#9ca3af)] text-xs text-[color:var(--storefront-text-muted,#6b7280)]">
              i
            </span>
            <div class="absolute left-0 top-7 z-20 hidden w-80 rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,17_24_39)/var(--tw-bg-opacity,1))] p-3 text-xs leading-5 text-[color:var(--storefront-text,#ffffff)] shadow-lg group-hover:block">
              {{ approvalHintText }}
            </div>
          </div>
        </div>

        <div
          v-if="showApprovalTabs"
          class="inline-flex w-fit rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-1"
        >
          <button
            v-for="tab in approvalTabs"
            :key="tab.id"
            type="button"
            :aria-pressed="activeApprovalKind === tab.id"
            class="storefront-action-secondary rounded-md px-3 py-1.5 text-sm font-medium transition-colors"
            :class="activeApprovalKind === tab.id ? 'bg-[color:rgb(var(--storefront-secondary-rgb,255_255_255)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-secondary-foreground,#1d4ed8)] shadow-sm' : 'text-[color:var(--storefront-secondary-foreground,#4b5563)] hover:text-[color:var(--storefront-secondary-hover-foreground,#111827)]'"
            @click="setApprovalKind(tab.id)"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <p v-if="approvalError" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
        {{ approvalError }}
      </p>

      <div v-else-if="approvalLoading && approvedOfferRows.length === 0" class="flex justify-center py-10">
        <div class="h-10 w-10 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      </div>

      <p v-else-if="approvedOfferRows.length === 0" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] py-8 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
        Пока нет одобренных предложений от лизинговых компаний.
      </p>

      <div v-else class="overflow-x-auto rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
        <table class="w-full min-w-[1180px] border-collapse text-sm">
          <thead>
            <tr class="bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-left text-xs font-semibold uppercase tracking-wide text-[color:var(--storefront-text-muted,#4b5563)]">
              <th
                v-for="column in approvalColumns"
                :key="column.key"
                class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2"
                :class="'align' in column && column.align === 'right' ? 'text-right' : ''"
              >
                <button
                  v-if="column.sortable"
                  type="button"
                  class="storefront-action-ghost inline-flex items-center gap-1 hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)]"
                  @click="setApprovalSort(column.key)"
                >
                  <span>{{ column.label }}</span>
                  <span class="text-[10px]">{{ sortIndicator(column.key) }}</span>
                </button>
                <span v-else>{{ column.label }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))]">
              <th class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-left font-semibold text-[color:var(--storefront-text,#111827)]">
                {{ requestedConditionRow.label }}
              </th>
              <td class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-[color:var(--storefront-text,#374151)]">
                Запрошенные условия
              </td>
              <td
                v-for="column in approvalMetricColumns"
                :key="column.key"
                class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right font-medium text-[color:var(--storefront-text,#111827)]"
              >
                {{ formatApprovalValue(requestedConditionRow.values[column.key], column.format) }}
              </td>
              <td class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">—</td>
            </tr>

            <tr
              v-for="row in approvedOfferRows"
              :key="row.id"
              :class="approvalRowClass(row)"
            >
              <th class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-left font-semibold text-[color:var(--storefront-text,#111827)]">
                {{ applicationNumber(row.item) }}
              </th>
              <td class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 font-medium text-[color:var(--storefront-text,#111827)]">
                {{ row.leasingCompanyName }}
              </td>
              <td
                v-for="column in approvalMetricColumns"
                :key="column.key"
                class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 text-right"
                :class="approvalCellClass(row, column.key)"
              >
                {{ formatApprovalValue(row.values[column.key], column.format) }}
              </td>
              <td class="border border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2">
                <div class="flex justify-end gap-2">
                  <template v-if="activeApprovalKind === 'preliminary'">
                    <div v-if="row.clientDecisionAction === 'accepted'" class="flex items-center gap-2">
                      <span class="rounded-md bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-success-text,#166534)]">Принято КП</span>
                      <button
                        type="button"
                        class="storefront-action-ghost rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:cursor-wait disabled:text-[color:var(--storefront-secondary-disabled-foreground,#9ca3af)]"
                        :disabled="decisionLoadingId === row.id"
                        @click="submitProposalDecision(row, 'cancelled')"
                      >
                        Отменить
                      </button>
                    </div>
                    <button
                      v-else
                      type="button"
                      class="storefront-action-primary rounded-md border border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:border-[color:var(--storefront-primary-disabled-border,#bfdbfe)] disabled:bg-[color:rgb(var(--storefront-primary-disabled-rgb,191_219_254)/var(--tw-bg-opacity,1))]"
                      :disabled="decisionLoadingId === row.id"
                      @click="submitProposalDecision(row, 'accepted')"
                    >
                      Принять КП
                    </button>
                  </template>

                  <template v-else>
                    <span
                      v-if="row.item.status === 'selected_lc'"
                      class="rounded-md bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-success-text,#166534)]"
                    >
                      Выбрана ЛК
                    </span>
                    <span
                      v-else-if="row.item.status === 'deal'"
                      class="rounded-md bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-success-text,#166534)]"
                    >
                      Сделка заключена
                    </span>
                    <button
                      v-else
                      type="button"
                      class="storefront-action-primary rounded-md border border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:border-[color:var(--storefront-primary-disabled-border,#bfdbfe)] disabled:bg-[color:rgb(var(--storefront-primary-disabled-rgb,191_219_254)/var(--tw-bg-opacity,1))]"
                      :disabled="isFinalSelectionDisabled(row)"
                      @click="confirmFinalSelection(row)"
                    >
                      Выбрать
                    </button>
                  </template>

                  <button
                    type="button"
                    class="storefront-action-ghost inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
                    @click="openPaymentSchedule(row.item, activeApprovalKind, row.proposal)"
                  >
                    <CalendarDaysIcon class="h-3.5 w-3.5" aria-hidden="true" />
                    График платежей
                  </button>

                  <button
                    type="button"
                    class="storefront-action-ghost inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-2.5 py-1.5 text-xs font-medium text-[color:var(--storefront-secondary-foreground,#374151)] hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))] disabled:cursor-not-allowed disabled:text-[color:var(--storefront-secondary-disabled-foreground,#9ca3af)]"
                    :disabled="downloadingResponsePdfId === row.id"
                    @click="downloadResponsePdf(row)"
                  >
                    <ArrowDownTrayIcon class="h-3.5 w-3.5" aria-hidden="true" />
                    {{ downloadingResponsePdfId === row.id ? 'Скачиваем...' : 'Скачать PDF' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="vehiclesWithAdditionalOptions.length > 0" class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-5 shadow-sm sm:p-6">
      <div class="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Дополнительное оборудование и услуги</h3>
          <p class="mt-1 text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
            Выбранные опции учитываются в итоговой стоимости после подтверждения цен.
          </p>
        </div>
        <div v-if="additionalOptionsGrandTotal > 0" class="text-sm font-medium text-[color:var(--storefront-text,#111827)] sm:text-right">
          Сумма опций: {{ formatPrice(additionalOptionsGrandTotal) }}
        </div>
      </div>

      <div class="space-y-4">
        <article
          v-for="vehicle in vehiclesWithAdditionalOptions"
          :key="vehicle.id as string"
          class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] p-4"
        >
          <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h4 class="font-semibold text-[color:var(--storefront-title,#111827)]">{{ vehicleTitle(vehicle) }}</h4>
          </div>

          <div class="grid gap-4 lg:grid-cols-2">
            <div>
              <div class="mb-2 flex flex-col gap-1 text-sm font-semibold sm:flex-row sm:items-center sm:justify-between">
                <h5 class="text-[color:var(--storefront-title,#1f2937)]">Дополнительное оборудование</h5>
                <span v-if="additionalEquipmentTotal(vehicle) > 0" class="font-medium text-[color:var(--storefront-text,#111827)]">
                  Сумма: {{ formatPrice(additionalEquipmentTotal(vehicle)) }}
                </span>
              </div>
              <p v-if="vehicleEquipments(vehicle).length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Не выбрано</p>
              <div v-else class="space-y-2">
                <div
                  v-for="option in vehicleEquipments(vehicle)"
                  :key="option.equipment_code"
                  class="flex items-center justify-between gap-3 rounded-md bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm"
                >
                  <div class="min-w-0">
                    <span class="text-[color:var(--storefront-text,#1f2937)]">{{ equipmentName(option.equipment_code) }}</span>
                    <p
                      v-if="option.comment?.trim()"
                      data-testid="equipment-option-comment"
                      class="mt-1 whitespace-pre-wrap text-xs text-[color:var(--storefront-text-muted,#6b7280)]"
                    >
                      {{ option.comment }}
                    </p>
                  </div>
                  <span v-if="hasAssignedOptionPrice(option.price)" class="shrink-0 font-medium text-[color:var(--storefront-text,#111827)]">
                    {{ formatPrice(Number(option.price)) }}
                  </span>
                  <span v-else class="shrink-0 text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">Цена не указана</span>
                </div>
              </div>
            </div>

            <div>
              <div class="mb-2 flex flex-col gap-1 text-sm font-semibold sm:flex-row sm:items-center sm:justify-between">
                <h5 class="text-[color:var(--storefront-title,#1f2937)]">Услуги</h5>
                <span v-if="additionalServicesTotal(vehicle) > 0" class="font-medium text-[color:var(--storefront-text,#111827)]">
                  Сумма: {{ formatPrice(additionalServicesTotal(vehicle)) }}
                </span>
              </div>
              <p v-if="vehicleServices(vehicle).length === 0" class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Не выбрано</p>
              <div v-else class="space-y-2">
                <div
                  v-for="option in vehicleServices(vehicle)"
                  :key="option.service_code"
                  class="flex items-center justify-between gap-3 rounded-md bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] px-3 py-2 text-sm"
                >
                  <div class="min-w-0">
                    <span class="text-[color:var(--storefront-text,#1f2937)]">{{ serviceName(option.service_code) }}</span>
                    <p
                      v-if="option.comment?.trim()"
                      data-testid="service-option-comment"
                      class="mt-1 whitespace-pre-wrap text-xs text-[color:var(--storefront-text-muted,#6b7280)]"
                    >
                      {{ option.comment }}
                    </p>
                  </div>
                  <span v-if="hasAssignedOptionPrice(option.price)" class="shrink-0 font-medium text-[color:var(--storefront-text,#111827)]">
                    {{ formatPrice(Number(option.price)) }}
                  </span>
                  <span v-else class="shrink-0 text-xs text-[color:var(--storefront-text-muted,#9ca3af)]">Цена не указана</span>
                </div>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <section class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-5 shadow-sm sm:p-6">
      <div class="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">Сведения по заявке</h3>
        <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Заявка {{ applicationNumberForSummary }}</div>
      </div>
      <div class="grid grid-cols-1 gap-4 text-sm md:grid-cols-2 xl:grid-cols-5">
        <div>
          <div class="text-[color:var(--storefront-text-muted,#6b7280)]">Компания-заявитель</div>
          <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ applicationCompanyNameForSummary }}</div>
        </div>
        <div>
          <div class="text-[color:var(--storefront-text-muted,#6b7280)]">Предмет лизинга</div>
          <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ leasingSubjectSummary }}</div>
        </div>
        <div>
          <div class="flex items-center gap-1 text-[color:var(--storefront-text-muted,#6b7280)]">
            <span>Общая стоимость</span>
            <span v-if="showConfirmedAdditionalOptionsHint" class="relative inline-flex group">
              <span class="inline-flex h-4 w-4 cursor-help select-none items-center justify-center rounded-full border border-[color:var(--storefront-border,#9ca3af)] text-[10px] leading-none text-[color:var(--storefront-text-muted,#6b7280)]">
                ?
              </span>
              <span class="absolute left-0 top-5 z-20 hidden w-64 rounded-lg bg-[color:rgb(var(--storefront-surface-muted-rgb,17_24_39)/var(--tw-bg-opacity,1))] px-3 py-2 text-xs leading-5 text-[color:var(--storefront-text,#ffffff)] shadow-lg group-hover:block">
                С учетом подтверждённых услуг и оборудования от дилера и лизинговой компании.
              </span>
            </span>
          </div>
          <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ applicationTotalAmount }}</div>
        </div>
        <div>
          <div class="text-[color:var(--storefront-text-muted,#6b7280)]">Стоимость техники</div>
          <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ applicationItemsAmount }}</div>
        </div>
        <div>
          <div class="text-[color:var(--storefront-text-muted,#6b7280)]">Количество единиц</div>
          <div class="font-medium text-[color:var(--storefront-text,#111827)]">{{ itemCountSummary }}</div>
        </div>
      </div>
    </section>

    <section
      v-if="showLcaCardsSection"
      class="rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-background-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-5 shadow-sm sm:p-6"
    >
      <div class="mb-4 flex items-center justify-between gap-3">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">{{ statusStepTitle }}</h3>
        <button
          type="button"
          class="storefront-action-ghost text-sm font-medium text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)] disabled:cursor-wait disabled:text-[color:var(--storefront-ghost-disabled-foreground,#93c5fd)]"
          :disabled="lcaLoading || approvalLoading"
          @click="() => refresh()"
        >
          Обновить
        </button>
      </div>

      <p v-if="lcaError" class="rounded-lg border border-[color:var(--storefront-error-border,#fecaca)] bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] px-4 py-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]">
        {{ lcaError }}
      </p>

      <div v-else-if="lcaLoading && lcaItems.length === 0" class="flex justify-center py-10">
        <div class="h-10 w-10 animate-spin rounded-full border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      </div>

      <p v-else-if="lcaItems.length === 0" class="py-8 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
        Заявки в лизинговые компании появятся после распределения.
      </p>

      <p v-else-if="filteredLcaItems.length === 0" class="py-8 text-center text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
        {{ emptyLcaText }}
      </p>

      <div v-else class="space-y-3">
        <article
          v-for="item in filteredLcaItems"
          :key="item.id"
          class="overflow-hidden rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] shadow-sm transition-shadow hover:shadow-md"
        >
          <div class="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
            <div class="min-w-0">
              <div class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">Заявка {{ applicationNumber(item) }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-2">
                <h4 class="text-base font-semibold text-[color:var(--storefront-title,#111827)]">{{ leasingCompanyName(item) }}</h4>
                <span
                  class="inline-flex shrink-0 rounded-full px-2.5 py-1 text-xs font-medium"
                  :class="statusClass(statusForBucket(item))"
                >
                  {{ statusText(statusForBucket(item)) }}
                </span>
              </div>
              <div class="mt-1 truncate text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                <span>Компания-заявитель: {{ applicationCompanyName(item) }}</span>
                <span class="px-1.5 text-[color:var(--storefront-text,#d1d5db)]">·</span>
                <span>Предмет лизинга: {{ leasingSubjectSummary }}</span>
                <span class="px-1.5 text-[color:var(--storefront-text,#d1d5db)]">·</span>
                <span>Дата подачи: {{ applicationSubmittedDate(item) }}</span>
                <span class="px-1.5 text-[color:var(--storefront-text,#d1d5db)]">·</span>
                <span>{{ applicationEmail }}</span>
              </div>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                type="button"
                class="storefront-action-ghost inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-3 py-1.5 text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] transition-colors hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
                @click="selectedLca = item"
              >
                <EyeIcon class="h-4 w-4" aria-hidden="true" />
                Подробнее
              </button>
              <button
                type="button"
                class="storefront-action-ghost inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-secondary-border,#d1d5db)] px-3 py-1.5 text-sm font-medium text-[color:var(--storefront-secondary-foreground,#374151)] transition-colors hover:bg-[color:rgb(var(--storefront-secondary-hover-rgb,249_250_251)/var(--tw-bg-opacity,1))]"
                @click="openPaymentSchedule(item)"
              >
                <CalendarDaysIcon class="h-4 w-4" aria-hidden="true" />
                График платежей
              </button>
              <button
                type="button"
                class="storefront-action-primary inline-flex items-center gap-1.5 rounded-md border border-[color:var(--storefront-primary-border,#2563eb)] bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))] px-3 py-1.5 text-sm font-medium text-[color:var(--storefront-primary-foreground,#ffffff)] transition-colors hover:bg-[color:rgb(var(--storefront-primary-hover-rgb,29_78_216)/var(--tw-bg-opacity,1))] disabled:cursor-wait disabled:border-[color:var(--storefront-primary-disabled-border,#93c5fd)] disabled:bg-[color:rgb(var(--storefront-primary-disabled-rgb,147_197_253)/var(--tw-bg-opacity,1))]"
                :disabled="downloadingPdfId === item.id"
                @click="downloadApplicationPdf(item)"
              >
                <ArrowDownTrayIcon class="h-4 w-4" aria-hidden="true" />
                {{ downloadingPdfId === item.id ? 'Формируем PDF...' : 'Скачать PDF' }}
              </button>
            </div>
          </div>

          <dl class="grid grid-cols-1 border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] text-sm sm:grid-cols-2 lg:grid-cols-8">
            <div
              v-for="field in lcaConditionFields(item)"
              :key="field.label"
              class="border-b border-[color:var(--storefront-border,#e5e7eb)] px-3 py-2 last:border-b-0 sm:[&:nth-last-child(-n+2)]:border-b-0 lg:border-b-0 lg:border-r lg:last:border-r-0"
            >
              <dt class="text-xs leading-4 text-[color:var(--storefront-text-muted,#6b7280)]">{{ field.label }}</dt>
              <dd class="mt-1 font-semibold text-[color:var(--storefront-value,#111827)]">{{ field.value }}</dd>
            </div>
          </dl>
        </article>
      </div>
    </section>

    <CheckoutOfferModal
      v-if="selectedLca"
      :show="Boolean(selectedLca)"
      :item="selectedLca"
      :application="application"
      @close="selectedLca = null"
      @changed="refresh"
    />

    <CheckoutPaymentScheduleModal
      v-if="selectedScheduleLca"
      :show="Boolean(selectedScheduleLca)"
      :item="selectedScheduleLca"
      :application="application"
      :source-kind="selectedScheduleKind"
      :source-proposal="selectedScheduleProposal"
      @close="closePaymentSchedule"
    />

    <Modal
      v-if="pendingFinalRow"
      :show="Boolean(pendingFinalRow)"
      title="Подтверждение выбора"
      :show-footer="true"
      cancel-text="Нет"
      confirm-text="Да"
      @cancel="pendingFinalRow = null"
      @close="pendingFinalRow = null"
      @confirm="selectFinalRow"
    >
      <p class="text-sm leading-6 text-[color:var(--storefront-text-muted,#4b5563)]">
        Вы уверены? Если нажмете «Да», вы выберете именно эту компанию. Другие компании уже нельзя будет выбрать.
      </p>
    </Modal>
  </section>
</template>

<script setup lang="ts">
import { useNotificationCompanyRequest } from '~/features/notifications'
const { request: notificationRequest, url: notificationUrl } = useNotificationCompanyRequest()
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowDownTrayIcon, CalendarDaysIcon, EyeIcon } from '@heroicons/vue/24/outline'
import Modal from '~/components/ui/Modal.vue'
import CheckoutOfferModal from '~/features/checkout/components/CheckoutOfferModal.vue'
import CheckoutPaymentScheduleModal from '~/features/checkout/components/CheckoutPaymentScheduleModal.vue'
import { formatApplicationVehicleTitle } from '~/features/applications/utils/applicationVehicleDisplay'
import {
  CHECKOUT_LCA_STATUS_BUCKETS,
  type CheckoutStatusBucket,
} from '~/features/checkout/utils/steps'
import { createAdditionalOptionsApi } from '~/utils/additionalOptionsApi'
import type { Application } from '@/types'
import type {
  ApprovalOffer,
  ClientLeasingResponsesResponse,
} from '~/features/leasing/api/leasingApi'

type ApplicationCompatible = Application & Record<string, unknown>
type ApprovalKind = 'preliminary' | 'final'
type ApprovalMetricKey = 'monthly_payment' | 'down_payment_percent' | 'down_payment' | 'lease_term_months' | 'total_amount' | 'total_cost' | 'buyout_amount' | 'total_interest'
type ApprovalColumnKey = 'application' | 'leasing_company' | ApprovalMetricKey | 'actions'
type ApprovalSortKey = Exclude<ApprovalColumnKey, 'actions'>
type SortDirection = 'asc' | 'desc'
type ScheduleSourceKind = 'requested' | 'preliminary' | 'final'
type RefreshOptions = {
  silent?: boolean
}

interface EquipmentOption {
  equipment_code: string
  price?: number | string | null
  comment?: string | null
}

interface ServiceOption {
  service_code: string
  price?: number | string | null
  comment?: string | null
}

interface LcaListItem {
  id: string
  application_id: string
  leasing_company_id: string
  leasing_company_name?: string | null
  leasing_company_inn?: string | null
  company_name?: string | null
  company_inn?: string | null
  display_number?: string | null
  application_status?: string | null
  status: string
  display_status?: string | null
  review_notes?: string | null
  decision_comment?: string | null
  response_pdf_s3_key?: string | null
  response_pdf_file_name?: string | null
  response_pdf_size?: number | null
  response_pdf_uploaded_at?: string | null
  submitted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  [key: string]: unknown
}

interface LcaListResponse {
  items: LcaListItem[]
}

interface LcaConditionField {
  label: string
  value: string
}

type ProposalWithClientDecision = ApprovalOffer['proposal']

interface ApprovalOfferRow {
  id: string
  item: LcaListItem
  proposal: ProposalWithClientDecision
  leasingCompanyName: string
  clientDecisionAction: string | null
  values: Partial<Record<ApprovalMetricKey, number | string | null>>
}

interface RequestedConditionRow {
  label: string
  values: Partial<Record<ApprovalMetricKey, number | string | null>>
}

const props = defineProps<{
  applicationId: string
  application: ApplicationCompatible | null
  statusBucket: CheckoutStatusBucket
  showConfirmedAdditionalOptionsTooltip?: boolean
}>()

const emit = defineEmits<{
  'lca-items-loaded': [items: LcaListItem[]]
}>()

const config = useRuntimeConfig()
const additionalOptionsApi = createAdditionalOptionsApi(config)
const lcaItems = ref<LcaListItem[]>([])
const clientResponses = ref<ClientLeasingResponsesResponse | null>(null)
const lcaLoading = ref(false)
const approvalLoading = ref(false)
const lcaError = ref('')
const approvalError = ref('')
const showApprovalTable = computed(() => props.statusBucket !== 'sent')
const showApprovalTabs = computed(() =>
  props.statusBucket !== 'preliminary' &&
  props.statusBucket !== 'final' &&
  props.statusBucket !== 'selected' &&
  props.statusBucket !== 'deal'
)
const approvalTableTitle = computed(() => {
  if (props.statusBucket === 'preliminary') return 'Предварительное одобрение'
  if (props.statusBucket === 'final') return 'Итоговое одобрение'
  if (props.statusBucket === 'selected' || props.statusBucket === 'deal') return 'Выбранная лизинговая компания'
  return 'Одобрение'
})
const showLcaCardsSection = computed(() => props.statusBucket !== 'selected' && props.statusBucket !== 'deal')
const emptyLcaText = computed(() => {
  if (props.statusBucket === 'preliminary') return 'Все назначенные компании отправили предварительное КП.'
  if (props.statusBucket === 'final') return 'Все назначенные компании отправили итоговое КП.'
  return 'В этом статусе пока нет заявок.'
})
const sectionApprovalKind = (): ApprovalKind => ['final', 'selected', 'deal'].includes(props.statusBucket) ? 'final' : 'preliminary'
const activeApprovalKind = ref<ApprovalKind>(sectionApprovalKind())
const approvalSort = ref<{ key: ApprovalSortKey; direction: SortDirection }>({
  key: 'monthly_payment',
  direction: 'asc',
})
const selectedLca = ref<LcaListItem | null>(null)
const selectedScheduleLca = ref<LcaListItem | null>(null)
const selectedScheduleKind = ref<ScheduleSourceKind | null>(null)
const selectedScheduleProposal = ref<ProposalWithClientDecision | null>(null)
const pendingFinalRow = ref<ApprovalOfferRow | null>(null)
const downloadingPdfId = ref<string | null>(null)
const downloadingResponsePdfId = ref<string | null>(null)
const decisionLoadingId = ref<string | null>(null)
const equipmentCatalog = ref<Array<{ equipment_code: string; equipment_display_name: string }>>([])
const serviceCatalog = ref<Array<{ service_code: string; service_display_name: string }>>([])
let timer: ReturnType<typeof setInterval> | null = null
const { formatPrice, formatMoneyDecimal } = useFormatPrice()
const { formatDate } = useFormatDate()
const toast = useToast()

const approvalTabs = [
  { id: 'preliminary', label: 'Предварительное КП' },
  { id: 'final', label: 'Итоговое КП' },
] as const satisfies readonly { id: ApprovalKind; label: string }[]

const approvalHintText = computed(() => (
  activeApprovalKind.value === 'preliminary'
    ? 'Вы можете выбрать несколько КП предварительно одобренных, и лизинговые компании рассмотрят заявку и пришлют вам итоговое одобрение.'
    : 'Вы можете выбрать только одну лизинговую компанию и заключить с ней сделку.'
))

const approvalMetricColumns = [
  { key: 'monthly_payment', label: 'Ежемесячный платёж', format: 'money' },
  { key: 'down_payment_percent', label: 'Аванс (%)', format: 'percent' },
  { key: 'down_payment', label: 'Аванс (руб.)', format: 'money' },
  { key: 'lease_term_months', label: 'Срок (мес.)', format: 'months' },
  { key: 'total_amount', label: 'Стоимость договора', format: 'money' },
  { key: 'total_cost', label: 'Общая стоимость', format: 'money' },
  { key: 'buyout_amount', label: 'Выкупная стоимость', format: 'money' },
  { key: 'total_interest', label: 'Проценты', format: 'money' },
] as const satisfies readonly {
  key: ApprovalMetricKey
  label: string
  format: 'money' | 'percent' | 'months'
}[]

const approvalColumns = [
  { key: 'application', label: 'Заявка', sortable: true },
  { key: 'leasing_company', label: 'Лизинговая компания', sortable: true },
  ...approvalMetricColumns.map(column => ({
    ...column,
    sortable: true,
    align: 'right' as const,
  })),
  { key: 'actions', label: 'Действия', sortable: false, align: 'right' as const },
] as const satisfies readonly {
  key: ApprovalColumnKey
  label: string
  sortable: boolean
  align?: 'right'
}[]

const comparableApprovalKeys: ApprovalMetricKey[] = [
  'monthly_payment',
  'down_payment_percent',
  'down_payment',
  'total_amount',
  'total_cost',
  'buyout_amount',
  'total_interest',
]

const statusStageOrder: Record<string, number> = {
  submitted: 10,
  pending_distribution: 10,
  under_review: 10,
  closed: 10,
  rejected_prescoring: 10,
  rejected_approved: 10,
  approved_scoring: 20,
  approved_scoring_another_cond: 20,
  documents_required: 30,
  under_review_with_docs: 30,
  approved_final: 40,
  approved_final_another_cond: 40,
  rejected_final: 40,
  selected_lc: 50,
  deal: 60,
}

const itemTimestamp = (item: LcaListItem): number => {
  const value = item.updated_at || item.submitted_at || item.created_at || ''
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

// The server keeps `status` as the actual workflow state. `display_status` is
// only a read-only presentation overlay (for example, while documents await
// review), so it must not be used by buttons or workflow requests.
const displayStatus = (item: LcaListItem): string => item.display_status ?? item.status

const statusForBucket = (item: LcaListItem): string => (
  props.statusBucket === 'documents' ? displayStatus(item) : item.status
)

const compareByNewestStatus = (a: LcaListItem, b: LcaListItem): number => {
  const statusDiff = (statusStageOrder[displayStatus(b)] || 0) - (statusStageOrder[displayStatus(a)] || 0)
  if (statusDiff !== 0) return statusDiff
  return itemTimestamp(b) - itemTimestamp(a)
}

const currentStatusBucket = computed(() => CHECKOUT_LCA_STATUS_BUCKETS[props.statusBucket])
const statusStepTitle = computed(() => {
  if (props.statusBucket === 'sent') return 'Назначенные лизинговые компании'
  if (props.statusBucket === 'preliminary') return 'Назначенные лизинговые компании без КП'
  if (props.statusBucket === 'final') return 'Назначенные лизинговые компании без итогового КП'
  return `Офферы: ${currentStatusBucket.value.label}`
})

const isFinalApprovalStatus = (status: string) =>
  status === 'approved_final' || status === 'approved_final_another_cond' || status === 'selected_lc' || status === 'deal'

const isPreliminaryApprovalStatus = (status: string) =>
  status.startsWith('approved') || isFinalApprovalStatus(status)

const filteredLcaItems = computed(() => {
  let items: LcaListItem[] = []
  if (props.statusBucket === 'sent') {
    items = lcaItems.value
  } else if (props.statusBucket === 'preliminary') {
    items = lcaItems.value.filter(item => !isPreliminaryApprovalStatus(statusForBucket(item)))
  } else if (props.statusBucket === 'final') {
    items = lcaItems.value.filter(item => !isFinalApprovalStatus(statusForBucket(item)))
  } else {
    const statuses = currentStatusBucket.value.statuses as readonly string[]
    items = lcaItems.value.filter(item => statuses.includes(statusForBucket(item)))
  }
  return [...items].sort(compareByNewestStatus)
})

const stringField = (source: Record<string, unknown> | null | undefined, field: string): string => {
  const value = source?.[field]
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}

const nestedCompanyName = (source: Record<string, unknown> | null | undefined): string => {
  const company = source?.company as Record<string, unknown> | null | undefined
  if (typeof company !== 'object' || company === null) return ''
  return stringField(company, 'name')
}

const numberField = (source: Record<string, unknown> | null | undefined, field: string): number | string | null => {
  const value = source?.[field]
  return typeof value === 'number' || typeof value === 'string' ? value : null
}

const normalizeNumber = (value: number | string | null | undefined): number | null => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const applicationNumber = (item: LcaListItem): string => {
  return item.display_number || stringField(props.application, 'display_number') || '—'
}

const applicationNumberForSummary = computed(() => stringField(props.application, 'display_number') || '—')

const applicationCompanyName = (item: LcaListItem): string => {
  return item.company_name || nestedCompanyName(props.application) || stringField(props.application, 'company_name') || 'Не указана'
}

const applicationCompanyNameForSummary = computed(() =>
  nestedCompanyName(props.application) || stringField(props.application, 'company_name') || 'Не указана',
)

const leasingCompanyName = (item: LcaListItem): string => {
  return item.leasing_company_name || '—'
}

const applicationTotalAmount = computed(() => formatMoneyValue(
  numberField(props.application, 'total_amount')
  ?? numberField(props.application, 'total_cost')
  ?? numberField(props.application, 'total_items_price')
  ?? numberField(props.application, 'total_vehicles_price'),
))

const applicationItemsAmount = computed(() => formatMoneyValue(
  numberField(props.application, 'total_items_price')
  ?? numberField(props.application, 'total_vehicles_price'),
))

const formatMoneyValue = (value: number | string | null): string => (value === null ? '—' : formatPrice(value))
const formatPlainValue = (value: number | string | null): string => (value === null || value === '' ? '—' : String(value))
const formatPercentValue = (value: number | string | null): string => {
  const numeric = normalizeNumber(value)
  if (numeric === null) return '—'
  return `${numeric.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

const conditionNumberField = (item: LcaListItem, field: string): number | string | null => (
  numberField(item, field) ?? numberField(props.application, field)
)

const lcaConditionFields = (item: LcaListItem): LcaConditionField[] => [
  { label: 'Ежемесячный платёж', value: formatMoneyValue(conditionNumberField(item, 'monthly_payment')) },
  { label: 'Аванс (%)', value: formatPercentValue(conditionNumberField(item, 'down_payment_percent')) },
  { label: 'Аванс (руб.)', value: formatMoneyValue(conditionNumberField(item, 'down_payment')) },
  { label: 'Срок (мес.)', value: formatPlainValue(conditionNumberField(item, 'lease_term_months')) },
  { label: 'Стоимость договора', value: formatMoneyValue(conditionNumberField(item, 'total_amount')) },
  {
    label: 'Общая стоимость',
    value: formatMoneyValue(
      conditionNumberField(item, 'total_cost')
      ?? conditionNumberField(item, 'total_amount')
      ?? conditionNumberField(item, 'total_items_price')
      ?? conditionNumberField(item, 'total_vehicles_price'),
    ),
  },
  { label: 'Выкупная стоимость', value: formatMoneyValue(conditionNumberField(item, 'buyout_amount')) },
  { label: 'Проценты', value: formatMoneyValue(conditionNumberField(item, 'total_interest')) },
]

const vehicleList = computed<Array<Record<string, unknown>>>(() => {
  const vehicles = props.application?.vehicles
  if (Array.isArray(vehicles)) return vehicles as Array<Record<string, unknown>>
  const details = props.application?.vehicle_details
  return Array.isArray(details) ? details as Array<Record<string, unknown>> : []
})

const historicalItemStatuses = new Set(['removed', 'replaced', 'rejected'])
const applicationItemList = computed<Array<Record<string, unknown>>>(() => {
  const items = props.application?.items
  if (!Array.isArray(items)) return []
  return (items as Array<Record<string, unknown>>).filter((item) => {
    const status = stringField(item, 'status')
    return !status || !historicalItemStatuses.has(status)
  })
})

const vehiclesWithAdditionalOptions = computed(() =>
  vehicleList.value.filter(vehicle =>
    vehicleEquipments(vehicle).length > 0 || vehicleServices(vehicle).length > 0
  )
)

const vehicleTitle = (vehicle: Record<string, unknown>): string => formatApplicationVehicleTitle(vehicle)

const vehicleEquipments = (vehicle: Record<string, unknown>): EquipmentOption[] =>
  Array.isArray(vehicle.equipments) ? vehicle.equipments as EquipmentOption[] : []

const vehicleServices = (vehicle: Record<string, unknown>): ServiceOption[] =>
  Array.isArray(vehicle.services) ? vehicle.services as ServiceOption[] : []

const equipmentName = (code: string): string =>
  equipmentCatalog.value.find(option => option.equipment_code === code)?.equipment_display_name || code

const serviceName = (code: string): string =>
  serviceCatalog.value.find(option => option.service_code === code)?.service_display_name || code

const hasAssignedOptionPrice = (price: number | string | null | undefined): boolean => {
  const value = Number(price)
  return Number.isFinite(value) && value > 0
}

const additionalEquipmentTotal = (vehicle: Record<string, unknown>): number => {
  const quantity = normalizeNumber(numberField(vehicle, 'quantity')) || 1
  return vehicleEquipments(vehicle).reduce(
    (sum, item) => sum + (hasAssignedOptionPrice(item.price) ? Number(item.price) : 0),
    0,
  ) * quantity
}

const additionalServicesTotal = (vehicle: Record<string, unknown>): number => {
  const quantity = normalizeNumber(numberField(vehicle, 'quantity')) || 1
  return vehicleServices(vehicle).reduce(
    (sum, item) => sum + (hasAssignedOptionPrice(item.price) ? Number(item.price) : 0),
    0,
  ) * quantity
}

const additionalOptionsTotal = (vehicle: Record<string, unknown>): number =>
  additionalEquipmentTotal(vehicle) + additionalServicesTotal(vehicle)

const additionalOptionsGrandTotal = computed(() =>
  vehiclesWithAdditionalOptions.value.reduce((sum, vehicle) => sum + additionalOptionsTotal(vehicle), 0)
)

const showConfirmedAdditionalOptionsHint = computed(() =>
  Boolean(props.showConfirmedAdditionalOptionsTooltip) && additionalOptionsGrandTotal.value > 0
)

const leasingSubjectSummary = computed(() => {
  if (applicationItemList.value.length > 0) {
    const titles = applicationItemList.value.map((item) => stringField(item, 'title') || 'Техника')
    if (titles.length <= 2) return titles.join(', ')
    return `${titles.slice(0, 2).join(', ')} и еще ${titles.length - 2}`
  }
  if (vehicleList.value.length === 0) return '—'
  const titles = vehicleList.value.map(vehicleTitle)
  if (titles.length <= 2) return titles.join(', ')
  return `${titles.slice(0, 2).join(', ')} и еще ${titles.length - 2}`
})

const itemCountSummary = computed(() => {
  const projectedCount = normalizeNumber(numberField(props.application, 'items_count'))
  if (projectedCount !== null) return `${projectedCount}`
  if (applicationItemList.value.length > 0) {
    const total = applicationItemList.value.reduce((sum, item) => (
      sum + (normalizeNumber(numberField(item, 'quantity')) || 1)
    ), 0)
    return `${total}`
  }
  if (vehicleList.value.length === 0) return stringField(props.application, 'total_vehicles') || '—'
  const total = vehicleList.value.reduce((sum, vehicle) => {
    const quantity = normalizeNumber(numberField(vehicle, 'quantity')) || 1
    return sum + quantity
  }, 0)
  return `${total}`
})

const applicationEmail = computed(() => (
  stringField(props.application, 'email') || 'Email не указан'
))

const applicationSubmittedDate = (item: LcaListItem): string => {
  return formatDate(
    item.submitted_at || item.created_at || stringField(props.application, 'created_at'),
    { year: 'numeric', month: 'long', day: 'numeric' },
  )
}

const valuesForApprovalSource = (
  proposal: ProposalWithClientDecision,
): Partial<Record<ApprovalMetricKey, number | string | null>> => (
  Object.fromEntries(approvalMetricColumns.map(column => [column.key, numberField(proposal as unknown as Record<string, unknown>, column.key)])) as Partial<Record<ApprovalMetricKey, number | string | null>>
)

const requestedConditionRow = computed<RequestedConditionRow>(() => {
  const requested = clientResponses.value?.requested || props.application || {}
  return {
    label: 'Запрошенные условия',
    values: Object.fromEntries(
      approvalMetricColumns.map(column => [column.key, numberField(requested, column.key)]),
    ) as Partial<Record<ApprovalMetricKey, number | string | null>>,
  }
})

const rawApprovedOfferRows = computed<ApprovalOfferRow[]>(() => {
  let offers = clientResponses.value?.approval_offers?.[activeApprovalKind.value] || []
  if (props.statusBucket === 'selected' || props.statusBucket === 'deal') {
    const selectedOffers = offers.filter(offer =>
      offer.lca.status === 'selected_lc' || offer.lca.status === 'deal' || offer.proposal.client_decision_action === 'accepted'
    )
    if (selectedOffers.length > 0) {
      offers = selectedOffers
    }
  }
  return offers
    .map((offer) => {
      return {
        id: offer.lca.id,
        item: offer.lca,
        proposal: offer.proposal,
        leasingCompanyName: offer.leasing_company?.name || leasingCompanyName(offer.lca),
        clientDecisionAction: offer.proposal.client_decision_action || null,
        values: valuesForApprovalSource(offer.proposal),
      }
    })
})

const compareApprovalRows = (a: ApprovalOfferRow, b: ApprovalOfferRow): number => {
  const key = approvalSort.value.key
  if (key === 'application') {
    return applicationNumber(a.item).localeCompare(applicationNumber(b.item), 'ru')
  }
  if (key === 'leasing_company') {
    return a.leasingCompanyName.localeCompare(b.leasingCompanyName, 'ru')
  }

  const left = normalizeNumber(a.values[key])
  const right = normalizeNumber(b.values[key])
  if (left === null && right === null) return 0
  if (left === null) return 1
  if (right === null) return -1
  return left - right
}

const sortApprovalRows = (rows: ApprovalOfferRow[]): ApprovalOfferRow[] => {
  const sorted = [...rows].sort(compareApprovalRows)
  return approvalSort.value.direction === 'asc' ? sorted : sorted.reverse()
}

const approvedOfferRows = computed(() => sortApprovalRows(rawApprovedOfferRows.value))

const bestApprovalValues = computed<Partial<Record<ApprovalMetricKey, number | null>>>(() => {
  const result: Partial<Record<ApprovalMetricKey, number | null>> = {}
  for (const key of comparableApprovalKeys) {
    const values = rawApprovedOfferRows.value
      .map(row => normalizeNumber(row.values[key]))
      .filter((value): value is number => value !== null)
    const uniqueValues = new Set(values)
    if (uniqueValues.size <= 1) {
      result[key] = null
      continue
    }
    result[key] = Math.min(...values)
  }
  return result
})

const approvalCellClass = (row: ApprovalOfferRow, key: ApprovalMetricKey): string => {
  if (!comparableApprovalKeys.includes(key)) return 'text-[color:var(--storefront-text,#111827)]'
  const value = normalizeNumber(row.values[key])
  const best = bestApprovalValues.value[key]
  if (value === null || best === null || best === undefined || value !== best) return 'text-[color:var(--storefront-text,#111827)]'
  return 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] font-semibold text-[color:var(--storefront-success-text,#14532d)]'
}

const approvalRowClass = (row: ApprovalOfferRow): string => {
  if (row.item.status === 'selected_lc') return 'bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/0.6)]'
  if (row.clientDecisionAction === 'accepted') return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]'
  return 'bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))]'
}

const formatApprovalValue = (
  value: number | string | null | undefined,
  format: 'money' | 'percent' | 'months',
): string => {
  if (value === null || value === undefined || value === '') return '—'
  if (format === 'money') return formatMoneyDecimal(value)
  if (format === 'percent') return formatPercentValue(value)
  return `${value} мес.`
}

const setApprovalKind = (kind: ApprovalKind) => {
  activeApprovalKind.value = kind
  approvalSort.value = { key: 'monthly_payment', direction: 'asc' }
}

const setApprovalSort = (key: ApprovalColumnKey) => {
  if (key === 'actions') return
  if (approvalSort.value.key === key) {
    approvalSort.value = {
      key,
      direction: approvalSort.value.direction === 'asc' ? 'desc' : 'asc',
    }
    return
  }
  approvalSort.value = { key, direction: 'asc' }
}

const sortIndicator = (key: ApprovalColumnKey): string => {
  if (key === 'actions' || approvalSort.value.key !== key) return '↕'
  return approvalSort.value.direction === 'asc' ? '↑' : '↓'
}

const selectedFinalLcaId = computed(() => lcaItems.value.find(item => item.status === 'selected_lc')?.id || null)

const isFinalSelectionDisabled = (row: ApprovalOfferRow): boolean => {
  if (decisionLoadingId.value === row.id) return true
  return Boolean(selectedFinalLcaId.value && selectedFinalLcaId.value !== row.id)
}

const responsePdfUrl = (row: ApprovalOfferRow): string => {
  const base = config.public.apiBase.replace(/\/$/, '')
  return `${base}/api/v1/applications/${row.item.application_id}/leasing-responses/${row.item.leasing_company_id}/pdf?proposal_kind=${activeApprovalKind.value}&lca_id=${row.item.id}`
}

const downloadFile = async (url: string, fileName: string) => {
  const response = await fetch(notificationUrl(url), { credentials: 'include' })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName
  link.click()
  URL.revokeObjectURL(objectUrl)
}

const downloadResponsePdf = async (row: ApprovalOfferRow) => {
  if (downloadingResponsePdfId.value) return
  downloadingResponsePdfId.value = row.id
  try {
    await downloadFile(responsePdfUrl(row), pdfFileName(row.item, activeApprovalKind.value))
  } catch (err) {
    console.error('LC response PDF download failed', err)
    toast.error('Не удалось скачать PDF КП')
  } finally {
    downloadingResponsePdfId.value = null
  }
}

const submitProposalDecision = async (row: ApprovalOfferRow, action: 'accepted' | 'cancelled') => {
  if (decisionLoadingId.value) return
  decisionLoadingId.value = row.id
  try {
    await notificationRequest(
      `/api/v1/applications/${props.applicationId}/proposals/${row.proposal.id}/decision`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include',
        method: 'POST',
        body: { action },
      },
    )
    await refresh()
  } catch (err) {
    console.error('Proposal decision failed', err)
    toast.error('Не удалось обновить выбор КП')
  } finally {
    decisionLoadingId.value = null
  }
}

const confirmFinalSelection = (row: ApprovalOfferRow) => {
  pendingFinalRow.value = row
}

const selectFinalRow = async () => {
  const row = pendingFinalRow.value
  if (!row || decisionLoadingId.value) return
  decisionLoadingId.value = row.id
  try {
    await notificationRequest(
      `/api/v1/applications/${props.applicationId}/lca/${row.item.id}/select`,
      {
        baseURL: config.public.apiBase,
        credentials: 'include',
        method: 'POST',
      },
    )
    pendingFinalRow.value = null
    await refresh()
  } catch (err) {
    console.error('Final LC selection failed', err)
    toast.error('Не удалось выбрать лизинговую компанию')
  } finally {
    decisionLoadingId.value = null
  }
}

const applicationPdfUrl = (item: LcaListItem): string => {
  const base = config.public.apiBase.replace(/\/$/, '')
  return `${base}/api/v1/applications/${item.application_id}/leasing-responses/${item.leasing_company_id}/pdf?lca_id=${item.id}`
}

const pdfFileName = (item: LcaListItem, kind: ApprovalKind | 'lca' = 'lca'): string => {
  const number = applicationNumber(item).replace(/[^\wа-яА-Я-]+/g, '-')
  return `leasing-response-${kind}-${number || 'application'}.pdf`
}

const downloadApplicationPdf = async (item: LcaListItem) => {
  if (downloadingPdfId.value) return
  downloadingPdfId.value = item.id
  try {
    await downloadFile(applicationPdfUrl(item), pdfFileName(item))
  } catch (err) {
    console.error('Application PDF download failed', err)
    toast.error('Не удалось скачать PDF заявки')
  } finally {
    downloadingPdfId.value = null
  }
}

const openPaymentSchedule = (
  item: LcaListItem,
  kind: ScheduleSourceKind | null = null,
  proposal: ProposalWithClientDecision | null = null,
) => {
  selectedScheduleLca.value = item
  selectedScheduleKind.value = kind
  selectedScheduleProposal.value = proposal
}

const closePaymentSchedule = () => {
  selectedScheduleLca.value = null
  selectedScheduleKind.value = null
  selectedScheduleProposal.value = null
}

const refresh = async (options: RefreshOptions = {}) => {
  if (!props.applicationId) return
  const shouldShowLoading = !options.silent
  if (shouldShowLoading) lcaLoading.value = true
  if (shouldShowLoading) approvalLoading.value = true
  if (shouldShowLoading) lcaError.value = ''
  if (shouldShowLoading) approvalError.value = ''

  const query = new URLSearchParams({
    application_id: props.applicationId,
    limit: '100',
  })

  const lcaRequest = notificationRequest<LcaListResponse>(
    `/api/v1/leasing-company-applications/?${query.toString()}`,
    { baseURL: config.public.apiBase, credentials: 'include' },
  )
    .then((lcaResponse) => {
      lcaItems.value = lcaResponse.items || []
      emit('lca-items-loaded', lcaItems.value)
    })
    .catch((err) => {
      console.error('LCA list loading failed', err)
      if (shouldShowLoading || lcaItems.value.length === 0) {
        lcaError.value = 'Не удалось загрузить офферы лизинговых компаний.'
      }
    })
    .finally(() => {
      if (shouldShowLoading) lcaLoading.value = false
    })

  const responsesRequest = notificationRequest<ClientLeasingResponsesResponse>(
    `/api/v1/applications/${props.applicationId}/leasing-responses`,
    { baseURL: config.public.apiBase, credentials: 'include' },
  )
    .then((responsesResponse) => {
      clientResponses.value = responsesResponse
    })
    .catch((err) => {
      console.error('Leasing responses loading failed', err)
      if (shouldShowLoading || approvedOfferRows.value.length === 0) {
        approvalError.value = 'Не удалось загрузить КП лизинговых компаний.'
      }
    })
    .finally(() => {
      if (shouldShowLoading) approvalLoading.value = false
    })

  await lcaRequest
  await responsesRequest
}

const startPolling = () => {
  if (timer) return
  timer = setInterval(() => {
    refresh({ silent: true })
  }, 15000)
}

const stopPolling = () => {
  if (!timer) return
  clearInterval(timer)
  timer = null
}

const statusText = (status: string) => {
  const labels: Record<string, string> = {
    submitted: 'Отправлена',
    pending_distribution: 'На распределении',
    under_review: 'На рассмотрении',
    under_review_with_docs: 'На рассмотрении с доп. документами',
    approved_scoring: 'Предварительное КП',
    approved_scoring_another_cond: 'Предварительное КП на других условиях',
    approved_final: 'Итоговое КП',
    approved_final_another_cond: 'Итоговое КП на других условиях',
    selected_lc: 'Выбрана ЛК',
    deal: 'Сделка заключена',
    rejected_prescoring: 'Отклонена на предварительном рассмотрении',
    rejected_approved: 'Отклонена после предварительного КП',
    rejected_final: 'Отклонена после итогового КП',
    closed: 'Закрыта',
    documents_required: 'Запрос дополнительных документов',
  }
  return labels[status] || status
}

const statusClass = (status: string) => {
  if (status.startsWith('approved') || status === 'selected_lc' || status === 'deal') {
    return 'bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]'
  }
  if (status.startsWith('rejected')) return 'bg-[color:rgb(var(--storefront-error-rgb,254_226_226)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-error-text,#991b1b)]'
  if (status === 'documents_required' || status === 'under_review_with_docs') {
    return 'bg-[color:rgb(var(--storefront-warning-rgb,254_243_199)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-warning-text,#92400e)]'
  }
  if (status === 'closed') return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#374151)]'
  return 'bg-[color:rgb(var(--storefront-surface-muted-rgb,219_234_254)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-text,#1e40af)]'
}

watch(() => props.applicationId, () => {
  activeApprovalKind.value = sectionApprovalKind()
  selectedLca.value = null
  closePaymentSchedule()
  pendingFinalRow.value = null
  refresh()
})

// A different status section is explicit navigation; polling the same section
// must not overwrite a proposal tab the client selected manually.
watch(() => props.statusBucket, () => {
  setApprovalKind(sectionApprovalKind())
})

async function loadAdditionalOptionCatalogs() {
  try {
    const equipments = await additionalOptionsApi.getEquipments()
    const services = await additionalOptionsApi.getServices()
    equipmentCatalog.value = equipments.items || []
    serviceCatalog.value = services.items || []
  } catch (err) {
    console.error('Error loading additional option catalogs:', err)
  }
}

onMounted(() => {
  loadAdditionalOptionCatalogs()
  refresh()
  startPolling()
})

onBeforeUnmount(stopPolling)
</script>
