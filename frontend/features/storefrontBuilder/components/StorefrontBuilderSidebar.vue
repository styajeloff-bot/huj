<template>
  <aside class="flex w-88 shrink-0 flex-col border-r border-gray-200 bg-white select-none shadow-sm z-20">
    <!-- Tabs Header -->
    <nav class="flex border-b border-gray-200 bg-gray-50/60" aria-label="Панель инструментов">
      <button
        v-for="tab in TABS"
        :key="tab.key"
        type="button"
        class="flex flex-1 flex-col items-center gap-1 py-2 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-inset"
        :class="activeTab === tab.key ? 'border-b-2 border-blue-600 bg-white text-blue-700 font-semibold' : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900'"
        @click="activeTab = tab.key"
      >
        <component :is="tab.icon" class="h-4 w-4" aria-hidden="true" />
        <span class="truncate max-w-full px-0.5 text-[11px]">{{ tab.label }}</span>
      </button>
    </nav>

    <!-- Tab Content -->
    <div class="flex-1 overflow-y-auto p-4">
      <!-- 1. TAB: WIDGETS -->
      <div v-show="activeTab === 'widgets'" class="space-y-4">
        <!-- Search & Filter -->
        <div class="relative">
          <MagnifyingGlassIcon class="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" aria-hidden="true" />
          <input
            v-model.trim="searchQuery"
            type="search"
            placeholder="Поиск виджетов…"
            class="h-9 w-full rounded-lg border border-gray-300 bg-white pl-9 pr-3 text-xs text-gray-900 placeholder:text-gray-400 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
        </div>

        <!-- Categories Filter -->
        <div class="flex flex-wrap gap-1">
          <button
            v-for="cat in CATEGORIES"
            :key="cat.key"
            type="button"
            class="rounded-full px-2.5 py-1 text-xs font-medium transition-colors"
            :class="selectedCategory === cat.key ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
            @click="selectedCategory = cat.key"
          >
            {{ cat.label }}
          </button>
        </div>

        <!-- Widgets Grid -->
        <div class="grid grid-cols-1 gap-2.5">
          <div
            v-for="widget in filteredWidgets"
            :key="widget.type"
            draggable="true"
            class="group flex cursor-grab items-start gap-3 rounded-lg border border-gray-200 bg-white p-3 shadow-xs transition-all hover:border-blue-500 hover:shadow-sm active:cursor-grabbing"
            @dragstart="handleDragStart($event, widget.type)"
            @click="handleWidgetClick(widget.type)"
          >
            <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors">
              <component :is="getWidgetIcon(widget.icon)" class="h-5 w-5" aria-hidden="true" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center justify-between">
                <h4 class="text-xs font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                  {{ widget.title }}
                </h4>
                <PlusIcon class="h-3.5 w-3.5 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
              </div>
              <p class="mt-0.5 text-xs text-gray-500 line-clamp-2 leading-relaxed">
                {{ widget.description }}
              </p>
            </div>
          </div>

          <div v-if="filteredWidgets.length === 0" class="py-8 text-center text-xs text-gray-500">
            Ничего не найдено по запросу «{{ searchQuery }}»
          </div>
        </div>

        <div class="rounded-lg bg-blue-50/70 p-3 border border-blue-100 text-xs text-blue-800 leading-relaxed">
          💡 Перетащите виджет на холст или нажмите на него, чтобы добавить в текущую активную секцию.
        </div>
      </div>

      <!-- 2. TAB: STRUCTURE (TREE) -->
      <div v-show="activeTab === 'structure'" class="space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold text-gray-700 uppercase tracking-wider">Дерево макета</span>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded text-xs font-medium text-blue-600 hover:text-blue-800"
            @click="builderStore.addSection()"
          >
            <PlusIcon class="h-3.5 w-3.5" aria-hidden="true" />
            Секция
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="(section, sIndex) in builderStore.layout.sections"
            :key="section.id"
            class="rounded-lg border bg-white transition-all overflow-hidden"
            :class="builderStore.selectedElementId === section.id ? 'border-blue-600 ring-1 ring-blue-600' : 'border-gray-200'"
          >
            <!-- Section Item Header -->
            <div
              class="flex items-center justify-between bg-gray-50/80 px-2.5 py-2 cursor-pointer hover:bg-gray-100 transition-colors"
              @click="builderStore.selectElement(section.id)"
            >
              <div class="flex items-center gap-1.5 min-w-0 flex-1">
                <button
                  type="button"
                  class="text-gray-400 hover:text-gray-600 p-0.5"
                  @click.stop="toggleSectionCollapse(section.id)"
                >
                  <ChevronDownIcon
                    class="h-3.5 w-3.5 transition-transform"
                    :class="collapsedSections[section.id] ? '-rotate-90' : ''"
                    aria-hidden="true"
                  />
                </button>
                <Squares2X2Icon class="h-4 w-4 shrink-0 text-gray-500" aria-hidden="true" />
                <span class="truncate text-xs font-semibold text-gray-900">
                  {{ section.name || `Секция ${sIndex + 1}` }}
                </span>
              </div>

              <!-- Section Actions -->
              <div class="flex items-center gap-1">
                <button
                  v-if="sIndex > 0"
                  type="button"
                  class="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
                  title="Поднять секцию"
                  @click.stop="builderStore.reorderSections(sIndex, sIndex - 1)"
                >
                  <ArrowUpIcon class="h-3 w-3" aria-hidden="true" />
                </button>
                <button
                  v-if="sIndex < builderStore.layout.sections.length - 1"
                  type="button"
                  class="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
                  title="Опустить секцию"
                  @click.stop="builderStore.reorderSections(sIndex, sIndex + 1)"
                >
                  <ArrowDownIcon class="h-3 w-3" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  class="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-700"
                  title="Дублировать секцию"
                  @click.stop="builderStore.duplicateSection(section.id)"
                >
                  <DocumentDuplicateIcon class="h-3 w-3" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  class="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                  title="Удалить секцию"
                  @click.stop="builderStore.removeSection(section.id)"
                >
                  <TrashIcon class="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            </div>

            <!-- Columns and Widgets -->
            <div v-show="!collapsedSections[section.id]" class="p-2 space-y-2 border-t border-gray-100 bg-white">
              <div
                v-for="(column, cIndex) in section.columns"
                :key="column.id"
                class="rounded border border-dashed border-gray-200 p-1.5"
                :class="builderStore.selectedElementId === column.id ? 'border-blue-500 bg-blue-50/20' : ''"
              >
                <!-- Column Header -->
                <div
                  class="flex items-center justify-between text-xs text-gray-500 px-1 py-0.5 cursor-pointer hover:text-gray-900"
                  @click.stop="builderStore.selectElement(column.id)"
                >
                  <span class="font-mono text-[10px]">Колонка {{ cIndex + 1 }} ({{ column.width }}/12)</span>
                  <button
                    v-if="section.columns.length > 1"
                    type="button"
                    class="text-gray-400 hover:text-red-500"
                    title="Удалить колонку"
                    @click.stop="builderStore.removeColumn(section.id, column.id)"
                  >
                    <TrashIcon class="h-2.5 w-2.5" aria-hidden="true" />
                  </button>
                </div>

                <!-- Widgets inside Column -->
                <div class="mt-1 space-y-1">
                  <div
                    v-for="(widget, wIndex) in column.widgets"
                    :key="widget.id"
                    class="flex items-center justify-between rounded px-2 py-1.5 text-xs transition-colors cursor-pointer"
                    :class="builderStore.selectedElementId === widget.id ? 'bg-blue-100/70 text-blue-900 font-medium' : 'bg-gray-50 text-gray-700 hover:bg-gray-100'"
                    @click.stop="builderStore.selectElement(widget.id)"
                  >
                    <div class="flex items-center gap-1.5 min-w-0 flex-1">
                      <component :is="getWidgetIcon(WIDGET_REGISTRY[widget.type]?.icon || 'Bars2Icon')" class="h-3.5 w-3.5 shrink-0 text-blue-600" aria-hidden="true" />
                      <span class="truncate">{{ getWidgetDisplayName(widget) }}</span>
                    </div>

                    <div class="flex items-center gap-1 shrink-0">
                      <!-- Visibility Toggle -->
                      <button
                        type="button"
                        class="p-0.5 text-gray-400 hover:text-gray-700"
                        :title="widget.is_hidden ? 'Виджет скрыт на сайте' : 'Виджет видим'"
                        @click.stop="toggleWidgetVisibility(widget)"
                      >
                        <EyeSlashIcon v-if="widget.is_hidden" class="h-3 w-3 text-amber-500" aria-hidden="true" />
                        <EyeIcon v-else class="h-3 w-3" aria-hidden="true" />
                      </button>

                      <!-- Duplicate -->
                      <button
                        type="button"
                        class="p-0.5 text-gray-400 hover:text-gray-700"
                        title="Дублировать виджет"
                        @click.stop="builderStore.duplicateWidget(widget.id)"
                      >
                        <DocumentDuplicateIcon class="h-3 w-3" aria-hidden="true" />
                      </button>

                      <!-- Delete -->
                      <button
                        type="button"
                        class="p-0.5 text-gray-400 hover:text-red-600"
                        title="Удалить виджет"
                        @click.stop="builderStore.removeWidget(widget.id)"
                      >
                        <TrashIcon class="h-3 w-3" aria-hidden="true" />
                      </button>
                    </div>
                  </div>

                  <div v-if="column.widgets.length === 0" class="py-2 text-center text-[11px] text-gray-400 italic">
                    Колонка пуста
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="builderStore.layout.sections.length === 0" class="py-10 text-center text-xs text-gray-400">
            Секций пока нет. Нажмите «Секция», чтобы добавить.
          </div>
        </div>
      </div>

      <!-- 3. TAB: GLOBAL STYLE -->
      <div v-show="activeTab === 'style'" class="space-y-5">
        <div>
          <h4 class="text-xs font-semibold text-gray-900 uppercase tracking-wider">Цветовая палитра витрины</h4>
          <p class="mt-1 text-xs text-gray-500">Глобальные цвета применяются ко всем базовым компонентам витрины.</p>
        </div>

        <div class="space-y-3">
          <!-- Primary Color -->
          <div>
            <label class="block text-xs font-medium text-gray-700">Основной цвет (Primary)</label>
            <div class="mt-1.5 flex items-center gap-2">
              <input
                type="color"
                :value="globalPalette['--storefront-primary']"
                class="h-8 w-8 cursor-pointer rounded border border-gray-300 p-0.5"
                @input="builderStore.updateGlobalSettings({ primary_color: ($event.target as HTMLInputElement).value })"
              >
              <input
                type="text"
                :value="globalPalette['--storefront-primary']"
                class="h-8 flex-1 rounded border border-gray-300 px-2 font-mono text-xs text-gray-800"
                @change="builderStore.updateGlobalSettings({ primary_color: ($event.target as HTMLInputElement).value })"
              >
            </div>
          </div>

          <!-- Background Color -->
          <div>
            <label class="block text-xs font-medium text-gray-700">Цвет фона страницы</label>
            <div class="mt-1.5 flex items-center gap-2">
              <input
                type="color"
                :value="globalPalette['--storefront-background']"
                class="h-8 w-8 cursor-pointer rounded border border-gray-300 p-0.5"
                @input="builderStore.updateGlobalSettings({ background_color: ($event.target as HTMLInputElement).value })"
              >
              <input
                type="text"
                :value="globalPalette['--storefront-background']"
                class="h-8 flex-1 rounded border border-gray-300 px-2 font-mono text-xs text-gray-800"
                @change="builderStore.updateGlobalSettings({ background_color: ($event.target as HTMLInputElement).value })"
              >
            </div>
          </div>

          <!-- Surface Color -->
          <div>
            <label class="block text-xs font-medium text-gray-700">Цвет поверхностей (Surface/Cards)</label>
            <div class="mt-1.5 flex items-center gap-2">
              <input
                type="color"
                :value="globalPalette['--storefront-surface']"
                class="h-8 w-8 cursor-pointer rounded border border-gray-300 p-0.5"
                @input="builderStore.updateGlobalSettings({ surface_color: ($event.target as HTMLInputElement).value })"
              >
              <input
                type="text"
                :value="globalPalette['--storefront-surface']"
                class="h-8 flex-1 rounded border border-gray-300 px-2 font-mono text-xs text-gray-800"
                @change="builderStore.updateGlobalSettings({ surface_color: ($event.target as HTMLInputElement).value })"
              >
            </div>
          </div>

          <!-- Text Color -->
          <div>
            <label class="block text-xs font-medium text-gray-700">Цвет текста</label>
            <div class="mt-1.5 flex items-center gap-2">
              <input
                type="color"
                :value="globalPalette['--storefront-text']"
                class="h-8 w-8 cursor-pointer rounded border border-gray-300 p-0.5"
                @input="builderStore.updateGlobalSettings({ text_color: ($event.target as HTMLInputElement).value })"
              >
              <input
                type="text"
                :value="globalPalette['--storefront-text']"
                class="h-8 flex-1 rounded border border-gray-300 px-2 font-mono text-xs text-gray-800"
                @change="builderStore.updateGlobalSettings({ text_color: ($event.target as HTMLInputElement).value })"
              >
            </div>
          </div>
        </div>

        <div class="border-t border-gray-200 pt-4">
          <label class="block text-xs font-semibold text-gray-900 uppercase tracking-wider">Скругление углов (Radius)</label>
          <div class="mt-2 grid grid-cols-4 gap-2">
            <button
              v-for="radius in RADII"
              :key="radius.key"
              type="button"
              class="rounded border py-2 text-center text-xs font-medium transition-colors"
              :class="(builderStore.layout.settings.border_radius || 'medium') === radius.key ? 'border-blue-600 bg-blue-50 text-blue-700 font-semibold' : 'border-gray-200 text-gray-700 hover:bg-gray-50'"
              @click="builderStore.updateGlobalSettings({ border_radius: radius.key as any })"
            >
              {{ radius.label }}
            </button>
          </div>
        </div>

        <div class="border-t border-gray-200 pt-4">
          <label class="block text-xs font-semibold text-gray-900 uppercase tracking-wider">Фирменный шрифт</label>
          <select
            :value="builderStore.layout.settings.font_id || ''"
            class="mt-2 h-9 w-full rounded-lg border border-gray-300 bg-white px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            @change="builderStore.updateGlobalSettings({ font_id: ($event.target as HTMLSelectElement).value || null })"
          >
            <option value="">Системный шрифт (Inter / Sans-serif)</option>
            <option v-for="font in fontsList" :key="font.id" :value="font.id">
              {{ font.name }} (загруженный)
            </option>
          </select>
          <p class="mt-1 text-[11px] text-gray-500">Загрузка новых шрифтов доступна во вкладке «Шрифты» панели витрин.</p>
        </div>
      </div>

      <!-- 4. TAB: HEADER (ШАПКА ВИТРИНЫ) -->
      <div v-show="activeTab === 'header'" class="space-y-4">
        <div>
          <h4 class="text-xs font-semibold text-gray-900 uppercase tracking-wider">Настройки шапки (Header)</h4>
          <p class="mt-1 text-xs text-gray-500 leading-relaxed">
            Контакты, логотип и пункты меню, отображаемые в шапке сайта витрины.
          </p>
        </div>

        <div v-if="headerSuccessMessage" class="rounded-lg border border-green-200 bg-green-50 p-2.5 text-xs text-green-800">
          {{ headerSuccessMessage }}
        </div>
        <div v-if="headerErrorMessage" class="rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-800">
          {{ headerErrorMessage }}
        </div>

        <!-- Contacts -->
        <div class="space-y-3">
          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">Контактный телефон</span>
            <input
              v-model.trim="builderStore.headerSettings.contact_phone"
              type="tel"
              placeholder="+7 (999) 000-00-00"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>

          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">Контактный email</span>
            <input
              v-model.trim="builderStore.headerSettings.contact_email"
              type="email"
              placeholder="sales@company.ru"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>
        </div>

        <!-- Logo -->
        <div class="border-t border-gray-200 pt-3 space-y-3">
          <label class="block text-xs font-semibold text-gray-900 uppercase tracking-wider">Логотип витрины</label>

          <div v-if="displayedLogoUrl" class="rounded-lg border border-gray-200 bg-gray-50 p-2.5">
            <div class="flex h-12 w-full items-center justify-center rounded border border-gray-200 bg-white p-2">
              <img
                :src="displayedLogoUrl"
                alt="Логотип витрины"
                class="max-h-10 max-w-full object-contain"
              >
            </div>
            <div class="mt-2 flex items-center justify-between">
              <span class="text-[11px] text-gray-500">
                {{ builderStore.storefront?.logo_url ? 'Собственный логотип' : 'Наследуется от основной' }}
              </span>
              <button
                v-if="builderStore.storefront?.logo_url"
                type="button"
                class="text-[11px] font-medium text-red-600 hover:text-red-800"
                :disabled="builderStore.isSavingHeader"
                @click="handleRemoveLogo"
              >
                Удалить логотип
              </button>
            </div>
          </div>

          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">URL логотипа</span>
            <input
              v-model.trim="builderStore.headerSettings.logo_url"
              type="text"
              placeholder="https://example.com/logo.png"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>

          <div>
            <span class="mb-1 block text-xs font-medium text-gray-700">Загрузка логотипа</span>
            <input
              ref="headerLogoFileInput"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              class="block w-full text-xs text-gray-500 file:mr-2 file:rounded file:border-0 file:bg-blue-50 file:px-2.5 file:py-1.5 file:text-xs file:font-semibold file:text-blue-700 hover:file:bg-blue-100"
              @change="handleSelectHeaderLogoFile"
            >
            <p class="mt-1 text-[11px] text-gray-500">PNG, JPEG или WebP до 5 МиБ</p>
          </div>
        </div>

        <!-- Menu Titles -->
        <div class="border-t border-gray-200 pt-3 space-y-3">
          <label class="block text-xs font-semibold text-gray-900 uppercase tracking-wider">Пункты меню</label>

          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">Главная страница</span>
            <input
              v-model.trim="builderStore.headerSettings.public_page_titles.home"
              type="text"
              required
              maxlength="120"
              placeholder="Главная"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>

          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">О нас</span>
            <input
              v-model.trim="builderStore.headerSettings.public_page_titles.about"
              type="text"
              required
              maxlength="120"
              placeholder="О нас"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>

          <label class="block">
            <span class="mb-1 block text-xs font-medium text-gray-700">Каталог (Транспортные средства)</span>
            <input
              v-model.trim="builderStore.headerSettings.public_page_titles.special_equipment_catalog"
              type="text"
              required
              maxlength="120"
              placeholder="Транспортные средства"
              class="h-9 w-full rounded-lg border border-gray-300 px-3 text-xs text-gray-900 focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
          </label>
        </div>

        <!-- Save Button -->
        <div class="border-t border-gray-200 pt-3">
          <button
            type="button"
            class="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-blue-500 disabled:opacity-50 transition-colors"
            :disabled="builderStore.isSavingHeader"
            @click="handleSaveHeader"
          >
            <ArrowPathIcon v-if="builderStore.isSavingHeader" class="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>{{ builderStore.isSavingHeader ? 'Сохранение настроек…' : 'Сохранить настройки шапки' }}</span>
          </button>
        </div>
      </div>

      <!-- 5. TAB: HISTORY (REVISIONS) -->
      <div v-show="activeTab === 'history'" class="space-y-4">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold text-gray-700 uppercase tracking-wider">Снимки ревизий</span>
          <button
            type="button"
            class="text-xs font-medium text-blue-600 hover:text-blue-800"
            @click="builderStore.loadRevisions()"
          >
            Обновить
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="rev in builderStore.revisions"
            :key="rev.id"
            class="rounded-lg border border-gray-200 bg-white p-3 shadow-xs hover:border-gray-300 transition-colors"
          >
            <div class="flex items-center justify-between">
              <span class="inline-flex items-center rounded bg-gray-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-gray-800">
                v{{ rev.version }}
              </span>
              <span class="text-[11px] text-gray-400">
                {{ formatDate(rev.created_at) }}
              </span>
            </div>
            <p class="mt-1.5 text-xs text-gray-700 leading-snug">
              {{ rev.summary || 'Автоматическое сохранение черновика' }}
            </p>
            <div v-if="rev.created_by_name" class="mt-1 text-[11px] text-gray-400">
              Автор: {{ rev.created_by_name }}
            </div>
            <div class="mt-2 flex justify-end">
              <button
                type="button"
                class="rounded bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100 transition-colors"
                @click="builderStore.restoreRevision(rev.id)"
              >
                Восстановить
              </button>
            </div>
          </div>

          <div v-if="builderStore.revisions.length === 0" class="py-8 text-center text-xs text-gray-400">
            История ревизий пуста. Сохраните черновик, чтобы создать первый снимок.
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  ArrowDownIcon,
  ArrowPathIcon,
  ArrowUpIcon,
  BanknotesIcon,
  Bars2Icon,
  BoltIcon,
  BuildingOfficeIcon,
  CalculatorIcon,
  ChevronDownIcon,
  ClipboardDocumentCheckIcon,
  ClockIcon,
  CursorArrowRaysIcon,
  DocumentDuplicateIcon,
  DocumentTextIcon,
  EyeIcon,
  EyeSlashIcon,
  MagnifyingGlassIcon,
  MapPinIcon,
  MegaphoneIcon,
  PaintBrushIcon,
  PlusIcon,
  QuestionMarkCircleIcon,
  ShieldCheckIcon,
  SparklesIcon,
  Squares2X2Icon,
  TrashIcon,
  TruckIcon,
  WindowIcon,
} from '@heroicons/vue/24/outline'
import {
  type WidgetDefinition,
  type WidgetInstance,
  type WidgetType,
  WIDGET_REGISTRY,
} from '../types'
import { useStorefrontBuilderStore } from '../store/storefrontBuilder'
import { buildStorefrontPageTheme } from '../utils/pageTheme'

