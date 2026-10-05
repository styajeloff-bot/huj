import { computed, onBeforeUnmount, shallowRef, ref } from 'vue'

interface LookupPage<T> {
  items: T[]
  pages: number
}

// Each search consumes every matching page. The selected records live in the
// form separately, and a response from a previous search cannot replace results.
export function useWarehouseLookup<T>(
  fetchPage: (search: string, page: number) => Promise<LookupPage<T>>,
  errorMessage: string
) {
  const items = shallowRef<T[]>([])
  const loading = ref(false)
  const error = ref('')
  const loaded = ref(false)
  const empty = computed(() => loaded.value && !loading.value && !error.value && items.value.length === 0)
  let revision = 0
  let currentSearch = ''

  const load = async (search = currentSearch): Promise<T[] | undefined> => {
    currentSearch = search
    const requestRevision = ++revision
    loading.value = true
    error.value = ''
    loaded.value = false
    items.value = []
    try {
      const matches: T[] = []
      let page = 1
      let pages = 1
      do {
        const response = await fetchPage(search, page)
        if (requestRevision !== revision) return
        matches.push(...response.items)
        pages = response.pages
        page += 1
      } while (page <= pages)
      items.value = matches
      loaded.value = true
      return matches
    } catch {
      if (requestRevision === revision) error.value = errorMessage
    } finally {
      if (requestRevision === revision) loading.value = false
    }
  }

  const reset = () => {
    revision += 1
    items.value = []
    loading.value = false
    error.value = ''
    loaded.value = false
  }

  onBeforeUnmount(reset)
  return { items, loading, error, empty, load, reset }
}
