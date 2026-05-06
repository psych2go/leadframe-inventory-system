import os
import re
import base64
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

import httpx

# 从 .env 文件加载环境变量
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logger = logging.getLogger(__name__)

API_URL = os.environ.get("PADDOLEOCR_API_URL", "")
TOKEN = os.environ.get("PADDOLEOCR_TOKEN", "")

# 已知厂家名列表：(匹配模式列表, 标准名称)
# 长名在前，避免短名误匹配
KNOWN_MANUFACTURERS = [
    (["天水华洋电子科技股份有限公司", "天水华洋"], "天水华洋电子科技股份有限公司"),
    (["华天科技(宝鸡)有限公司", "华天科技"], "华天科技(宝鸡)有限公司"),
    (["厦门捷昕精密科技股份有限公司", "厦门捷昕"], "厦门捷昕精密科技股份有限公司"),
    (["泰兴市永志电子器件有限公司", "泰兴市永志", "泰山市永志电子器件有限公司", "泰山市永志"], "泰兴市永志电子器件有限公司"),
    (["FUSHENG"], "中山复盛"),
    (["AAMI", "ASM"], "AAMI"),
]


def _resolve_manufacturer(raw_text: str, extracted: str) -> str:
    """从已知厂家名列表中匹配并归一化厂家名称"""
    # 先去除非文字干扰字符，拼接可能的跨行文本
    raw_joined = re.sub(r"[|\-*#_~`\n\r]+", " ", raw_text)
    raw_joined = re.sub(r"\s+", " ", raw_joined)

    # 已提取到厂家名时，尝试归一化（如 ASM → AAMI, FUSHENG → 中山复盛）
    if extracted:
        extracted_clean = re.sub(r"[|\-*#_~`\n\r]+", " ", extracted).strip()
        for patterns, canonical in KNOWN_MANUFACTURERS:
            for p in patterns:
                if re.search(re.escape(p), extracted_clean, re.IGNORECASE):
                    return canonical
        return extracted_clean if extracted_clean else extracted

    # 关键词未提取到厂家名时，扫描 OCR 原文匹配已知厂家名
    for patterns, canonical in KNOWN_MANUFACTURERS:
        for p in patterns:
            if re.search(re.escape(p), raw_joined, re.IGNORECASE):
                return canonical

    return ""


def _resolve_aami_spec(raw_text: str) -> str:
    """AAMI 厂家专用规格提取规则"""
    clean_text = re.sub(r"[#|`]", " ", raw_text)

    def extract(keywords):
        for keyword in keywords:
            pattern = rf"{re.escape(keyword)}\s*[:：]\s*(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                sub = re.match(r"(.+?)\s+\w+\s*[:：]", val)
                if sub:
                    return sub.group(1).strip()
                return val
            pattern = rf"{re.escape(keyword)}\s+(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    # 优先级1: CUST P/N 或 CUSTOMER P/N
    cust_pn = extract(["CUST P/N", "CUSTOMER P/N"])
    if cust_pn:
        return cust_pn

    # 优先级2: P/N 包含封装类型关键词则用 P/N，否则用 DESC
    pn = extract(["P/N"])
    desc = extract(["DESC", "DESCRIPTION"])

    if pn and any(kw in pn.upper() for kw in ["SOP", "QFP", "DIP", "FN"]):
        return pn

    return desc


def _format_k(val: float) -> str:
    """将 K 单位数值格式化，保留最多 3 位小数，不保留无意义尾零"""
    s = f"{round(val, 3):.3f}".rstrip("0")
    return s[:-1] if s.endswith(".") else s


