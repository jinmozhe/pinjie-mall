import type { ProductImageRead } from "@pinjie/api-client";

export function validateGallery(images: ProductImageRead[], detail: boolean): string | undefined {
  if (images.length > 20) return "每组最多 20 张图片";
  if (new Set(images.map((image) => image.asset_id)).size !== images.length) return "该图片已在本组中，请勿重复选择";
  if (!detail) return undefined;
  if (images.reduce((total, image) => total + image.file_size, 0) > 20 * 1024 * 1024) return "详情图片总体积不能超过 20 MiB";
  for (const image of images) {
    if (!image.width || !image.height || !image.frame_count) return "图片尺寸未核验，请先完成资产尺寸回填";
    if (image.frame_count !== 1) return "详情只支持静态图片";
    if (image.file_size > 2 * 1024 * 1024 || Math.max(image.width, image.height) > 4096 || image.width * image.height > 8_000_000) {
      return "详情单图不得超过 2 MiB、单边 4096 像素及 800 万像素";
    }
  }
  return undefined;
}
