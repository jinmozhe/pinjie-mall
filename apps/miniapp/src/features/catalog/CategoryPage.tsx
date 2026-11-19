import { useState } from 'react'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { Button, Input, ScrollView, Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ResponseModelListCategoryRead } from '@pinjie/api-client'
import { Icon } from '@/components/Icon'
import { QueryState } from '@/components/QueryState'
import { getPublic } from '@/lib/api'
import { queryClient } from '@/lib/query'
import { CategoryProducts } from './CategoryProducts'
import { categoryPath } from './domain'
import { takePendingCategorySelection } from './navigation'

export function CategoryPage({ initialCategory }: { initialCategory?: string }) {
  const [visible, setVisible] = useState(true)
  const [selected, setSelected] = useState(() => takePendingCategorySelection() ?? initialCategory)
  const [draft, setDraft] = useState('')
  const [keyword, setKeyword] = useState('')
  const [revision, setRevision] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const categories = useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: ({ signal }) => getPublic<ResponseModelListCategoryRead>('/product-categories', signal),
    enabled: visible,
  })
  useDidShow(() => {
    setVisible(true)
    const pending = takePendingCategorySelection()
    if (pending !== undefined) {
      setSelected(pending)
      setDraft('')
      setKeyword('')
      setRevision((value) => value + 1)
    }
  })
  useDidHide(() => {
    setVisible(false)
    void queryClient.cancelQueries({ queryKey: ['catalog', 'category-products'] })
  })

  const rows = categories.data ?? []
  const path = categoryPath(rows, selected)
  const root = path[0]
  const second = path[1]
  const roots = rows.filter((category) => !category.parent_id)
  const children = root ? rows.filter((category) => category.parent_id === root.id) : []
  const grandchildren = second ? rows.filter((category) => category.parent_id === second.id) : []
  const missing = Boolean(selected && !rows.some((category) => category.id === selected))
  const scope = path.map((category) => category.name).join(' / ') || (selected ? '所选分类' : '全部商品')

  function submitSearch(value: string) {
    const next = value.trim()
    setDraft(next)
    setKeyword(next)
    setRevision((value) => value + 1)
    void Taro.hideKeyboard().catch(() => { void Taro.showToast({ title: '请手动收起键盘', icon: 'none' }) })
  }

  async function refresh() {
    if (refreshing) return
    setRefreshing(true)
    await queryClient.cancelQueries({ queryKey: ['catalog', 'category-products'] })
    await categories.refetch()
    setRevision((value) => value + 1)
    setRefreshing(false)
  }

  const filters = <>
    {children.length > 0 && <ScrollView scrollX className='category-subnav' scrollIntoView={`subcategory-${second?.id ?? 'all'}`}>
      <View className='category-subnav-items'>
        <Button id='subcategory-all' className={`category-filter ${!second ? 'is-selected' : ''}`} ariaLabel={`${root.name}全部商品`} onClick={() => setSelected(root.id)}>全部</Button>
        {children.map((category) => <Button id={`subcategory-${category.id}`} key={category.id} className={`category-filter ${second?.id === category.id ? 'is-selected' : ''}`} onClick={() => setSelected(category.id)}>{category.name}</Button>)}
      </View>
    </ScrollView>}
    {grandchildren.length > 0 && <ScrollView scrollX className='category-subnav' scrollIntoView={`leafcategory-${path[2]?.id ?? 'all'}`}>
      <View className='category-subnav-items'>
        <Button id='leafcategory-all' className={`category-filter ${!path[2] ? 'is-selected' : ''}`} ariaLabel={`${second.name}全部商品`} onClick={() => setSelected(second.id)}>全部</Button>
        {grandchildren.map((category) => <Button id={`leafcategory-${category.id}`} key={category.id} className={`category-filter ${selected === category.id ? 'is-selected' : ''}`} onClick={() => setSelected(category.id)}>{category.name}</Button>)}
      </View>
    </ScrollView>}
  </>

  return <View className='category-page'>
    <View className='category-search'>
      <View className='category-search-field'>
        <Icon name='Search' size={32} />
        <Input className='category-search-input' ariaLabel={`在${scope}中搜索商品名称`} value={draft} maxlength={200} confirmType='search'
          placeholder={selected ? `在“${path[path.length - 1]?.name ?? '所选分类'}”中搜索` : '搜索全部商品'}
          onInput={(event) => setDraft(event.detail.value)} onConfirm={(event) => submitSearch(event.detail.value)} />
        {(draft || keyword) && <Button className='category-clear' ariaLabel='清空搜索' onClick={() => submitSearch('')}><Icon name='Close' size={28} /></Button>}
      </View>
      <Button className='category-search-submit' onClick={() => submitSearch(draft)}>搜索</Button>
    </View>
    {!categories.data ? <QueryState
      title={categories.isError ? '分类加载失败' : categories.fetchStatus === 'paused' ? '等待网络连接' : '正在加载分类'}
      error={categories.isError ? categories.error : undefined}
      retry={categories.isError ? () => { void categories.refetch() } : undefined}
    /> : <>
      {categories.isError && <View className='category-warning'>分类更新失败，当前显示上次内容。<Button className='category-text-action' onClick={() => { void categories.refetch() }}>重试</Button></View>}
      <View className='category-columns'>
        <ScrollView className='category-sidebar' scrollY scrollIntoView={`category-${root?.id ?? 'all'}`}>
          <Button id='category-all' className={`category-menu-item ${!selected ? 'is-selected' : ''}`} onClick={() => setSelected(undefined)}>全部商品</Button>
          {roots.map((category) => <Button id={`category-${category.id}`} key={category.id}
            className={`category-menu-item ${root?.id === category.id ? 'is-selected' : ''}`}
            onClick={() => setSelected(category.id)}>{category.name}</Button>)}
        </ScrollView>
        <View className='category-main'>
          {missing ? <QueryState title='该分类已不可用' detail='分类可能已停用，请选择其他分类。' retry={() => setSelected(undefined)} /> : <CategoryProducts
            key={JSON.stringify([selected, keyword, revision])}
            categoryId={selected} keyword={keyword} scope={scope} visible={visible} revision={revision}
            filters={filters} refreshing={refreshing} onRefresh={() => { void refresh() }}
            clearSearch={() => submitSearch('')} searchAll={() => { setDraft(keyword); setSelected(undefined) }}
          />}
          {!roots.length && <Text className='category-no-categories'>暂无启用分类</Text>}
        </View>
      </View>
    </>}
  </View>
}
