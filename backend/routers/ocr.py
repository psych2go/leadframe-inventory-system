import os
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

    with open(filepath, "wb") as f:
        f.write(content)

    try:
        from ocr_service import recognize_image
        result = await recognize_image(filepath)
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

