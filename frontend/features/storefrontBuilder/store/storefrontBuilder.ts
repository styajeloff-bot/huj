import { defineStore } from 'pinia'
import {
  type Column,
  type PageGlobalSettings,
  type PageLayout,
  type Section,
  type SectionStyles,
  type StorefrontPageDetail,
  type StorefrontPageListItem,
  type StorefrontPageRevision,
  type StorefrontTemplate,
  type WidgetInstance,
  type WidgetStyles,
  type WidgetType,
  BUILT_IN_TEMPLATES,
  createEmptyLayout,
  WIDGET_REGISTRY,
} from '../types'
import { createStorefrontBuilderApi } from '../api/storefrontBuilderApi'
import {
  createStorefrontsAdminApi,
  type AdminStorefront,
  type StorefrontWriteRequest,
} from '~/features/admin/storefronts/api/storefrontsAdminApi'

export interface StorefrontHeaderSettings {
  contact_phone: string
  contact_email: string
  logo_url: string
  public_page_titles: {
    home: string
    about: string
    special_equipment_catalog: string
  }
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function cloneDeep<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

export type PreviewDevice = 'desktop' | 'laptop' | 'tablet'

export interface HistoryState {
  past: string[]
  future: string[]
}

export const useStorefrontBuilderStore = defineStore('storefrontBuilder', () => {
  const config = useRuntimeConfig()
  const api = createStorefrontBuilderApi(config)

  // State
  const activeStorefrontId = ref<string | null>(null)
  const activePageId = ref<string | null>(null)
  const storefront = ref<AdminStorefront | null>(null)
  const availablePages = ref<StorefrontPageListItem[]>([])
  const currentPage = ref<StorefrontPageDetail | null>(null)
  const layout = ref<PageLayout>(createEmptyLayout())
  const selectedElementId = ref<string | null>(null)

  const historyStack = ref<HistoryState>({
    past: [],
    future: [],
  })

  const isDirty = ref(false)
  const isSaving = ref(false)
  const isPublishing = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const previewDevice = ref<PreviewDevice>('desktop')
  const previewMode = ref(false)

  // Header settings state
  const headerSettings = reactive<StorefrontHeaderSettings>({
    contact_phone: '',
    contact_email: '',
    logo_url: '',
    public_page_titles: {
      home: 'Главная',
      about: 'О нас',
      special_equipment_catalog: 'Транспортные средства',
    },
  })
  const isSavingHeader = ref(false)

  // Modals state
  const showTemplatesModal = ref(false)
  const showPresetModal = ref(false)
  const showRevisionsModal = ref(false)
  const showPublishConfirmModal = ref(false)
  const showCreatePageModal = ref(false)

  const revisions = ref<StorefrontPageRevision[]>([])
  const templates = ref<StorefrontTemplate[]>(BUILT_IN_TEMPLATES)

  // Getters
  const canUndo = computed(() => historyStack.value.past.length > 0)
  const canRedo = computed(() => historyStack.value.future.length > 0)

  const selectedElementType = computed<'section' | 'column' | 'widget' | null>(() => {
    if (!selectedElementId.value) return null
    for (const section of layout.value.sections) {
      if (section.id === selectedElementId.value) return 'section'
      for (const col of section.columns) {
        if (col.id === selectedElementId.value) return 'column'
        for (const w of col.widgets) {
          if (w.id === selectedElementId.value) return 'widget'
        }
      }
    }
    return null
  })

  const selectedWidget = computed<WidgetInstance | null>(() => {
    if (!selectedElementId.value) return null
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        for (const w of col.widgets) {
          if (w.id === selectedElementId.value) return w
        }
      }
    }
    return null
  })

  const selectedSection = computed<Section | null>(() => {
    if (!selectedElementId.value) return null
    for (const section of layout.value.sections) {
      if (section.id === selectedElementId.value) return section
      for (const col of section.columns) {
        if (col.id === selectedElementId.value) return section
        for (const w of col.widgets) {
          if (w.id === selectedElementId.value) return section
        }
      }
    }
    return null
  })