const builderStore = useStorefrontBuilderStore()
const globalPalette = computed(() => buildStorefrontPageTheme(builderStore.layout.settings, builderStore.storefront?.appearance))

const activeTab = ref<'widgets' | 'structure' | 'style' | 'header' | 'history'>('widgets')
const searchQuery = ref('')
const selectedCategory = ref<'all' | 'promo' | 'catalog' | 'interaction' | 'content' | 'layout'>('all')
const collapsedSections = reactive<Record<string, boolean>>({})
const fontsList = ref<Array<{ id: string; name: string }>>([])

const TABS = [
  { key: 'widgets' as const, label: 'Виджеты', icon: Squares2X2Icon },
  { key: 'structure' as const, label: 'Структура', icon: Bars2Icon },
  { key: 'style' as const, label: 'Глобальный стиль', icon: PaintBrushIcon },
  { key: 'header' as const, label: 'Шапка', icon: WindowIcon },
  { key: 'history' as const, label: 'История', icon: ClockIcon },
]

const CATEGORIES = [
  { key: 'all' as const, label: 'Все' },
  { key: 'promo' as const, label: 'Промо' },
  { key: 'catalog' as const, label: 'Каталог' },
  { key: 'interaction' as const, label: 'Интерактив' },
  { key: 'content' as const, label: 'Контент' },
  { key: 'layout' as const, label: 'Макет' },
]