def _normalize_qty(val: str) -> str:
    val = val.strip()
    # 去除数字中的逗号（如 46,368 → 46368）
    clean = re.sub(r"(?<=\d),(?=\d)", "", val)

    # 万: 3万 → 30, 1.5万 → 15
    m = re.match(r"([\d.]+)\s*万", clean)
    if m:
        return _format_k(float(m.group(1)) * 10)
    # 只: 5000只 → 5, 1500只 → 1.5
    m = re.match(r"([\d.]+)\s*只", clean)
    if m:
        num = float(m.group(1))
        return _format_k(num / 1000)
    # PCS: 46368 PCS → 46.368K（PCS 转 K 需除以 1000）
    m = re.match(r"([\d.]+)\s*(?:PCS|pcs)", clean, re.IGNORECASE)
    if m:
        return _format_k(float(m.group(1)) / 1000)
    # K/KPC/KPD: 已经是K单位，直接取值
    m = re.match(r"([\d.]+)\s*(?:K|KPC|KPD|k|kpc|kpd)", clean, re.IGNORECASE)
    if m:
        return _format_k(float(m.group(1)))
    # 纯数字: 500 → 0.5
    m = re.match(r"([\d.]+)$", clean)
    if m:
        num = float(m.group(1))
        if num >= 1000:
            return _format_k(num / 1000)
        return _format_k(num)
    # 兜底: 尝试提取数字
    m = re.search(r"([\d.]+)", clean)
    if m:
        return _format_k(float(m.group(1)))
    return val


