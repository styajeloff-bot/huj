<template>
  <div class="mt-4 rounded-lg border border-purple-100 bg-purple-50/40 p-4 space-y-3" :aria-label="`Поддержка: ${vehicle.vin}`">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h4 class="text-sm font-semibold text-gray-900">Поддержка</h4>
      <div class="flex gap-2 flex-wrap">
        <button
          v-if="canOpenPrograms"
          type="button"
          class="btn-outline text-sm px-3 py-1.5"
          @click="programsOpen = true"
        >
          Программы поддержки
        </button>
        <button
          v-if="canRequest"
          type="button"
          class="btn-outline text-sm px-3 py-1.5"
          @click="requestOpen = true"
        >
          Запросить у дистрибьютора
        </button>
        <button
          v-if="canDecide"
          type="button"
          class="btn-primary text-sm px-3 py-1.5"
          @click="decisionOpen = true"
        >
          Принять решение
        </button>
      </div>
    </div>

    <ul v-if="applied.length" class="space-y-1 text-sm">
      <li v-for="item in applied" :key="item.id" class="flex items-start justify-between gap-3">
        <span class="min-w-0">
          <span class="text-gray-900">{{ item.name }}</span>
          <span v-if="item.affects_price === false" class="block text-xs text-gray-500">
            Не снижает цену: используется для компенсаций
          </span>
        </span>
        <span class="flex items-center gap-3 shrink-0">
          <span class="tabular-nums text-gray-900">{{ formatMoney(item.support_amount) }}</span>
          <button
            v-if="canRemove"
            type="button"
            class="text-red-600 hover:text-red-700"
            :disabled="ctx.busy.value"
            :aria-label="`Снять программу: ${item.name}`"
            @click="remove(item.id)"
          >
            Снять
          </button>
        </span>
      </li>
    </ul>
    <p v-else-if="vehicle.applied_supports" class="text-sm text-gray-500">Программы поддержки не применены.</p>

    <p v-if="vehicle.support_amount && hasAmount(vehicle.support_amount)" class="text-sm text-gray-700">
      Учтено в цене: <strong class="tabular-nums">{{ formatMoney(vehicle.support_amount) }}</strong>
    </p>

    <div
      v-if="hasAmount(vehicle.unaccounted_support)"
      class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 flex items-center justify-between gap-3 flex-wrap"
    >
      <span>Неучтённая поддержка: <strong class="tabular-nums">{{ formatMoney(vehicle.unaccounted_support) }}</strong></span>
      <button
        v-if="ctx.can('apply_support')"
        type="button"
        class="btn-primary text-sm px-3 py-1.5"
        :disabled="ctx.busy.value"
        @click="applyUnaccounted"
      >
        Применить
      </button>
    </div>

    <div v-if="request" class="rounded-lg border border-gray-200 bg-white p-3 text-sm space-y-1">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="font-medium text-gray-900">Запрос поддержки</span>
        <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="supportStatusTones[request.status] ?? 'bg-gray-100 text-gray-700'">
          {{ supportStatusLabel(request.status) }}
        </span>
        <span v-if="request.distributor_name" class="text-gray-500">· {{ request.distributor_name }}</span>
      </div>
      <p class="text-gray-700">Запрошено: <span class="tabular-nums">{{ formatMoney(request.requested_amount) }}</span></p>
      <p v-if="request.decided_amount && request.status !== 'cancelled'" class="text-gray-700">
        Согласовано: <span class="tabular-nums">{{ formatMoney(request.decided_amount) }}</span>
      </p>
      <p v-if="request.comment" class="text-gray-600">Комментарий дилера: {{ request.comment }}</p>
      <p v-if="request.decision_comment" class="text-gray-600">
        {{ request.status === 'cancelled' ? 'Причина отказа' : 'Комментарий дистрибьютора' }}: {{ request.decision_comment }}
      </p>
      <p v-if="request.status === 'pre_approved'" class="text-xs text-gray-500">Предварительное согласование: цена пока не меняется.</p>
    </div>

    <p v-if="vehicle.support_hint && !canRequest" class="text-sm text-gray-600">{{ vehicle.support_hint }}</p>

    <FastDealCardError :error="error" />

    <FastDealSupportProgramsModal v-if="programsOpen" :vehicle="vehicle" @close="programsOpen = false" />
    <FastDealSupportRequestModal v-if="requestOpen" :vehicle="vehicle" @close="requestOpen = false" />
    <FastDealSupportDecisionModal v-if="decisionOpen && request" :vehicle="vehicle" :request="request" @close="decisionOpen = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatMoney, isPositiveMoney, supportStatusLabel, supportStatusTones } from '../composables/fastDealCardFormat'
import type { FastDealVehicle } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealSupportDecisionModal from './FastDealSupportDecisionModal.vue'
import FastDealSupportProgramsModal from './FastDealSupportProgramsModal.vue'
import FastDealSupportRequestModal from './FastDealSupportRequestModal.vue'

const props = defineProps<{ vehicle: FastDealVehicle }>()

const ctx = useFastDealCardContext()
const programsOpen = ref(false)
const requestOpen = ref(false)
const decisionOpen = ref(false)
const error = ref<ActionFailure | null>(null)

const applied = computed(() => props.vehicle.applied_supports ?? [])
const request = computed(() => props.vehicle.support_request ?? null)
const hasAmount = (value: string | null | undefined) => isPositiveMoney(value)

/** Programs belong to catalog units and are applied by the dealer while it still has a say. */
const canOpenPrograms = computed(() => ctx.dealerSide.value && ctx.can('edit') && props.vehicle.vehicle_source_type === 'product')
const canRemove = computed(() => ctx.dealerSide.value && ctx.can('edit'))
const canRequest = computed(() => ctx.can('request_support') && props.vehicle.can_request_support === true)
const canDecide = computed(
  () => ctx.can('decide_support') && request.value !== null && (request.value.status === 'requested' || request.value.status === 'pre_approved'),
)

async function remove(appliedId: string) {
  error.value = null
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.removeAppliedSupport(card.id, props.vehicle.id, appliedId, etag))
  if (!result.ok) error.value = result.error
}

/** Accounts the approved amount: a DD returns to a draft, a DL starts a change cycle. */
async function applyUnaccounted() {
  error.value = null
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.applySupport(card.id, props.vehicle.id, etag))
  if (!result.ok) error.value = result.error
}
</script>