const RADII = [
  { key: 'none', label: '0px' },
  { key: 'small', label: '4px' },
  { key: 'medium', label: '8px' },
  { key: 'large', label: '16px' },
]

const iconMap: Record<string, any> = {
  MegaphoneIcon,
  CalculatorIcon,
  TruckIcon,
  SparklesIcon,
  ClipboardDocumentCheckIcon,
  BuildingOfficeIcon,
  DocumentTextIcon,
  QuestionMarkCircleIcon,
  MapPinIcon,
  CursorArrowRaysIcon,
  Bars2Icon,
  BoltIcon,
  ShieldCheckIcon,
  BanknotesIcon,
}

function getWidgetIcon(iconName: string) {
  return iconMap[iconName] || Bars2Icon
}

function getWidgetDisplayName(widget: WidgetInstance): string {
  const def = WIDGET_REGISTRY[widget.type]
  if (widget.props?.title) {
    return `${def?.title || widget.type}: ${widget.props.title}`
  }
  return def?.title || widget.type
}

const allWidgets = Object.values(WIDGET_REGISTRY)

const filteredWidgets = computed(() => {
  return allWidgets.filter((w) => {
    const matchesCategory = selectedCategory.value === 'all' || w.category === selectedCategory.value
    const matchesSearch =
      !searchQuery.value ||
      w.title.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      w.description.toLowerCase().includes(searchQuery.value.toLowerCase())
    return matchesCategory && matchesSearch
  })
})

