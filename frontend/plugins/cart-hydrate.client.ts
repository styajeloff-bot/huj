export default defineNuxtPlugin(async () => {
  const cartStore = useCartStore()
  await cartStore.initialize()
})
