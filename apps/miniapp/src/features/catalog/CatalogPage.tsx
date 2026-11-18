import { useEffect, useState } from 'react'
import Taro, { useDidHide, useDidShow, usePullDownRefresh } from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/Button'
import type { CategoryRead, ResponseModelListCategoryRead, ResponseModelPageResultPublicProductRead } from '@pinjie/api-client'
import { getPublic } from '@/lib/api'
import { queryClient } from '@/lib/query'
import { priceLabel } from '@/lib/money'
import { QueryState } from '@/components/QueryState'
import { ProductImage } from '@/components/ProductImage'
import { assetUrl } from '@/platform/media'

// 跨原生 Tab 跳转时缓存待定位的分类 ID，避免 switchTab URL 无法携带 query 参数
let pendingCategorySelection: string | undefined

function takePendingCategorySelection(): string | undefined {
  const next = pendingCategorySelection
  pendingCategorySelection = undefined
  return next
}

function CategoryIcon({
  url,
  className = 'category-icon',
  fallbackText,
}: {
  url?: string | null
  className?: string
  fallbackText?: string
}) {
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [url])
  if (!url || failed) {
    return fallbackText ? <View className='home-category-fallback'>{fallbackText.slice(0, 1)}</View> : null
  }
  let source: string
  try {
    source = assetUrl(url)
  } catch {
    return fallbackText ? <View className='home-category-fallback'>{fallbackText.slice(0, 1)}</View> : <Text className='muted'>图标来源无效</Text>
  }
  return <Image className={className} src={source} mode='aspectFit' onError={() => setFailed(true)} />
}

function ProductPage({ categoryId, visible }: { categoryId?: string; visible: boolean }) {
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: ['catalog', 'products', categoryId ?? 'all', page],
    queryFn: ({ signal }) => getPublic<ResponseModelPageResultPublicProductRead>(`/products?page=${page}&page_size=20${categoryId ? `&category_id=${encodeURIComponent(categoryId)}` : ''}`, signal),
    enabled: visible,
    gcTime: 0,
  })
  const data = query.data
  function changePage(next: number) { setPage(next); void Taro.pageScrollTo({ scrollTop: 0, duration: 0 }) }
  return <View>
    {query.isPending && <QueryState title={query.fetchStatus === 'paused' ? '等待网络连接' : '正在加载商品'} />}
    {query.isError && <QueryState title='商品加载失败' error={query.error} retry={() => { void query.refetch() }} />}
    {data && !query.isError && <>
      {!data.items.length ? <QueryState title='暂无商品' detail={categoryId ? '该分类目前没有公开上架的商品' : '商品上架后会在这里展示'} /> : <View className='catalog-grid'>
        {data.items.map((product) => <View key={product.id} className='product-card' onClick={() => { void Taro.navigateTo({ url: `/subpackages/catalog/detail/index?id=${encodeURIComponent(product.id)}` }) }}>
          <ProductImage url={product.images[0]} />
          <View className='product-card-body'>
            <View className='product-name'>{product.name}</View>
            <View className='price-small'>{priceLabel(product.skus.filter((sku) => sku.is_active).map((sku) => sku.price))}</View>
            <Text className='label'>{product.product_type === 'physical' ? '实物商品' : '虚拟商品'}</Text>
          </View>
        </View>)}
      </View>}
      <View className='catalog-footer'>
        <View className='muted'>第 {page} 页 · 共 {data.total} 件商品{query.isFetching ? ' · 更新中' : ''}</View>
        <View className='category-strip'>
          <Button fill='outline' disabled={page <= 1 || query.isFetching} onClick={() => changePage(page - 1)}>上一页</Button>
          <Button type='primary' fill='outline' disabled={page * data.page_size >= data.total || query.isFetching} onClick={() => changePage(page + 1)}>下一页</Button>
        </View>
      </View>
    </>}
  </View>
}

