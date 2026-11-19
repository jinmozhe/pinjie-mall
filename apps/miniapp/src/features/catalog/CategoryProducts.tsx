import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import Taro from '@tarojs/taro'
import { Button, ScrollView, Text, View } from '@tarojs/components'
import { useInfiniteQuery, type InfiniteData } from '@tanstack/react-query'
import type { PageResultPublicProductRead, ResponseModelPageResultPublicProductRead } from '@pinjie/api-client'
import { Icon } from '@/components/Icon'
import { ProductImage } from '@/components/ProductImage'
import { QueryState } from '@/components/QueryState'
import { getPublic } from '@/lib/api'
import { CATEGORY_MAX_PAGES, CATEGORY_PAGE_SIZE, nextProductPage, productPrice, uniqueProducts } from './domain'

type Direction = 'next' | 'previous'
type Rect = { id: string; top: number; bottom: number; height: number }
type WindowAnchor = { row: Rect; viewport: Rect }
type WindowData = InfiniteData<PageResultPublicProductRead>

function rect(value: unknown): Rect {
  if (!value || typeof value !== 'object' || !('top' in value) || typeof value.top !== 'number'
    || !('bottom' in value) || typeof value.bottom !== 'number'
    || !('height' in value) || typeof value.height !== 'number') {
    throw new Error('无法读取列表位置，请刷新后重试')
  }
  return { id: 'id' in value && typeof value.id === 'string' ? value.id : '', top: value.top, bottom: value.bottom, height: value.height }
}

function layout(): Promise<{ viewport: Rect; content: Rect; rows: Rect[]; scrollTop: number }> {
  return new Promise((resolve, reject) => {
    const query = Taro.createSelectorQuery()
    query.select('#category-products-scroll').boundingClientRect()
    query.select('#category-products-content').boundingClientRect()
    query.selectAll('.category-product-row').boundingClientRect()
    query.select('#category-products-scroll').scrollOffset()
    query.exec((values: unknown[]) => {
      try {
        if (!Array.isArray(values[2])) throw new Error('无法读取商品位置，请刷新后重试')
        const offset = values[3]
        if (!offset || typeof offset !== 'object' || !('scrollTop' in offset) || typeof offset.scrollTop !== 'number') {
          throw new Error('无法读取滚动位置，请刷新后重试')
        }
        resolve({ viewport: rect(values[0]), content: rect(values[1]), rows: values[2].map(rect), scrollTop: offset.scrollTop })
      } catch (error) { reject(error) }
    })
  })
}

const rendered = () => new Promise<void>((resolve) => Taro.nextTick(resolve))

