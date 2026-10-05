<template>
  <section data-storefront-block="client.application" class="rounded-lg border border-[color:var(--storefront-border,#bfdbfe)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] p-4" aria-labelledby="application-support-title">
    <h3 id="application-support-title" class="text-lg font-semibold text-[color:var(--storefront-title,#172554)]">Поддержка</h3>
    <ul class="mt-3 space-y-3">
      <li v-for="program in programs" :key="program.key" class="rounded-lg bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] p-3 text-sm">
        <p class="font-semibold text-[color:var(--storefront-text,#030712)]">{{ program.name }}</p>
        <p class="mt-1 text-[color:var(--storefront-text,#374151)]">
          <span class="font-medium">Ценовые условия:</span> {{ program.pricing }}
        </p>
        <NuxtLink
          v-if="linkEnabled && supportRoute(program)"
          :to="supportRoute(program) ?? { path: '/workspace/support' }"
          class="mt-2 inline-flex font-semibold text-[color:var(--storefront-link,#1d4ed8)] hover:text-[color:var(--storefront-link-hover,#1e3a8a)]"
        >
          Открыть поддержку
        </NuxtLink>
        <p v-else-if="linkEnabled" class="mt-2 text-[color:var(--storefront-text-muted,#6b7280)]">Связанная поддержка больше недоступна</p>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import type { ApplicationSupportProgramRow } from '~/features/applications/applicationSupportPrograms'
import { createSupportDeepLinkQuery } from '~/utils/supportDeepLink'

withDefaults(defineProps<{
  programs: ApplicationSupportProgramRow[]
  linkEnabled?: boolean
}>(), {
  linkEnabled: false,
})

const supportRoute = (program: ApplicationSupportProgramRow) => {
  const query = createSupportDeepLinkQuery(program)
  return query ? { path: '/workspace/support', query } : null
}
</script>