export function CatalogPage({ categoryMode = false, initialCategory }: { categoryMode?: boolean; initialCategory?: string }) {
  const [visible, setVisible] = useState(true)
  const [selected, setSelected] = useState<string | undefined>(() => (categoryMode ? takePendingCategorySelection() ?? initialCategory : undefined))
  useDidShow(() => {
    setVisible(true)
    if (categoryMode) {
      // 分类 Tab 页已在栈中挂载后再次被首页唤起时，消费待定位的分类 ID
      const pending = takePendingCategorySelection()
      if (pending !== undefined) {
        setSelected(pending)
        void Taro.pageScrollTo({ scrollTop: 0, duration: 0 })
      }
    }
  })
  useDidHide(() => { setVisible(false); void queryClient.cancelQueries({ queryKey: ['catalog'] }) })
  const categories = useQuery({ queryKey: ['catalog', 'categories'], queryFn: ({ signal }) => getPublic<ResponseModelListCategoryRead>('/product-categories', signal), enabled: visible })
  usePullDownRefresh(() => {
    void queryClient.invalidateQueries({ queryKey: ['catalog'] }).finally(() => Taro.stopPullDownRefresh())
  })
  const active = categories.data?.find((item) => item.id === selected)
  const byId = new Map(categories.data?.map((item) => [item.id, item]))
  const homeCategories = categories.data?.filter((item) => !item.parent_id).slice(0, 8) ?? []

  function label(category: CategoryRead): string {
    const path = [category.name]
    let parent = category.parent_id ? byId.get(category.parent_id) : undefined
    const seen = new Set([category.id])
    while (parent && !seen.has(parent.id)) { seen.add(parent.id); path.unshift(parent.name); parent = parent.parent_id ? byId.get(parent.parent_id) : undefined }
    return path.join(' / ')
  }

  async function openCategoryTab(categoryId: string) {
    pendingCategorySelection = categoryId
    try {
      await Taro.switchTab({ url: '/pages/category/index' })
    } catch {
      pendingCategorySelection = undefined
      void Taro.showToast({ title: '切换分类失败，请重试', icon: 'none' })
    }
  }

  return <View className='page'>
    <View className='title'>{categoryMode ? '商品分类' : '拼捷商城'}</View>
    <View className='muted'>{categoryMode ? '按分类浏览上架商品' : '认真挑选，安心生活'}</View>
    {categories.isPending && <QueryState title={categories.fetchStatus === 'paused' ? '等待网络连接' : '正在加载分类'} />}
    {categories.isError && <QueryState title='分类加载失败' error={categories.error} retry={() => { void categories.refetch() }} />}
    {categories.data && !categories.isError && (categoryMode ? <>
      {!categories.data.length && <View className='note'>暂无启用分类，商品上架后可在这里浏览。</View>}
      <View className='category-strip'>
        <View className={`category-chip ${!selected ? 'active' : ''}`} onClick={() => setSelected(undefined)}>全部商品</View>
        {categories.data.map((category) => <View key={category.id} className={`category-chip ${selected === category.id ? 'active' : ''}`} onClick={() => setSelected(category.id)}>
          <CategoryIcon url={category.icon_url} />{label(category)}
        </View>)}
      </View>
    </> : <>
      {!homeCategories.length ? <View className='note'>暂无启用分类，商品上架后可在这里浏览。</View> : <View className='home-category-card'>
        <View className='home-category-grid'>
          {homeCategories.map((category) => <View key={category.id} className='home-category-item' onClick={() => { void openCategoryTab(category.id) }}>
            <View className='home-category-icon-wrap'>
              <CategoryIcon url={category.icon_url} className='home-category-icon' fallbackText={category.name} />
            </View>
            <Text className='home-category-name'>{category.name}</Text>
          </View>)}
        </View>
      </View>}
    </>)}
    <View className='section-title'>{categoryMode ? (active?.name ?? (selected ? '所选分类' : '全部商品')) : '全部商品'}</View>
    <ProductPage key={categoryMode ? (selected ?? 'all') : 'home-all'} categoryId={categoryMode ? selected : undefined} visible={visible} />
  </View>
}