function handleDragStart(event: DragEvent, type: WidgetType) {
  if (event.dataTransfer) {
    event.dataTransfer.setData('text/plain', type)
    event.dataTransfer.setData('application/json', JSON.stringify({ widgetType: type }))
  }
}

function handleWidgetClick(type: WidgetType) {
  // If a section is selected, add to its first column; otherwise add to first section or create new
  let sectionId = builderStore.selectedSection?.id
  let columnId = builderStore.selectedColumn?.id

  if (!sectionId) {
    if (builderStore.layout.sections.length > 0) {
      sectionId = builderStore.layout.sections[0].id
      columnId = builderStore.layout.sections[0].columns[0]?.id
    } else {
      const newSec = builderStore.addSection()
      sectionId = newSec.id
      columnId = newSec.columns[0]?.id
    }
  }

  if (sectionId && columnId) {
    builderStore.addWidget(sectionId, columnId, type)
  }
}

function toggleSectionCollapse(sectionId: string) {
  collapsedSections[sectionId] = !collapsedSections[sectionId]
}

function toggleWidgetVisibility(widget: WidgetInstance) {
  builderStore.updateWidgetProps(widget.id, {})
  widget.is_hidden = !widget.is_hidden
  builderStore.recordHistory()
}

function formatDate(isoDate: string): string {
  if (!isoDate) return ''
  try {
    const date = new Date(isoDate)
    return date.toLocaleString('ru-RU', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoDate
  }
}

const headerPendingLogoFile = ref<File | null>(null)
const headerSuccessMessage = ref('')
const headerErrorMessage = ref('')
const headerLogoFileInput = ref<HTMLInputElement | null>(null)

const displayedLogoUrl = computed(() => {
  if (headerPendingLogoFile.value) {
    return URL.createObjectURL(headerPendingLogoFile.value)
  }
  if (builderStore.headerSettings.logo_url) {
    return builderStore.headerSettings.logo_url
  }
  const sf = builderStore.storefront
  const url = sf?.logo_url || sf?.effective_logo_url
  if (!url) return null
  return `${url}${url.includes('?') ? '&' : '?'}v=${sf?.version ?? 0}`
})

function handleSelectHeaderLogoFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) return
  const allowed = ['image/png', 'image/jpeg', 'image/webp']
  if (!allowed.includes(file.type) || file.size > 5 * 1024 * 1024) {
    headerErrorMessage.value = 'Выберите PNG, JPEG или WebP размером не более 5 МиБ'
    input.value = ''
    headerPendingLogoFile.value = null
    return
  }
  headerErrorMessage.value = ''
  headerPendingLogoFile.value = file
}

async function handleSaveHeader() {
  headerSuccessMessage.value = ''
  headerErrorMessage.value = ''
  const ok = await builderStore.saveHeaderSettings(headerPendingLogoFile.value)
  if (ok) {
    headerSuccessMessage.value = 'Настройки шапки успешно сохранены'
    headerPendingLogoFile.value = null
    if (headerLogoFileInput.value) headerLogoFileInput.value.value = ''
    setTimeout(() => {
      headerSuccessMessage.value = ''
    }, 4000)
  } else {
    headerErrorMessage.value = builderStore.error || 'Не удалось сохранить настройки шапки'
  }
}

async function handleRemoveLogo() {
  headerSuccessMessage.value = ''
  headerErrorMessage.value = ''
  const ok = await builderStore.removeHeaderLogo()
  if (ok) {
    headerSuccessMessage.value = 'Логотип удалён'
    headerPendingLogoFile.value = null
    if (headerLogoFileInput.value) headerLogoFileInput.value.value = ''
    setTimeout(() => {
      headerSuccessMessage.value = ''
    }, 4000)
  } else {
    headerErrorMessage.value = builderStore.error || 'Не удалось удалить логотип'
  }
}
</script>
