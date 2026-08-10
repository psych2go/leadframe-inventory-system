import os
import asyncio
import uuid
import logging
import io
import warnings

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from routers.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIMENSION = 8_000
OUTPUT_MAX_DIMENSION = 2_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _normalize_image(content: bytes) -> bytes:
    """验证真实图片内容并统一转码，阻断主动内容和图片压缩炸弹。"""
    if not content:
        raise HTTPException(400, "图片内容为空")

    try:
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as probe:
                image_format = (probe.format or "").upper()
                if image_format not in ALLOWED_IMAGE_FORMATS:
                    raise HTTPException(400, "仅支持 JPEG、PNG、WEBP 图片")
                probe.verify()

            with Image.open(io.BytesIO(content)) as source:
                source.load()
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise HTTPException(400, "图片尺寸过大")

                image = ImageOps.exif_transpose(source)
                if image.mode in ("RGBA", "LA"):
                    rgba = image.convert("RGBA")
                    background = Image.new("RGB", rgba.size, "white")
                    background.paste(rgba, mask=rgba.getchannel("A"))
                    image = background
                elif image.mode != "RGB":
                    image = image.convert("RGB")
                else:
                    image = image.copy()

                image.thumbnail(
                    (OUTPUT_MAX_DIMENSION, OUTPUT_MAX_DIMENSION),
                    Image.Resampling.LANCZOS,
                )
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=90, optimize=True)
                return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        raise HTTPException(400, "图片文件无效或已损坏")


@router.post("/ocr")
async def ocr_recognize(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        return {"error": "请上传图片文件"}

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "图片文件不能超过 20MB")

    normalized_content = await asyncio.to_thread(_normalize_image, content)
    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = os.path.join(UPLOAD_DIR, filename)

    try:
        from ocr_service import recognize_image
        # 直接从内存 bytes 调 OCR，不阻塞读盘
        result = await recognize_image(normalized_content)
        if result.get("error"):
            return result
        # OCR 完成后异步存盘，不阻塞响应
        asyncio.create_task(_save_file_async(filepath, normalized_content))
        result["image_path"] = filename
        return result
    except Exception as e:
        logger.error("OCR failed: %s", e)
        raise HTTPException(502, "OCR 服务调用失败")


async def _save_file_async(path: str, data: bytes):
    """异步保存上传的图片文件，异常仅记录不抛出"""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_file, path, data)
    except Exception as e:
        logger.error("Failed to save uploaded file %s: %s", path, e)


def _write_file(path: str, data: bytes):
    """同步写文件（在 run_in_executor 中执行）"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
