import { useRouter } from '@tarojs/taro'
import { ProductDetail } from '@/features/catalog-detail'
export default function DetailPage() { const router = useRouter(); return <ProductDetail productId={router.params.id} /> }
