from .schemas import ProductImageRead

DETAIL_MAX_IMAGES = 20
DETAIL_MAX_FILE_BYTES = 2 * 1024 * 1024
DETAIL_MAX_TOTAL_BYTES = 20 * 1024 * 1024
DETAIL_MAX_SIDE = 4096
DETAIL_MAX_PIXELS = 8_000_000


def validate_detail_images(images: list[ProductImageRead]) -> None:
    if len(images) > DETAIL_MAX_IMAGES or len({image.asset_id for image in images}) != len(images):
        raise ValueError("详情图片最多 20 张且不能重复")
    if sum(image.file_size for image in images) > DETAIL_MAX_TOTAL_BYTES:
        raise ValueError("详情图片总体积不能超过 20 MiB")
    for image in images:
        if image.width is None or image.height is None or image.frame_count is None:
            raise ValueError("详情图片缺少可信尺寸，请先完成资产尺寸回填")
        if image.frame_count != 1:
            raise ValueError("详情图片只支持静态图片")
        if (
            image.file_size > DETAIL_MAX_FILE_BYTES
            or max(image.width, image.height) > DETAIL_MAX_SIDE
            or image.width * image.height > DETAIL_MAX_PIXELS
        ):
            raise ValueError("详情单图不得超过 2 MiB、单边 4096 像素及 800 万像素")
