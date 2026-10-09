import { useState } from 'react'
import Taro, { useDidHide, useDidShow, usePullDownRefresh } from '@tarojs/taro'
import { Input, ScrollView, Swiper, SwiperItem, Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/Button'
import { Popup } from '@nutui/nutui-react-taro/dist/es/packages/popup/popup'
import '@nutui/nutui-react-taro/dist/es/packages/popup/style'
import type { PublicProductDetailRead, ResponseModelPublicProductDetailRead, ResponseModelPageResultProductReviewRead } from '@pinjie/api-client'
import { getPublic, ApiError } from '@/lib/api'
import { queryClient } from '@/lib/query'
import { priceLabel } from '@/lib/money'
import { previewImages } from '@/platform/media'
import { ProductImage } from '@/components/ProductImage'
import { QueryState } from '@/components/QueryState'
import { canSelect, matchingSkus, resolvedSku, specGroups } from './domain/sku'
import type { Selection } from './domain/sku'
import './detail.scss'

function Reviews({ productId, visible }: { productId: string; visible: boolean }) {
  const [page, setPage] = useState(1)
  const query = useQuery({
    queryKey: ['catalog-detail', productId, 'reviews', page],
    queryFn: ({ signal }) => getPublic<ResponseModelPageResultProductReviewRead>(`/products/${productId}/reviews?page=${page}&page_size=10`, signal),
    gcTime: 0, enabled: visible,
  })
  return <View className='surface'>
    <View className='section-title'>商品评价{query.data ? `（${query.data.total}）` : ''}</View>
    {query.isPending && <QueryState title={query.fetchStatus === 'paused' ? '等待网络连接' : '正在加载评价'} />}
    {query.isError && <QueryState title='评价加载失败' error={query.error} retry={() => { void query.refetch() }} />}
    {query.data && !query.isError && <>
      {!query.data.items.length && <View className='muted'>暂无公开评价</View>}
      {query.data.items.map((review) => <View key={review.id} className='review-row'>
        <View className='muted'>{review.rating} / 5 分 · {review.published_at.slice(0, 10)}</View>
        <View>{review.content}</View>
      </View>)}
      {query.data.total > 10 && <View className='category-strip'>
        <Button fill='outline' disabled={page === 1 || query.isFetching} onClick={() => setPage(page - 1)}>上一页评价</Button>
        <Button fill='outline' disabled={page * 10 >= query.data.total || query.isFetching} onClick={() => setPage(page + 1)}>下一页评价</Button>
      </View>}
    </>}
  </View>
}

function DetailContent({ product, visible }: { product: PublicProductDetailRead; visible: boolean }) {
  const [open, setOpen] = useState(false)
  const [selection, setSelection] = useState<Selection>({})
  const [quantity, setQuantity] = useState('1')
  const [confirmed, setConfirmed] = useState<{ selection: Selection; quantity: string }>({ selection: {}, quantity: '1' })
  const groups = specGroups(product.skus)
  const selectedSku = resolvedSku(product.skus, selection)
  const displaySelection = open ? selection : confirmed.selection
  const displaySku = resolvedSku(product.skus, displaySelection)
  const price = displaySku ? `¥${displaySku.price}` : priceLabel(matchingSkus(product.skus, displaySelection).map((sku) => sku.price))
  const validQuantity = /^\d+$/.test(quantity) && Number(quantity) >= 1 && Number(quantity) <= 99
  const canSell = product.skus.some((sku) => sku.is_active)
  function openSheet() { setSelection({ ...confirmed.selection }); setQuantity(confirmed.quantity); setOpen(true) }
  function select(name: string, value: string) {
    const next = { ...selection }
    if (next[name] === value) delete next[name]
    else next[name] = value
    setSelection(next)
    setQuantity('1')
  }
  return <View className='detail-page'>
    {product.images.length ? <Swiper className='detail-hero' indicatorDots indicatorActiveColor='#B42318'>
      {product.images.map((url) => <SwiperItem key={url}><ProductImage url={url} mode='aspectFit' style={{ height: '100%' }} onClick={() => { void previewImages(product.images, url) }} /></SwiperItem>)}
    </Swiper> : <QueryState title='暂无商品主图' />}
    <View className='detail-body'>
      <View className='surface'>
        <View className='price'>{price}</View>
        {displaySku?.market_price && <View className='muted'>参考划线价 ¥{displaySku.market_price}</View>}
        <View className='title'>{product.name}</View>
        <Text className='label'>{product.product_type === 'physical' ? '实物商品 · 需配送' : '虚拟商品 · 无需配送'}</Text>
        <View className='muted'>公开基础价格仅供浏览，库存与成交价格以服务端确认为准。</View>
        {!canSell && <View className='note'>当前暂无可售规格</View>}
      </View>
      <View className='surface'>
        <View className='spec-entry' onClick={() => { if (canSell) openSheet() }}>
          <View><Text className='muted'>规格 </Text>{displaySku ? Object.values(displaySku.specifications).join(' / ') || '默认规格' : '请选择规格'}{displaySku ? ` · ${confirmed.quantity} 件` : ''}</View>
          <Text>{canSell ? '选择 ›' : '不可售'}</Text>
        </View>
      </View>
      {product.attributes.some((item) => !item.is_variant) && <View className='surface'>
        <View className='section-title'>商品参数</View>
        {product.attributes.filter((item) => !item.is_variant).map((item) => <View className='attribute-row' key={item.id}>
          <Text className='muted'>{item.name_snapshot}</Text>
          <Text>{Array.isArray(item.value) ? item.value.map((value) => item.display_snapshot?.[value] ?? value).join('、') : item.value ? item.display_snapshot?.[item.value] ?? item.value : '未提供'}{item.value && item.unit_snapshot ? ` ${item.unit_snapshot}` : ''}</Text>
        </View>)}
      </View>}
      <View className='surface'>
        <View className='section-title'>商品说明</View>
        <View className='muted'>{product.description ? '文字说明暂未开放，请先查看商品参数和详情图片。' : '暂无文字说明'}</View>
      </View>
      <View className='section-title'>商品详情</View>
      {!product.detail_images.length && <View className='surface muted'>暂无详情图片</View>}
      {product.detail_images.map((image) => <View className='detail-slice' key={image.url} style={{ paddingTop: `${image.height / image.width * 100}%` }}>
        <ProductImage url={image.url} mode='widthFix' onClick={() => { void previewImages(product.detail_images.map((item) => item.url), image.url) }} />
      </View>)}
      <Reviews productId={product.id} visible={visible} />
      <View className='note'>当前开放商品浏览。微信登录接入后可使用购物车和下单。</View>
    </View>
    <View className='detail-actions'><Button block type='primary' disabled={!canSell} onClick={openSheet}>{canSell ? '选择商品规格' : '暂无可售规格'}</Button></View>
    <Popup className='sku-popup' visible={open} position='bottom' round closeable onClose={() => setOpen(false)} style={{ height: '80vh' }}>
      <View className='sku-sheet'>
        <View className='sku-header'><ProductImage url={product.images[0]} /><View><View className='price'>{price}</View><View className='sku-name'>{product.name}</View></View></View>
        <ScrollView scrollY className='sku-scroll'>
          {!groups.length && <View className='note'>默认规格</View>}
          {groups.map((group) => <View key={group.name}>
            <View className='section-title'>{group.name}</View>
            <View className='spec-options'>{group.values.map((value) => {
              const active = selection[group.name] === value
              const available = active || canSelect(product.skus, selection, group.name, value)
              return <Button key={value} className={active ? 'spec-active' : ''} fill='outline' disabled={!available} onClick={() => select(group.name, value)}>{value}{!available ? '（组合不可选）' : ''}</Button>
            })}</View>
          </View>)}
          {!!groups.length && <View className='muted'>点击已选规格可取消，再选择其他组合。</View>}
          <View className='section-title'>数量</View>
          <View className='quantity-control'>
            <Button fill='outline' disabled={!validQuantity || Number(quantity) <= 1} onClick={() => setQuantity(String(Number(quantity) - 1))}>−</Button>
            <Input type='number' value={quantity} maxlength={3} onInput={(event) => setQuantity(event.detail.value)} ariaLabel='规格预览数量' />
            <Button fill='outline' disabled={!validQuantity || Number(quantity) >= 99} onClick={() => setQuantity(String(Number(quantity) + 1))}>＋</Button>
          </View>
          {!validQuantity && <View className='note'>请输入 1 至 99 的整数预览数量</View>}
          <View className='muted'>数量仅作本地规格预览；可购买数量和库存待交易接入后由服务端确认。</View>
        </ScrollView>
        <View className='sku-footer'><Button block type='primary' disabled={!selectedSku || !validQuantity} onClick={() => { setConfirmed({ selection: { ...selection }, quantity }); setOpen(false) }}>{selectedSku ? '确认规格' : '请选择完整规格'}</Button></View>
      </View>
    </Popup>
  </View>
}

export function ProductDetail({ productId }: { productId?: string }) {
  const [visible, setVisible] = useState(true)
  const valid = !!productId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(productId)
  useDidShow(() => { setVisible(true) })
  useDidHide(() => { setVisible(false); void queryClient.cancelQueries({ queryKey: ['catalog-detail', productId] }) })
  const query = useQuery({ queryKey: ['catalog-detail', productId, 'product'], enabled: valid && visible,
    queryFn: ({ signal }) => getPublic<ResponseModelPublicProductDetailRead>(`/products/${productId}`, signal) })
  usePullDownRefresh(() => {
    void queryClient.invalidateQueries({ queryKey: ['catalog-detail', productId] }).finally(() => Taro.stopPullDownRefresh())
  })
  if (!valid) return <QueryState title='商品链接无效' detail='请返回商品列表重新选择' />
  if (query.isPending) return <QueryState title={query.fetchStatus === 'paused' ? '等待网络连接' : '正在加载商品'} />
  if (query.isError) return <QueryState title={query.error instanceof ApiError && query.error.status === 404 ? '商品不存在或已下架' : '商品加载失败'} error={query.error} retry={() => { void query.refetch() }} />
  return <DetailContent key={query.data.id} product={query.data} visible={visible} />
}
