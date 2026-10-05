export const useImageCarousel = (images: Ref<string[]> | ComputedRef<string[]>) => {
  const currentImageIndex = ref(0)
  const touchStartX = ref(0)
  const touchEndX = ref(0)

  const previousImage = () => {
    if (currentImageIndex.value > 0) currentImageIndex.value--
  }

  const nextImage = () => {
    if (currentImageIndex.value < images.value.length - 1) currentImageIndex.value++
  }

  const handleTouchStart = (e: TouchEvent) => {
    touchStartX.value = e.touches[0].clientX
  }

  const handleTouchMove = (e: TouchEvent) => {
    touchEndX.value = e.touches[0].clientX
  }

  const handleTouchEnd = () => {
    if (touchStartX.value - touchEndX.value > 75) nextImage()
    if (touchEndX.value - touchStartX.value > 75) previousImage()
  }

  const handleKeyboard = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft') previousImage()
    else if (e.key === 'ArrowRight') nextImage()
  }

  const reset = () => {
    currentImageIndex.value = 0
  }

  onMounted(() => window.addEventListener('keydown', handleKeyboard))
  onUnmounted(() => window.removeEventListener('keydown', handleKeyboard))

  return {
    currentImageIndex,
    previousImage,
    nextImage,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
    reset,
  }
}
