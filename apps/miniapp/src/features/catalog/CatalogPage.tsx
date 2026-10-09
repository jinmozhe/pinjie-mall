import { useState } from 'react'
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

function CategoryIcon({ url }: { url?: string | null }) {
  const [failed, setFailed] = useState(false)
  if (!url || failed) return null
  let source: string
  try { source = assetUrl(url) } catch { return <Text className='muted'>图标来源无效</Text> }
  return <Image className='category-icon' src={source} onError={() => setFailed(true)} />
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
  const [selected, setSelected] = useState<string | undefined>(initialCategory)
  useDidShow(() => { setVisible(true) })
  useDidHide(() => { setVisible(false); void queryClient.cancelQueries({ queryKey: ['catalog'] }) })
  const categories = useQuery({ queryKey: ['catalog', 'categories'], queryFn: ({ signal }) => getPublic<ResponseModelListCategoryRead>('/product-categories', signal), enabled: visible })
  usePullDownRefresh(() => {
    void queryClient.invalidateQueries({ queryKey: ['catalog'] }).finally(() => Taro.stopPullDownRefresh())
  })
  const active = categories.data?.find((item) => item.id === selected)
  const byId = new Map(categories.data?.map((item) => [item.id, item]))
  function label(category: CategoryRead): string {
    const path = [category.name]
    let parent = category.parent_id ? byId.get(category.parent_id) : undefined
    const seen = new Set([category.id])
    while (parent && !seen.has(parent.id)) { seen.add(parent.id); path.unshift(parent.name); parent = parent.parent_id ? byId.get(parent.parent_id) : undefined }
    return path.join(' / ')
  }
  return <View className='page'>
    <View className='title'>{categoryMode ? '商品分类' : '拼捷商城'}</View>
    <View className='muted'>{categoryMode ? '按分类浏览上架商品' : '认真挑选，安心生活'}</View>
    {categories.isPending && <QueryState title={categories.fetchStatus === 'paused' ? '等待网络连接' : '正在加载分类'} />}
    {categories.isError && <QueryState title='分类加载失败' error={categories.error} retry={() => { void categories.refetch() }} />}
    {categories.data && !categories.isError && <>
      {!categories.data.length && <View className='note'>暂无启用分类，商品上架后可在这里浏览。</View>}
      <View className='category-strip'>
        <View className={`category-chip ${!selected ? 'active' : ''}`} onClick={() => setSelected(undefined)}>全部商品</View>
        {categories.data.map((category) => <View key={category.id} className={`category-chip ${selected === category.id ? 'active' : ''}`} onClick={() => setSelected(category.id)}>
          <CategoryIcon url={category.icon_url} />{label(category)}
        </View>)}
      </View>
    </>}
    <View className='section-title'>{active?.name ?? (selected ? '所选分类' : '全部商品')}</View>
    <ProductPage key={selected ?? 'all'} categoryId={selected} visible={visible} />
  </View>
}
