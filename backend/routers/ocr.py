import os
import asyncio
import uuid
import logging

from fastapi import APIRouter, UploadFile, File

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB


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

    try:
        from ocr_service import recognize_image
        # 直接从内存 bytes 调 OCR，不阻塞读盘
        result = await recognize_image(content)
        # OCR 完成后异步存盘，不阻塞响应
        asyncio.create_task(_save_file_async(filepath, content))
        result["image_path"] = filename
        return result
    except Exception as e:
        logger.error("OCR failed: %s", e)
        return {"error": str(e)}


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
