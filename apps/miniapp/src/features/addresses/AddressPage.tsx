import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Input, Picker, Switch, Text, Textarea, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import { areaList } from '@vant/area-data'
import type { AddressInput, AddressRead, ResponseModelAddressRead, ResponseModelListAddressRead, ResponseModelNoneType } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'

const provinces = Object.entries(areaList.province_list)
function cities(index: number) { return Object.entries(areaList.city_list).filter(([code]) => code.slice(0, 2) === provinces[index]?.[0].slice(0, 2)) }
function districts(p: number, c: number) { return Object.entries(areaList.county_list).filter(([code]) => code.slice(0, 4) === cities(p)[c]?.[0].slice(0, 4)) }
function Editor({ original, close }: { original: AddressRead | null; close: () => void }) {
  const [name, setName] = useState(original?.receiver_name ?? '')
  const [mobile, setMobile] = useState(original?.mobile ?? '')
  const [street, setStreet] = useState(original?.street_address ?? '')
  const [isDefault, setDefault] = useState(original?.is_default ?? false)
  const p = Math.max(0, provinces.findIndex(([code]) => code === original?.province_code))
  const c = Math.max(0, cities(p).findIndex(([code]) => code === original?.city_code))
  const d = Math.max(0, districts(p, c).findIndex(([code]) => code === original?.district_code))
  const [indices, setIndices] = useState([p, c, d])
  const [region, setRegion] = useState(original ? { province_code: original.province_code, province: original.province, city_code: original.city_code, city: original.city, district_code: original.district_code, district: original.district } : null)
  const save = useMutation({ mutationFn: async () => {
    if (!region || !name.trim() || !/^\+?[0-9]{6,20}$/.test(mobile.trim()) || !street.trim()) throw new Error('请填写姓名、有效联系电话、地区和详细地址')
    const data: AddressInput = { ...region, receiver_name: name.trim(), mobile: mobile.trim(), street_address: street.trim(), is_default: isDefault }
    await privateRequest<ResponseModelAddressRead>(original ? `/addresses/${original.id}` : '/addresses', { method: original ? 'PUT' : 'POST', data: original ? { ...data, revision: original.revision } : data })
    await queryClient.invalidateQueries({ queryKey: ['private', 'addresses'] }); close()
  } })
  return <View className='page trade-page'><View className='title'>{original ? '编辑收货地址' : '新增收货地址'}</View><View className='surface address-form'>
    <View className='field-label'>收货人</View><Input value={name} maxlength={100} placeholder='姓名' ariaLabel='收货人姓名' onInput={(event) => setName(event.detail.value)} />
    <View className='field-label'>联系电话</View><Input value={mobile} maxlength={21} placeholder='手机号或含区号的联系电话' ariaLabel='收货联系电话' onInput={(event) => setMobile(event.detail.value)} />
    <View className='field-label'>所在地区</View><Picker mode='multiSelector' value={indices} range={[provinces.map(([, label]) => label), cities(indices[0]).map(([, label]) => label), districts(indices[0], indices[1]).map(([, label]) => label)]} onColumnChange={(event) => { const { column, value } = event.detail; setIndices((current) => column === 0 ? [value, 0, 0] : column === 1 ? [current[0], value, 0] : [current[0], current[1], value]) }} onChange={(event) => {
      const [pi, ci, di] = event.detail.value
      const province = provinces[pi], city = cities(pi)[ci], district = districts(pi, ci)[di]
      if (!province || !city || !district) { setRegion(null); return }
      setIndices([pi, ci, di]); setRegion({ province_code: province[0], province: province[1], city_code: city[0], city: city[1], district_code: district[0], district: district[1] })
    }}><View className='touch link'>{region ? `${region.province} ${region.city} ${region.district}` : '请选择省、市、区县'} ›</View></Picker>
    <View className='field-label'>详细地址</View><Textarea value={street} maxlength={300} autoHeight placeholder='街道、门牌号等' ariaLabel='详细收货地址' onInput={(event) => setStreet(event.detail.value)} />
    <View className='trade-row spread touch'><Text>设为默认地址</Text><Switch checked={isDefault} color='#B42318' onChange={(event) => setDefault(event.detail.value)} /></View></View>
    {save.isError && <QueryState title='地址保存未完成' error={save.error} detail='版本冲突时返回重新读取。网络失败时请先返回核对已有地址，再决定是否重试。' />}
    <View className='trade-footer'><Button block type='primary' disabled={save.isPending} loading={save.isPending} onClick={() => save.mutate()}>保存地址</Button><Button block fill='outline' disabled={save.isPending} onClick={close}>返回地址列表</Button></View>
  </View>
}
function Content() {
  const session = useSession()
  const [editing, setEditing] = useState<AddressRead | null | undefined>()
  const query = useQuery({ queryKey: ['private', 'addresses', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelListAddressRead>('/addresses', { signal }) })
  useDidShow(() => { void query.refetch() })
  const remove = useMutation({ mutationFn: async (address: AddressRead) => {
    const answer = await Taro.showModal({ title: '删除地址', content: `确认删除 ${address.receiver_name} 的收货地址？` })
    if (!answer.confirm || session.epoch !== sessionScope()) return
    await privateRequest<ResponseModelNoneType>(`/addresses/${address.id}?revision=${address.revision}`, { method: 'DELETE' })
  }, onSettled: () => queryClient.invalidateQueries({ queryKey: ['private', 'addresses'] }) })
  if (editing !== undefined) return <Editor original={editing} close={() => { setEditing(undefined); void query.refetch() }} />
  return <View className='page trade-page'><View className='title'>收货地址</View><View className='muted'>最多保存 20 个地址</View>
    {query.isPending && <QueryState title='正在读取收货地址' />}{query.isError && <QueryState title='地址读取失败' error={query.error} retry={() => { void query.refetch() }} />}{remove.error && <QueryState title='删除未完成，请重新读取地址确认' error={remove.error} />}
    {query.data && !query.isError && <>{!query.data.length && <QueryState title='还没有收货地址' detail='添加地址，实物商品下单更方便' />}{query.data.map((address) => <View className='surface' key={address.id}><View className='trade-row spread'><View>{address.receiver_name} · {address.mobile}</View>{address.is_default && <Text className='label'>默认</Text>}</View><View className='muted'>{address.province}{address.city}{address.district}{address.street_address}</View><View className='category-strip'><Button fill='outline' disabled={remove.isPending} onClick={() => setEditing(address)}>编辑</Button><Button fill='outline' disabled={remove.isPending} onClick={() => remove.mutate(address)}>删除</Button></View></View>)}</>}
    <View className='trade-footer'><Button type='primary' block disabled={query.isPending || query.isError || remove.isPending || (query.data?.length ?? 20) >= 20} onClick={() => setEditing(null)}>新增地址</Button></View>
  </View>
}
export function AddressPage() { const session = useSession(); return <AuthGate><Content key={session.epoch} /></AuthGate> }