def _normalize_date(raw: str) -> str:
    """将各种日期格式统一为 YYYY-MM-DD"""
    raw = raw.strip()
    if not raw:
        return ""

    # 英文月份映射
    MONTHS_EN = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09", "sept": "09",
        "oct": "10", "nov": "11", "dec": "12",
    }

    # 1. DD-Mon-YYYY / DD-Month-YYYY (e.g. 17-Jun-2022, 05-March-2024)
    m = re.search(r"(\d{1,2})\s*[-/.]\s*([A-Za-z]+)\s*[-/.]\s*(\d{4})", raw)
    if m:
        day, month_str, year = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTHS_EN.get(month_str)
        if month:
            return f"{year}-{month}-{int(day):02d}"

    # 2. Mon DD, YYYY / Month DD, YYYY (e.g. Jun 17, 2022)
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})", raw)
    if m:
        month_str, day, year = m.group(1).lower(), m.group(2), m.group(3)
        month = MONTHS_EN.get(month_str)
        if month:
            return f"{year}-{month}-{int(day):02d}"

    # 3. YYYY/MM/DD or YYYY-MM-DD or YYYY.MM.DD
    m = re.search(r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})", raw)
    if m:
        year, month, day = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"

    # 4. YYYY年MM月DD日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?", raw)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # 5. YYYYMMDD (纯数字8位)
    m = re.search(r"(\d{4})(\d{2})(\d{2})", raw)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"

    # 6. DD/MM/YYYY 或 DD-MM-YYYY（兜底，仅当月份<=12且无法匹配其他格式时）
    m = re.search(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", raw)
    if m:
        day, month, year = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{year}-{month}-{day}"

    return raw


def parse_ocr_markdown(markdown_text: str) -> dict:
    """将 OCR 返回的 Markdown 文本解析为结构化字段"""
    result = {
        "manufacturer": "",
        "spec": "",
        "batch_no": "",
        "quantity": "",
        "production_date": "",
        "expiry_date": "",
    }

    # 只去除 Markdown 标题/代码符号，保留 * 等可能出现在规格中的字符
    clean_text = re.sub(r"[#|`]", " ", markdown_text)

    # 提取冒号后的值，遇到下一个 "Key:" 或 "Key：" 模式时截断
    def extract(keywords):
        for keyword in keywords:
            pattern = rf"{re.escape(keyword)}\s*[:：]\s*(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                # 截断：如果值里还嵌套了 "Key: Value" 模式，只取前面部分
                sub = re.match(r"(.+?)\s+\w+\s*[:：]", val)
                if sub:
                    return sub.group(1).strip()
                return val
            pattern = rf"{re.escape(keyword)}\s+(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    # 生产厂家: SUPPLIER / 生产厂家
    result["manufacturer"] = extract([
        "SUPPLIER", "Supplier", "supplier",
        "生产厂家", "厂家", "生产厂商", "制造商", "厂商",
    ])

    # 规格: Name + Spec 拼接，兜底 Type + Spec
    name_val = extract([
        "Name", "name", "NAME",
        "ITEM", "Item", "item",
        "品名", "产品名称", "名称",
    ])
    type_val = extract([
        "Type", "type", "TYPE",
        "型号", "产品型号",
    ])
    spec_val = extract([
        "Spec", "spec", "SPEC",
        "规格", "规格型号",
    ])
    if name_val and spec_val:
        result["spec"] = f"{name_val} {spec_val}"
    elif name_val:
        result["spec"] = name_val
    elif type_val and spec_val:
        result["spec"] = f"{type_val} {spec_val}"
    elif spec_val:
        result["spec"] = spec_val
    elif type_val:
        result["spec"] = type_val

    # 批号: Lot No. / 批号
    result["batch_no"] = extract([
        "Lot No", "Lot No.", "LOT NO", "Lot Number", "lot no",
        "LOTNO",
        "lot", "Lot", "LOT",
        "批号", "批次号", "批次", "产品批号", "生产批号",
    ])

    # 数量: 支持 K/KPC/KPD/PCS/只/万，统一转为 K 单位
    qty_raw = extract([
        "Q'ty", "Qty", "qty", "QTY",
        "数量", "件数", "总数",
    ])
    if qty_raw:
        qty_raw = qty_raw.strip()
        if "/" in qty_raw:
            qty_raw = qty_raw.split("/", 1)[0].strip()
        result["quantity"] = _normalize_qty(qty_raw)

    # 生产日期
    result["production_date"] = _normalize_date(extract([
        "PD", "pd", "Pd",
        "PLATED DATE", "Plated Date", "plated date",
        "MFG DATE", "MFG date", "mfg date", "MFG. DATE",
        "Production DATE", "production date", "Production date",
        "生产日期", "制造日期", "生产时间",
    ]))

    # 有效日期
    result["expiry_date"] = _normalize_date(extract([
        "EXP", "exp", "Exp",
        "VALID DATE", "Valid Date", "valid date",
        "EXP DATE", "EXP date", "exp date", "EXP. DATE",
        "Expiration DATE", "expiration date", "Expiration date",
        "Expiry DATE", "expiry date", "Expiry date",
        "有效期至", "有效日期", "过期日期", "失效日期", "保质期至", "到期日期",
    ]))

    return result


async def recognize_image(image_path: str) -> dict:
    """调用 PaddleOCR-VL-1.5 云端 API 对图片执行 OCR 识别"""
    if not TOKEN:
        return {"error": "未配置 PaddleOCR API TOKEN，请设置环境变量 PADDOLEOCR_TOKEN"}

    try:
        with open(image_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("ascii")

        headers = {
            "Authorization": f"token {TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "file": file_data,
            "fileType": 1,
            "useDocOrientationClassify": True,
            "useDocUnwarping": False,
            "useLayoutDetection": True,
            "useChartRecognition": True,
            "prettifyMarkdown": True,
        }

        # 连接超时 10 秒，读取超时 120 秒（PaddleOCR 冷启动可能较慢）
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)) as client:
            response = await client.post(API_URL, json=payload, headers=headers)

        if response.status_code != 200:
            logger.error("PaddleOCR API error: %s %s", response.status_code, response.text)
            return {"error": f"OCR 服务返回错误: {response.status_code}"}

        resp_json = response.json()
        if resp_json.get("errorCode", -1) != 0:
            logger.error("PaddleOCR API error: %s", resp_json.get('errorMsg', 'unknown'))
            return {"error": f"OCR 服务错误: {resp_json.get('errorMsg', '未知错误')}"}

        result_data = resp_json["result"]
        markdown_texts = []
        for page in result_data.get("layoutParsingResults", []):
            md = page.get("markdown", {})
            if md.get("text"):
                markdown_texts.append(md["text"])

        full_markdown = "\n".join(markdown_texts)

        # 去除 HTML 标签和图片引用，只保留纯文本
        clean_raw = re.sub(r"<[^>]+>", "", full_markdown)
        clean_raw = re.sub(r"!\[.*?\]\(.*?\)", "", clean_raw)
        clean_raw = re.sub(r"\n{3,}", "\n\n", clean_raw).strip()

        parsed = parse_ocr_markdown(full_markdown)
        parsed["manufacturer"] = _resolve_manufacturer(clean_raw, parsed.get("manufacturer", ""))

        # AAMI 专用规格提取规则
        if parsed["manufacturer"] == "AAMI":
            aami_spec = _resolve_aami_spec(clean_raw)
            if aami_spec:
                parsed["spec"] = aami_spec

        return {
            "raw_text": clean_raw,
            "parsed": parsed,
            "confidence": True,
        }
    except httpx.TimeoutException:
        logger.error("PaddleOCR API timeout")
        return {"error": "OCR 识别超时，请重试"}
    except Exception as e:
        logger.error("OCR recognition failed: %s", e)
        return {"error": str(e)}
