import Taro from '@tarojs/taro'

// switchTab does not carry query parameters. Consume this intent only on category entry.
let pendingCategorySelection: string | undefined

export function takePendingCategorySelection() {
  const category = pendingCategorySelection
  pendingCategorySelection = undefined
  return category
}

export async function openCategoryTab(categoryId: string) {
  pendingCategorySelection = categoryId
  try {
    await Taro.switchTab({ url: '/pages/category/index' })
  } catch {
    pendingCategorySelection = undefined
    void Taro.showToast({ title: '切换分类失败，请重试', icon: 'none' })
  }
}
