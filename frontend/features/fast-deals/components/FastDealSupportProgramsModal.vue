<template>
  <Modal
    :show="true"
    title="Программы поддержки"
    :subtitle="`${vehicleTitle(vehicle)} · ${vehicle.vin}`"
    size="3xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <p class="text-sm text-gray-600">
        Сумма программы рассчитывается сервером. Новая программа должна быть совместима с уже применёнными.
        Поддержка учитывается в цене один раз.
      </p>

      <p v-if="loading" class="text-sm text-gray-500">Загрузка программ…</p>
      <p v-else-if="loadError" role="alert" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
        {{ loadError }}
        <button type="button" class="underline ml-1" @click="load">Повторить</button>
      </p>
      <template v-else>
        <p v-if="hint" class="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">{{ hint }}</p>
        <p v-else-if="!items.length" class="text-sm text-gray-500">Для этой техники нет доступных программ поддержки.</p>
        <ul v-else class="divide-y divide-gray-100 rounded-lg border border-gray-200">
          <li v-for="item in items" :key="item.id" class="flex items-start justify-between gap-4 p-3">
            <div class="min-w-0 space-y-1">
              <p class="text-sm font-medium text-gray-900">{{ item.name }}</p>
              <p class="text-xs text-gray-500">
                <template v-if="item.starts_at || item.ends_at">
                  Действует {{ item.starts_at ? `с ${formatDate(item.starts_at)}` : '' }} {{ item.ends_at ? `по ${formatDate(item.ends_at)}` : '' }}
                </template>
              </p>
              <p v-if="item.affects_price === false" class="text-xs text-gray-500">Не снижает цену: используется для компенсаций</p>
              <p v-if="!item.is_compatible && !item.applied" class="text-xs text-red-600">
                Несовместима с уже применёнными программами
              </p>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <span class="text-sm tabular-nums text-gray-900">{{ formatMoney(item.support_amount) }}</span>
              <span v-if="item.applied" class="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">Применена</span>
              <button
                v-if="item.applied && appliedIdOf(item.id)"
                type="button"
                class="text-sm text-red-600 hover:text-red-700"
                :disabled="ctx.busy.value"
                @click="remove(item.id)"
              >
                Снять
              </button>
              <button
                v-else-if="!item.applied"
                type="button"
                class="btn-outline text-sm px-3 py-1.5"
                :disabled="ctx.busy.value || !item.is_compatible"
                @click="apply(item.id)"
              >
                Применить
              </button>
            </div>
          </li>
        </ul>
      </template>

      <FastDealCardError :error="error" />
    </div>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Закрыть</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { parseFastDealError } from '../api/fastDealsApi'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatDate, formatMoney, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealVehicle, SupportProgramOption } from '../types'
import FastDealCardError from './FastDealCardError.vue'

const props = defineProps<{ vehicle: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()
const items = ref<SupportProgramOption[]>([])
const hint = ref('')
const loading = ref(true)
const loadError = ref('')
const error = ref<ActionFailure | null>(null)

/** The applied row of a program: removal works with its id, not the program's. */
const appliedIdOf = (programId: string): string | undefined =>
  (props.vehicle.applied_supports ?? []).find(item => item.support_program_id === programId)?.id

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await ctx.api.supportPrograms(ctx.dealId, props.vehicle.id)
    items.value = response.items
    hint.value = response.support_hint ?? ''
  } catch (failure) {
    loadError.value = parseFastDealError(failure).detail
  } finally {
    loading.value = false
  }
}

async function apply(programId: string) {
  error.value = null
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.applySupportProgram(card.id, props.vehicle.id, etag, programId))
  if (!result.ok) {
    error.value = result.error
    return
  }
  await load()
}

async function remove(programId: string) {
  const appliedId = appliedIdOf(programId)
  if (!appliedId) return
  error.value = null
  if (!(await ctx.confirmEdit())) return
  const result = await ctx.run((etag, card) => ctx.api.removeAppliedSupport(card.id, props.vehicle.id, appliedId, etag))
  if (!result.ok) {
    error.value = result.error
    return
  }
  await load()
}

onMounted(load)
</script>