  const selectedColumn = computed<Column | null>(() => {
    if (!selectedElementId.value) return null
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        if (col.id === selectedElementId.value) return col
        for (const w of col.widgets) {
          if (w.id === selectedElementId.value) return col
        }
      }
    }
    return null
  })

  const hasUnpublishedChanges = computed(() => {
    if (isDirty.value) return true
    if (!currentPage.value) return false
    return Boolean(currentPage.value.has_unpublished_draft)
  })

  // History Helper
  function recordHistory() {
    const snapshot = JSON.stringify(layout.value)
    historyStack.value.past.push(snapshot)
    if (historyStack.value.past.length > 50) {
      historyStack.value.past.shift()
    }
    historyStack.value.future = []
    isDirty.value = true
  }

  function undo() {
    if (!canUndo.value) return
    const previous = historyStack.value.past.pop()
    if (!previous) return
    historyStack.value.future.push(JSON.stringify(layout.value))
    try {
      layout.value = JSON.parse(previous)
      isDirty.value = true
    } catch (e) {
      console.error('Failed to parse undo layout snapshot', e)
    }
  }

  function redo() {
    if (!canRedo.value) return
    const next = historyStack.value.future.pop()
    if (!next) return
    historyStack.value.past.push(JSON.stringify(layout.value))
    try {
      layout.value = JSON.parse(next)
      isDirty.value = true
    } catch (e) {
      console.error('Failed to parse redo layout snapshot', e)
    }
  }

  function selectElement(id: string | null) {
    selectedElementId.value = id
  }

  function clearSelection() {
    selectedElementId.value = null
  }

  // Header actions
  function updateHeaderSettings(updates: Partial<{
    contact_phone: string
    contact_email: string
    logo_url: string
    public_page_titles: Partial<StorefrontHeaderSettings['public_page_titles']>
  }>) {
    if (updates.contact_phone !== undefined) headerSettings.contact_phone = updates.contact_phone
    if (updates.contact_email !== undefined) headerSettings.contact_email = updates.contact_email
    if (updates.logo_url !== undefined) headerSettings.logo_url = updates.logo_url
    if (updates.public_page_titles) {
      headerSettings.public_page_titles = {
        ...headerSettings.public_page_titles,
        ...updates.public_page_titles,
      }
    }
  }

  async function saveHeaderSettings(logoFile?: File | null) {
    if (!activeStorefrontId.value) return false
    isSavingHeader.value = true
    error.value = null
    try {
      const storefrontsAdminApi = createStorefrontsAdminApi(config)
      const payload: StorefrontWriteRequest = {
        contact_phone: headerSettings.contact_phone.trim() || null,
        contact_email: headerSettings.contact_email.trim() || null,
        public_ui: {
          home_page_key: storefront.value?.public_ui?.home_page_key || 'home',
          pages: {
            home: { title: headerSettings.public_page_titles.home.trim() || 'Главная' },
            about: { title: headerSettings.public_page_titles.about.trim() || 'О нас' },
            special_equipment_catalog: {
              title: headerSettings.public_page_titles.special_equipment_catalog.trim() || 'Транспортные средства',
            },
          },
        },
      }

      let updated = await storefrontsAdminApi.update(activeStorefrontId.value, payload)

      if (logoFile) {
        updated = await storefrontsAdminApi.uploadLogo(activeStorefrontId.value, logoFile)
      }

      storefront.value = updated
      headerSettings.contact_phone = updated.contact_phone || updated.effective_contact_phone || ''
      headerSettings.contact_email = updated.contact_email || updated.effective_contact_email || ''
      headerSettings.logo_url = updated.logo_url || updated.effective_logo_url || ''
      headerSettings.public_page_titles = {
        home: updated.public_ui?.pages?.home?.title || 'Главная',
        about: updated.public_ui?.pages?.about?.title || 'О нас',
        special_equipment_catalog: updated.public_ui?.pages?.special_equipment_catalog?.title || 'Транспортные средства',
      }
      return true
    } catch (err: any) {
      error.value = err?.data?.message || err?.message || 'Ошибка сохранения настроек шапки'
      console.error('Error saving header settings:', err)
      return false
    } finally {
      isSavingHeader.value = false
    }
  }

  async function removeHeaderLogo() {
    if (!activeStorefrontId.value) return false
    isSavingHeader.value = true
    error.value = null
    try {
      const storefrontsAdminApi = createStorefrontsAdminApi(config)
      const updated = await storefrontsAdminApi.deleteLogo(activeStorefrontId.value)
      storefront.value = updated
      headerSettings.logo_url = updated.logo_url || updated.effective_logo_url || ''
      return true
    } catch (err: any) {
      error.value = err?.data?.message || err?.message || 'Ошибка удаления логотипа'
      console.error('Error removing logo:', err)
      return false
    } finally {
      isSavingHeader.value = false
    }
  }

  // Load Storefront and Page
  async function loadPage(storefrontId: string, pageId?: string) {
    isLoading.value = true
    error.value = null

    // Reset previous state when switching to a different storefront or on initial load
    if (activeStorefrontId.value !== storefrontId) {
      availablePages.value = []
      currentPage.value = null
      layout.value = createEmptyLayout()
      selectedElementId.value = null
      historyStack.value = { past: [], future: [] }
      error.value = null
      isDirty.value = false
      storefront.value = null
      activePageId.value = null
      revisions.value = []
      headerSettings.contact_phone = ''
      headerSettings.contact_email = ''
      headerSettings.logo_url = ''
      headerSettings.public_page_titles = {
        home: 'Главная',
        about: 'О нас',
        special_equipment_catalog: 'Транспортные средства',
      }
    }

    activeStorefrontId.value = storefrontId

    try {
      // Load storefront details
      const sf = await api.getStorefront(storefrontId)
      storefront.value = sf
      headerSettings.contact_phone = sf.contact_phone || sf.effective_contact_phone || ''
      headerSettings.contact_email = sf.contact_email || sf.effective_contact_email || ''
      headerSettings.logo_url = sf.logo_url || sf.effective_logo_url || ''
      headerSettings.public_page_titles = {
        home: sf.public_ui?.pages?.home?.title || 'Главная',
        about: sf.public_ui?.pages?.about?.title || 'О нас',
        special_equipment_catalog: sf.public_ui?.pages?.special_equipment_catalog?.title || 'Транспортные средства',
      }

      // Load available pages for this storefront
      const pagesResp = await api.listPages(storefrontId).catch(() => ({ items: [] }))
      const pages: StorefrontPageListItem[] = pagesResp.items ? [...pagesResp.items] : []

      // Guarantee system pages exist in availablePages:
      // «Главная» (home), «О нас» (about), «Транспортные средства» (special_equipment_catalog)
      const systemPagesDef: Array<{ page_key: string; title: string; slug: string }> = [
        { page_key: 'home', title: 'Главная', slug: '' },
        { page_key: 'about', title: 'О нас', slug: 'about' },
        { page_key: 'special_equipment_catalog', title: 'Транспортные средства', slug: 'special-equipment' },
      ]

      for (const sysDef of systemPagesDef) {
        const found = pages.find((p) => p.page_key === sysDef.page_key)
        if (!found) {
          pages.push({
            id: generateId(),
            storefront_id: storefrontId,
            page_key: sysDef.page_key,
            title: sysDef.title,
            slug: sysDef.slug,
            is_system: true,
            status: 'draft',
            version: 1,
            has_unpublished_draft: false,
            published_at: null,
            updated_at: new Date().toISOString(),
          })
        }
      }
      availablePages.value = pages

      // If no pageId is specified, find home page or first page
      let targetPageId = pageId
      if (targetPageId) {
        const found = availablePages.value.find((p) => p.id === targetPageId || p.page_key === targetPageId)
        if (found) {
          targetPageId = found.id
        }
      } else {
        const homePage = availablePages.value.find((p) => p.page_key === 'home')
        targetPageId = homePage ? homePage.id : availablePages.value[0]?.id
      }

      if (targetPageId) {
        activePageId.value = targetPageId
        let pageDetail: StorefrontPageDetail | null = null
        try {
          pageDetail = await api.getPage(storefrontId, targetPageId)
        } catch (getErr) {
          // If this is a synthetic system page, create it on backend so it gets persisted
          const sysItem = availablePages.value.find((p) => p.id === targetPageId && p.is_system)
          if (sysItem) {
            try {
              pageDetail = await api.createPage(storefrontId, {
                title: sysItem.title,
                page_key: sysItem.page_key,
                slug: sysItem.slug,
              })
              sysItem.id = pageDetail.id
              activePageId.value = pageDetail.id
            } catch {
              // ignore
            }
          }
          if (!pageDetail) throw getErr
        }

        currentPage.value = pageDetail

        // Initialize layout from draft_layout or published_layout or fallback
        if (pageDetail.draft_layout && pageDetail.draft_layout.sections) {
          layout.value = cloneDeep(pageDetail.draft_layout)
        } else if (pageDetail.published_layout && pageDetail.published_layout.sections) {
          layout.value = cloneDeep(pageDetail.published_layout)
        } else {
          // If empty, initialize from classic template
          layout.value = cloneDeep(BUILT_IN_TEMPLATES[0].layout)
        }

        // Reset history stack
        historyStack.value = { past: [], future: [] }
        isDirty.value = false
        selectedElementId.value = null

        // Load revisions in background
        loadRevisions()
      } else {
        // No pages exist yet; fallback to classic template
        layout.value = cloneDeep(BUILT_IN_TEMPLATES[0].layout)
        isDirty.value = false
      }
    } catch (err: any) {
      error.value = err?.data?.message || err?.message || 'Не удалось загрузить страницу витрины'
      console.error('Error loading storefront builder:', err)
    } finally {
      isLoading.value = false
    }
  }

  // Section Actions
  function addSection(index?: number, layoutType: 'container' | 'full_width' = 'container') {
    recordHistory()
    const newSection: Section = {
      id: generateId(),
      name: `Секция ${layout.value.sections.length + 1}`,
      layout_type: layoutType,
      styles: {
        padding: '32px 0',
      },
      columns: [
        {
          id: generateId(),
          width: 12,
          widgets: [],
        },
      ],
    }

    if (typeof index === 'number' && index >= 0 && index <= layout.value.sections.length) {
      layout.value.sections.splice(index, 0, newSection)
    } else {
      layout.value.sections.push(newSection)
    }
    selectedElementId.value = newSection.id
    return newSection
  }

  function removeSection(sectionId: string) {
    recordHistory()
    const idx = layout.value.sections.findIndex((s) => s.id === sectionId)
    if (idx !== -1) {
      layout.value.sections.splice(idx, 1)
      if (selectedElementId.value === sectionId) {
        selectedElementId.value = null
      }
    }
  }

  function reorderSections(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return
    if (fromIndex < 0 || fromIndex >= layout.value.sections.length) return
    if (toIndex < 0 || toIndex >= layout.value.sections.length) return

    recordHistory()
    const [moved] = layout.value.sections.splice(fromIndex, 1)
    layout.value.sections.splice(toIndex, 0, moved)
  }

  function updateSectionStyles(sectionId: string, styles: Partial<SectionStyles>) {
    const sec = layout.value.sections.find((s) => s.id === sectionId)
    if (!sec) return
    recordHistory()
    sec.styles = { ...sec.styles, ...styles }
  }

  function duplicateSection(sectionId: string) {
    const sec = layout.value.sections.find((s) => s.id === sectionId)
    if (!sec) return
    recordHistory()
    const clone = cloneDeep(sec)
    clone.id = generateId()
    clone.name = `${sec.name} (копия)`
    for (const col of clone.columns) {
      col.id = generateId()
      for (const w of col.widgets) {
        w.id = generateId()
      }
    }
    const idx = layout.value.sections.findIndex((s) => s.id === sectionId)
    layout.value.sections.splice(idx + 1, 0, clone)
    selectedElementId.value = clone.id
  }

  // Column Actions
  function addColumn(sectionId: string, width = 6) {
    const sec = layout.value.sections.find((s) => s.id === sectionId)
    if (!sec) return
    recordHistory()
    const newCol: Column = {
      id: generateId(),
      width,
      widgets: [],
    }
    sec.columns.push(newCol)
    selectedElementId.value = newCol.id
  }

  function removeColumn(sectionId: string, columnId: string) {
    const sec = layout.value.sections.find((s) => s.id === sectionId)
    if (!sec || sec.columns.length <= 1) return
    recordHistory()
    const idx = sec.columns.findIndex((c) => c.id === columnId)
    if (idx !== -1) {
      sec.columns.splice(idx, 1)
      if (selectedElementId.value === columnId) {
        selectedElementId.value = sec.id
      }
    }
  }

  // Widget Actions
  function addWidget(
    sectionId: string,
    columnId: string,
    widgetType: WidgetType,
    props?: Record<string, any>,
  ) {
    recordHistory()
    let targetSection = layout.value.sections.find((s) => s.id === sectionId)
    if (!targetSection) {
      targetSection = addSection()
    }

    let targetColumn = targetSection.columns.find((c) => c.id === columnId)
    if (!targetColumn) {
      if (targetSection.columns.length === 0) {
        targetColumn = { id: generateId(), width: 12, widgets: [] }
        targetSection.columns.push(targetColumn)
      } else {
        targetColumn = targetSection.columns[0]
      }
    }

    const definition = WIDGET_REGISTRY[widgetType]
    const newWidget: WidgetInstance = {
      id: generateId(),
      type: widgetType,
      props: cloneDeep(props || definition?.defaultProps || {}),
      styles: cloneDeep(definition?.defaultStyles || {}),
    }

    targetColumn.widgets.push(newWidget)
    selectedElementId.value = newWidget.id
    return newWidget
  }

  function removeWidget(widgetId: string) {
    recordHistory()
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        const idx = col.widgets.findIndex((w) => w.id === widgetId)
        if (idx !== -1) {
          col.widgets.splice(idx, 1)
          if (selectedElementId.value === widgetId) {
            selectedElementId.value = col.id
          }
          return
        }
      }
    }
  }

  function updateWidgetProps(widgetId: string, props: Record<string, any>) {
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        const w = col.widgets.find((item) => item.id === widgetId)
        if (w) {
          recordHistory()
          w.props = { ...w.props, ...props }
          return
        }
      }
    }
  }

  function updateWidgetStyles(widgetId: string, styles: Partial<WidgetStyles>) {
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        const w = col.widgets.find((item) => item.id === widgetId)
        if (w) {
          recordHistory()
          w.styles = { ...w.styles, ...styles }
          return
        }
      }
    }
  }

  function duplicateWidget(widgetId: string) {
    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        const idx = col.widgets.findIndex((w) => w.id === widgetId)
        if (idx !== -1) {
          recordHistory()
          const clone = cloneDeep(col.widgets[idx])
          clone.id = generateId()
          col.widgets.splice(idx + 1, 0, clone)
          selectedElementId.value = clone.id
          return
        }
      }
    }
  }

  function reorderWidgets(
    sourceColumnId: string,
    targetColumnId: string,
    fromIndex: number,
    toIndex: number,
  ) {
    let sourceCol: Column | null = null
    let targetCol: Column | null = null

    for (const section of layout.value.sections) {
      for (const col of section.columns) {
        if (col.id === sourceColumnId) sourceCol = col
        if (col.id === targetColumnId) targetCol = col
      }
    }

    if (!sourceCol || !targetCol) return
    recordHistory()

    const [moved] = sourceCol.widgets.splice(fromIndex, 1)
    if (moved) {
      targetCol.widgets.splice(toIndex, 0, moved)
    }
  }

  function updateGlobalSettings(settings: Partial<PageGlobalSettings>) {
    recordHistory()
    layout.value.settings = { ...layout.value.settings, ...settings }
  }

  // Save Draft
  async function saveDraft(summary = 'Обновление разметки в Конструкторе') {
    if (!activeStorefrontId.value || !activePageId.value || !currentPage.value) return false
    isSaving.value = true
    error.value = null

    try {
      const resp = await api.saveDraft(activeStorefrontId.value, activePageId.value, {
        title: currentPage.value.title,
        expected_version: currentPage.value.version,
        summary,
        draft_layout: layout.value,
      })

      currentPage.value.version = resp.version
      currentPage.value.updated_at = resp.updated_at
      currentPage.value.draft_layout = cloneDeep(layout.value)
      currentPage.value.has_unpublished_draft = true

      isDirty.value = false
      historyStack.value.past = []
      historyStack.value.future = []

      const listItem = availablePages.value.find((p) => p.id === activePageId.value)
      if (listItem) {
        listItem.version = resp.version
        listItem.has_unpublished_draft = true
        listItem.updated_at = resp.updated_at
      }

      // Refresh revisions list
      await loadRevisions()
      return true
    } catch (err: any) {
      error.value = err?.data?.message || err?.message || 'Ошибка сохранения черновика'
      console.error('Error saving draft:', err)
      return false
    } finally {
      isSaving.value = false
    }
  }

  // Publish Page
  async function publishPage() {
    if (!activeStorefrontId.value || !activePageId.value || !currentPage.value) return false

    // If there are unsaved local modifications, save draft first
    if (isDirty.value) {
      const saved = await saveDraft('Автосохранение перед публикацией')
      if (!saved) return false
    }

    isPublishing.value = true
    error.value = null

    try {
      const resp = await api.publishPage(activeStorefrontId.value, activePageId.value, {
        expected_version: currentPage.value.version,
      })

      currentPage.value.version = resp.version
      currentPage.value.status = 'published'
      currentPage.value.published_at = resp.published_at
      currentPage.value.published_layout = cloneDeep(layout.value)
      currentPage.value.has_unpublished_draft = false
      isDirty.value = false
      historyStack.value.past = []
      historyStack.value.future = []

      const listItem = availablePages.value.find((p) => p.id === activePageId.value)
      if (listItem) {
        listItem.version = resp.version
        listItem.status = 'published'
        listItem.has_unpublished_draft = false
        listItem.published_at = resp.published_at
      }

      if (storefront.value) {
        storefront.value.version = (storefront.value.version || 0) + 1
      }
      return true
    } catch (err: any) {
      error.value = err?.data?.message || err?.message || 'Ошибка при публикации страницы'
      console.error('Error publishing page:', err)
      return false
    } finally {
      isPublishing.value = false
    }
  }

  // Revisions
  async function loadRevisions() {
    if (!activeStorefrontId.value || !activePageId.value) return
    try {
      revisions.value = await api.getRevisions(activeStorefrontId.value, activePageId.value)
    } catch (err) {
      console.warn('Could not load revisions history:', err)
    }
  }

  async function restoreRevision(revisionId: string) {
    if (!activeStorefrontId.value || !activePageId.value || !currentPage.value) return false
    recordHistory()
    isLoading.value = true

    try {
      const resp = await api.restoreRevision(
        activeStorefrontId.value,
        activePageId.value,
        revisionId,
        { expected_version: currentPage.value.version },
      )

      currentPage.value.version = resp.version
      if (resp.draft_layout) {
        layout.value = cloneDeep(resp.draft_layout)
      }
      isDirty.value = true
      selectedElementId.value = null
      return true
    } catch (err: any) {
      // Fallback: search local revisions snapshot if available
      const localRev = revisions.value.find((r) => r.id === revisionId)
      if (localRev?.layout_snapshot) {
        layout.value = cloneDeep(localRev.layout_snapshot)
        isDirty.value = true
        selectedElementId.value = null
        return true
      }
      error.value = err?.data?.message || err?.message || 'Ошибка при восстановлении ревизии'
      return false
    } finally {
      isLoading.value = false
    }
  }

  // Templates
  function applyTemplate(templateLayout: PageLayout) {
    recordHistory()
    layout.value = cloneDeep(templateLayout)
    // Regenerate unique IDs so there are no collisions
    for (const sec of layout.value.sections) {
      sec.id = generateId()
      for (const col of sec.columns) {
        col.id = generateId()
        for (const w of col.widgets) {
          w.id = generateId()
        }
      }
    }
    selectedElementId.value = null
    isDirty.value = true
  }

  // Preset import/export
  function importPreset(presetData: PageLayout) {
    recordHistory()
    layout.value = cloneDeep(presetData)
    // Ensure all sections/columns/widgets have valid IDs
    for (const sec of layout.value.sections) {
      if (!sec.id) sec.id = generateId()
      for (const col of sec.columns) {
        if (!col.id) col.id = generateId()
        for (const w of col.widgets) {
          if (!w.id) w.id = generateId()
        }
      }
    }
    selectedElementId.value = null
    isDirty.value = true
  }

  function exportPreset(): string {
    const payload = {
      schema_version: '1.0',
      exported_at: new Date().toISOString(),
      storefront_id: activeStorefrontId.value,
      page_key: currentPage.value?.page_key || 'custom',
      title: currentPage.value?.title || layout.value.settings.title,
      layout: layout.value,
    }
    return JSON.stringify(payload, null, 2)
  }

  function setPreviewDevice(device: PreviewDevice) {
    previewDevice.value = device
  }

  // Create Page Action
  async function createPage(
    payloadOrTitle:
      | string
      | {
          title: string
          page_key: string
          slug?: string
          template_code?: string
        },
    pageKey?: string,
  ) {
    if (!activeStorefrontId.value) {
      const err = new Error('Активная витрина не выбрана')
      error.value = err.message
      throw err
    }
    isLoading.value = true

    const payload =
      typeof payloadOrTitle === 'string'
        ? {
            title: payloadOrTitle,
            page_key: pageKey || payloadOrTitle.toLowerCase().replace(/\s+/g, '-'),
            slug: pageKey || payloadOrTitle.toLowerCase().replace(/\s+/g, '-'),
          }
        : {
            title: payloadOrTitle.title,
            page_key: payloadOrTitle.page_key,
            slug: payloadOrTitle.slug ?? payloadOrTitle.page_key,
            template_code: payloadOrTitle.template_code,
          }

    try {
      const newPage = await api.createPage(activeStorefrontId.value, payload)
      const newItem: StorefrontPageListItem = {
        id: newPage.id,
        storefront_id: newPage.storefront_id,
        page_key: newPage.page_key,
        title: newPage.title,
        slug: newPage.slug,
        is_system: newPage.is_system,
        status: newPage.status,
        version: newPage.version,
        has_unpublished_draft: false,
        published_at: newPage.published_at,
        updated_at: newPage.updated_at,
      }

      const existingIdx = availablePages.value.findIndex((p) => p.page_key === newPage.page_key)
      if (existingIdx >= 0) {
        availablePages.value[existingIdx] = newItem
      } else {
        availablePages.value.push(newItem)
      }

      activePageId.value = newPage.id
      await loadPage(activeStorefrontId.value, newPage.id)
      return newPage
    } catch (err: any) {
      error.value = err?.data?.message || err?.data?.detail || err?.message || 'Ошибка при создании страницы'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // Update Page Metadata Action
  async function updatePageMetadata(pageId: string, title?: string, slug?: string) {
    if (!activeStorefrontId.value) {
      const err = new Error('Активная витрина не выбрана')
      error.value = err.message
      throw err
    }
    isLoading.value = true
    error.value = null
    try {
      const updated = await api.updatePageMetadata(activeStorefrontId.value, pageId, { title, slug })
      const pageInList = availablePages.value.find((p) => p.id === pageId)
      if (pageInList) {
        if (title !== undefined) pageInList.title = updated.title
        if (slug !== undefined) pageInList.slug = updated.slug
        pageInList.updated_at = updated.updated_at
      }
      if (currentPage.value && currentPage.value.id === pageId) {
        if (title !== undefined) currentPage.value.title = updated.title
        if (slug !== undefined) currentPage.value.slug = updated.slug
        currentPage.value.updated_at = updated.updated_at
      }
      return updated
    } catch (err: any) {
      error.value = err?.data?.message || err?.data?.detail || err?.message || 'Ошибка при обновлении страницы'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  return {
    // State
    activeStorefrontId,
    activePageId,
    storefront,
    availablePages,
    currentPage,
    layout,
    selectedElementId,
    historyStack,
    isDirty,
    isSaving,
    isPublishing,
    isLoading,
    error,
    previewDevice,
    previewMode,
    showTemplatesModal,
    showPresetModal,
    showRevisionsModal,
    showPublishConfirmModal,
    showCreatePageModal,
    revisions,
    templates,

    // Header management
    headerSettings,
    isSavingHeader,
    updateHeaderSettings,
    saveHeaderSettings,
    removeHeaderLogo,
    contact_phone: computed({
      get: () => headerSettings.contact_phone,
      set: (val: string) => {
        headerSettings.contact_phone = val
      },
    }),
    contact_email: computed({
      get: () => headerSettings.contact_email,
      set: (val: string) => {
        headerSettings.contact_email = val
      },
    }),
    logo_url: computed({
      get: () => headerSettings.logo_url,
      set: (val: string) => {
        headerSettings.logo_url = val
      },
    }),
    public_page_titles: headerSettings.public_page_titles,

    // Getters
    canUndo,
    canRedo,
    selectedElementType,
    selectedWidget,
    selectedSection,
    selectedColumn,
    hasUnpublishedChanges,

    // Actions
    recordHistory,
    undo,
    redo,
    selectElement,
    clearSelection,
    loadPage,
    addSection,
    removeSection,
    reorderSections,
    updateSectionStyles,
    duplicateSection,
    addColumn,
    removeColumn,
    addWidget,
    removeWidget,
    updateWidgetProps,
    updateWidgetStyles,
    duplicateWidget,
    reorderWidgets,
    updateGlobalSettings,
    saveDraft,
    publishPage,
    loadRevisions,
    restoreRevision,
    applyTemplate,
    importPreset,
    exportPreset,
    setPreviewDevice,
    createPage,
    updatePageMetadata,
    api,
  }
})
