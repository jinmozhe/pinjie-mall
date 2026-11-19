import { useEffect, useState } from 'react'
import Taro, { useDidHide, useDidShow, usePullDownRefresh } from '@tarojs/taro'
import { Image, Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ResponseModelListCategoryRead, ResponseModelPageResultPublicProductRead } from '@pinjie/api-client'
import { getPublic } from '@/lib/api'
import { queryClient } from '@/lib/query'
import { priceLabel } from '@/lib/money'
import { QueryState } from '@/components/QueryState'
import { ProductImage } from '@/components/ProductImage'
import { assetUrl } from '@/platform/media'
import { CategoryPage } from './CategoryPage'
import { openCategoryTab } from './navigation'

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

function ProductPage({ visible }: { visible: boolean }) {
  const query = useQuery({
    queryKey: ['catalog', 'home-products'],
    queryFn: ({ signal }) => getPublic<ResponseModelPageResultPublicProductRead>('/products?page=1&page_size=20', signal),
    enabled: visible,
    gcTime: 0,
  })
  const data = query.data
  return <View>
    {query.isPending && <QueryState title={query.fetchStatus === 'paused' ? '等待网络连接' : '正在加载商品'} />}
    {query.isError && <QueryState title='商品加载失败' error={query.error} retry={() => { void query.refetch() }} />}
    {data && !query.isError && <>
      {!data.items.length ? <QueryState title='暂无商品' detail='商品上架后会在这里展示' /> : <View className='catalog-grid'>
        {data.items.map((product) => <View key={product.id} className='product-card' onClick={() => { void Taro.navigateTo({ url: `/subpackages/catalog/detail/index?id=${encodeURIComponent(product.id)}` }) }}>
          <ProductImage url={product.images[0]} />
          <View className='product-card-body'>
            <View className='product-name'>{product.name}</View>
            <View className='price-small'>{priceLabel(product.skus.filter((sku) => sku.is_active).map((sku) => sku.price))}</View>
            <Text className='label'>{product.product_type === 'physical' ? '实物商品' : '虚拟商品'}</Text>
          </View>
        </View>)}
      </View>}
    </>}
  </View>
}

export function CatalogPage({ categoryMode = false, initialCategory }: { categoryMode?: boolean; initialCategory?: string }) {
  return categoryMode ? <CategoryPage initialCategory={initialCategory} /> : <HomeCatalogPage />
}

function HomeCatalogPage() {
  const [visible, setVisible] = useState(true)
  useDidShow(() => { setVisible(true) })
  useDidHide(() => { setVisible(false); void queryClient.cancelQueries({ queryKey: ['catalog', 'home-products'] }) })
  const categories = useQuery({ queryKey: ['catalog', 'categories'], queryFn: ({ signal }) => getPublic<ResponseModelListCategoryRead>('/product-categories', signal), enabled: visible })
  usePullDownRefresh(() => {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['catalog', 'home-products'] }),
      queryClient.invalidateQueries({ queryKey: ['catalog', 'categories'] }),
    ]).finally(() => Taro.stopPullDownRefresh())
  })
  const homeCategories = categories.data?.filter((item) => !item.parent_id).slice(0, 8) ?? []

  return <View className='page'>
    <View className='title'>拼捷商城</View>
    <View className='muted'>认真挑选，安心生活</View>
    {categories.isPending && <QueryState title={categories.fetchStatus === 'paused' ? '等待网络连接' : '正在加载分类'} />}
    {categories.isError && <QueryState title='分类加载失败' error={categories.error} retry={() => { void categories.refetch() }} />}
    {categories.data && !categories.isError && <>
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
    </>}
    <View className='section-title'>全部商品</View>
    <ProductPage visible={visible} />
  </View>
}
