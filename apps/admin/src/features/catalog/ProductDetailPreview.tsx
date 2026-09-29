import type { ProductImageRead } from "@pinjie/api-client";
import { Empty, Image, theme } from "antd";

export function ProductDetailPreview({ description, images }: { description: string; images: ProductImageRead[] }) {
  const { token } = theme.useToken();
  return <div style={{ width: "100%", maxWidth: 375, marginInline: "auto", background: token.colorBgContainer, border: "1px solid " + token.colorBorder }}>
    {description && (
      <div
        dangerouslySetInnerHTML={{ __html: description }}
        style={{
          padding: token.paddingSM,
          fontSize: 14,
          lineHeight: 1.75,
          color: token.colorText,
          wordBreak: "break-all",
          overflowWrap: "anywhere",
        }}
      />
    )}
    {!images.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无详情图片" />}
    <Image.PreviewGroup>{images.map((image) => <div key={image.asset_id} style={{ width: "100%", aspectRatio: image.width && image.height ? image.width + " / " + image.height : undefined }}>
      <Image src={image.url} alt={image.original_name} width="100%" style={{ display: "block", width: "100%", height: "auto" }}
        styles={{ root: { display: "block", width: "100%" } }} />
    </div>)}</Image.PreviewGroup>
  </div>;
}