export function CategoryProducts({
  categoryId, keyword, scope, visible, revision, filters, refreshing, onRefresh, clearSearch, searchAll,
}: {
  categoryId?: string; keyword: string; scope: string; visible: boolean; revision: number; filters: ReactNode
  refreshing: boolean; onRefresh: () => void; clearSearch: () => void; searchAll: () => void
}) {
  const [scrollTop, setScrollTop] = useState(0)
  const [direction, setDirection] = useState<Direction>()
  const [positionError, setPositionError] = useState('')
  const [navigationError, setNavigationError] = useState('')
  const [navigating, setNavigating] = useState(false)
  const busy = useRef(false)
  const navigationPending = useRef(false)
  const preservePosition = useRef(false)
  const windowAnchor = useRef<WindowAnchor>()
  const committedData = useRef<WindowData>()
  const commitWaiter = useRef<{ data: WindowData; resolve: () => void }>()
  const live = useRef(true)
  const shown = useRef(visible)
  useEffect(() => { shown.current = visible }, [visible])
  useEffect(() => {
    live.current = true
    return () => { live.current = false; commitWaiter.current?.resolve(); commitWaiter.current = undefined }
  }, [])
  const query = useInfiniteQuery({
    queryKey: ['catalog', 'category-products', categoryId ?? 'all', keyword, revision],
    initialPageParam: 1,
    queryFn: async ({ pageParam, signal }) => {
      const page = await getPublic<ResponseModelPageResultPublicProductRead>(
        `/products?page=${pageParam}&page_size=${CATEGORY_PAGE_SIZE}${categoryId ? `&category_id=${encodeURIComponent(categoryId)}` : ''}${keyword ? `&search=${encodeURIComponent(keyword)}` : ''}`, signal,
      )
      if (page.page !== pageParam || page.page_size !== CATEGORY_PAGE_SIZE) throw new Error('商品分页响应无效，请刷新后重试')
      if (pageParam > 1 && !page.items.length) throw new Error('商品列表已变化，请刷新商品')
      if (preservePosition.current && shown.current) {
        // Capture after the network wait, so scrolling while loading is not undone.
        const before = await layout()
        const row = before.rows.find((item) => item.bottom > before.viewport.top + 1 && item.top < before.viewport.bottom)
        if (!row) throw new Error('无法保留当前浏览位置，请刷新后重试')
        windowAnchor.current = { row, viewport: before.viewport }
      }
      return page
    },
    getNextPageParam: nextProductPage,
    getPreviousPageParam: (page) => page.page > 1 ? page.page - 1 : undefined,
    maxPages: CATEGORY_MAX_PAGES,
    enabled: visible,
    // Keep the current browsing window on detail return. Refresh explicitly starts at page one.
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const pages = query.data?.pages
  const products = uniqueProducts(pages ?? [])
  const total = pages?.[pages.length - 1]?.total

  useEffect(() => {
    committedData.current = query.data
    if (commitWaiter.current?.data === query.data) {
      commitWaiter.current?.resolve()
      commitWaiter.current = undefined
    }
  }, [query.data])

  const load = useCallback(async (nextDirection: Direction, retry = false) => {
    if (!shown.current || busy.current || query.isFetching || query.fetchStatus === 'paused' || refreshing || positionError) return
    if (nextDirection === 'next' ? !query.hasNextPage : !query.hasPreviousPage) return
    if (!retry && query.isError) return
    busy.current = true
    setDirection(nextDirection)
    try {
      preservePosition.current = nextDirection === 'previous' || (query.data?.pages.length ?? 0) >= CATEGORY_MAX_PAGES
      const result = nextDirection === 'next'
        ? await query.fetchNextPage({ cancelRefetch: false })
        : await query.fetchPreviousPage({ cancelRefetch: false })
      const anchor = windowAnchor.current
      if (!live.current || !shown.current || result.isError || !anchor || !result.data) return
      if (committedData.current !== result.data) {
        await new Promise<void>((resolve) => { commitWaiter.current = { data: result.data, resolve } })
      }
      if (!live.current || !shown.current) return
      await rendered()
      const after = await layout()
      const moved = after.rows.find((row) => row.id === anchor.row.id)
      if (!moved) throw new Error('商品列表已变化，请刷新商品')
      const target = Math.max(0, after.scrollTop + (moved.top - after.viewport.top) - (anchor.row.top - anchor.viewport.top))
      // First synchronize the prop with native scrolling, then issue a distinct scroll command.
      setScrollTop(after.scrollTop)
      await rendered()
      if (!live.current) return
      setScrollTop(target)
      await rendered()
    } catch (error) {
      if (live.current && shown.current) setPositionError(error instanceof Error ? error.message : '列表位置更新失败，请刷新后重试')
    } finally {
      busy.current = false
      preservePosition.current = false
      windowAnchor.current = undefined
      if (live.current) setDirection(undefined)
    }
  }, [query, refreshing, positionError])

  useEffect(() => {
    if (!visible || !pages || query.isFetching || query.isError || direction || positionError || refreshing || !query.hasNextPage) return
    let active = true
    // A short first page must not leave undisplayed pages unreachable without a scroll gesture.
    void rendered().then(layout).then(({ viewport, content }) => {
      if (active && viewport.height > 0 && content.height <= viewport.height + 1) void load('next')
    }).catch((error: unknown) => {
      if (active) setPositionError(error instanceof Error ? error.message : '无法读取列表高度，请刷新后重试')
    })
    return () => { active = false }
  }, [visible, pages, query.isFetching, query.isError, query.hasNextPage, direction, positionError, refreshing, load])

  async function openProduct(id: string) {
    if (navigationPending.current || busy.current) return
    navigationPending.current = true
    setNavigating(true)
    setNavigationError('')
    try {
      await Taro.navigateTo({ url: `/subpackages/catalog/detail/index?id=${encodeURIComponent(id)}` })
    } catch {
      if (live.current) setNavigationError('打开商品失败，请再次点击商品')
    } finally {
      navigationPending.current = false
      if (live.current) setNavigating(false)
    }
  }

  return <>
    <View className='category-heading'>
      <View className='category-scope'>{scope}</View>
      <Text className='category-count'>{total === undefined ? '正在查询' : `${keyword ? '找到' : '共'} ${total} 件商品`}</Text>
      {keyword && <View className='category-keyword'>搜索：{keyword}</View>}
    </View>
    {filters}
    {navigationError && <View className='category-warning'>{navigationError}</View>}
    {positionError && <View className='category-warning'>{positionError}<Button className='category-text-action' onClick={onRefresh}>刷新商品</Button></View>}
    <ScrollView id='category-products-scroll' className='category-products-scroll' scrollY scrollTop={scrollTop}
      lowerThreshold={120} upperThreshold={80} scrollWithAnimation={false}
      onScrollToLower={() => { void load('next') }} onScrollToUpper={() => { void load('previous') }}
      refresherEnabled={!query.hasPreviousPage && !direction} refresherTriggered={refreshing} onRefresherRefresh={onRefresh}>
      <View id='category-products-content'>
        {query.isPending && <QueryState title={query.fetchStatus === 'paused' ? '等待网络连接' : '正在加载商品'} />}
        {!pages && query.isError && <QueryState title='商品加载失败' error={query.error} retry={() => { void query.refetch() }} />}
        {pages && <>
          {query.hasPreviousPage && <View className='category-load-state'>
            {query.isFetchPreviousPageError ? <Button className='category-text-action' onClick={() => { void load('previous', true) }}>前面商品加载失败，点击重试</Button>
              : direction === 'previous' ? '正在加载前面的商品…' : '向上滑动查看前面的商品'}
          </View>}
          {!products.length && <View className='category-empty'>
            <Icon name='Search' size={56} />
            <View className='category-empty-title'>{keyword ? '未找到相关商品' : '暂无商品'}</View>
            <View className='muted'>{keyword ? `“${scope}”中未找到“${keyword}”` : '当前范围暂无公开上架商品'}</View>
            {keyword && categoryId && <Button className='category-empty-primary' onClick={searchAll}>在全部商品中搜索</Button>}
            {keyword && <Button className='category-text-action' onClick={clearSearch}>清空搜索</Button>}
          </View>}
          {products.map((product) => {
            const price = productPrice(product)
            return <View id={`product-${product.id}`} key={product.id} className='category-product-row'
              role='button' ariaLabel={`查看${product.name}详情`} onClick={() => { void openProduct(product.id) }}>
              <View className='category-product-image'><ProductImage url={product.images[0]} /></View>
              <View className='category-product-info'>
                <View className='category-product-name'>{product.name}</View>
                <View className='category-product-meta'>{product.product_type === 'physical' ? '实物商品' : '虚拟商品'}{price.multiple ? ' · 多规格可选' : ''}</View>
                <View className='category-product-bottom'>
                  <View className='category-product-prices'>
                    <View className='category-product-price'>{price.label}</View>
                    {price.market && <Text className='category-market-price'>¥{price.market}</Text>}
                  </View>
                  <Button className='category-product-open' ariaLabel={`查看${product.name}详情`} disabled={navigating || Boolean(direction)}
                    onClick={(event) => { event.stopPropagation(); void openProduct(product.id) }}>
                    <View className='category-plus'><Icon name='Plus' size={32} /></View>
                  </Button>
                </View>
              </View>
            </View>
          })}
          {products.length > 0 && <View className='category-load-state'>
            {query.fetchStatus === 'paused' ? '等待网络连接'
              : query.isFetchNextPageError ? <Button className='category-text-action' onClick={() => { void load('next', true) }}>加载失败，点击重试</Button>
              : direction === 'next' ? '正在加载更多商品…'
              : query.hasNextPage ? '向下滑动加载更多'
              : `已经到底了 · 共 ${total} 件商品`}
          </View>}
          {pages && query.isError && <View className='category-warning'>{query.error.message}</View>}
          {products.length > 0 && <Button className='category-text-action category-refresh' disabled={refreshing || Boolean(direction)} onClick={onRefresh}>刷新商品</Button>}
        </>}
      </View>
    </ScrollView>
  </>
}
