<template>
  <div class="se-form-stack">
    <div v-if="errorMessage" class="se-form-alert se-form-alert--error" role="alert">
      <ExclamationCircleIcon aria-hidden="true" />
      <div>
        <strong>Не удалось сохранить</strong>
        <p>{{ errorMessage }}</p>
      </div>
    </div>

    <fieldset v-if="entity === 'products' && mode === 'create'" class="se-form-section">
      <legend>Форма создания</legend>
      <div class="se-choice-grid" role="radiogroup" aria-label="Тип создаваемого объявления">
        <label class="se-choice-card" :class="{ 'se-choice-card--active': productCreationKind === 'vehicle' }">
          <input
            type="radio"
            name="product-creation-kind"
            value="vehicle"
            :checked="productCreationKind === 'vehicle'"
            @change="changeProductCreationKind('vehicle')"
          >
          <span><strong>Создание техники</strong><small>Обычное объявление техники с возможностью сразу выбрать совместимые надстройки.</small></span>
        </label>
        <label class="se-choice-card" :class="{ 'se-choice-card--active': productCreationKind === 'attachment' }">
          <input
            type="radio"
            name="product-creation-kind"
            value="attachment"
            :checked="productCreationKind === 'attachment'"
            @change="changeProductCreationKind('attachment')"
          >
          <span><strong>Создание надстройки</strong><small>Самостоятельная надстройка либо новое предложение-комплект.</small></span>
        </label>
      </div>
      <div v-if="productCreationKind === 'attachment'" class="se-radio-row" role="radiogroup" aria-label="Режим создания надстройки">
        <label>
          <input type="radio" name="attachment-create-mode" value="standalone" :checked="attachmentCreateMode === 'standalone'" @change="changeAttachmentCreateMode('standalone')">
          Самостоятельное объявление
        </label>
        <label>
          <input type="radio" name="attachment-create-mode" value="kit" :checked="attachmentCreateMode === 'kit'" @change="changeAttachmentCreateMode('kit')">
          Комплект с техникой
        </label>
      </div>
    </fieldset>

    <fieldset class="se-form-section">
      <legend>Основные сведения</legend>
      <p class="se-section-help">Все поля названы так же, как в русском шаблоне импорта.</p>
      <div class="se-form-stack">
        <label v-if="entity !== 'trims' || mode === 'edit'" class="se-field">
          <span>
            Код <b>*</b>
            <CatalogHelpPopover
              label="Код"
              text="Уникальный постоянный идентификатор для связей и импорта. После первого сохранения код изменить нельзя."
            />
          </span>
          <input
            :value="text('code')"
            type="text"
            maxlength="80"
            autocomplete="off"
            :disabled="mode === 'edit'"
            placeholder="Например, EXCAVATOR"
            required
            aria-required="true"
            @input="setCode($event)"
          >
          <small v-if="mode === 'create'" class="se-field-help">Предлагается автоматически по названию; до сохранения его можно исправить.</small>
        </label>

        <label v-if="entity !== 'products'" class="se-field">
          <span>Название <b>*</b></span>
          <input
            :value="text('name')"
            type="text"
            maxlength="255"
            required
            aria-required="true"
            @input="setName($event)"
          >
        </label>

        <label v-if="supportsActivity && (entity !== 'trims' || mode === 'edit')" class="se-checkbox-row">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="bool('is_active')"
            @change="set('is_active', checkedValue($event))"
          >
          <span>
            <strong>
              Активно
              <CatalogHelpPopover
                label="Активность"
                text="Неактивная запись остаётся в истории, но её нельзя выбрать для новой публикации. Уже сохранённые связи будут явно помечены."
              />
            </strong>
            <small>Разрешить использовать запись в новых связях.</small>
          </span>
        </label>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'categories'" class="se-form-section">
      <legend>Категория</legend>
      <div class="se-form-stack">
        <label class="se-field">
          <span>
            Показатель эксплуатации <b>*</b>
            <CatalogHelpPopover
              label="Показатель эксплуатации"
              text="Жёстко определяет, что показывать для техники с пробегом в этой категории: пробег либо моточасы. В одном объявлении оба показателя недопустимы."
            />
          </span>
          <select class="select-field" :value="text('usage_metric')" required aria-required="true" @change="setText('usage_metric', $event)">
            <option value="mileage_km">Пробег</option>
            <option value="engine_hours">Моточасы</option>
          </select>
        </label>
        <label class="se-field">
          <span>Порядок показа</span>
          <input :value="numberValue('sort_order', 0)" type="number" min="0" step="1" @input="setNumber('sort_order', $event)">
        </label>
        <label class="se-checkbox-row">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="boolValue('is_attachment_category')"
            @change="set('is_attachment_category', checkedValue($event))"
          >
          <span>
            <strong>
              Категория надстроек
              <CatalogHelpPopover
                label="Категория надстроек"
                text="Категория становится корнем ветви надстроек. Все её потомки также считаются надстройками. Сервер не позволит снять признак, пока от него зависят товары или связи."
              />
            </strong>
            <small>Использовать эту категорию и её дочерние категории для объявлений надстроек.</small>
          </span>
        </label>
        <label class="se-checkbox-row">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="bool('is_visible_in_catalog')"
            @change="set('is_visible_in_catalog', checkedValue($event))"
          >
          <span>
            <strong>
              Отображать в каталоге
              <CatalogHelpPopover
                label="Отображать в каталоге"
                text="Если флаг снят, категория скрывается в публичном каталоге, но остаётся доступной в панели управления."
              />
            </strong>
            <small>Показывать категорию клиентам в публичной витрине каталога.</small>
          </span>
        </label>
        <div class="se-field">
          <span>
            Родительские категории
            <CatalogHelpPopover
              label="Родительские категории"
              text="Категория может находиться сразу в нескольких ветках. Основного родителя нет; каждый путь проверяется отдельно."
            />
          </span>
          <CatalogCategoryMultiSelect
            :model-value="uuidArray('parent_ids')"
            :categories="categories"
            :disabled-ids="categoryParentDisabledIds"
            title="Выберите родительские категории"
            @update:model-value="set('parent_ids', $event)"
          />
        </div>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'categories'" class="se-form-section">
      <legend>Характеристики категории</legend>
      <p class="se-section-help">Прямые настройки объединяются с характеристиками всех предков категории.</p>
      <div class="se-card-attribute-count" aria-live="polite">
        <strong>На карточке объявления: {{ visibleCardAttributeCount }} из {{ MAX_CARD_ATTRIBUTES }}</strong>
        <span>Учитываются прямые и наследуемые характеристики.</span>
        <span v-if="visibleCardAttributeCount > MAX_CARD_ATTRIBUTES" class="se-field-error" role="alert">
          Уменьшите количество отображаемых характеристик до шести.
        </span>
      </div>
      <div v-if="inheritedCategoryLinks.length" class="se-inherited-attributes">
        <h3>Наследуемые характеристики</h3>
        <p class="se-section-help">Они применятся автоматически от выбранных родительских категорий.</p>
        <ul>
          <li v-for="link in inheritedCategoryLinks" :key="link.attribute_id">
            <span>{{ categoryLinkAttribute(link)?.name || 'Неизвестная характеристика' }}</span>
            <span>{{ link.is_visible ? 'Отображается на карточке' : 'Только в характеристиках' }}</span>
          </li>
        </ul>
      </div>
      <CatalogCategoryAttributePicker
        :attributes="attributes"
        :groups="groups"
        :linked-attribute-ids="categoryLinks.map(link => link.attribute_id)"
        :loading="attributesLoading"
        :error-message="attributesErrorMessage"
        @apply="applyCategoryAttributes"
        @retry="emit('retry-attributes')"
      />
      <div v-if="categoryLinks.length === 0" class="se-quiet-state">Характеристики ещё не добавлены.</div>
      <div v-else class="se-attribute-bindings">
        <article v-for="(link, index) in categoryLinks" :key="`${link.attribute_id}-${index}`" class="se-attribute-binding">
          <div class="se-attribute-binding__heading">
            <strong>{{ categoryLinkAttribute(link)?.name || 'Неизвестная характеристика' }}</strong>
            <span>{{ categoryLinkGroupName(link) }}</span>
          </div>
          <label class="se-field se-category-group-override">
            <span>Группа в этой категории</span>
            <CatalogSearchableSelect
              :model-value="link.group_id ?? ''"
              :options="groups"
              :label="`Группа характеристики «${categoryLinkAttribute(link)?.name ?? ''}»`"
              :placeholder="categoryLinkInheritedGroupLabel(link)"
              @change="changeCategoryLinkGroup(index, $event)"
            />
            <small class="se-field-help">Оставьте наследование либо переопределите группу для этой категории.</small>
          </label>
          <div class="se-link-options">
            <label>
              <input class="se-checkbox" type="checkbox" :checked="link.is_required" @change="patchCategoryLink(index, 'is_required', checkedValue($event))">
              <span>
                Обязательно
                <CatalogHelpPopover
                  label="Обязательность"
                  text="Публикация блокируется, пока у модификации не заполнена обязательная характеристика."
                />
              </span>
            </label>
            <label><input class="se-checkbox" type="checkbox" :checked="link.is_filterable" @change="patchCategoryLink(index, 'is_filterable', checkedValue($event))"> В фильтре</label>
            <label>
              <input
                class="se-checkbox"
                type="checkbox"
                :checked="link.is_visible"
                :disabled="!canEnableCategoryLinkCard(index)"
                @change="patchCategoryLink(index, 'is_visible', checkedValue($event))"
              >
              Отображать на карточке объявления
            </label>
            <label class="se-link-order">Порядок <input type="number" min="0" step="1" :value="link.sort_order" @input="setCategoryLinkSortOrder(index, $event)"></label>
          </div>
          <button type="button" class="se-button se-button--ghost-danger se-button--small" @click="removeCategoryLink(index)">Удалить связь</button>
        </article>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'colors'" class="se-form-section">
      <legend>Применимость цвета</legend>
      <div class="se-form-stack">
        <label class="se-field">
          <span>Где используется <b>*</b></span>
          <select class="select-field" :value="text('applicability') || 'body'" required aria-required="true" @change="setText('applicability', $event)">
            <option value="body">Только кузов</option>
            <option value="interior">Только салон</option>
            <option value="both">Кузов и салон</option>
          </select>
        </label>
        <p v-if="mode === 'edit'" class="se-inline-warning" role="note">
          Код цвета используется в интеграциях и импорте. Меняйте его только если внешние связи уже согласованы.
        </p>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'models'" class="se-form-section">
      <legend>Принадлежность модели</legend>
      <div class="se-field-row">
        <label class="se-field">
          <span>Марка <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('mark_id')"
            :options="marks"
            label="Марка модели"
            placeholder="Найдите марку"
            required
            @update:model-value="set('mark_id', $event)"
          />
        </label>
        <label class="se-field">
          <span>Категория <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('category_id')"
            :options="modelCategoryOptions"
            label="Категория модели"
            placeholder="Выберите категорию"
            required
            @update:model-value="set('category_id', $event)"
          />
        </label>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'trims'" class="se-form-section">
      <legend>Принадлежность комплектации</legend>
      <p class="se-section-help">Комплектация создаётся внутри одной модификации. После создания модификация не меняется.</p>
      <div class="se-field-row">
        <label class="se-field">
          <span>Марка <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('selected_mark_id')"
            :options="marks"
            label="Марка комплектации"
            placeholder="Найдите марку"
            :disabled="mode === 'edit'"
            required
            @change="changeMark"
          />
        </label>
        <label class="se-field">
          <span>Модель <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('selected_model_id')"
            :options="models"
            label="Модель комплектации"
            placeholder="Найдите модель"
            :disabled="mode === 'edit' || !text('selected_mark_id') || modelsLoading"
            required
            @change="changeModel"
          />
        </label>
      </div>
      <label class="se-field">
        <span>Модификация <b>*</b></span>
        <CatalogSearchableSelect
          :model-value="uuidValue('modification_id')"
          :options="modifications"
          label="Модификация комплектации"
          placeholder="Найдите модификацию"
          :disabled="mode === 'edit' || !text('selected_model_id') || modificationsLoading"
          required
          @change="changeModification"
        />
      </label>
      <label class="se-field">
        <span>Порядок показа</span>
        <input :value="numberValue('sort_order', 0)" type="number" min="0" step="1" @input="setNumber('sort_order', $event)">
      </label>
    </fieldset>

    <fieldset v-if="entity === 'trims'" class="se-form-section">
      <legend>Характеристики комплектации</legend>
      <p class="se-section-help">Сначала выберите группы, затем характеристики и сохраните форму. Сервер проверит актуальность комплектации перед каждым изменением.</p>
      <div v-if="!uuidValue('modification_id')" class="se-quiet-state">Сначала выберите модификацию.</div>
      <CatalogTrimAttributePicker
        v-else
        :groups="trimAttributeCandidateGroups"
        :model-value="trimAttributes"
        :loading="trimAttributeCandidatesLoading"
        :error-message="trimAttributeCandidatesErrorMessage"
        @apply="replaceTrimAttributes"
        @retry="emit('trim-candidates-retry', uuidValue('modification_id') || null)"
      />
      <div v-if="trimAttributes.length === 0" class="se-quiet-state">Характеристики ещё не добавлены.</div>
      <div v-else class="se-attribute-bindings">
        <article v-for="(link, index) in trimAttributes" :key="link.attribute_id" class="se-attribute-binding">
          <div class="se-attribute-binding__heading">
            <strong>{{ link.attribute_name || link.attribute_id }}</strong>
            <span>{{ trimGroupName(link.group_id) }}</span>
          </div>
          <div class="se-link-options">
            <label><input class="se-checkbox" type="checkbox" :checked="link.is_required" @change="patchTrimAttribute(index, 'is_required', checkedValue($event))"> Обязательно</label>
            <label><input class="se-checkbox" type="checkbox" :checked="link.is_filterable" @change="patchTrimAttribute(index, 'is_filterable', checkedValue($event))"> В фильтре</label>
            <label class="se-link-order">Порядок <input type="number" min="0" step="1" :value="link.sort_order" @input="patchTrimAttribute(index, 'sort_order', normalizeCatalogInteger(inputValue($event)) ?? 0)"></label>
          </div>
          <label class="se-field se-trim-value-field">
            <span>Значение характеристики</span>
            <CatalogSearchableSelect
              v-if="link.data_type === 'select'"
              :model-value="trimOptionValue(link.attribute_id)"
              :options="trimAttributeOptions(link)"
              :label="`Значение характеристики «${link.attribute_name || link.attribute_id}»`"
              placeholder="Не задано"
              @change="setTrimAttributeValue(link.attribute_id, { option_id: $event })"
            />
            <select
              v-else-if="link.data_type === 'boolean'"
              class="select-field"
              :value="String(trimAttributeValue(link.attribute_id)?.value_boolean ?? '')"
              @change="setTrimAttributeValue(link.attribute_id, { value_boolean: trimBooleanValue($event) })"
            >
              <option value="">Не задано</option>
              <option value="true">Да</option>
              <option value="false">Нет</option>
            </select>
            <input
              v-else
              :value="trimScalarValue(link.attribute_id)"
              :type="link.data_type === 'number' ? 'number' : 'text'"
              @input="setTrimAttributeValue(link.attribute_id, link.data_type === 'number' ? { value_number: normalizeCatalogPrice(inputValue($event)) } : { value_text: inputValue($event) })"
            >
          </label>
          <button type="button" class="se-button se-button--ghost-danger se-button--small" @click="removeTrimAttribute(index)">Удалить связь</button>
        </article>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'superstructures'" class="se-form-section">
      <legend>Разрешенные категории</legend>
      <p class="se-section-help">Выберите категории каталога, для которых разрешён этот тип надстройки.</p>
      <div class="se-field">
        <span>Категории</span>
        <CatalogCategoryMultiSelect
          :model-value="uuidArray('category_ids')"
          :categories="categories"
          :disabled-ids="inactiveProductCategoryIds"
          title="Разрешенные категории надстройки"
          @update:model-value="set('category_ids', $event)"
        />
      </div>
    </fieldset>

    <fieldset v-if="entity === 'superstructures'" class="se-form-section">
      <legend>Характеристики надстройки</legend>
      <p class="se-section-help">Сначала выберите группу, затем характеристики. Они будут использоваться в объявлениях этого типа надстройки.</p>
      <CatalogSuperstructureAttributePicker
        :groups="groups"
        :model-value="superstructureAttributes"
        :api="api"
        :disabled="false"
        @update:model-value="set('attributes', $event)"
      />
    </fieldset>

    <fieldset v-if="entity === 'modifications' || (entity === 'products' && !isKit)" class="se-form-section">
      <legend>{{ entity === 'products' ? (isStandaloneAttachment ? 'Модификация и тип надстройки' : 'Модификация объявления') : 'Принадлежность модификации' }}</legend>
      <p class="se-section-help">{{ isStandaloneAttachment ? 'Выберите тип надстройки, затем марку, модель и модификацию.' : 'Сначала выберите марку, затем модель и только после этого модификацию.' }}</p>

      <label v-if="isStandaloneAttachment" class="se-field">
        <span>Тип надстройки <b>*</b></span>
        <CatalogSearchableSelect
          :model-value="uuidValue('superstructure_id')"
          :options="kitAvailableSuperstructureTypes"
          label="Тип надстройки"
          placeholder="Выберите тип надстройки"
          :disabled="allSuperstructuresLoading"
          required
          @change="changeStandaloneSuperstructureType"
        />
        <small v-if="!uuidValue('superstructure_id')" class="se-field-help">Тип надстройки определяет доступные категории объявления.</small>
      </label>

      <div class="se-field-row">
        <label class="se-field">
          <span>Марка <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('selected_mark_id')"
            :options="marks"
            :label="entity === 'products' ? 'Марка объявления' : 'Марка модификации'"
            placeholder="Найдите марку"
            required
            @change="changeMark"
          />
        </label>
        <label class="se-field">
          <span>Модель <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('selected_model_id') || (entity === 'modifications' ? uuidValue('model_id') : '')"
            :options="models"
            :label="entity === 'products' ? 'Модель объявления' : 'Модель модификации'"
            placeholder="Найдите модель"
            :disabled="!text('selected_mark_id') || modelsLoading"
            required
            @change="changeModel"
          />
        </label>
      </div>
      <label v-if="entity === 'products'" class="se-field">
        <span>Модификация <b>*</b></span>
        <CatalogSearchableSelect
          :model-value="uuidValue('modification_id')"
          :options="modifications"
          label="Модификация объявления"
          placeholder="Найдите модификацию"
          :disabled="!text('selected_model_id') || modificationsLoading"
          required
          @change="changeModification"
        />
      </label>
      <label v-if="entity === 'products' && uuidValue('modification_id')" class="se-field">
        <span>Комплектация<b v-if="trimRequired"> *</b></span>
        <CatalogSearchableSelect
          :model-value="uuidValue('trim_id')"
          :options="trimOptions"
          label="Комплектация объявления"
          :placeholder="trimsLoading ? 'Загрузка…' : trimRequired ? 'Выберите комплектацию' : 'Без комплектации'"
          :disabled="trimsLoading || trimOptions.length === 0"
          :required="trimRequired"
          @change="changeTrim"
        />
        <small v-if="trimOptions.length === 0 && !trimsLoading" class="se-field-help">У выбранной модификации нет активных комплектаций.</small>
      </label>
    </fieldset>

    <fieldset v-if="entity === 'modifications'" class="se-form-section">
      <legend>Годы и категории</legend>
      <div class="se-field-row">
        <label class="se-field">
          <span>
            Год начала выпуска
            <CatalogHelpPopover label="Годы выпуска" text="Диапазон проверяется при создании объявления. Сузить его поверх существующих объявлений нельзя." />
          </span>
          <input
            :value="yearDraft('year_from')"
            type="text"
            aria-label="Год начала выпуска"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="4"
            :aria-invalid="Boolean(yearError('year_from'))"
            :aria-describedby="yearError('year_from') ? 'year-from-error' : undefined"
            @input="setYearDraft('year_from', $event)"
            @blur="blurYear('year_from')"
            @keydown.up.prevent="stepYear('year_from', 1)"
            @keydown.down.prevent="stepYear('year_from', -1)"
          >
          <small v-if="yearError('year_from')" id="year-from-error" class="se-field-error">{{ yearError('year_from') }}</small>
        </label>
        <label class="se-field">
          <span>Год окончания выпуска</span>
          <input
            :value="yearDraft('year_to')"
            type="text"
            aria-label="Год окончания выпуска"
            inputmode="numeric"
            pattern="[0-9]*"
            maxlength="4"
            :aria-invalid="Boolean(yearError('year_to'))"
            :aria-describedby="yearError('year_to') ? 'year-to-error' : undefined"
            @input="setYearDraft('year_to', $event)"
            @blur="blurYear('year_to')"
            @keydown.up.prevent="stepYear('year_to', 1)"
            @keydown.down.prevent="stepYear('year_to', -1)"
          >
          <small v-if="yearError('year_to')" id="year-to-error" class="se-field-error">{{ yearError('year_to') }}</small>
        </label>
      </div>
      <div class="se-field">
        <span>
          Категории по умолчанию
          <CatalogHelpPopover
            label="Категории модификации"
            text="При создании объявления эти категории предлагаются как исходный набор. Администратор всё равно явно сохраняет итоговый выбор."
          />
        </span>
        <CatalogCategoryMultiSelect
          ref="modificationCategoryPicker"
          :model-value="uuidArray('category_ids')"
          :categories="categories"
          title="Категории модификации"
          @update:model-value="changeModificationCategories"
        />
        <ol v-if="selectedModificationCategories.length" class="se-category-order">
          <li v-for="(category, index) in selectedModificationCategories" :key="category.id">
            <span>
              <strong>{{ category.name }}</strong>
              <small>{{ index === 0 ? 'Основная категория' : `Дополнительная категория ${index}` }}</small>
            </span>
            <span class="se-category-order__actions">
              <button
                type="button"
                class="se-icon-button"
                :disabled="index === 0"
                :aria-label="`Поднять категорию «${category.name}»`"
                @click="moveModificationCategory(index, -1)"
              >
                ↑
              </button>
              <button
                type="button"
                class="se-icon-button"
                :disabled="index === selectedModificationCategories.length - 1"
                :aria-label="`Опустить категорию «${category.name}»`"
                @click="moveModificationCategory(index, 1)"
              >
                ↓
              </button>
            </span>
          </li>
        </ol>
        <small class="se-field-help">Первая категория сохраняется как основная; порядок остальных задаёт приоритет характеристик.</small>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'modifications'" class="se-form-section">
      <legend>Характеристики модификации</legend>
      <p class="se-section-help">Значения принадлежат модификации. Объявления используют их как живую проекцию без копирования.</p>
      <div v-if="uuidArray('category_ids').length === 0" class="se-quiet-state">Сначала выберите категории модификации.</div>
      <div v-else-if="modificationAttributes.length === 0" class="se-quiet-state">У выбранных категорий нет характеристик.</div>
      <div v-else class="se-modification-groups">
        <section v-for="group in modificationAttributeGroups" :key="group.id ?? 'ungrouped'" class="se-modification-group">
          <h3>{{ group.name || 'Прочие' }}</h3>
          <div class="se-form-stack">
            <label v-for="field in group.fields" :key="field.attribute.id" class="se-field">
              <span>{{ field.attribute.name }}<small v-if="field.attribute.unit">, {{ field.attribute.unit }}</small><b v-if="field.isRequired"> *</b></span>
              <CatalogSearchableSelect
                v-if="field.attribute.data_type === 'select'"
                :model-value="modificationOptionValue(field.attribute.id)"
                :options="modificationAttributeOptions(field.attribute)"
                :label="`Значение характеристики «${field.attribute.name}»`"
                placeholder="Не задано"
                :required="field.isRequired"
                @change="setModificationValue(field.attribute.id, $event ?? '')"
              />
              <select
                v-else-if="field.attribute.data_type === 'boolean'"
                class="select-field"
                :value="String(modificationValue(field.attribute.id) ?? '')"
                :required="field.isRequired"
                :aria-required="field.isRequired"
                @change="setModificationValue(field.attribute.id, booleanSelectValue($event))"
              >
                <option value="">Не задано</option>
                <option value="true">Да</option>
                <option value="false">Нет</option>
              </select>
              <input
                v-else
                :value="modificationValue(field.attribute.id)"
                :type="field.attribute.data_type === 'number' ? 'number' : 'text'"
                :required="field.isRequired"
                :aria-required="field.isRequired"
                @input="setModificationValue(field.attribute.id, inputValue($event))"
              >
            </label>
          </div>
        </section>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'products' && isKit" class="se-form-section">
      <legend>Блок 1. Шасси</legend>
      <p class="se-section-help">Выберите категорию шасси, марку и модель, затем модификацию и цвета. Если модификация не выбрана, характеристики заполняются вручную.</p>

      <div class="se-field">
        <span>Категории шасси <b>*</b></span>
        <CatalogCategoryMultiSelect
          :model-value="kitChassisCategoryIds"
          :categories="categories"
          :allowed-ids="chassisAllowedCategoryIds"
          :disabled-ids="inactiveProductCategoryIds"
          title="Категории шасси"
          required
          @update:model-value="changeKitChassisCategories"
        />
        <small v-if="kitChassisCategoryIds.length === 0" class="se-field-help">Выберите категорию для фильтрации марок и моделей шасси.</small>
      </div>

      <div class="se-field-row">
        <label class="se-field">
          <span>Марка шасси <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('selected_mark_id')"
            :options="kitChassisMarks"
            label="Марка шасси"
            placeholder="Найдите марку"
            required
            @change="changeKitChassisMark"
          />
        </label>
        <label class="se-field">
          <span>Модель шасси <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('model_id')"
            :options="kitChassisModels"
            label="Модель шасси"
            placeholder="Найдите модель"
            :disabled="!text('selected_mark_id') || modelsLoading"
            required
            @change="changeKitChassisModel"
          />
        </label>
      </div>

      <label class="se-field">
        <span>Модификация шасси</span>
        <CatalogSearchableSelect
          :model-value="uuidValue('modification_id')"
          :options="modifications"
          label="Модификация шасси"
          placeholder="Без модификации (необязательно)"
          :disabled="!text('model_id') || modificationsLoading"
          @change="changeKitChassisModification"
        />
      </label>

      <div class="se-field-row">
        <label class="se-field">
          <span>Цвет кузова</span>
          <CatalogSearchableSelect
            :model-value="uuidValue('body_color_id')"
            :options="bodyColorSelectOptions"
            label="Цвет кузова"
            placeholder="Не указан"
            @change="set('body_color_id', $event ?? '')"
          />
          <small v-if="inactiveBodyColorLabel" class="se-field-help">Текущий цвет неактивен: {{ inactiveBodyColorLabel }}. Его можно сохранить как есть или очистить, но нельзя выбрать заново.</small>
        </label>
        <label class="se-field">
          <span>Цвет салона</span>
          <CatalogSearchableSelect
            :model-value="uuidValue('interior_color_id')"
            :options="interiorColorSelectOptions"
            label="Цвет салона"
            placeholder="Не указан"
            @change="set('interior_color_id', $event ?? '')"
          />
          <small v-if="inactiveInteriorColorLabel" class="se-field-help">Текущий цвет неактивен: {{ inactiveInteriorColorLabel }}. Его можно сохранить как есть или очистить, но нельзя выбрать заново.</small>
        </label>
      </div>

      <label class="se-field">
        <span>VIN шасси{{ !boolValue('no_vin') ? ' *' : '' }}</span>
        <input
          :value="text('chassis_vin')"
          type="text"
          maxlength="32"
          :disabled="boolValue('no_vin')"
          :required="!boolValue('no_vin')"
          :aria-required="!boolValue('no_vin')"
          placeholder="Укажите VIN шасси"
          @input="setText('chassis_vin', $event)"
        >
        <small v-if="boolValue('no_vin')" class="se-field-help">Для техники без VIN поле заблокировано.</small>
      </label>

      <!-- Model category warning -->
      <div
        v-if="selectedChassisModel && !selectedChassisModel.category_id && !uuidValue('modification_id')"
        class="se-form-alert se-form-alert--error"
        role="alert"
      >
        <ExclamationCircleIcon aria-hidden="true" />
        <div>
          <strong>Категория модели не указана</strong>
          <p>У выбранной модели шасси нет категории в справочнике. Назначьте категорию модели в справочнике, чтобы определить характеристики шасси.</p>
        </div>
      </div>

      <!-- Chassis attributes -->
      <div v-if="selectedModification || (selectedChassisModel?.category_id || (!selectedChassisModel && kitChassisCategoryIds.length > 0))" class="se-kit-chassis-attributes">
        <div v-if="selectedModification">
          <div class="se-section-heading">
            <h4>Характеристики шасси</h4>
            <span class="se-badge-note">Значения из модификации</span>
          </div>
          <dl v-if="selectedModification.attribute_values.length" class="se-readonly-specs">
            <div v-for="val in selectedModification.attribute_values" :key="val.attribute_id">
              <dt>{{ val.attribute_name || 'Характеристика' }}</dt>
              <dd>{{ val.display_value ?? val.value ?? 'Не задано' }}</dd>
            </div>
          </dl>
          <div v-else class="se-quiet-state">У модификации нет заполненных характеристик.</div>
        </div>

        <div v-else>
          <div class="se-section-heading">
            <h4>Характеристики шасси</h4>
            <small class="se-field-help">Заполняются вручную по правилам выбранных категорий.</small>
          </div>
          <div v-if="chassisAttributeGroups.length === 0" class="se-quiet-state">
            У выбранных категорий нет характеристик.
          </div>
          <div v-else class="se-modification-groups">
            <section v-for="group in chassisAttributeGroups" :key="group.id ?? 'ungrouped'" class="se-modification-group">
              <h3>{{ group.name || 'Прочие' }}</h3>
              <div class="se-form-stack">
                <label v-for="field in group.fields" :key="field.attribute.id" class="se-field">
                  <span>{{ field.attribute.name }}<small v-if="field.attribute.unit">, {{ field.attribute.unit }}</small><b v-if="field.isRequired"> *</b></span>
                  <CatalogSearchableSelect
                    v-if="field.attribute.data_type === 'select'"
                    :model-value="chassisOptionValue(field.attribute.id)"
                    :options="modificationAttributeOptions(field.attribute)"
                    :label="`Значение характеристики «${field.attribute.name}»`"
                    placeholder="Не задано"
                    :required="field.isRequired"
                    @change="setChassisValue(field.attribute.id, { option_id: $event || null })"
                  />
                  <select
                    v-else-if="field.attribute.data_type === 'boolean'"
                    :value="String(chassisValue(field.attribute.id)?.value_boolean ?? '')"
                    :required="field.isRequired"
                    :aria-required="field.isRequired"
                    @change="setChassisValue(field.attribute.id, { value_boolean: nullableBooleanSelectValue($event) })"
                  >
                    <option value="">Не задано</option>
                    <option value="true">Да</option>
                    <option value="false">Нет</option>
                  </select>
                  <input
                    v-else
                    :value="field.attribute.data_type === 'number' ? chassisValue(field.attribute.id)?.value_number ?? '' : chassisValue(field.attribute.id)?.value_text ?? ''"
                    :type="field.attribute.data_type === 'number' ? 'number' : 'text'"
                    :required="field.isRequired"
                    :aria-required="field.isRequired"
                    @input="setChassisValue(field.attribute.id, field.attribute.data_type === 'number' ? { value_number: normalizeCatalogPrice(inputValue($event)) } : { value_text: inputValue($event) })"
                  >
                </label>
              </div>
            </section>
          </div>
        </div>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'products' && isKit" class="se-form-section">
      <legend>Блок 2. Надстройка</legend>

      <!-- Mode switcher -->
      <div class="se-choice-grid se-choice-grid--compact" role="radiogroup" aria-label="Способ заполнения надстройки">
        <label class="se-choice-card" :class="{ 'se-choice-card--active': superstructureSourceMode === 'manual' }">
          <input
            type="radio"
            name="superstructure-source-mode"
            value="manual"
            :checked="superstructureSourceMode === 'manual'"
            @change="changeSuperstructureSourceMode('manual')"
          >
          <span><strong>Ввести самим</strong><small>Указать характеристики вручную.</small></span>
        </label>
        <label class="se-choice-card" :class="{ 'se-choice-card--active': superstructureSourceMode === 'existing' }">
          <input
            type="radio"
            name="superstructure-source-mode"
            value="existing"
            :checked="superstructureSourceMode === 'existing'"
            @change="changeSuperstructureSourceMode('existing')"
          >
          <span><strong>Выбрать существующую</strong><small>Использовать существующее объявление надстройки.</small></span>
        </label>
      </div>

      <!-- Mode 'manual' -->
      <div v-if="superstructureSourceMode === 'manual'" class="se-superstructure-form">
        <label class="se-field">
          <span>Тип надстройки <b>*</b></span>
          <CatalogSearchableSelect
            :model-value="uuidValue('superstructure_id')"
            :options="kitAvailableSuperstructureTypes"
            label="Тип надстройки"
            placeholder="Выберите тип"
            :disabled="allSuperstructuresLoading"
            required
            @change="changeKitSuperstructureType"
          />
        </label>

        <label class="se-field">
          <span>Название надстройки <b>*</b></span>
          <input
            :value="text('superstructure_name')"
            type="text"
            maxlength="255"
            placeholder="Например, АТЗ-10"
            required
            aria-required="true"
            @input="setText('superstructure_name', $event)"
          >
        </label>

        <label class="se-field">
          <span>Производитель надстройки <b>*</b></span>
          <input
            :value="text('superstructure_manufacturer')"
            type="text"
            maxlength="255"
            placeholder="Например, Palfinger или НПО Вектор"
            required
            aria-required="true"
            @input="setText('superstructure_manufacturer', $event)"
          >
        </label>

        <label class="se-field">
          <span>VIN надстройки</span>
          <input
            :value="text('superstructure_vin')"
            type="text"
            maxlength="32"
            :disabled="boolValue('no_vin')"
            placeholder="Укажите VIN надстройки (необязательно)"
            @input="setText('superstructure_vin', $event)"
          >
          <small v-if="boolValue('no_vin')" class="se-field-help">Для техники без VIN поле заблокировано.</small>
        </label>

        <!-- Superstructure attributes for selected type -->
        <div v-if="selectedSuperstructureTypeAttributes.length > 0" class="se-superstructure-type-attributes">
          <div class="se-section-heading">
            <h4>Характеристики надстройки</h4>
            <small class="se-field-help">Заполняются по правилам выбранного типа надстройки.</small>
          </div>
          <div class="se-modification-groups">
            <section v-for="group in superstructureAttributeGroups" :key="group.id ?? 'ungrouped'" class="se-modification-group">
              <h3>{{ group.name || 'Прочие' }}</h3>
              <div class="se-form-stack">
                <label v-for="field in group.fields" :key="field.attribute.id" class="se-field">
                  <span>{{ field.attribute.name }}<small v-if="field.attribute.unit">, {{ field.attribute.unit }}</small><b v-if="field.isRequired"> *</b></span>
                  <CatalogSearchableSelect
                    v-if="field.attribute.data_type === 'select'"
                    :model-value="superstructureOptionValue(field.attribute.id)"
                    :options="modificationAttributeOptions(field.attribute)"
                    :label="`Значение характеристики «${field.attribute.name}»`"
                    placeholder="Не задано"
                    :required="field.isRequired"
                    @change="setSuperstructureValue(field.attribute.id, { option_id: $event || null })"
                  />
                  <select
                    v-else-if="field.attribute.data_type === 'boolean'"
                    :value="String(superstructureVal(field.attribute.id)?.value_boolean ?? '')"
                    :required="field.isRequired"
                    :aria-required="field.isRequired"
                    @change="setSuperstructureValue(field.attribute.id, { value_boolean: nullableBooleanSelectValue($event) })"
                  >
                    <option value="">Не задано</option>
                    <option value="true">Да</option>
                    <option value="false">Нет</option>
                  </select>
                  <input
                    v-else
                    :value="field.attribute.data_type === 'number' ? superstructureVal(field.attribute.id)?.value_number ?? '' : superstructureVal(field.attribute.id)?.value_text ?? ''"
                    :type="field.attribute.data_type === 'number' ? 'number' : 'text'"
                    :required="field.isRequired"
                    :aria-required="field.isRequired"
                    @input="setSuperstructureValue(field.attribute.id, field.attribute.data_type === 'number' ? { value_number: normalizeCatalogPrice(inputValue($event)) } : { value_text: inputValue($event) })"
                  >
                </label>
              </div>
            </section>
          </div>
        </div>
      </div>

      <!-- Mode 'existing' -->
      <div v-else class="se-superstructure-existing">
        <div class="se-field-row">
          <label class="se-field">
            <span>Тип надстройки <b>*</b></span>
            <CatalogSearchableSelect
              :model-value="uuidValue('superstructure_id')"
              :options="kitAvailableSuperstructureTypes"
              label="Тип надстройки"
              placeholder="Выберите тип"
              :disabled="allSuperstructuresLoading"
              required
              @change="changeKitSuperstructureType"
            />
          </label>
          <label class="se-field">
            <span>Производитель надстройки <b>*</b></span>
            <CatalogSearchableSelect
              :model-value="kitSuperstructureMarkId"
              :options="kitSuperstructureMarks"
              label="Производитель надстройки"
              placeholder="Найдите производителя"
              required
              @change="changeKitSuperstructureMark"
            />
          </label>
        </div>

        <div class="se-field-row">
          <label class="se-field">
            <span>Модель надстройки <b>*</b></span>
            <CatalogSearchableSelect
              :model-value="kitSuperstructureModelId"
              :options="superstructureModels"
              label="Модель надстройки"
              placeholder="Найдите модель"
              :disabled="!kitSuperstructureMarkId || superstructureModelsLoading"
              required
              @change="changeKitSuperstructureModel"
            />
          </label>
          <label class="se-field">
            <span>Модификация надстройки</span>
            <CatalogSearchableSelect
              :model-value="uuidValue('superstructure_modification_id')"
              :options="superstructureModifications"
              label="Модификация надстройки"
              placeholder="Без модификации (необязательно)"
              :disabled="!kitSuperstructureModelId || superstructureModificationsLoading"
              @change="changeKitSuperstructureModification"
            />
          </label>
        </div>

        <label class="se-field">
          <span>VIN надстройки</span>
          <input
            :value="text('superstructure_vin')"
            type="text"
            maxlength="32"
            :disabled="boolValue('no_vin')"
            placeholder="Укажите VIN надстройки (необязательно)"
            @input="setText('superstructure_vin', $event)"
          >
          <small v-if="boolValue('no_vin')" class="se-field-help">Для техники без VIN поле заблокировано.</small>
        </label>

        <p v-if="!kitSuperstructureModelId || !uuidValue('superstructure_id')" class="se-field-help se-source-prompt">
          Выберите модель и тип надстройки
        </p>

        <div v-else class="se-superstructure-existing-body">
          <p v-if="sourceInvalidError" class="se-field-error" role="alert">
            {{ sourceInvalidError }}
          </p>

          <!-- Selected ad card -->
          <article v-if="hasSelectedAd && !isSelectingSourceAd" class="se-source-card">
            <div class="se-source-card__header">
              <div class="se-source-card__main">
                <span class="se-source-card__code">{{ currentSourceAdCode }}</span>
                <strong class="se-source-card__title">{{ currentSourceAdTitle }}</strong>
                <span v-if="currentSourceAdStatusLabel" class="se-source-card__status">{{ currentSourceAdStatusLabel }}</span>
              </div>
              <button
                type="button"
                class="se-button se-button--ghost se-button--small"
                @click="startChangingSourceAd"
              >
                Изменить
              </button>
            </div>
            <div class="se-source-card__details">
              <div>
                <span class="se-source-card__label">Название надстройки:</span>
                <span class="se-source-card__value">{{ currentSourceAdModelName }}</span>
              </div>
              <div>
                <span class="se-source-card__label">Производитель:</span>
                <span class="se-source-card__value">{{ currentSourceAdMarkName }}</span>
              </div>
            </div>
          </article>

          <!-- Search and picker if not selected or changing -->
          <div v-if="!hasSelectedAd || isSelectingSourceAd" class="se-source-picker">
            <div class="se-source-picker__header">
              <label class="se-field">
                <span>Поиск объявления надстройки</span>
                <input
                  v-model="attachmentSourceSearch"
                  type="search"
                  placeholder="Поиск по коду или названию"
                  @input="onSearchAttachmentSources"
                >
              </label>
              <button
                v-if="hasSelectedAd"
                type="button"
                class="se-button se-button--ghost se-button--small"
                @click="isSelectingSourceAd = false"
              >
                Отмена
              </button>
            </div>
            <div v-if="attachmentSourcesLoading" class="se-quiet-state">Поиск объявлений надстроек…</div>
            <div v-else-if="attachmentSources.length > 0" class="se-source-list">
              <button
                v-for="src in attachmentSources"
                :key="src.id"
                type="button"
                class="se-source-item"
                :class="{ 'se-source-item--active': src.id === draft.superstructure_source_product_id }"
                @click="pickAttachmentSource(src)"
              >
                <div class="se-source-item__top">
                  <span class="se-source-item__code">{{ src.code }}</span>
                  <span class="se-source-item__status">{{ publicationStatusLabel(src.publication_status) }}</span>
                </div>
                <strong>{{ sourceItemTitle(src) }}</strong>
                <small>Надстройка: {{ src.superstructure_name || (typeof src.model === 'object' ? src.model?.name : src.model) || '' }} · Производитель: {{ src.superstructure_manufacturer || (typeof src.mark === 'object' ? src.mark?.name : src.mark) || '' }}</small>
              </button>
            </div>
            <div v-else class="se-quiet-state">Объявления надстроек не найдены.</div>
          </div>

          <!-- Characteristics (editable, copied from selected ad) -->
          <div v-if="hasSelectedAd && selectedSuperstructureTypeAttributes.length > 0" class="se-superstructure-type-attributes">
            <div class="se-section-heading">
              <h4>Характеристики надстройки</h4>
              <small class="se-field-help">Заполнены из выбранного объявления; доступны для редактирования.</small>
            </div>
            <div class="se-modification-groups">
              <section v-for="group in superstructureAttributeGroups" :key="group.id ?? 'ungrouped'" class="se-modification-group">
                <h3>{{ group.name || 'Прочие' }}</h3>
                <div class="se-form-stack">
                  <label v-for="field in group.fields" :key="field.attribute.id" class="se-field">
                    <span>{{ field.attribute.name }}<small v-if="field.attribute.unit">, {{ field.attribute.unit }}</small><b v-if="field.isRequired"> *</b></span>
                    <CatalogSearchableSelect
                      v-if="field.attribute.data_type === 'select'"
                      :model-value="superstructureOptionValue(field.attribute.id)"
                      :options="modificationAttributeOptions(field.attribute)"
                      :label="`Значение характеристики «${field.attribute.name}»`"
                      placeholder="Не задано"
                      :required="field.isRequired"
                      @change="setSuperstructureValue(field.attribute.id, { option_id: $event || null })"
                    />
                    <select
                      v-else-if="field.attribute.data_type === 'boolean'"
                      :value="String(superstructureVal(field.attribute.id)?.value_boolean ?? '')"
                      :required="field.isRequired"
                      :aria-required="field.isRequired"
                      @change="setSuperstructureValue(field.attribute.id, { value_boolean: nullableBooleanSelectValue($event) })"
                    >
                      <option value="">Не задано</option>
                      <option value="true">Да</option>
                      <option value="false">Нет</option>
                    </select>
                    <input
                      v-else
                      :value="field.attribute.data_type === 'number' ? superstructureVal(field.attribute.id)?.value_number ?? '' : superstructureVal(field.attribute.id)?.value_text ?? ''"
                      :type="field.attribute.data_type === 'number' ? 'number' : 'text'"
                      :required="field.isRequired"
                      :aria-required="field.isRequired"
                      @input="setSuperstructureValue(field.attribute.id, field.attribute.data_type === 'number' ? { value_number: normalizeCatalogPrice(inputValue($event)) } : { value_text: inputValue($event) })"
                    >
                  </label>
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>

      <div v-if="uuidValue('superstructure_id')" class="se-field se-kit-categories-field">
        <span>Категории комплекта <b>*</b></span>
        <CatalogCategoryMultiSelect
          :model-value="uuidArray('category_ids')"
          :categories="categories"
          :allowed-ids="kitCategoryAllowedIds"
          :disabled-ids="inactiveProductCategoryIds"
          title="Категории комплекта"
          required
          @update:model-value="set('category_ids', $event)"
        />
        <small v-if="kitCategoryAllowedIds.length === 0" class="se-field-error">
          У выбранного типа надстройки нет разрешенных категорий каталога для размещения комплекта. Назначьте категории типу надстройки в справочнике.
        </small>
        <small v-else-if="uuidArray('category_ids').length === 0" class="se-field-help">
          Выберите одну или несколько категорий, в которых будет размещено объявление комплекта.
        </small>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'products' && !isKit" class="se-form-section">
      <legend>Связи и состав объявления</legend>
      <p class="se-section-help">При создании связи сохраняются атомарно вместе с объявлением.</p>
      <div class="se-product-relations">
        <CatalogProductRelationEditor
          v-if="showsCompatibleAttachments"
          kind="attachments"
          :product-id="productId"
          :model-value="attachmentLinks"
          :opposite-count="0"
          :blocked-reason="boolValue('is_attachment') ? 'Объявление надстройки не может владеть списком совместимых надстроек.' : ''"
          @update:model-value="set('compatible_attachments', $event)"
        />
        <div v-if="!showsCompatibleAttachments" class="se-quiet-state">
          Самостоятельная надстройка сохраняется как отдельное объявление без состава.
        </div>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'products'" class="se-form-section">
      <legend>Параметры объявления</legend>
      <div class="se-form-stack">
        <div v-if="!isKit" class="se-field">
          <span>Категории объявления <b>*</b></span>
          <CatalogCategoryMultiSelect
            :model-value="uuidArray('category_ids')"
            :categories="categories"
            :allowed-ids="productCategoryAllowedIds"
            :disabled-ids="inactiveProductCategoryIds"
            title="Категории объявления"
            required
            @update:model-value="set('category_ids', $event)"
          />
          <small class="se-field-help">Категории модификации выбраны по умолчанию. Можно добавить другие активные категории с тем же показателем эксплуатации.</small>
        </div>
        <label class="se-checkbox-row">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="priceOnRequest"
            :disabled="priceModeLocked"
            :aria-describedby="priceModeLocked ? 'price-on-request-locked' : 'price-on-request-help'"
            @change="set('price_on_request', checkedValue($event))"
          >
          <span>
            <strong>Цена по запросу</strong>
            <small id="price-on-request-help">Можно показать нижнюю границу «от N ₽» или оставить цену полностью по запросу.</small>
            <small v-if="priceModeLocked" id="price-on-request-locked" class="se-field-help">
              Режим нельзя изменить после публикации объявления.
            </small>
          </span>
        </label>
        <div v-if="priceOnRequest" class="se-field-row">
          <label class="se-field">
            <span>От, ₽ <small>(необязательно)</small></span>
            <input
              :value="text('price_from')"
              type="number"
              min="0.01"
              step="0.01"
              :aria-invalid="Boolean(priceFromError)"
              :aria-describedby="priceFromError ? 'price-from-error' : 'price-from-help'"
              @input="setText('price_from', $event)"
            >
            <small id="price-from-help" class="se-field-help">Пустое поле покажет «Цена по запросу».</small>
            <small v-if="priceFromError" id="price-from-error" class="se-field-error">{{ priceFromError }}</small>
          </label>
        </div>
        <div v-else class="se-field-row">
          <label class="se-field">
            <span>Цена, ₽{{ text('sale_status') === 'on_order' ? ' *' : '' }}</span>
            <input :value="text('price')" type="number" min="0.01" step="0.01" :required="text('sale_status') === 'on_order'" :aria-required="text('sale_status') === 'on_order'" @input="setText('price', $event)">
          </label>
          <label class="se-field">
            <span>Специальная цена, ₽</span>
            <input
              :value="text('special_price')"
              type="number"
              min="0.01"
              step="0.01"
              :aria-invalid="Boolean(specialPriceError)"
              :aria-describedby="specialPriceError ? 'special-price-error' : undefined"
              @input="setText('special_price', $event)"
            >
            <small v-if="specialPriceError" id="special-price-error" class="se-field-error">{{ specialPriceError }}</small>
          </label>
        </div>
        <div class="se-field-row">
          <label class="se-field">
            <span>Год выпуска</span>
            <input
              :value="yearDraft('manufacture_year')"
              type="text"
              aria-label="Год выпуска"
              inputmode="numeric"
              pattern="[0-9]*"
              maxlength="4"
              :aria-invalid="Boolean(yearError('manufacture_year'))"
              :aria-describedby="yearError('manufacture_year') ? 'manufacture-year-error' : undefined"
              @input="setYearDraft('manufacture_year', $event)"
              @blur="blurYear('manufacture_year')"
              @keydown.up.prevent="stepYear('manufacture_year', 1)"
              @keydown.down.prevent="stepYear('manufacture_year', -1)"
            >
            <small v-if="yearError('manufacture_year')" id="manufacture-year-error" class="se-field-error">{{ yearError('manufacture_year') }}</small>
          </label>
        </div>
        <div class="se-field">
          <span>Состояние <b>*</b></span>
          <div class="se-radio-row">
            <label><input type="radio" name="condition" value="new" required aria-required="true" :checked="text('condition') === 'new'" @change="changeCondition('new')"> Новое</label>
            <label><input type="radio" name="condition" value="used" required aria-required="true" :checked="text('condition') === 'used'" @change="changeCondition('used')"> С пробегом</label>
          </div>
        </div>
        <label v-if="text('condition') === 'used' && selectedUsageMetric === 'mileage_km'" class="se-field">
          <span>
            Пробег, км <b>*</b>
            <CatalogHelpPopover label="Пробег" text="Для техники с пробегом указывается только показатель, разрешённый выбранными категориями." />
          </span>
          <input :value="nullableNumber('mileage_km')" type="number" min="0" step="1" required aria-label="Пробег, км" aria-required="true" @input="setNullableInteger('mileage_km', $event)">
        </label>
        <label v-if="text('condition') === 'used' && selectedUsageMetric === 'engine_hours'" class="se-field">
          <span>
            Моточасы <b>*</b>
            <CatalogHelpPopover label="Моточасы" text="Для техники с пробегом указывается только показатель, разрешённый выбранными категориями." />
          </span>
          <input :value="nullableNumber('engine_hours')" type="number" min="0" step="1" required aria-label="Моточасы" aria-required="true" @input="setNullableInteger('engine_hours', $event)">
        </label>
        <label v-if="text('condition') === 'used'" class="se-field">
          <span>Количество владельцев <b>*</b></span>
          <input
            :value="nullableNumber('owners_count')"
            type="number"
            min="0"
            step="1"
            required
            aria-required="true"
            @input="setNullableInteger('owners_count', $event)"
          >
        </label>
        <p v-if="usageMetricConflict" class="se-inline-error" role="alert">
          Выбраны категории с разными показателями эксплуатации. Такой набор сохранить нельзя.
        </p>
        <label class="se-field">
          <span>Статус продажи</span>
          <select class="select-field" :value="text('sale_status')" @change="setText('sale_status', $event)">
            <option value="available">В наличии</option>
            <option value="on_order">Под заказ</option>
            <option value="reserved">Зарезервировано</option>
            <option value="sold">Продано</option>
            <option value="unavailable">Недоступно</option>
          </select>
        </label>
        <label class="se-field">
          <span>Публикация</span>
          <select class="select-field" :value="text('publication_status')" @change="setText('publication_status', $event)">
            <option value="draft">Черновик</option>
            <option value="published">Опубликовано</option>
            <option value="archived">В архиве</option>
          </select>
        </label>
        <label class="se-field">
          <span>Компания-продавец</span>
          <CatalogSearchableSelect
            :model-value="uuidValue('seller_company_id')"
            :options="sellerOptions"
            label="Компания-продавец"
            placeholder="Найдите компанию по названию или ИНН"
            @change="changeSeller"
          />
        </label>
        <label class="se-field">
          <span>Склад{{ warehouseRequired ? ' *' : '' }}</span>
          <CatalogSearchableSelect
            :model-value="uuidValue('warehouse_id')"
            :options="warehouseOptions"
            label="Склад"
            :placeholder="warehousesLoading ? 'Загрузка складов…' : 'Выберите активный склад'"
            :disabled="boolValue('no_vin') || warehousesLoading || Boolean(warehousesErrorMessage)"
            :required="warehouseRequired"
            @change="changeWarehouse"
          />
          <small v-if="warehousesErrorMessage" class="se-field-help se-form-alert--error" role="alert">Не удалось загрузить активные склады. <button type="button" class="se-button-link" @click="emit('retry-warehouses')">Повторить</button></small>
          <template v-else>
            <small v-if="warehouseOwnerMessage" class="se-field-help" role="status">{{ warehouseOwnerMessage }}</small>
            <small v-if="warehouseOwnerConflictMessage" class="se-field-help se-form-alert--error" role="alert">{{ warehouseOwnerConflictMessage }}</small>
            <small v-if="boolValue('no_vin')" class="se-field-help">Для товара без VIN склад не назначается.</small>
            <small v-else-if="text('sale_status') === 'on_order'" class="se-field-help">Для товара под заказ склад можно не выбирать.</small>
          </template>
        </label>
        <div v-if="!isKit" class="se-field-row">
          <label class="se-field">
            <span>Цвет кузова</span>
            <CatalogSearchableSelect
              :model-value="uuidValue('body_color_id')"
              :options="bodyColorSelectOptions"
              label="Цвет кузова"
              placeholder="Не указан"
              @change="set('body_color_id', $event ?? '')"
            />
            <small v-if="inactiveBodyColorLabel" class="se-field-help">Текущий цвет неактивен: {{ inactiveBodyColorLabel }}. Его можно сохранить как есть или очистить, но нельзя выбрать заново.</small>
          </label>
          <label class="se-field">
            <span>Цвет салона</span>
            <CatalogSearchableSelect
              :model-value="uuidValue('interior_color_id')"
              :options="interiorColorSelectOptions"
              label="Цвет салона"
              placeholder="Не указан"
              @change="set('interior_color_id', $event ?? '')"
            />
            <small v-if="inactiveInteriorColorLabel" class="se-field-help">Текущий цвет неактивен: {{ inactiveInteriorColorLabel }}. Его можно сохранить как есть или очистить, но нельзя выбрать заново.</small>
          </label>
        </div>
        <label class="se-field">
          <span>VIN Транспортного средства{{ !boolValue('no_vin') ? ' *' : '' }}</span>
          <input
            :value="text('vin')"
            type="text"
            maxlength="17"
            :disabled="boolValue('no_vin')"
            :required="!boolValue('no_vin')"
            :aria-required="!boolValue('no_vin')"
            @input="setText('vin', $event)"
          >
        </label>
        <label class="se-checkbox-row">
          <input
            class="se-checkbox"
            type="checkbox"
            :checked="boolValue('no_vin')"
            @change="changeNoVin"
          >
          <span><strong>Нет VIN</strong><small>VIN отсутствует у этой единицы техники. Заводской номер не затрагивается.</small></span>
        </label>
        <label class="se-field">
          <span>Описание</span>
          <textarea :value="text('description')" maxlength="10000" @input="setText('description', $event)" />
        </label>
      </div>
    </fieldset>

    <fieldset v-if="entity === 'products' && !isKit" class="se-form-section">
      <legend>Характеристики модификации объявления</legend>
      <p class="se-section-help">Эти данные берутся из выбранной модификации и не копируются в объявление.</p>
      <div v-if="!selectedModification" class="se-quiet-state">Выберите модификацию.</div>
      <dl v-else-if="selectedModification.attribute_values.length" class="se-readonly-specs">
        <div v-for="value in selectedModification.attribute_values" :key="value.attribute_id">
          <dt>{{ value.attribute_name || 'Характеристика' }}</dt>
          <dd>{{ value.display_value ?? value.value ?? 'Не задано' }}</dd>
        </div>
      </dl>
      <div v-else class="se-quiet-state">У модификации нет заполненных характеристик.</div>
    </fieldset>

    <fieldset v-if="entity === 'products' && !isKit && uuidValue('trim_id')" class="se-form-section">
      <legend>Характеристики комплектации объявления</legend>
      <p class="se-section-help">Эти данные принадлежат выбранной комплектации и не копируются в объявление или модификацию.</p>
      <div v-if="selectedProductTrimAttributesLoading" class="se-quiet-state" role="status" aria-live="polite">
        Загружаем характеристики комплектации…
      </div>
      <div v-else-if="selectedProductTrimAttributesErrorMessage" class="se-form-alert se-form-alert--error" role="alert">
        <ExclamationCircleIcon aria-hidden="true" />
        <div>
          <strong>Не удалось загрузить характеристики комплектации</strong>
          <p>{{ selectedProductTrimAttributesErrorMessage }}</p>
        </div>
        <button
          type="button"
          class="se-button se-button--secondary se-button--small"
          @click="emit('trim-change', uuidValue('trim_id') || null)"
        >
          Повторить загрузку
        </button>
      </div>
      <dl v-else-if="selectedProductTrimAttributes.length" class="se-readonly-specs">
        <div v-for="spec in selectedProductTrimSpecs" :key="spec.attributeId">
          <dt>{{ spec.name }}</dt>
          <dd>{{ spec.displayValue }}</dd>
        </div>
      </dl>
      <div v-else class="se-quiet-state">У комплектации нет заполненных характеристик.</div>
    </fieldset>

    <fieldset v-if="entity === 'attributes'" class="se-form-section">
      <legend>Тип и фильтрация</legend>
      <div class="se-field-row">
        <label class="se-field">
          <span>Тип значения <b>*</b></span>
          <select class="select-field" :value="text('data_type')" required aria-required="true" @change="changeAttributeDataType">
            <option value="text">Текст</option>
            <option value="number">Число</option>
            <option value="boolean">Да / Нет</option>
            <option value="select">Выбор из вариантов</option>
          </select>
        </label>
        <label class="se-field">
          <span>Способ фильтрации</span>
          <select class="select-field" :value="text('filter_kind')" @change="setText('filter_kind', $event)">
            <option v-for="filterKind in compatibleAttributeFilterKinds" :key="filterKind" :value="filterKind">
              {{ attributeFilterKindLabel(filterKind) }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="!attributeFilterCompatible" class="se-inline-error" role="alert">
        Выбранный способ фильтрации несовместим с типом характеристики.
      </p>
      <label class="se-field">
        <span>Единица измерения</span>
        <CatalogSearchableSelect
          :model-value="uuidValue('unit_id')"
          :options="unitOptions"
          label="Единица измерения"
          placeholder="Без единицы измерения"
          @change="changeAttributeUnit"
        />
      </label>
      <label class="se-field">
        <span>Группа по умолчанию</span>
        <CatalogSearchableSelect
          :model-value="uuidValue('attribute_group_id')"
          :options="groups"
          label="Группа характеристики по умолчанию"
          placeholder="Без группы («Прочие»)"
          @change="set('attribute_group_id', $event)"
        />
      </label>
    </fieldset>

    <fieldset v-if="entity === 'attributes' && text('data_type') === 'select'" class="se-form-section">
      <legend>Варианты значения</legend>
      <p class="se-section-help">Модификация хранит идентификатор выбранного варианта, а не произвольный текст.</p>
      <div class="se-option-list">
        <article v-for="(option, index) in attributeOptions" :key="option.id ?? index" class="se-option-row">
          <label class="se-field">
            <span>Код варианта</span>
            <input
              :value="option.code"
              maxlength="100"
              required
              :aria-invalid="optionFieldInvalid(option, 'code')"
              :disabled="Boolean(option.id)"
              @input="patchOption(index, 'code', inputValue($event))"
            >
            <small v-if="optionFieldInvalid(option, 'code')" class="se-field-error">Код варианта обязателен.</small>
          </label>
          <label class="se-field">
            <span>Название</span>
            <input
              :value="option.name"
              maxlength="255"
              required
              :aria-invalid="optionFieldInvalid(option, 'name')"
              @input="patchOption(index, 'name', inputValue($event))"
            >
            <small v-if="optionFieldInvalid(option, 'name')" class="se-field-error">Название варианта обязательно.</small>
          </label>
          <button type="button" class="se-icon-button se-icon-button--danger" aria-label="Удалить вариант" @click="removeOption(index)">
            <TrashIcon aria-hidden="true" />
          </button>
        </article>
      </div>
      <button type="button" class="se-button se-button--secondary se-button--small" @click="addOption">
        <PlusIcon aria-hidden="true" />
        Добавить вариант
      </button>
    </fieldset>

    <fieldset v-if="entity === 'attribute-groups'" class="se-form-section">
      <legend>Оформление группы</legend>
      <label class="se-field">
        <span>Порядок показа</span>
        <input :value="numberValue('sort_order', 0)" type="number" min="0" step="1" @input="setNumber('sort_order', $event)">
      </label>
      <div class="se-field">
        <span>Характеристики группы</span>
        <input
          v-model.trim="groupAttributeSearch"
          type="search"
          autocomplete="off"
          placeholder="Найти характеристику"
        >
        <div class="se-checkbox-picker__list">
          <label v-for="attribute in filteredGroupAttributes" :key="attribute.id">
            <input
              class="se-checkbox"
              type="checkbox"
              :checked="uuidArray('attribute_ids').includes(attribute.id)"
              @change="toggleGroupAttribute(attribute.id)"
            >
            <span>{{ attribute.name }}{{ attribute.unit ? `, ${attribute.unit}` : '' }}</span>
          </label>
        </div>
      </div>
    </fieldset>

    <Modal
      :show="pendingModificationCategoryChange !== null"
      title="Очистить несовместимые характеристики?"
      size="sm"
      :closable="false"
      :close-on-overlay="false"
      :show-footer="true"
      confirm-text="Очистить и продолжить"
      cancel-text="Отмена"
      @cancel="cancelModificationCategoryChange"
      @confirm="confirmModificationCategoryChange"
      @after-close="focusModificationCategoryPicker"
    >
      <p>Новый набор категорий не поддерживает заполненные характеристики:</p>
      <ul class="se-confirmation-list">
        <li v-for="name in pendingRemovedAttributeNames" :key="name">{{ name }}</li>
      </ul>
      <p>Значения будут удалены только после подтверждения.</p>
    </Modal>

    <Modal
      :show="pendingAttributeDataType !== null"
      title="Изменить тип характеристики?"
      size="sm"
      :closable="false"
      :close-on-overlay="false"
      :show-footer="true"
      confirm-text="Подтвердить преобразование"
      cancel-text="Отмена"
      @cancel="cancelAttributeDataTypeChange"
      @confirm="confirmAttributeDataTypeChange"
    >
      <p>{{ pendingAttributeConversionDescription }}</p>
      <p>Категорийные связи, группа, код и порядок характеристики сохранятся.</p>
    </Modal>

    <Modal
      :show="pendingKitConfirm !== null"
      :title="pendingKitConfirm?.title ?? 'Подтверждение'"
      size="sm"
      :closable="false"
      :close-on-overlay="false"
      :show-footer="true"
      confirm-text="Продолжить"
      cancel-text="Отмена"
      @cancel="cancelKitConfirm"
      @confirm="confirmKitConfirm"
    >
      <p>{{ pendingKitConfirm?.message }}</p>
      <ul v-if="pendingKitConfirm?.items?.length" class="se-confirmation-list">
        <li v-for="item in pendingKitConfirm.items" :key="item">{{ item }}</li>
      </ul>
    </Modal>
  </div>
</template>

<script setup lang="ts">
import {
  ExclamationCircleIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import Modal from '~/components/ui/Modal.vue'
import { isUuid, type UUID } from '~/types/ids'
import {
  isCatalogAttributeOptionFieldInvalid,
  patchCatalogAttributeOption,
  suggestCatalogCode,
  syncSuggestedCatalogCode,
} from './catalogCode'
import {
  catalogAttributeFilterKinds,
  isCatalogAttributeFilterCompatible,
} from './catalogAttributeFilter'
import { appendCategoryAttributeLinks } from './categoryAttributeLinks'
import { categoryDescendantIds } from './categoryGraph'
import { normalizeCatalogInteger } from './catalogInteger'
import { normalizeCatalogPrice } from './catalogPrice'
import {
  catalogYearDraft,
  catalogYearDraftError,
  stepCatalogYearDraft,
} from './catalogYearDraft'
import {
  categoryIsInAttachmentBranch,
  productSelectableCategoryIds,
  replaceProductCategoryDefaults,
} from './catalogProductCategories'
import { buildModificationAttributeGroups } from './modificationAttributeGroups'
import {
  applyProductSellerSelection,
  applyProductWarehouseSelection,
  productWarehouseConflictMessage,
  productWarehouseOwner,
} from './productWarehouseOwner'
import { presentProductTrimAttribute } from './trimAttributePresentation'
import CatalogCategoryAttributePicker from './CatalogCategoryAttributePicker.vue'
import CatalogCategoryMultiSelect from './CatalogCategoryMultiSelect.vue'
import CatalogHelpPopover from './CatalogHelpPopover.vue'
import CatalogProductRelationEditor from './CatalogProductRelationEditor.vue'
import CatalogSearchableSelect from './CatalogSearchableSelect.vue'
import CatalogTrimAttributePicker from './CatalogTrimAttributePicker.vue'
import CatalogSuperstructureAttributePicker from './CatalogSuperstructureAttributePicker.vue'
import { createCatalogCorrectionApi } from './api'
import type { ModificationAttributeField } from './modificationAttributeGroups'
import type {
  AttachmentSourceItem,
  CatalogAttribute,
  CatalogActiveWarehouse,
  CatalogAttributeGroup,
  CatalogAttributeOption,
  CatalogCategory,
  CatalogCategoryAttributeLink,
  CatalogColorSelectItem,
  CatalogDataType,
  CatalogDraft,
  CatalogEntity,
  CatalogFilterKind,
  CatalogMark,
  CatalogModel,
  CatalogModification,
  CatalogModificationValue,
  CatalogNamedRef,
  CatalogProduct,
  CatalogProductAttachmentLink,
  CatalogProductChassisValue,
  CatalogProductSuperstructureValue,
  CatalogSellerCompany,
  CatalogSuperstructure,
  CatalogSuperstructureAttribute,
  CatalogTrimLifecycleItem,
  CatalogTrimAttributeAssignment,
  CatalogTrimAttributeCandidateGroup,
  CatalogTrimAttributeValue,
  CatalogUnit,
  CatalogUsageMetric,
} from './types'

const props = defineProps<{
  entity: CatalogEntity
  mode: 'create' | 'edit'
  modelValue: CatalogDraft
  categories: CatalogCategory[]
  marks: CatalogMark[]
  models: CatalogModel[]
  modifications: CatalogModification[]
  attributes: CatalogAttribute[]
  groups: CatalogAttributeGroup[]
  sellers: CatalogSellerCompany[]
  warehouses: CatalogActiveWarehouse[]
  warehousesLoading?: boolean
  warehousesErrorMessage?: string
  bodyColorOptions: CatalogColorSelectItem[]
  interiorColorOptions: CatalogColorSelectItem[]
  modelsLoading: boolean
  modificationsLoading: boolean
  selectedModification: CatalogModification | null
  selectedProductTrimAttributes: CatalogTrimAttributeAssignment[]
  selectedProductTrimAttributesLoading?: boolean
  selectedProductTrimAttributesErrorMessage?: string
  trims: CatalogTrimLifecycleItem[]
  trimsLoading?: boolean
  trimRequired?: boolean
  trimAttributeCandidateGroups: CatalogTrimAttributeCandidateGroup[]
  trimAttributeCandidatesLoading?: boolean
  trimAttributeCandidatesErrorMessage?: string
  attributesLoading?: boolean
  attributesErrorMessage?: string
  units?: CatalogUnit[]
  errorMessage?: string
}>()
const MAX_CARD_ATTRIBUTES = 6
const emit = defineEmits<{
  'update:modelValue': [value: CatalogDraft]
  'mark-change': [markId: UUID | null]
  'model-change': [modelId: UUID | null]
  'modification-change': [modificationId: UUID | null]
  'trim-change': [trimId: UUID | null]
  'trim-candidates-retry': [modificationId: UUID | null]
  'retry-attributes': []
  'retry-warehouses': []
}>()

const api = createCatalogCorrectionApi(useRuntimeConfig())
const draft = computed(() => props.modelValue)
const sellerOptions = computed<CatalogNamedRef[]>(() => props.sellers.map(seller => ({
  id: seller.id,
  name: seller.name,
  ...(seller.inn ? { code: `ИНН ${seller.inn}` } : {}),
})))
const warehouseOwnerMessage = ref('')
const warehouseOwnerConflictMessage = computed(() =>
  productWarehouseConflictMessage(props.warehouses ?? []))
const warehouseOptions = computed<CatalogNamedRef[]>(() => (props.warehouses ?? [])
  .filter(warehouse => productWarehouseOwner(warehouse).kind !== 'conflict')
  .map(warehouse => ({
    id: warehouse.id,
    name: warehouse.address,
    code: [warehouse.brand, warehouse.city_name].filter(Boolean).join(' · ') || undefined,
  })))
const trimOptions = computed<CatalogNamedRef[]>(() => props.trims.map(trim => ({
  id: trim.id,
  name: trim.name,
  is_active: trim.is_active,
})))
const unitOptions = computed<CatalogNamedRef[]>(() =>
  (props.units ?? [])
    .filter(u => u.is_active || u.id === draft.value.unit_id)
    .map(u => ({
      id: u.id,
      name: `${u.name} (${u.code})`,
      code: u.code,
    }))
)
const changeAttributeUnit = (unitId: UUID | string | null) => {
  const selected = (props.units ?? []).find(u => u.id === unitId)
  emit('update:modelValue', {
    ...draft.value,
    unit_id: (unitId as UUID) || null,
    unit: selected?.name ?? null,
  })
}

const currentColorRef = (field: 'body_color' | 'interior_color'): CatalogNamedRef | null => {
  const value = draft.value[field]
  return value && typeof value === 'object' && 'id' in value && 'name' in value
    ? value as CatalogNamedRef
    : null
}
const colorOptions = (
  options: CatalogColorSelectItem[],
  current: CatalogNamedRef | null,
): CatalogNamedRef[] => {
  const active = options.map(item => ({ id: item.id, name: item.name }))
  if (!current || current.is_active !== false || active.some(item => item.id === current.id)) return active
  return [{ id: current.id, name: `${current.name} · Неактивен`, is_active: false }, ...active]
}
const bodyColorSelectOptions = computed<CatalogNamedRef[]>(() =>
  colorOptions(props.bodyColorOptions, currentColorRef('body_color')))
const interiorColorSelectOptions = computed<CatalogNamedRef[]>(() =>
  colorOptions(props.interiorColorOptions, currentColorRef('interior_color')))
const inactiveBodyColorLabel = computed(() => {
  const color = currentColorRef('body_color')
  return color?.is_active === false ? color.name : ''
})
const inactiveInteriorColorLabel = computed(() => {
  const color = currentColorRef('interior_color')
  return color?.is_active === false ? color.name : ''
})
const codeManuallyEdited = ref(false)
const supportsActivity = computed(() => props.entity !== 'products')
const text = (key: string): string => {
  const value = draft.value[key]
  return typeof value === 'string' ? value : ''
}
const specialPriceError = computed(() => {
  if (props.entity !== 'products' || !text('special_price').trim()) return ''
  const specialPrice = normalizeCatalogPrice(draft.value.special_price)
  if (specialPrice === null) return 'Укажите корректную специальную цену.'
  const basePrice = normalizeCatalogPrice(draft.value.price)
  if (basePrice === null) return 'Сначала укажите обычную цену.'
  return Number(specialPrice) >= Number(basePrice)
    ? 'Специальная цена должна быть ниже обычной.'
    : ''
})
const priceOnRequest = computed(() => props.entity === 'products' && boolValue('price_on_request'))
const priceModeLocked = computed(() => props.entity === 'products'
  && props.mode === 'edit'
  && draft.value.published_at !== null
  && draft.value.published_at !== undefined)
const priceFromError = computed(() => {
  if (!priceOnRequest.value) return ''
  if (!text('price_from').trim()) return ''
  const priceFrom = normalizeCatalogPrice(draft.value.price_from)
  return priceFrom !== null && Number(priceFrom) > 0
    ? ''
    : 'Укажите положительную нижнюю границу стоимости.'
})
const bool = (key: string): boolean => draft.value[key] !== false
const boolValue = (key: string): boolean => draft.value[key] === true
const uuidValue = (key: string): UUID | '' => {
  const value = draft.value[key]
  return typeof value === 'string' ? value as UUID | '' : ''
}
const numberValue = (key: string, fallback = 0): number => {
  const value = draft.value[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}
const nullableNumber = (key: string): string | number => {
  const value = draft.value[key]
  return typeof value === 'number' ? value : ''
}
const uuidArray = (key: string): UUID[] => Array.isArray(draft.value[key])
  ? draft.value[key] as UUID[]
  : []
const productId = computed<UUID | null>(() => {
  const value = draft.value.id
  return typeof value === 'string' && isUuid(value) ? value : null
})
const inactiveProductCategoryIds = computed<UUID[]>(() => props.categories
  .filter(category => category.is_active === false)
  .map(category => category.id))

const attachmentCategoryAllowedIds = computed<UUID[]>(() => {
  const attachmentIds = props.categories
    .filter(c => categoryIsInAttachmentBranch(c.id, props.categories) || c.is_attachment_category)
    .map(c => c.id)
  return attachmentIds.length > 0 ? attachmentIds : props.categories.map(c => c.id)
})

const modelCategoryOptions = computed<CatalogNamedRef[]>(() => {
  const currentCatId = uuidValue('category_id')
  return props.categories
    .filter(c => c.is_active !== false || c.id === currentCatId)
    .map(c => ({
      id: c.id,
      name: c.is_active === false ? `${c.name} · Неактивна` : c.name,
      code: c.code,
    }))
})

const attachmentLinks = computed<CatalogProductAttachmentLink[]>(() =>
  Array.isArray(draft.value.compatible_attachments)
    ? draft.value.compatible_attachments as CatalogProductAttachmentLink[]
    : [])
const productCreationKind = computed<'vehicle' | 'attachment'>(() =>
  draft.value.creation_kind === 'attachment' ? 'attachment' : 'vehicle')
const attachmentCreateMode = computed<'standalone' | 'kit'>(() =>
  draft.value.attachment_create_mode === 'kit' ? 'kit' : 'standalone')
const isKitDraft = computed(() => props.entity === 'products'
  && props.mode === 'create'
  && productCreationKind.value === 'attachment'
  && attachmentCreateMode.value === 'kit')
const isKit = computed(() => props.entity === 'products'
  && (isKitDraft.value || (props.mode === 'edit' && (Boolean(draft.value.model_id && draft.value.superstructure_id) || Boolean(draft.value.is_kit)))))

const isStandaloneAttachment = computed(() =>
  props.entity === 'products'
  && !isKit.value
  && (
    (productCreationKind.value === 'attachment' && attachmentCreateMode.value === 'standalone')
    || (props.mode === 'edit' && Boolean(draft.value.is_attachment || (draft.value.superstructure_id && !draft.value.model_id)))
  )
)

const productCategoryAllowedIds = computed<UUID[]>(() => {
  if (isStandaloneAttachment.value) {
    if (uuidValue('superstructure_id')) {
      const sType = selectedSuperstructureType.value
      const typeCats = sType?.category_ids ?? []
      if (typeCats.length > 0) {
        return [...new Set([...typeCats, ...uuidArray('category_ids')])]
      }
    }
    return attachmentCategoryAllowedIds.value
  }
  return [
    ...new Set([
      ...productSelectableCategoryIds(props.categories),
      ...uuidArray('category_ids'),
    ]),
  ]
})
const warehouseRequired = computed(() => !boolValue('no_vin')
  && text('sale_status') === 'available')
const showsCompatibleAttachments = computed(() =>
  !isKit.value && !boolValue('is_attachment') && !uuidValue('superstructure_id'))
const set = (key: string, value: unknown) => emit('update:modelValue', { ...draft.value, [key]: value })
const inputValue = (event: Event): string => {
  const input = event.currentTarget
  return input instanceof HTMLInputElement || input instanceof HTMLSelectElement || input instanceof HTMLTextAreaElement
    ? input.value
    : ''
}
const checkedValue = (event: Event): boolean => {
  const input = event.currentTarget
  return input instanceof HTMLInputElement ? input.checked : false
}
const setText = (key: string, event: Event) => set(key, inputValue(event))
const setCode = (event: Event) => {
  if (props.mode === 'create') codeManuallyEdited.value = true
  setText('code', event)
}
const setNumber = (key: string, event: Event) =>
  set(key, normalizeCatalogInteger(inputValue(event)) ?? 0)
const setNullableInteger = (
  key: string,
  event: Event,
  min = 0,
  max = 9007199254740991,
) => {
  const value = inputValue(event)
  set(key, value === '' ? null : normalizeCatalogInteger(value, { min, max }))
}
type CatalogYearKey = 'year_from' | 'year_to' | 'manufacture_year'
const touchedYears = reactive<Record<CatalogYearKey, boolean>>({
  year_from: false,
  year_to: false,
  manufacture_year: false,
})
const yearDraft = (key: CatalogYearKey): string => catalogYearDraft(draft.value[key])
const yearError = (key: CatalogYearKey): string => touchedYears[key]
  ? catalogYearDraftError(draft.value[key])
  : ''
const setYearDraft = (key: CatalogYearKey, event: Event) => set(key, inputValue(event))
const blurYear = (key: CatalogYearKey) => { touchedYears[key] = true }
const stepYear = (key: CatalogYearKey, direction: -1 | 1) => {
  touchedYears[key] = true
  set(key, stepCatalogYearDraft(draft.value[key], direction))
}
const changeProductCreationKind = (kind: 'vehicle' | 'attachment') => {
  emit('update:modelValue', {
    ...draft.value,
    creation_kind: kind,
    attachment_create_mode: kind === 'attachment' ? 'standalone' : null,
    is_attachment: kind === 'attachment',
    compatible_attachments: kind === 'vehicle' ? draft.value.compatible_attachments : [],
    components: [],
  })
}
const changeAttachmentCreateMode = (mode: 'standalone' | 'kit') => {
  emit('update:modelValue', {
    ...draft.value,
    creation_kind: 'attachment',
    attachment_create_mode: mode,
    is_attachment: true,
    compatible_attachments: [],
    components: mode === 'kit' ? draft.value.components : [],
  })
}
const setName = (event: Event) => {
  const name = inputValue(event)
  const next = {
    ...draft.value,
    name,
    code: syncSuggestedCatalogCode({
      mode: props.mode,
      currentName: text('name'),
      currentCode: text('code'),
      nextName: name,
      codeManuallyEdited: codeManuallyEdited.value,
    }),
  }
  emit('update:modelValue', next)
}
const changeMark = (markId: UUID | null) => {
  const value = markId ?? ''
  emit('update:modelValue', {
    ...draft.value,
    selected_mark_id: value,
    selected_model_id: '',
    model_id: props.entity === 'modifications' ? '' : draft.value.model_id,
    modification_id: props.entity === 'products' || props.entity === 'trims' ? '' : draft.value.modification_id,
    trim_id: props.entity === 'products' ? '' : draft.value.trim_id,
    trim_attributes: props.entity === 'trims' ? [] : draft.value.trim_attributes,
    trim_attribute_values: props.entity === 'trims' ? [] : draft.value.trim_attribute_values,
    category_ids: props.entity === 'products' ? [] : draft.value.category_ids,
    ...(props.entity === 'products' && props.mode === 'create' && !codeManuallyEdited.value
      ? { code: '' }
      : {}),
  })
  if (props.entity === 'products' || props.entity === 'trims') emit('modification-change', null)
  emit('mark-change', value || null)
}
const changeModel = (modelId: UUID | null) => {
  const value = modelId ?? ''
  const selected = props.models.find(item => item.id === value)
  let nextCategoryIds = props.entity === 'products' ? [] : draft.value.category_ids
  if (props.entity === 'modifications' && selected?.category_id) {
    nextCategoryIds = [selected.category_id]
  }
  emit('update:modelValue', {
    ...draft.value,
    selected_model_id: value,
    model_id: props.entity === 'modifications' ? value : draft.value.model_id,
    modification_id: props.entity === 'products' || props.entity === 'trims' ? '' : draft.value.modification_id,
    trim_id: props.entity === 'products' ? '' : draft.value.trim_id,
    trim_attributes: props.entity === 'trims' ? [] : draft.value.trim_attributes,
    trim_attribute_values: props.entity === 'trims' ? [] : draft.value.trim_attribute_values,
    category_ids: nextCategoryIds,
    ...(props.entity === 'products' && props.mode === 'create' && !codeManuallyEdited.value
      ? { code: '' }
      : {}),
  })
  if (props.entity === 'products' || props.entity === 'trims') emit('modification-change', null)
  emit('model-change', value || null)
}
const changeModification = (modificationId: UUID | null) => {
  const value = modificationId ?? ''
  const selected = props.modifications.find(item => item.id === value)
  const previous = props.modifications.find(item => item.id === uuidValue('modification_id'))
  const next = {
    ...draft.value,
    modification_id: value,
    trim_id: props.entity === 'products' ? '' : draft.value.trim_id,
    trim_attributes: props.entity === 'trims' ? [] : draft.value.trim_attributes,
    trim_attribute_values: props.entity === 'trims' ? [] : draft.value.trim_attribute_values,
    category_ids: props.entity === 'products'
      ? replaceProductCategoryDefaults(uuidArray('category_ids'), previous, selected)
      : draft.value.category_ids,
  }
  if (props.entity === 'products' && props.mode === 'create' && !codeManuallyEdited.value) {
    next.code = selected ? suggestCatalogCode(selected.code) : ''
  }
  emit('update:modelValue', next)
  emit('modification-change', value || null)
}
const changeTrim = (trimId: UUID | null) => {
  set('trim_id', trimId ?? '')
  emit('trim-change', trimId)
}
const selectedProductTrimSpecs = computed(() => props.selectedProductTrimAttributes.map(assignment =>
  presentProductTrimAttribute(
    assignment,
    props.attributes.find(attribute => attribute.id === assignment.attribute_id),
  )))
const trimAttributeCandidateById = computed(() => {
  const items = new Map<UUID, CatalogTrimAttributeCandidateGroup['attributes'][number]>()
  for (const group of props.trimAttributeCandidateGroups) {
    for (const attribute of group.attributes) items.set(attribute.attribute_id, attribute)
  }
  return items
})
const trimAttributes = computed<CatalogTrimAttributeAssignment[]>(() => {
  const assignments = Array.isArray(draft.value.trim_attributes)
    ? draft.value.trim_attributes as CatalogTrimAttributeAssignment[]
    : []
  return assignments.map((assignment) => {
    const candidate = trimAttributeCandidateById.value.get(assignment.attribute_id)
    return candidate
      ? {
          ...assignment,
          attribute_code: assignment.attribute_code ?? candidate.attribute_code,
          attribute_name: assignment.attribute_name ?? candidate.attribute_name,
          data_type: assignment.data_type ?? candidate.data_type,
          options: assignment.options ?? candidate.options,
          unit: assignment.unit ?? candidate.unit,
        }
      : assignment
  })
})
const trimAttributeValues = computed<CatalogTrimAttributeValue[]>(() =>
  Array.isArray(draft.value.trim_attribute_values)
    ? draft.value.trim_attribute_values as CatalogTrimAttributeValue[]
    : [])
const replaceTrimAttributes = (items: CatalogTrimAttributeAssignment[]) => {
  const selectedAttributeIds = new Set(items.map(item => item.attribute_id))
  emit('update:modelValue', {
    ...draft.value,
    trim_attributes: items,
    trim_attribute_values: trimAttributeValues.value.filter(
      item => selectedAttributeIds.has(item.attribute_id),
    ),
  })
}
const trimAttributeValue = (attributeId: UUID): CatalogTrimAttributeValue | undefined =>
  trimAttributeValues.value.find(item => item.attribute_id === attributeId)
const emptyTrimAttributeValue = (attributeId: UUID): CatalogTrimAttributeValue => ({
  attribute_id: attributeId,
  value_number: null,
  value_text: null,
  value_boolean: null,
  option_id: null,
})
const replaceTrimAttributeValues = (items: CatalogTrimAttributeValue[]) =>
  set('trim_attribute_values', items)
const setTrimAttributeValue = (
  attributeId: UUID,
  patch: Partial<Omit<CatalogTrimAttributeValue, 'attribute_id'>>,
) => {
  const nextValue = {
    ...emptyTrimAttributeValue(attributeId),
    ...patch,
  }
  const hasValue = nextValue.value_number !== null
    || (typeof nextValue.value_text === 'string' && nextValue.value_text.trim().length > 0)
    || nextValue.value_boolean !== null
    || nextValue.option_id !== null
  const rest = trimAttributeValues.value.filter(item => item.attribute_id !== attributeId)
  replaceTrimAttributeValues(hasValue ? [...rest, nextValue] : rest)
}
const trimOptionValue = (attributeId: UUID): UUID | '' =>
  trimAttributeValue(attributeId)?.option_id ?? ''
const trimScalarValue = (attributeId: UUID): string | number => {
  const value = trimAttributeValue(attributeId)
  return value?.value_number ?? value?.value_text ?? ''
}
const trimBooleanValue = (event: Event): boolean | null => {
  const value = inputValue(event)
  return value === '' ? null : value === 'true'
}
const trimAttributeOptions = (link: CatalogTrimAttributeAssignment): CatalogNamedRef[] =>
  (link.options ?? []).map(option => ({
    id: option.id,
    name: option.name,
    code: option.code,
    is_active: option.is_active,
  }))
const patchTrimAttribute = (index: number, key: keyof CatalogTrimAttributeAssignment, value: unknown) => {
  replaceTrimAttributes(trimAttributes.value.map((item, position) =>
    position === index ? { ...item, [key]: value } : item))
}
const removeTrimAttribute = (index: number) =>
  replaceTrimAttributes(trimAttributes.value.filter((_, position) => position !== index))
const trimGroupName = (groupId: UUID | null): string =>
  props.trimAttributeCandidateGroups.find(group => group.group_id === groupId)?.group_name
  ?? props.groups.find(group => group.id === groupId)?.name
  ?? 'Прочие'


const categoryParentDisabledIds = computed<UUID[]>(() => {
  if (!draft.value.id) return []
  return [
    draft.value.id,
    ...categoryDescendantIds(props.categories, draft.value.id),
  ]
})

const categoryLinks = computed<CatalogCategoryAttributeLink[]>(() =>
  Array.isArray(draft.value.attribute_links)
    ? draft.value.attribute_links as CatalogCategoryAttributeLink[]
    : [])
const inheritedCategoryLinks = computed<CatalogCategoryAttributeLink[]>(() => {
  const directIds = new Set(categoryLinks.value.map(link => link.attribute_id))
  const inherited = new Map<UUID, CatalogCategoryAttributeLink>()
  const categoriesById = new Map(props.categories.map(category => [category.id, category]))
  const visited = new Set<UUID>()
  const isAttachment = (id: UUID) => categoryIsInAttachmentBranch(id, props.categories)
  const currentIsInAttachmentBranch = Boolean(draft.value.is_attachment_category)
    || uuidArray('parent_ids').some(parentId => isAttachment(parentId))
  const collect = (categoryId: UUID, childIsInAttachment: boolean) => {
    if (visited.has(categoryId)) return
    visited.add(categoryId)
    const category = categoriesById.get(categoryId)
    if (!category) return
    const categoryIsAtt = isAttachment(categoryId)
    if (childIsInAttachment && !categoryIsAtt) return
    if (category.effective_attribute_links?.length) {
      for (const link of category.effective_attribute_links) {
        if (!inherited.has(link.attribute_id)) {
          inherited.set(link.attribute_id, { ...link, inherited: true })
        }
      }
      return
    }
    for (const link of category.attribute_links ?? []) {
      if (!inherited.has(link.attribute_id)) inherited.set(link.attribute_id, { ...link, inherited: true })
    }
    for (const parentId of category.parent_ids) collect(parentId, categoryIsAtt)
  }
  for (const parentId of uuidArray('parent_ids')) collect(parentId, currentIsInAttachmentBranch)
  return [...inherited.values()]
    .filter(link => !directIds.has(link.attribute_id))
    .sort((left, right) => left.sort_order - right.sort_order)
})
const visibleCardAttributeCount = computed(() => {
  const effective = new Map<UUID, CatalogCategoryAttributeLink>()
  for (const link of inheritedCategoryLinks.value) effective.set(link.attribute_id, link)
  for (const link of categoryLinks.value) effective.set(link.attribute_id, link)
  return [...effective.values()].filter(link => link.is_visible).length
})
const canEnableCategoryLinkCard = (index: number): boolean =>
  categoryLinks.value[index]?.is_visible === true
  || visibleCardAttributeCount.value < MAX_CARD_ATTRIBUTES
const replaceCategoryLinks = (links: CatalogCategoryAttributeLink[]) => set('attribute_links', links)
const patchCategoryLink = (index: number, key: keyof CatalogCategoryAttributeLink, value: unknown) => {
  if (key === 'is_visible' && value === true && !canEnableCategoryLinkCard(index)) return
  replaceCategoryLinks(categoryLinks.value.map((link, position) =>
    position === index ? { ...link, [key]: value } : link))
}
const setCategoryLinkSortOrder = (index: number, event: Event) =>
  patchCategoryLink(index, 'sort_order', normalizeCatalogInteger(inputValue(event)) ?? 0)
const removeCategoryLink = (index: number) =>
  replaceCategoryLinks(categoryLinks.value.filter((_, position) => position !== index))
const categoryLinkAttribute = (link: CatalogCategoryAttributeLink) =>
  props.attributes.find(attribute => attribute.id === link.attribute_id)
const effectiveCategoryLinkGroupId = (link: CatalogCategoryAttributeLink): UUID | null => {
  if (link.group_id) return link.group_id
  const attribute = categoryLinkAttribute(link)
  return attribute?.attribute_group_id || null
}
const categoryLinkGroupName = (link: CatalogCategoryAttributeLink): string => {
  const groupId = effectiveCategoryLinkGroupId(link)
  return props.groups.find(group => group.id === groupId)?.name ?? 'Прочие'
}
const categoryLinkInheritedGroupLabel = (link: CatalogCategoryAttributeLink): string => {
  const attribute = categoryLinkAttribute(link)
  const group = props.groups.find(item => item.id === attribute?.attribute_group_id)
  return `Наследовать: ${group?.name ?? 'Прочие'}`
}
const changeCategoryLinkGroup = (index: number, groupId: UUID | null) =>
  patchCategoryLink(index, 'group_id', groupId)
const applyCategoryAttributes = (attributeIds: UUID[]) =>
  replaceCategoryLinks(appendCategoryAttributeLinks(categoryLinks.value, attributeIds))

const modificationValues = computed<CatalogModificationValue[]>(() =>
  Array.isArray(draft.value.attribute_values)
    ? draft.value.attribute_values as CatalogModificationValue[]
    : [])
const modificationValue = (attributeId: UUID) =>
  modificationValues.value.find(value => value.attribute_id === attributeId)?.option_id
  ?? modificationValues.value.find(value => value.attribute_id === attributeId)?.value
  ?? ''
const modificationOptionValue = (attributeId: UUID): UUID | '' => {
  const value = modificationValue(attributeId)
  return typeof value === 'string' && isUuid(value) ? value : ''
}
const modificationAttributeOptions = (attribute: CatalogAttribute): CatalogNamedRef[] =>
  attribute.options.flatMap(option => option.id
    ? [{ id: option.id, name: option.name, code: option.code, is_active: option.is_active }]
    : [])
const setModificationValue = (attributeId: UUID, value: unknown) => {
  const withoutCurrent = modificationValues.value.filter(item => item.attribute_id !== attributeId)
  const attribute = props.attributes.find(item => item.id === attributeId)
  const normalizedValue = value
  const entry = attribute?.data_type === 'select'
    ? { attribute_id: attributeId, option_id: value as UUID }
    : { attribute_id: attributeId, value: normalizedValue as string | number | boolean }
  set('attribute_values', value === '' || value === null
    ? withoutCurrent
    : [...withoutCurrent, entry])
}
const booleanSelectValue = (event: Event): boolean | '' => {
  const value = inputValue(event)
  return value === '' ? '' : value === 'true'
}
const nullableBooleanSelectValue = (event: Event): boolean | null => {
  const val = booleanSelectValue(event)
  return typeof val === 'boolean' ? val : null
}

const modificationAttributesForCategories = (categoryIds: UUID[]): CatalogAttribute[] => {
  return buildModificationAttributeGroups({
    categoryIds,
    categories: props.categories,
    attributes: props.attributes,
  }).flatMap(group => group.fields.map(field => field.attribute))
}
const modificationAttributeGroups = computed(() => buildModificationAttributeGroups({
  categoryIds: uuidArray('category_ids'),
  categories: props.categories,
  attributes: props.attributes,
}))
const modificationAttributes = computed<CatalogAttribute[]>(() =>
  modificationAttributeGroups.value.flatMap(group => group.fields.map(field => field.attribute)))
type PendingModificationCategoryChange = {
  categoryIds: UUID[]
  values: CatalogModificationValue[]
  removedValues: CatalogModificationValue[]
}
type CategoryPickerInstance = { focusTrigger: () => void }
const modificationCategoryPicker = ref<CategoryPickerInstance | null>(null)
const pendingModificationCategoryChange = ref<PendingModificationCategoryChange | null>(null)
const focusModificationCategoryPicker = () => modificationCategoryPicker.value?.focusTrigger()
const pendingRemovedAttributeNames = computed(() =>
  pendingModificationCategoryChange.value?.removedValues.map((value) =>
    props.attributes.find(attribute => attribute.id === value.attribute_id)?.name
      ?? value.attribute_id) ?? [])
const applyModificationCategoryChange = (
  categoryIds: UUID[],
  values: CatalogModificationValue[],
) => emit('update:modelValue', {
  ...draft.value,
  category_ids: categoryIds,
  attribute_values: values,
})
const changeModificationCategories = (categoryIds: UUID[]) => {
  const allowed = new Set(
    modificationAttributesForCategories(categoryIds).map(attribute => attribute.id),
  )
  const values = modificationValues.value.filter(value => allowed.has(value.attribute_id))
  const removedValues = modificationValues.value.filter(value => !allowed.has(value.attribute_id))
  if (removedValues.length > 0) {
    pendingModificationCategoryChange.value = { categoryIds, values, removedValues }
    return
  }
  applyModificationCategoryChange(categoryIds, values)
}
const cancelModificationCategoryChange = () => {
  pendingModificationCategoryChange.value = null
}
const confirmModificationCategoryChange = () => {
  const pending = pendingModificationCategoryChange.value
  if (!pending) return
  applyModificationCategoryChange(pending.categoryIds, pending.values)
  pendingModificationCategoryChange.value = null
}
const selectedModificationCategories = computed(() =>
  uuidArray('category_ids').flatMap(categoryId => {
    const category = props.categories.find(item => item.id === categoryId)
    return category ? [category] : []
  }))
const moveModificationCategory = (index: number, direction: -1 | 1) => {
  const categoryIds = [...uuidArray('category_ids')]
  const target = index + direction
  if (index < 0 || target < 0 || target >= categoryIds.length) return
  ;[categoryIds[index], categoryIds[target]] = [categoryIds[target]!, categoryIds[index]!]
  set('category_ids', categoryIds)
}
watch(
  () => modificationAttributes.value.map(item => item.id).join('|'),
  () => {
    if (props.entity !== 'modifications' || pendingModificationCategoryChange.value) return
    changeModificationCategories(uuidArray('category_ids'))
  },
)

const groupAttributeSearch = ref('')
const filteredGroupAttributes = computed(() => {
  const search = groupAttributeSearch.value.toLocaleLowerCase('ru-RU')
  return props.attributes.filter(attribute =>
    !search || attribute.name.toLocaleLowerCase('ru-RU').includes(search))
})
const toggleGroupAttribute = (attributeId: UUID) => {
  const selected = new Set(uuidArray('attribute_ids'))
  if (selected.has(attributeId)) selected.delete(attributeId)
  else selected.add(attributeId)
  set('attribute_ids', [...selected])
}

const attributeOptions = computed<CatalogAttributeOption[]>(() =>
  Array.isArray(draft.value.options)
    ? draft.value.options as CatalogAttributeOption[]
    : [])
const optionFieldInvalid = (
  option: CatalogAttributeOption,
  field: 'code' | 'name',
): boolean => isCatalogAttributeOptionFieldInvalid(option, field)
const replaceOptions = (options: CatalogAttributeOption[]) => set('options', options)
const addOption = () => replaceOptions([
  ...attributeOptions.value,
  {
    code: '',
    name: '',
    sort_order: attributeOptions.value.length * 10,
    is_active: true,
  },
])
const patchOption = (index: number, key: 'code' | 'name', value: string) =>
  replaceOptions(attributeOptions.value.map((option, position) =>
    position === index ? patchCatalogAttributeOption(option, key, value) : option))
const removeOption = (index: number) =>
  replaceOptions(attributeOptions.value.filter((_, position) => position !== index))

const attributeFilterKindLabels: Record<CatalogFilterKind, string> = {
  exact: 'Точное совпадение',
  range: 'Диапазон',
  search: 'Поиск по тексту',
}
const compatibleAttributeFilterKinds = computed(() =>
  catalogAttributeFilterKinds(draft.value.data_type))
const attributeFilterCompatible = computed(() =>
  props.entity !== 'attributes'
  || isCatalogAttributeFilterCompatible(draft.value.data_type, draft.value.filter_kind))
const attributeFilterKindLabel = (filterKind: CatalogFilterKind): string =>
  attributeFilterKindLabels[filterKind]
const pendingAttributeDataType = ref<CatalogDataType | null>(null)
const pendingAttributeConversionDescription = computed(() =>
  text('data_type') === 'text' && pendingAttributeDataType.value === 'select'
    ? 'Существующие непустые текстовые значения будут преобразованы сервером в варианты выбора одной транзакцией.'
    : 'Сервер проверит существующие значения. Несовместимое преобразование будет отклонено без потери данных.')
const applyAttributeDataType = (dataType: CatalogDataType, confirmed: boolean) => {
  const compatible = catalogAttributeFilterKinds(dataType)
  const currentFilterKind = draft.value.filter_kind
  emit('update:modelValue', {
    ...draft.value,
    data_type: dataType,
    confirm_type_conversion: confirmed,
    filter_kind: isCatalogAttributeFilterCompatible(dataType, currentFilterKind)
      ? currentFilterKind
      : compatible[0] ?? 'exact',
  })
}
const changeAttributeDataType = (event: Event) => {
  const dataType = inputValue(event) as CatalogDataType
  if (props.mode === 'edit' && dataType !== text('data_type')) {
    pendingAttributeDataType.value = dataType
    const select = event.currentTarget
    if (select instanceof HTMLSelectElement) select.value = text('data_type')
    return
  }
  applyAttributeDataType(dataType, false)
}
const cancelAttributeDataTypeChange = () => { pendingAttributeDataType.value = null }
const confirmAttributeDataTypeChange = () => {
  const dataType = pendingAttributeDataType.value
  if (!dataType) return
  pendingAttributeDataType.value = null
  applyAttributeDataType(dataType, true)
}

const selectedCategoryMetrics = computed(() => new Set(
  props.categories
    .filter(category => uuidArray('category_ids').includes(category.id))
    .map(category => category.usage_metric),
))
const usageMetricConflict = computed(() => selectedCategoryMetrics.value.size > 1)
const selectedUsageMetric = computed(() =>
  selectedCategoryMetrics.value.size === 1
    ? [...selectedCategoryMetrics.value][0]
    : null)
const changeCondition = (condition: 'new' | 'used') => {
  emit('update:modelValue', {
    ...draft.value,
    condition,
    owners_count: condition === 'new' ? null : draft.value.owners_count,
    mileage_km: condition === 'new' ? null : draft.value.mileage_km,
    engine_hours: condition === 'new' ? null : draft.value.engine_hours,
  })
}
const changeNoVin = (event: Event) => {
  const noVin = checkedValue(event)
  emit('update:modelValue', {
    ...draft.value,
    no_vin: noVin,
    vin: noVin ? '' : draft.value.vin,
    chassis_vin: noVin ? '' : draft.value.chassis_vin,
    superstructure_vin: noVin ? '' : draft.value.superstructure_vin,
    warehouse_id: noVin ? '' : draft.value.warehouse_id,
    warehouse_id_touched: noVin ? true : draft.value.warehouse_id_touched,
  })
}
const changeSeller = (sellerCompanyId: UUID | null) => {
  const change = applyProductSellerSelection(draft.value, sellerCompanyId, props.warehouses ?? [])
  warehouseOwnerMessage.value = change.message
  emit('update:modelValue', change.draft)
}
const changeWarehouse = (warehouseId: UUID | null) => {
  const warehouse = (props.warehouses ?? []).find(item => item.id === warehouseId) ?? null
  const change = applyProductWarehouseSelection(draft.value, warehouse)
  warehouseOwnerMessage.value = change.message
  emit('update:modelValue', change.draft)
}

// --- Superstructures directory ---
const superstructureAttributes = computed<CatalogSuperstructureAttribute[]>(() =>
  Array.isArray(draft.value.attributes)
    ? draft.value.attributes as CatalogSuperstructureAttribute[]
    : [])
// --- Kit Confirmation Dialog ---
interface PendingKitConfirm {
  title: string
  message: string
  items?: string[]
  onConfirm: () => void
}
const pendingKitConfirm = ref<PendingKitConfirm | null>(null)
const cancelKitConfirm = () => { pendingKitConfirm.value = null }
const confirmKitConfirm = () => {
  if (pendingKitConfirm.value) {
    pendingKitConfirm.value.onConfirm()
    pendingKitConfirm.value = null
  }
}

// --- Block 1. Kit Chassis ---
const kitChassisCategoryIds = ref<UUID[]>([])

const selectedChassisModel = computed<CatalogModel | undefined>(() => {
  const modelId = uuidValue('model_id')
  if (!modelId) {
    const draftModel = draft.value.model
    if (draftModel && typeof draftModel === 'object') {
      return draftModel as CatalogModel
    }
    return undefined
  }
  return props.models.find(m => m.id === modelId)
    ?? (draft.value.model && typeof draft.value.model === 'object' ? draft.value.model as CatalogModel : undefined)
})

const chassisAllowedCategoryIds = computed<UUID[]>(() =>
  props.categories
    .filter(c => !categoryIsInAttachmentBranch(c.id, props.categories))
    .map(c => c.id))

const chassisAttributeGroups = computed(() => {
  const targetCatId = selectedChassisModel.value?.category_id
    || (!selectedChassisModel.value ? kitChassisCategoryIds.value[0] : null)
    || null
  return buildModificationAttributeGroups({
    categoryIds: targetCatId ? [targetCatId] : [],
    categories: props.categories,
    attributes: props.attributes,
  })
})

const chassisValues = computed<CatalogProductChassisValue[]>(() =>
  Array.isArray(draft.value.chassis_values)
    ? draft.value.chassis_values as CatalogProductChassisValue[]
    : [])

const chassisValue = (attributeId: UUID): CatalogProductChassisValue | undefined =>
  chassisValues.value.find(v => v.attribute_id === attributeId)

const chassisOptionValue = (attributeId: UUID): UUID | '' =>
  chassisValue(attributeId)?.option_id ?? ''

const setChassisValue = (
  attributeId: UUID,
  patch: Partial<Omit<CatalogProductChassisValue, 'attribute_id'>>,
) => {
  const current = chassisValue(attributeId) ?? {
    attribute_id: attributeId,
    value_number: null,
    value_text: null,
    value_boolean: null,
    option_id: null,
  }
  const nextValue: CatalogProductChassisValue = {
    ...current,
    ...patch,
  }
  const hasValue = nextValue.value_number !== null
    || (typeof nextValue.value_text === 'string' && nextValue.value_text.trim().length > 0)
    || nextValue.value_boolean !== null
    || nextValue.option_id !== null
  const rest = chassisValues.value.filter(v => v.attribute_id !== attributeId)
  set('chassis_values', hasValue ? [...rest, nextValue] : rest)
}

const changeKitChassisCategories = (categoryIds: UUID[]) => {
  kitChassisCategoryIds.value = categoryIds
  void loadKitCategoryMarks()
}

const kitCategoryMarks = ref<CatalogMark[]>([])
const kitCategoryMarksLoading = ref(false)

const loadKitCategoryMarks = async () => {
  const catIds = kitChassisCategoryIds.value
  if (!catIds.length) {
    kitCategoryMarks.value = []
    return
  }
  kitCategoryMarksLoading.value = true
  try {
    const lists = await Promise.all(
      catIds.map(catId => api.listAll<CatalogMark>('marks', { category_id: catId }))
    )
    const combined = lists.flat()
    const seen = new Set<UUID>()
    kitCategoryMarks.value = combined.filter(m => {
      if (seen.has(m.id)) return false
      seen.add(m.id)
      return true
    })
  } catch {
    kitCategoryMarks.value = []
  } finally {
    kitCategoryMarksLoading.value = false
  }
}

const kitChassisMarks = computed<CatalogNamedRef[]>(() => {
  const catIds = kitChassisCategoryIds.value
  const currentMarkId = uuidValue('selected_mark_id')
  if (catIds.length === 0) {
    return props.marks
  }
  if (kitCategoryMarks.value.length > 0) {
    const list = kitCategoryMarks.value.map(m => ({ id: m.id, name: m.name, code: m.code }))
    if (currentMarkId && !list.some(m => m.id === currentMarkId)) {
      const cur = props.marks.find(m => m.id === currentMarkId)
      if (cur) list.unshift(cur)
    }
    return list
  }
  return props.marks
})

const kitChassisModels = computed<CatalogNamedRef[]>(() => {
  const catIds = new Set(kitChassisCategoryIds.value)
  const currentModelId = uuidValue('model_id')
  if (catIds.size === 0) {
    return props.models.map(m => ({ id: m.id, name: m.name, code: m.code }))
  }
  return props.models
    .filter(m => m.id === currentModelId || (m.category_id && catIds.has(m.category_id)))
    .map(m => ({ id: m.id, name: m.name, code: m.code }))
})

const changeKitChassisMark = (markId: UUID | null) => {
  const value = markId ?? ''
  emit('update:modelValue', {
    ...draft.value,
    selected_mark_id: value,
    model_id: '',
    modification_id: '',
  })
  emit('mark-change', value || null)
}

const changeKitChassisModel = (modelId: UUID | null) => {
  const value = modelId ?? ''
  const selectedModel = props.models.find(m => m.id === value)
  if (selectedModel?.category_id) {
    kitChassisCategoryIds.value = [selectedModel.category_id]
  }
  emit('update:modelValue', {
    ...draft.value,
    model_id: value,
    modification_id: '',
  })
  emit('model-change', value || null)
}

const applyKitChassisModification = (modificationId: UUID | null) => {
  const value = modificationId ?? ''
  emit('update:modelValue', {
    ...draft.value,
    modification_id: value,
    chassis_values: [],
  })
  emit('modification-change', value || null)
}

const changeKitChassisModification = (modificationId: UUID | null) => {
  const value = modificationId ?? ''
  if (value && chassisValues.value.length > 0) {
    pendingKitConfirm.value = {
      title: 'Использовать характеристики модификации?',
      message: 'При выборе модификации ручные значения характеристик шасси будут очищены и заменены данными модификации.',
      onConfirm: () => applyKitChassisModification(value),
    }
    return
  }
  applyKitChassisModification(value)
}

// --- Block 2. Kit Superstructure ---
const allSuperstructures = ref<CatalogSuperstructure[]>([])
const allSuperstructuresLoading = ref(false)

const loadAllSuperstructures = async () => {
  allSuperstructuresLoading.value = true
  try {
    const items = await api.listAll<CatalogSuperstructure>('superstructures', { is_active: true })
    allSuperstructures.value = items
  } catch {
    allSuperstructures.value = []
  } finally {
    allSuperstructuresLoading.value = false
  }
}

const kitSuperstructureMarkId = ref<UUID | ''>('')
const kitSuperstructureModelId = ref<UUID | ''>('')
const superstructureModels = ref<CatalogModel[]>([])
const superstructureModelsLoading = ref(false)
const superstructureModifications = ref<CatalogModification[]>([])
const superstructureModificationsLoading = ref(false)

const superstructureTypeMarks = ref<CatalogMark[]>([])
const superstructureTypeMarksLoading = ref(false)

const loadSuperstructureTypeMarks = async (superstructureId: UUID | null) => {
  if (!superstructureId) {
    superstructureTypeMarks.value = []
    return
  }
  const sType = allSuperstructures.value.find(s => s.id === superstructureId)
    ?? (draft.value.superstructure as CatalogSuperstructure | undefined)
  const catIds = sType?.category_ids ?? []
  if (!catIds.length) {
    superstructureTypeMarks.value = []
    return
  }
  superstructureTypeMarksLoading.value = true
  try {
    const lists = await Promise.all(
      catIds.map(catId => api.listAll<CatalogMark>('marks', { category_id: catId }))
    )
    const combined = lists.flat()
    const seen = new Set<UUID>()
    superstructureTypeMarks.value = combined.filter(m => {
      if (seen.has(m.id)) return false
      seen.add(m.id)
      return true
    })
  } catch {
    superstructureTypeMarks.value = []
  } finally {
    superstructureTypeMarksLoading.value = false
  }
}

const kitSuperstructureMarks = computed<CatalogNamedRef[]>(() => {
  const currentMarkId = kitSuperstructureMarkId.value
  if (!uuidValue('superstructure_id')) {
    return props.marks
  }
  if (superstructureTypeMarks.value.length > 0) {
    const list = superstructureTypeMarks.value.map(m => ({ id: m.id, name: m.name, code: m.code }))
    if (currentMarkId && !list.some(m => m.id === currentMarkId)) {
      const cur = props.marks.find(m => m.id === currentMarkId)
      if (cur) list.unshift(cur)
    }
    return list
  }
  return props.marks
})

const changeStandaloneSuperstructureType = (superstructureId: UUID | null) => {
  const value = superstructureId ?? ''
  const selectedType = allSuperstructures.value.find(s => s.id === value)
  const allowedCatIds = new Set(selectedType?.category_ids ?? [])
  const currentCatIds = uuidArray('category_ids')
  const nextCatIds = allowedCatIds.size > 0
    ? currentCatIds.filter(id => allowedCatIds.has(id))
    : currentCatIds
  emit('update:modelValue', {
    ...draft.value,
    superstructure_id: value,
    superstructure: selectedType ?? draft.value.superstructure,
    category_ids: nextCatIds,
  })
}

const kitAvailableSuperstructureTypes = computed<CatalogNamedRef[]>(() => {
  const list = allSuperstructures.value.map(s => ({
    id: s.id,
    name: s.name,
    code: s.code,
  }))
  const currentId = uuidValue('superstructure_id')
  if (currentId && !list.some(s => s.id === currentId)) {
    const currentSuper = draft.value.superstructure as CatalogSuperstructure | undefined
    if (currentSuper) {
      list.unshift({
        id: currentSuper.id,
        name: currentSuper.name,
        code: currentSuper.code,
      })
    }
  }
  return list
})

const selectedSuperstructureType = computed<CatalogSuperstructure | null>(() => {
  const typeId = uuidValue('superstructure_id')
  if (!typeId) return null
  return allSuperstructures.value.find(s => s.id === typeId)
    ?? (draft.value.superstructure as CatalogSuperstructure | undefined)
    ?? null
})

const kitCategoryAllowedIds = computed<UUID[]>(() =>
  (selectedSuperstructureType.value?.category_ids ?? [])
    .filter(id => !categoryIsInAttachmentBranch(id, props.categories))
)

const selectedSuperstructureTypeAttributes = computed<CatalogSuperstructureAttribute[]>(() =>
  selectedSuperstructureType.value?.attributes ?? [])

const superstructureAttributeGroups = computed(() => {
  const attrs = selectedSuperstructureTypeAttributes.value
  if (!attrs.length) return []
  const groupsMap = new Map<string, { id: UUID | null; name: string; fields: Array<{ attribute: CatalogAttribute; isRequired: boolean }> }>()
  for (const item of attrs) {
    const gId = item.group_id ?? null
    const key = gId ?? 'ungrouped'
    if (!groupsMap.has(key)) {
      groupsMap.set(key, {
        id: gId,
        name: item.group_name || props.groups.find(g => g.id === gId)?.name || 'Прочие',
        fields: [],
      })
    }
    const existingAttr = props.attributes.find(a => a.id === item.attribute_id)
    const attr: CatalogAttribute = existingAttr ?? {
      id: item.attribute_id,
      code: item.attribute_code ?? '',
      name: item.attribute_name ?? '',
      data_type: item.data_type ?? 'text',
      unit: item.unit ?? null,
      unit_id: null,
      filter_kind: 'exact',
      options: [],
      attribute_group_id: gId,
      is_active: true,
    }
    groupsMap.get(key)!.fields.push({
      attribute: attr,
      isRequired: item.is_required,
    })
  }
  return Array.from(groupsMap.values())
})

const superstructureValues = computed<CatalogProductSuperstructureValue[]>(() =>
  Array.isArray(draft.value.superstructure_values)
    ? draft.value.superstructure_values as CatalogProductSuperstructureValue[]
    : [])

const superstructureVal = (attributeId: UUID): CatalogProductSuperstructureValue | undefined =>
  superstructureValues.value.find(v => v.attribute_id === attributeId)

const superstructureOptionValue = (attributeId: UUID): UUID | '' =>
  superstructureVal(attributeId)?.option_id ?? ''

const setSuperstructureValue = (
  attributeId: UUID,
  patch: Partial<Omit<CatalogProductSuperstructureValue, 'attribute_id'>>,
) => {
  const current = superstructureVal(attributeId) ?? {
    attribute_id: attributeId,
    value_number: null,
    value_text: null,
    value_boolean: null,
    option_id: null,
  }
  const nextValue: CatalogProductSuperstructureValue = {
    ...current,
    ...patch,
  }
  const hasValue = nextValue.value_number !== null
    || (typeof nextValue.value_text === 'string' && nextValue.value_text.trim().length > 0)
    || nextValue.value_boolean !== null
    || nextValue.option_id !== null
  const rest = superstructureValues.value.filter(v => v.attribute_id !== attributeId)
  set('superstructure_values', hasValue ? [...rest, nextValue] : rest)
}

const loadSuperstructureModels = async (markId: UUID) => {
  superstructureModelsLoading.value = true
  try {
    const sType = selectedSuperstructureType.value
    const catIds = new Set(sType?.category_ids ?? [])
    const items = await api.listAll<CatalogModel>('models', { mark_id: markId })
    superstructureModels.value = catIds.size > 0
      ? items.filter(m => !m.category_id || catIds.has(m.category_id))
      : items
  } catch {
    superstructureModels.value = []
  } finally {
    superstructureModelsLoading.value = false
  }
}

const loadSuperstructureModifications = async (modelId: UUID) => {
  superstructureModificationsLoading.value = true
  try {
    const items = await api.listAll<CatalogModification>('modifications', { model_id: modelId })
    superstructureModifications.value = items
  } catch {
    superstructureModifications.value = []
  } finally {
    superstructureModificationsLoading.value = false
  }
}

const changeKitSuperstructureMark = async (markId: UUID | null) => {
  const value = markId ?? ''
  kitSuperstructureMarkId.value = value
  kitSuperstructureModelId.value = ''
  superstructureModels.value = []
  superstructureModifications.value = []
  selectedSourceAd.value = null
  isSelectingSourceAd.value = false
  emit('update:modelValue', {
    ...draft.value,
    selected_superstructure_mark_id: value,
    superstructure_model_id: '',
    superstructure_modification_id: '',
    superstructure_source_product_id: null,
    superstructure_source: null,
  })
  if (value) {
    await loadSuperstructureModels(value)
  }
}

const changeKitSuperstructureModel = async (modelId: UUID | null) => {
  const value = modelId ?? ''
  kitSuperstructureModelId.value = value
  superstructureModifications.value = []
  selectedSourceAd.value = null
  isSelectingSourceAd.value = false
  emit('update:modelValue', {
    ...draft.value,
    superstructure_model_id: value,
    superstructure_modification_id: '',
    superstructure_source_product_id: null,
    superstructure_source: null,
  })
  if (value) {
    await loadSuperstructureModifications(value)
  }
  if (superstructureSourceMode.value === 'existing') {
    await loadAttachmentSources()
  }
}

const changeKitSuperstructureModification = async (modificationId: UUID | null) => {
  const value = modificationId ?? ''
  selectedSourceAd.value = null
  isSelectingSourceAd.value = false
  emit('update:modelValue', {
    ...draft.value,
    superstructure_modification_id: value,
    superstructure_source_product_id: null,
    superstructure_source: null,
  })
  if (superstructureSourceMode.value === 'existing') {
    await loadAttachmentSources()
  }
}

const applyKitSuperstructureType = (superstructureId: UUID | null) => {
  const value = superstructureId ?? ''
  const selectedType = allSuperstructures.value.find(s => s.id === value)
  const nextAllowedAttrIds = new Set((selectedType?.attributes ?? []).map(a => a.attribute_id))
  const filteredValues = superstructureValues.value.filter(v => nextAllowedAttrIds.has(v.attribute_id))
  const nextAllowedCatIds = new Set(
    (selectedType?.category_ids ?? []).filter(id => !categoryIsInAttachmentBranch(id, props.categories)),
  )
  const currentCats = uuidArray('category_ids')
  const filteredCats = currentCats.filter(id => nextAllowedCatIds.has(id))
  emit('update:modelValue', {
    ...draft.value,
    superstructure_id: value,
    superstructure_values: filteredValues,
    category_ids: filteredCats,
    superstructure: selectedType ?? draft.value.superstructure,
  })
  void loadSuperstructureTypeMarks(value || null)
}

const changeKitSuperstructureType = (superstructureId: UUID | null) => {
  const value = superstructureId ?? ''
  const selectedType = allSuperstructures.value.find(s => s.id === value)
  const nextAllowedAttrIds = new Set((selectedType?.attributes ?? []).map(a => a.attribute_id))
  const lostValues = superstructureValues.value.filter(v => !nextAllowedAttrIds.has(v.attribute_id))

  const nextAllowedCatIds = new Set(
    (selectedType?.category_ids ?? []).filter(id => !categoryIsInAttachmentBranch(id, props.categories)),
  )
  const currentCats = uuidArray('category_ids')
  const lostCategories = currentCats.filter(id => !nextAllowedCatIds.has(id))

  if (lostCategories.length > 0 || lostValues.length > 0) {
    const items: string[] = []
    for (const catId of lostCategories) {
      const cat = props.categories.find(c => c.id === catId)
      items.push(cat ? `Категория размещения «${cat.name}»` : `Категория ${catId}`)
    }
    for (const v of lostValues) {
      const attr = props.attributes.find(a => a.id === v.attribute_id)
      items.push(attr ? `Характеристика «${attr.name}»` : `Характеристика ${v.attribute_id}`)
    }

    const title = lostCategories.length > 0 && lostValues.length > 0
      ? 'Исключить несовместимые категории и характеристики?'
      : lostCategories.length > 0
        ? 'Исключить несовместимые категории комплекта?'
        : 'Очистить несовместимые характеристики надстройки?'

    const message = lostCategories.length > 0 && lostValues.length > 0
      ? 'Новый тип надстройки не поддерживает ранее выбранные категории размещения и заполненные характеристики:'
      : lostCategories.length > 0
        ? 'Новый тип надстройки не разрешает ранее выбранные категории размещения комплекта. Они будут исключены из объявления:'
        : 'Новый тип надстройки не поддерживает ранее заполненные характеристики:'

    pendingKitConfirm.value = {
      title,
      message,
      items,
      onConfirm: () => applyKitSuperstructureType(value || null),
    }
    return
  }
  applyKitSuperstructureType(value || null)
}

// Mode & Attachment source handling
const selectedSourceAd = ref<AttachmentSourceItem | null>(null)
const isSelectingSourceAd = ref(false)
const attachmentSourceSearch = ref('')
const attachmentSources = ref<AttachmentSourceItem[]>([])
const attachmentSourcesLoading = ref(false)

const superstructureSourceMode = computed<'manual' | 'existing'>({
  get: () => {
    if (draft.value.superstructure_source_mode === 'existing' || draft.value.superstructure_source_mode === 'manual') {
      return draft.value.superstructure_source_mode
    }
    return Boolean(draft.value.superstructure_source_product_id) ? 'existing' : 'manual'
  },
  set: (val) => {
    changeSuperstructureSourceMode(val)
  },
})

const changeSuperstructureSourceMode = (mode: 'manual' | 'existing') => {
  if (mode === superstructureSourceMode.value) return
  if (mode === 'manual') {
    const ad = currentSourceAd.value
    const adName = ad ? (ad.superstructure_name || (typeof ad.model === 'object' ? ad.model?.name : ad.model) || '') : text('superstructure_name')
    const adManufacturer = ad ? (ad.superstructure_manufacturer || (typeof ad.mark === 'object' ? ad.mark?.name : ad.mark) || '') : text('superstructure_manufacturer')
    const adModelId = (typeof ad?.model === 'object' ? ad?.model?.id : null) || kitSuperstructureModelId.value || ''
    const adModId = (typeof ad?.modification === 'object' ? ad?.modification?.id : null) || uuidValue('superstructure_modification_id') || ''

    selectedSourceAd.value = null
    isSelectingSourceAd.value = false

    emit('update:modelValue', {
      ...draft.value,
      superstructure_source_mode: 'manual',
      superstructure_source_product_id: null,
      superstructure_source: null,
      superstructure_name: adName,
      superstructure_manufacturer: adManufacturer,
      superstructure_model_id: adModelId,
      superstructure_modification_id: adModId,
    })
  } else {
    emit('update:modelValue', {
      ...draft.value,
      superstructure_source_mode: 'existing',
      superstructure_source_product_id: selectedSourceAd.value?.id || draft.value.superstructure_source_product_id || null,
    })
    if (kitSuperstructureModelId.value && uuidValue('superstructure_id')) {
      void loadAttachmentSources()
    }
  }
}

interface DraftSuperstructureSource {
  id: UUID
  code: string
  name: string
  publication_status: string
  mark: string
  model: string
  modification: string | null
}

interface DraftSuperstructureModel {
  id: UUID
  code: string
  name: string
  mark: { id: UUID; code: string; name: string }
}

const draftSuperstructureSource = computed<DraftSuperstructureSource | null>(() => {
  const src = draft.value.superstructure_source
  return src && typeof src === 'object' ? src as DraftSuperstructureSource : null
})

const draftSuperstructureModel = computed<DraftSuperstructureModel | null>(() => {
  const model = draft.value.superstructure_model
  return model && typeof model === 'object' ? model as DraftSuperstructureModel : null
})

const currentSourceAd = computed(() => {
  if (selectedSourceAd.value) return selectedSourceAd.value
  const src = draftSuperstructureSource.value
  if (src && draft.value.superstructure_source_product_id) {
    return {
      id: src.id,
      code: src.code,
      name: src.name,
      publication_status: src.publication_status,
      mark: { id: '' as UUID, name: src.mark },
      model: { id: '' as UUID, name: src.model },
      modification: src.modification ? { id: '' as UUID, name: src.modification } : null,
      superstructure_name: src.model,
      superstructure_manufacturer: src.mark,
      superstructure_values_by_attribute: {},
    } as AttachmentSourceItem
  }
  return null
})

const hasSelectedAd = computed(() => Boolean(draft.value.superstructure_source_product_id || currentSourceAd.value))

const currentSourceAdCode = computed(() => currentSourceAd.value?.code ?? '')
const currentSourceAdTitle = computed(() => {
  const ad = currentSourceAd.value
  if (!ad) return ''
  const markName = typeof ad.mark === 'object' ? ad.mark?.name : (ad.mark || ad.superstructure_manufacturer)
  const modelName = typeof ad.model === 'object' ? ad.model?.name : (ad.model || ad.superstructure_name)
  const modName = typeof ad.modification === 'object' ? ad.modification?.name : ad.modification
  return [markName, modelName, modName].filter(Boolean).join(' ') || ad.name || ad.code
})
const currentSourceAdStatusLabel = computed(() => {
  const status = currentSourceAd.value?.publication_status
  if (!status) return ''
  return publicationStatusLabel(status)
})
const currentSourceAdModelName = computed(() => {
  const ad = currentSourceAd.value
  if (!ad) return ''
  return (typeof ad.model === 'object' ? ad.model?.name : ad.model) || ad.superstructure_name || ''
})
const currentSourceAdMarkName = computed(() => {
  const ad = currentSourceAd.value
  if (!ad) return ''
  return (typeof ad.mark === 'object' ? ad.mark?.name : ad.mark) || ad.superstructure_manufacturer || ''
})

const publicationStatusLabel = (status?: string): string => {
  switch (status) {
    case 'draft': return 'Черновик'
    case 'published': return 'Опубликовано'
    case 'archived': return 'В архиве'
    default: return status ?? ''
  }
}

const sourceItemTitle = (src: AttachmentSourceItem): string => {
  const markName = (typeof src.mark === 'object' ? src.mark?.name : src.mark) || src.superstructure_manufacturer
  const modelName = (typeof src.model === 'object' ? src.model?.name : src.model) || src.superstructure_name
  const modName = (typeof src.modification === 'object' ? src.modification?.name : src.modification)
  return [markName, modelName, modName].filter(Boolean).join(' ') || src.name || src.code
}

const sourceInvalidError = computed(() => {
  if (!props.errorMessage) return ''
  if (props.errorMessage.includes('KIT_SUPERSTRUCTURE_SOURCE_INVALID')) {
    return 'Выбранное объявление надстройки недоступно для связывания (должно быть не комплектом, в статусе «Черновик» или «Опубликовано» и принадлежать категории надстроек).'
  }
  return ''
})

const loadAttachmentSources = async () => {
  if (!kitSuperstructureModelId.value || !uuidValue('superstructure_id')) {
    attachmentSources.value = []
    return
  }
  attachmentSourcesLoading.value = true
  try {
    const res = await api.listAttachmentSources({
      model_id: kitSuperstructureModelId.value as UUID,
      modification_id: (uuidValue('superstructure_modification_id') as UUID) || null,
      search: attachmentSourceSearch.value.trim() || undefined,
      exclude_product_id: productId.value,
    })
    attachmentSources.value = res.items
  } catch {
    attachmentSources.value = []
  } finally {
    attachmentSourcesLoading.value = false
  }
}

let attachmentSearchTimer: ReturnType<typeof setTimeout> | null = null
const onSearchAttachmentSources = () => {
  if (attachmentSearchTimer) clearTimeout(attachmentSearchTimer)
  attachmentSearchTimer = setTimeout(() => {
    void loadAttachmentSources()
  }, 300)
}

const startChangingSourceAd = () => {
  isSelectingSourceAd.value = true
  void loadAttachmentSources()
}

const applyAttachmentSource = (src: AttachmentSourceItem) => {
  selectedSourceAd.value = src
  isSelectingSourceAd.value = false

  const typeAttrIds = new Set(selectedSuperstructureTypeAttributes.value.map(a => a.attribute_id))
  const mappedValues: CatalogProductSuperstructureValue[] = []
  if (src.superstructure_values_by_attribute) {
    for (const [attrId, val] of Object.entries(src.superstructure_values_by_attribute)) {
      if (typeAttrIds.size === 0 || typeAttrIds.has(attrId as UUID)) {
        mappedValues.push({
          attribute_id: attrId as UUID,
          option_id: val.option_id ?? null,
          value_text: val.value_text ?? null,
          value_number: val.value_number ?? null,
          value_boolean: val.value_boolean ?? null,
        })
      }
    }
  }

  const markName = (typeof src.mark === 'object' ? src.mark?.name : src.mark) || src.superstructure_manufacturer || ''
  const modelName = (typeof src.model === 'object' ? src.model?.name : src.model) || src.superstructure_name || ''
  const modName = (typeof src.modification === 'object' ? src.modification?.name : src.modification) || null

  emit('update:modelValue', {
    ...draft.value,
    superstructure_source_product_id: src.id,
    superstructure_source: {
      id: src.id,
      code: src.code,
      name: src.name,
      publication_status: src.publication_status,
      mark: markName,
      model: modelName,
      modification: modName,
    },
    superstructure_values: mappedValues,
  })
}

const pickAttachmentSource = (src: AttachmentSourceItem) => {
  if (draft.value.superstructure_source_product_id && draft.value.superstructure_source_product_id !== src.id) {
    pendingKitConfirm.value = {
      title: 'Заменить характеристики надстройки?',
      message: 'Заменить характеристики надстройки значениями из выбранного объявления?',
      onConfirm: () => {
        applyAttachmentSource(src)
      },
    }
    return
  }
  applyAttachmentSource(src)
}

// Hydrate superstructure details in edit mode
watch(
  () => [
    isKit.value,
    isStandaloneAttachment.value,
    draft.value.superstructure_id,
    draft.value.superstructure_model_id,
    draftSuperstructureModel.value,
    draft.value.superstructure_source_product_id,
  ] as const,
  async ([kit, standalone, superId, modelId, modelObj]) => {
    if (kit || standalone) {
      if (allSuperstructures.value.length === 0 && !allSuperstructuresLoading.value) {
        void loadAllSuperstructures()
      }
    }
    if (superId) {
      void loadSuperstructureTypeMarks(superId as UUID)
    }
    if (!kit) return

    const markId = modelObj?.mark?.id
      || (draft.value.selected_superstructure_mark_id as UUID | undefined)
      || (typeof modelId === 'string' && modelId ? props.models.find(m => m.id === modelId)?.mark_id : undefined)
      || ''

    const targetModelId = (typeof modelId === 'string' && modelId ? modelId : modelObj?.id) || ''

    if (markId && kitSuperstructureMarkId.value !== markId) {
      kitSuperstructureMarkId.value = markId
      await loadSuperstructureModels(markId)
    }

    if (targetModelId && kitSuperstructureModelId.value !== targetModelId) {
      kitSuperstructureModelId.value = targetModelId
      await loadSuperstructureModifications(targetModelId)
    }

    const src = draftSuperstructureSource.value
    if (draft.value.superstructure_source_product_id && !selectedSourceAd.value && src) {
      selectedSourceAd.value = {
        id: src.id,
        code: src.code,
        name: src.name,
        publication_status: src.publication_status,
        mark: { id: '' as UUID, name: src.mark },
        model: { id: '' as UUID, name: src.model },
        modification: src.modification ? { id: '' as UUID, name: src.modification } : null,
        superstructure_name: src.model,
        superstructure_manufacturer: src.mark,
        superstructure_values_by_attribute: {},
      }
    }
  },
  { immediate: true },
)

watch(
  () => [isKit.value, kitChassisCategoryIds.value.join('|')] as const,
  ([kit]) => {
    if (kit) void loadKitCategoryMarks()
  },
  { immediate: true },
)

watch(
  () => [isKit.value, draft.value.model_id, draft.value.model, props.models] as const,
  ([kit]) => {
    if (!kit) return
    const model = selectedChassisModel.value
    if (model?.category_id) {
      kitChassisCategoryIds.value = [model.category_id]
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.se-choice-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.se-choice-card { display: flex; min-height: 92px; align-items: flex-start; gap: 10px; padding: 14px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); cursor: pointer; }
.se-choice-card--active { border-color: hsl(var(--se-primary)); background: hsl(var(--se-primary-soft)); }
.se-choice-card > span { display: grid; gap: 4px; }
.se-choice-card small { color: hsl(var(--se-muted)); line-height: 1.45; }
.se-radio-row { display: flex; flex-wrap: wrap; gap: 8px; }
.se-radio-row label { display: flex; min-height: 44px; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
@media (min-width: 1280px) {
  .se-radio-row label { white-space: nowrap; }
}
.se-readonly-specs { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; overflow: hidden; margin: 0; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius); background: hsl(var(--se-border)); }
.se-readonly-specs > div { display: flex; justify-content: space-between; gap: 12px; padding: 10px 12px; background: hsl(var(--se-surface)); }
.se-readonly-specs dt { color: hsl(var(--se-muted)); }
.se-readonly-specs dd { margin: 0; font-weight: 700; text-align: right; }
.se-attribute-binding__heading { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; }
.se-attribute-binding__heading span { color: hsl(var(--se-muted)); font-size: 14px; }
.se-category-group-override { margin-top: 12px; }
.se-card-attribute-count { display: grid; gap: 3px; padding: 12px; border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); }
.se-card-attribute-count span { color: hsl(var(--se-muted)); font-size: 14px; }
.se-inherited-attributes { display: grid; gap: 8px; padding: 12px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
.se-inherited-attributes h3 { margin: 0; font-size: 15px; }
.se-inherited-attributes ul { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.se-inherited-attributes li { display: flex; justify-content: space-between; gap: 12px; font-size: 14px; }
.se-inherited-attributes li span:last-child { color: hsl(var(--se-muted)); text-align: right; }
.se-checkbox-picker { display: grid; gap: 10px; padding: 12px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
.se-checkbox-picker__list { display: grid; max-height: 280px; gap: 2px; overflow-y: auto; }
.se-checkbox-picker__list label { display: flex; min-height: 42px; align-items: center; gap: 10px; padding: 7px 8px; border-radius: 8px; }
.se-checkbox-picker__list label:hover { background: hsl(var(--se-surface-muted)); }
.se-category-order { display: grid; gap: 6px; margin: 10px 0 0; padding: 0; list-style: none; }
.se-category-order li { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border: 1px solid hsl(var(--se-border)); border-radius: 8px; }
.se-category-order li > span:first-child { display: grid; gap: 2px; }
.se-category-order small { color: hsl(var(--se-muted)); }
.se-category-order__actions { display: flex; gap: 4px; }
.se-product-relations { display: grid; gap: 28px; }
.se-product-relations > * + * { padding-top: 24px; border-top: 1px solid hsl(var(--se-border)); }
.se-confirmation-list { display: grid; gap: 6px; margin: 12px 0; padding-left: 20px; }
.se-modification-groups { display: grid; gap: 18px; }
.se-modification-group { display: grid; gap: 12px; padding: 14px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); }
.se-modification-group h3 { margin: 0; font-size: 15px; }
.se-choice-grid--compact { margin-bottom: 16px; }
.se-source-picker { display: grid; gap: 12px; padding: 14px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); margin-bottom: 16px; }
.se-source-list { display: grid; gap: 6px; max-height: 240px; overflow-y: auto; }
.se-source-item { display: grid; gap: 2px; padding: 10px 12px; text-align: left; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); background: hsl(var(--se-surface)); cursor: pointer; }
.se-source-item:hover { border-color: hsl(var(--se-primary)); background: hsl(var(--se-primary-soft)); }
.se-source-item small { color: hsl(var(--se-muted)); }
.se-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.se-section-heading h4 { margin: 0; font-size: 15px; }
.se-badge-note { font-size: 12px; color: hsl(var(--se-muted)); background: hsl(var(--se-surface-muted)); padding: 2px 8px; border-radius: 4px; }
.se-kit-chassis-attributes { margin-top: 16px; }
.se-superstructure-form { display: grid; gap: 16px; }
.se-superstructure-type-attributes { margin-top: 8px; }
.se-superstructure-existing { display: grid; gap: 16px; }
.se-superstructure-existing-body { display: grid; gap: 16px; }
.se-source-card { display: grid; gap: 12px; padding: 14px; border: 1px solid hsl(var(--se-border)); border-radius: var(--se-radius-sm); background: hsl(var(--se-surface-muted)); }
.se-source-card__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.se-source-card__main { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.se-source-card__code { font-family: monospace; font-size: 13px; color: hsl(var(--se-muted)); }
.se-source-card__title { font-size: 15px; font-weight: 600; }
.se-source-card__status { font-size: 12px; color: hsl(var(--se-muted)); background: hsl(var(--se-surface)); padding: 2px 8px; border-radius: 4px; border: 1px solid hsl(var(--se-border)); }
.se-source-card__details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding-top: 10px; border-top: 1px solid hsl(var(--se-border)); }
.se-source-card__label { color: hsl(var(--se-muted)); font-size: 13px; margin-right: 6px; }
.se-source-card__value { font-weight: 500; font-size: 14px; }
.se-source-picker__header { display: flex; align-items: flex-end; gap: 10px; }
.se-source-picker__header label { flex: 1; }
.se-source-item__top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.se-source-item__code { font-family: monospace; font-size: 12px; color: hsl(var(--se-muted)); }
.se-source-item__status { font-size: 11px; color: hsl(var(--se-muted)); }
.se-source-prompt { color: hsl(var(--se-muted)); font-size: 14px; }
</style>
