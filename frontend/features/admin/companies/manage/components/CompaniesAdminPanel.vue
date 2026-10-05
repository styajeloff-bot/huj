<template>
  <div>
    <div class="border-b border-gray-200 mb-6">
      <nav class="flex space-x-6">
        <button
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeSubTab === 'companies' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeSubTab = 'companies'"
        >
          Компании
        </button>
        <button
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeSubTab === 'contractors' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeSubTab = 'contractors'"
        >
          Подрядчики
        </button>
        <button
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeSubTab === 'distributors' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeSubTab = 'distributors'"
        >
          Дистрибьюторы
        </button>
        <button
          class="py-2 px-1 border-b-2 font-medium text-sm"
          :class="activeSubTab === 'dealer-groups' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeSubTab = 'dealer-groups'"
        >
          Группы дилеров
        </button>
      </nav>
    </div>

    <div v-if="activeSubTab === 'companies'">
      <CompaniesListPanel />
    </div>

    <div v-else-if="activeSubTab === 'contractors'">
      <ContractorsPanel />
    </div>

    <div v-else-if="activeSubTab === 'distributors'">
      <DistributorsPanel />
    </div>

    <div v-else-if="activeSubTab === 'dealer-groups'">
      <DealerGroupsPanel />
    </div>
  </div>
</template>

<script setup lang="ts">
import CompaniesListPanel from './CompaniesListPanel.vue'
import ContractorsPanel from './ContractorsPanel.vue'
import DealerGroupsPanel from './DealerGroupsPanel.vue'
import DistributorsPanel from './DistributorsPanel.vue'

const activeSubTab = ref('companies')
</script>
