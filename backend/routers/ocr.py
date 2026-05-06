import os
import uuid
import logging
import tempfile

from fastapi import APIRouter, UploadFile, File
from PIL import Image

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


def _compress_for_ocr(image_path: str, max_size: int = 1024, quality: int = 70) -> str:
    """将图片压缩到指定尺寸，返回临时文件路径。用于减小传给 OCR API 的体积。"""
    img = Image.open(image_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_size:
        ratio = max_size / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(tmp, format="JPEG", quality=quality)
    tmp.close()
    return tmp.name


@router.post("/ocr")
async def ocr_recognize(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        return {"error": "请上传图片文件"}

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        return {"error": "图片文件不能超过 20MB"}

    ext = os.path.splitext(file.filename or "image.jpg")[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    try:
        from ocr_service import recognize_image
        # 二次压缩供 OCR 使用，保留原图存档
        compressed = _compress_for_ocr(filepath)
        try:
            result = await recognize_image(compressed)
        finally:
            os.unlink(compressed)
        result["image_path"] = filename
        return result
    except Exception as e:
        # OCR 失败时清理已上传的文件
        try:
            os.remove(filepath)
        except OSError:
            pass
        logger.error("OCR failed: %s", e)
        return {"error": str(e)}
