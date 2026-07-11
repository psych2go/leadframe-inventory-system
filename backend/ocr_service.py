import os
import re
import json
import logging
import asyncio
import math
from pathlib import Path
from collections import defaultdict

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


def _ocr_env(key: str, default: str = "") -> str:
    """读取 OCR 环境变量：优先规范名 PADDLEOCR_*，回退到历史拼写 PADDOLEOCR_*。

    历史上变量名误拼为 PADDOLEOCR_*（多了一个 O），已部署的 .env 仍在使用。
    这里做向后兼容：新部署用 PADDLEOCR_*，旧部署的 PADDOLEOCR_* 继续生效。
    """
    return os.environ.get(f"PADDLEOCR_{key}") or os.environ.get(f"PADDOLEOCR_{key}", default)


API_URL = _ocr_env("API_URL")
TOKEN = _ocr_env("TOKEN")
MODEL = _ocr_env("MODEL", "PP-OCRv5")

# 复用连接池，轮询场景需要较长超时
_http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0))


async def close_http_client():
    """应用关闭时清理 HTTP 连接池"""
    try:
        await _http_client.aclose()
    except Exception as e:
        logger.warning("Error closing HTTP client: %s", e)

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
            esc = re.escape(keyword)
            pattern = rf"\b{esc}\.?\s*[:：]\s*(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                val = match.group(1).strip().lstrip(":：")
                sub = re.match(r"(.+?)\s+\w+\s*[:：]", val)
                if sub:
                    return sub.group(1).strip()
                return val
            pattern = rf"\b{esc}\s+(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            # 兜底：关键词与值直接相连无分隔符
            pattern = rf"(?<!\w){esc}([A-Z0-9].*?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    # 优先级1: CUSTP/N 或 CUST P/N 或 CUSTOMER P/N
    cust_pn = extract(["CUSTP/N", "CUST P/N", "CUSTOMER P/N"])
    if cust_pn:
        return cust_pn

    # 优先级2: P/N 包含封装类型关键词则用 P/N，否则用 DESC
    pn = extract(["P/N"])
    desc = extract(["DESC", "DESCRIPTION"])

    if pn and any(kw in pn.upper() for kw in ["SOP", "QFP", "DIP", "FN"]):
        return pn

    return desc


def _normalize_box(box):
    """将各种坐标格式统一为 [x_min, y_min, x_max, y_max]"""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    if all(isinstance(v, (int, float)) for v in box):
        return list(box)
    if all(isinstance(v, (list, tuple)) and len(v) == 2 for v in box):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        return [min(xs), min(ys), max(xs), max(ys)]
    return None


def _box_center(box):
    """返回文本块的中心点 (cx, cy)"""
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _box_size(box):
    """返回文本块宽高"""
    return (box[2] - box[0], box[3] - box[1])


def _is_cjk(ch):
    """判断字符是否为 CJK 统一汉字"""
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
            or 0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF)


def _smart_join(texts):
    """智能拼接：中文字符间不加空格，英文/数字间加空格"""
    if not texts:
        return ""
    result = texts[0]
    for t in texts[1:]:
        if result and t and _is_cjk(result[-1]) and _is_cjk(t[0]):
            result += t
        else:
            result += " " + t
    return result


def _merge_blocks_by_coords(text_blocks):
    """基于 Y 轴重合度分行，每行按 X 坐标排序后拼接文本

    使用行基准线（Y 中心均值）判断新块归属，避免 any() 链式塌陷：
    倾斜标签下 A-B 重合、B-C 重合但 A-C 不重合，any() 会把三者串成一行。
    改为只与基准线比较，确保所有同行块都与行的整体位置对齐。
    """
    if not text_blocks:
        return []

    sorted_blocks = sorted(
        text_blocks,
        key=lambda b: (b["box"][1] + b["box"][3]) / 2,
    )

    lines = []
    current_line = [sorted_blocks[0]]

    def _line_baseline():
        """当前行所有块的 Y 中心均值"""
        return sum((b["box"][1] + b["box"][3]) / 2 for b in current_line) / len(current_line)

    def _line_bbox():
        """当前行的合并 Y 范围 [y_min, y_max]"""
        ymin = min(b["box"][1] for b in current_line)
        ymax = max(b["box"][3] for b in current_line)
        return [ymin, ymax]

    for block in sorted_blocks[1:]:
        bbox = _line_bbox()
        overlap = max(0, min(bbox[1], block["box"][3]) - max(bbox[0], block["box"][1]))
        line_height = bbox[1] - bbox[0]
        block_height = block["box"][3] - block["box"][1]
        min_h = min(line_height, block_height)
        ratio = overlap / min_h if min_h > 0 else 0
        if ratio > 0.4:
            current_line.append(block)
        else:
            current_line.sort(key=lambda b: b["box"][0])
            lines.append(_smart_join([b["text"] for b in current_line]))
            current_line = [block]

    if current_line:
        current_line.sort(key=lambda b: b["box"][0])
        lines.append(_smart_join([b["text"] for b in current_line]))

    return lines


def _merge_by_colon(ocr_texts):
    """无坐标时的兜底合并：以冒号结尾的文本与下一项拼接"""
    lines = []
    i = 0
    while i < len(ocr_texts):
        text = ocr_texts[i].strip()
        i += 1
        if text and (text.endswith(':') or text.endswith('：')) and i < len(ocr_texts):
            text += ' ' + ocr_texts[i].strip()
            i += 1
        lines.append(text)
    return lines


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


# ===================== 空间感知 OCR 解析（方案 A/B/C）=====================

# 字段标签模式：优先级靠前的优先匹配
_FIELD_PATTERNS = {
    "manufacturer": [
        ("SUPPLIER", "en"), ("Supplier", "en"), ("supplier", "en"),
        ("生产厂家", "cn"), ("厂家", "cn"), ("生产厂商", "cn"), ("制造商", "cn"), ("厂商", "cn"),
    ],
    "spec": [
        ("CUSTP/N", "en"), ("CUST P/N", "en"), ("CUSTOMER P/N", "en"),
        ("P/N", "en"), ("Part No", "en"), ("Part Number", "en"), ("PN", "en"),
        ("DESC", "en"), ("DESCRIPTION", "en"),
        ("Name", "en"), ("NAME", "en"),
        ("ITEM", "en"), ("Item", "en"),
        ("Type", "en"), ("TYPE", "en"),
        ("Spec", "en"), ("SPEC", "en"),
        ("规格", "cn"), ("规格型号", "cn"), ("产品型号", "cn"), ("型号", "cn"),
        ("品名", "cn"), ("产品名称", "cn"), ("名称", "cn"),
    ],
    "batch_no": [
        ("Lot No", "en"), ("LOT NO", "en"), ("Lot Number", "en"),
        ("LOTNO", "en"), ("LotNo", "en"),
        ("Lot", "en"), ("LOT", "en"), ("lot", "en"),
        ("批号", "cn"), ("批次号", "cn"), ("批次", "cn"), ("产品批号", "cn"), ("生产批号", "cn"),
    ],
    "quantity": [
        ("Q'ty", "en"), ("Qty", "en"), ("qty", "en"), ("QTY", "en"),
        ("Quantity", "en"), ("数量", "cn"), ("件数", "cn"), ("总数", "cn"),
    ],
    "production_date": [
        ("PD", "en"), ("PLATED DATE", "en"),
        ("MFGDATE", "en"), ("MFG DATE", "en"), ("MFG. DATE", "en"), ("MfgDate", "en"),
        ("ProductionDate", "en"), ("Production DATE", "en"), ("Production date", "en"),
        ("生产日期", "cn"), ("制造日期", "cn"), ("生产时间", "cn"),
    ],
    "expiry_date": [
        ("EXP", "en"), ("EXPDATE", "en"), ("EXP DATE", "en"), ("EXP. DATE", "en"), ("ExpDate", "en"),
        ("VALID DATE", "en"), ("Valid Date", "en"),
        ("ExpirationDate", "en"), ("Expiration DATE", "en"), ("Expiration date", "en"),
        ("ExpiryDate", "en"), ("Expiry DATE", "en"), ("Expiry date", "en"),
        ("有效期至", "cn"), ("有效日期", "cn"), ("过期日期", "cn"), ("失效日期", "cn"), ("保质期至", "cn"), ("到期日期", "cn"),
    ],
}

# 字段值的后验验证 / 清理
_VALUE_FILTERS = {
    "quantity": re.compile(r"[\d.,/\s]+(?:[Kk]?\s*(?:PCS|pcs|只|万|条|KPC|KPD)?)?"),
    "batch_no": re.compile(r"[A-Za-z0-9\-_.]+"),
    "production_date": re.compile(r"[\d\-/.A-Za-z,\s]+"),
    "expiry_date": re.compile(r"[\d\-/.A-Za-z,\s]+"),
}


def _detect_columns(text_blocks, n_clusters=2):
    """检测文本块是否存在明显的多列布局（方案 B）。

    使用一维 K-Means（X 中心）把块分为左右两簇，若两簇中心距离 > 阈值则认为是两栏。
    返回列边界列表（x 范围），或 None 表示未检测到明显分栏。
    """
    if not text_blocks or len(text_blocks) < 4:
        return None

    centers = [_box_center(b["box"])[0] for b in text_blocks]
    w = max(centers) - min(centers) if max(centers) > min(centers) else 1
    if w < 30:
        return None

    # 一维 k-means，k=2，初始点取 1/3 和 2/3
    centers_arr = sorted(centers)
    c1, c2 = centers_arr[len(centers_arr) // 3], centers_arr[2 * len(centers_arr) // 3]
    for _ in range(20):
        g1, g2 = [], []
        for x in centers_arr:
            (g1 if abs(x - c1) <= abs(x - c2) else g2).append(x)
        if not g1 or not g2:
            break
        c1, c2 = sum(g1) / len(g1), sum(g2) / len(g2)
        if c1 == c2:
            break

    gap = abs(c2 - c1)
    if gap / w < 0.25:
        return None

    left_x = [x for x in centers_arr if abs(x - c1) <= abs(x - c2)]
    right_x = [x for x in centers_arr if abs(x - c2) < abs(x - c1)]
    return [
        (min(left_x) - 10, max(left_x) + 10),
        (min(right_x) - 10, max(right_x) + 10),
    ]


def _match_label_block(block, field):
    """判断一个文本块是否匹配某字段的标签模式。返回 (匹配到的关键词, 置信度 0-1)。"""
    text = block["text"]
    # 中文字符串不能用 \b 做边界，因此对中文按子串匹配，英文按单词边界
    for kw, lang in _FIELD_PATTERNS[field]:
        escaped = re.escape(kw)
        if lang == "cn":
            # 中文：直接包含即算匹配，但防止更短的关键词覆盖更长的（如"厂家"匹配到"生产厂商"仍允许，
            # 外层调用按最长关键词优先，因为 _FIELD_PATTERNS 里长词在前）
            if kw in text:
                return kw, 1.0
        else:
            # 英文/数字：按单词边界，同时支持后接冒号/空格/结束
            if re.search(rf"(?<!\w){escaped}(?!\w)|(?<!\w){escaped}\s*[:：]|(?<!\w){escaped}\s*$", text, re.IGNORECASE):
                return kw, 1.0
            if text.lower() == kw.lower():
                return kw, 1.0
    return None, 0.0


def _find_value_by_proximity(label_block, candidates, direction="right", max_dist_factor=12.0):
    """基于空间邻近度为标签块寻找最可能的值块（方案 A）。

    direction: right|below|both
    max_dist_factor: 最大距离倍数，基于标签块高度

    评分综合考虑：
    - 空间距离（越小越好）
    - 水平/垂直对齐（同列/同行更好）
    - 值块是否像该字段的值（通过 _VALUE_FILTERS 初筛）
    """
    if not candidates:
        return None, 0.0

    lb = label_block["box"]
    lcx, lcy = _box_center(lb)
    lw, lh = _box_size(lb)
    best = None
    best_score = -1.0

    for cand in candidates:
        cb = cand["box"]
        ccx, ccy = _box_center(cb)
        cw, ch = _box_size(cb)

        dx = ccx - lcx
        dy = ccy - lcy

        # 方向过滤：默认优先右侧/下方，但也允许同行右侧小偏移
        if direction == "right" and dx < -lw * 0.3:
            continue
        if direction == "below" and dy < -lh * 0.3:
            continue

        # 距离打分：以标签高度为基准
        dist = math.hypot(dx / max(lh, 1), dy / max(lh, 1))
        if dist > max_dist_factor:
            continue

        # 对齐打分：同列（x 中心接近）或同行（y 中心接近）
        h_align = 1.0 - min(abs(dx) / max(lw + cw, 1), 1.0)
        v_align = 1.0 - min(abs(dy) / max(lh + ch, 1), 0.5)
        align_score = (h_align + v_align) / 2

        # 内容匹配：值块越像有效值越好
        content_score = 0.5
        for field, pattern in _VALUE_FILTERS.items():
            if pattern.search(cand["text"]):
                content_score = 0.8
                break

        # 同行右侧的值优先：如果 dy 很小且 dx 为正，给予额外奖励
        same_line_bonus = 0.0
        if abs(dy) < lh * 0.6 and dx > 0:
            same_line_bonus = 0.15

        score = (1.0 / (1.0 + dist)) * 0.45 + align_score * 0.3 + content_score * 0.2 + same_line_bonus
        if score > best_score:
            best_score = score
            best = cand

    if best is None:
        return None, 0.0
    return best, best_score


def _strip_label_prefix(text, label_kw):
    """从值块文本中去除残留的关键词前缀"""
    # 去除关键词本身及常见冒号/空格
    patterns = [
        rf"^{re.escape(label_kw)}\s*[:：]\s*",
        rf"^{re.escape(label_kw)}\s+",
        rf"^{re.escape(label_kw)}(?=\w)",
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    return text.strip()


def _extract_field_by_proximity(text_blocks, field, direction="right"):
    """用空间邻近提取单个字段。返回 (raw_value, confidence) 或 ("", 0)。"""
    candidates = [b for b in text_blocks if b["box"] is not None]
    # 优先匹配最长关键词，避免短标签误匹配；_FIELD_PATTERNS 里长词已在前
    best_value = ""
    best_conf = 0.0
    matched_label_blocks = set()
    for block in candidates:
        kw, conf = _match_label_block(block, field)
        if conf <= 0:
            continue
        # 一个文本块只能作为一个字段的标签；已被更长关键词匹配过则跳过
        block_id = id(block)
        if block_id in matched_label_blocks:
            continue
        matched_label_blocks.add(block_id)
        others = [b for b in candidates if b is not block]
        val_block, score = _find_value_by_proximity(block, others, direction=direction)
        if val_block and score > best_conf:
            raw = _strip_label_prefix(val_block["text"], kw)
            # 如果值块还包含下一个标签，截断到下一个已知标签前
            raw = _truncate_at_next_label(raw, field)
            best_value = raw
            best_conf = score
    return best_value, best_conf


def _truncate_at_next_label(text, current_field):
    """当值文本中混入其他字段关键词时，截断到最早出现的关键词前"""
    earliest = len(text)
    for field, patterns in _FIELD_PATTERNS.items():
        if field == current_field:
            continue
        for kw, _ in patterns:
            m = re.search(rf"(?<!\w){re.escape(kw)}(?=\w|\s*[:：])", text, re.IGNORECASE)
            if m and m.start() < earliest and m.start() > 0:
                earliest = m.start()
    return text[:earliest].strip()


def _extract_all_by_proximity(text_blocks):
    """方案 A 主入口：用空间键值配对提取所有字段。"""
    result = {}
    confidences = {}
    for field in _FIELD_PATTERNS:
        # 数量/日期/批号 优先右侧/下方；厂家/规格 允许更灵活
        direction = "both" if field in ("manufacturer", "spec") else "right"
        val, conf = _extract_field_by_proximity(text_blocks, field, direction=direction)
        result[field] = val
        confidences[field] = conf
    return result, confidences


def _extract_with_columns(text_blocks):
    """方案 B 主入口：先检测两栏布局，在每一栏内分别做空间键值配对。

    如果检测到两栏：左栏通常放标签，右栏放值；分别提取后合并。
    """
    columns = _detect_columns(text_blocks)
    if not columns or len(columns) < 2:
        return _extract_all_by_proximity(text_blocks)

    # 按列分块
    col_blocks = [[] for _ in columns]
    for b in text_blocks:
        cx = _box_center(b["box"])[0]
        best_i = min(range(len(columns)), key=lambda i: abs(cx - (columns[i][0] + columns[i][1]) / 2))
        col_blocks[best_i].append(b)

    # 左栏优先作为标签源，右栏作为值源，但如果右栏也有标签则互换
    label_col, value_col = 0, 1
    if col_blocks[1] and not col_blocks[0]:
        label_col, value_col = 1, 0

    # 提取：标签列内找标签，值列内找对应值
    result = {}
    confidences = {}
    for field in _FIELD_PATTERNS:
        best_val, best_conf = "", 0.0
        for block in col_blocks[label_col]:
            kw, conf = _match_label_block(block, field)
            if conf <= 0:
                continue
            val_block, score = _find_value_by_proximity(
                block,
                [b for b in col_blocks[value_col] if b is not block],
                direction="right",
                max_dist_factor=12.0,
            )
            if val_block and score > best_conf:
                raw = _strip_label_prefix(val_block["text"], kw)
                raw = _truncate_at_next_label(raw, field)
                best_val, best_conf = raw, score
        # 兜底：如果分栏没找到，用全图邻近
        if not best_val:
            best_val, best_conf = _extract_field_by_proximity(text_blocks, field, direction="both")
        result[field] = best_val
        confidences[field] = best_conf
    return result, confidences


# ===================== 表格结构识别（方案 C）=====================

def _extract_table_cells(jsonl_text: str):
    """从 PaddleOCR JSONL 中尝试提取表格/布局单元格（方案 C）。

    兼容两种可能结构：
    1) result.tableResults[].table_cells[{row,col,text}]（PP-Structure）
    2) result.layoutResults[].layout[{label,region,text}]（版面分析）
    3) data.tableResults / data.layoutResults（某些 API 把结果包在 data 下）

    返回按 (row, col) 排序的单元格列表，若未检测到表格则返回空列表。
    """
    cells = []
    for line in jsonl_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # 兼容 result / data / 顶层直接是数组
        result = obj.get("result") or obj.get("data") or obj
        if not isinstance(result, dict):
            continue

        # 1) tableResults
        for table in result.get("tableResults", []):
            for cell in table.get("table_cells", []):
                text = cell.get("text", "").strip()
                if text:
                    cells.append({
                        "text": text,
                        "row": cell.get("row", 0),
                        "col": cell.get("col", 0),
                        "rowspan": cell.get("rowspan", 1),
                        "colspan": cell.get("colspan", 1),
                    })

        # 2) layoutResults: 按 label=table 或包含单元格文本的布局块分组
        for layout in result.get("layoutResults", []):
            for region in layout.get("layout", []):
                label = region.get("label", "").lower()
                if "table" in label:
                    # 简单策略：把 table 区域内的所有文字按坐标分行
                    inner_text = region.get("text", "").strip()
                    if inner_text:
                        cells.append({"text": inner_text, "row": 0, "col": 0})

    # 去重并按行列排序
    seen = set()
    unique = []
    for c in cells:
        key = (c.get("text"), c.get("row"), c.get("col"))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    unique.sort(key=lambda c: (c.get("row", 0), c.get("col", 0)))
    return unique


def _parse_table_cells(cells):
    """把表格单元格转换为类 Markdown 行文本，供 parse_ocr_markdown 处理。"""
    if not cells:
        return []
    # 按 row 分组
    rows = defaultdict(list)
    for c in cells:
        rows[c.get("row", 0)].append(c)
    lines = []
    for row_idx in sorted(rows.keys()):
        row_cells = sorted(rows[row_idx], key=lambda c: c.get("col", 0))
        # 把每对相邻单元格拼成 "Key: Value" 形式（标签在左，值在右）
        parts = []
        for i, cell in enumerate(row_cells):
            text = cell["text"]
            # 如果当前像标签，下一个是值，则拼接
            if i + 1 < len(row_cells):
                parts.append(f"{text}: {row_cells[i + 1]['text']}")
            else:
                parts.append(text)
        lines.append(" ".join(parts))
    return lines


def parse_ocr_markdown(markdown_text: str, text_blocks=None, jsonl_text: str = None) -> dict:
    """将 OCR 返回的 Markdown 文本解析为结构化字段。

    现在支持三层策略：
    1. 表格结构识别（方案 C）：如果 JSONL 含 tableResults，直接按表格单元格解析。
    2. 两栏布局 + 空间键值配对（方案 B）：检测到两栏时按列提取。
    3. 纯空间键值配对（方案 A）：通用邻近提取。
    4. 兜底：原有正则从 markdown 文本提取。
    """
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

    # ===== 方案 C：表格结构识别 =====
    table_lines = []
    if jsonl_text:
        cells = _extract_table_cells(jsonl_text)
        if cells:
            table_lines = _parse_table_cells(cells)
            logger.info("OCR table layout detected: %d cells", len(cells))

    table_text = "\n".join(table_lines) if table_lines else ""

    # ===== 方案 A/B：空间感知提取 =====
    spatial_result = {}
    spatial_conf = {}
    if text_blocks:
        spatial_result, spatial_conf = _extract_with_columns(text_blocks)
        logger.info("Spatial extraction confidence: %s", spatial_conf)

    # ===== 原有正则兜底 =====
    regex_result = _extract_by_regex(clean_text)

    # ===== 合并策略 =====
    # 优先级：表格 > 空间（置信度>0.5）> 正则
    for field in result:
        val = ""
        src = "regex"
        # 表格
        if table_text:
            tval = _extract_single_field_by_regex(table_text, field)
            if tval:
                val, src = tval, "table"
        # 空间提取
        if not val and spatial_conf.get(field, 0) > 0.5 and spatial_result.get(field):
            val, src = spatial_result[field], "spatial"
        # 正则兜底
        if not val:
            val = regex_result.get(field, "")
            src = "regex"

        result[field] = val
        logger.debug("Field %s from %s: %s", field, src, val)

    return result


def _extract_single_field_by_regex(clean_text: str, field: str) -> str:
    """从文本中用原有正则逻辑提取单个字段（供表格文本复用）。"""
    temp = _extract_by_regex(clean_text)
    return temp.get(field, "")


def _extract_by_regex(clean_text: str) -> dict:
    """原有的正则提取逻辑，独立出来作为兜底方案。"""
    result = {
        "manufacturer": "",
        "spec": "",
        "batch_no": "",
        "quantity": "",
        "production_date": "",
        "expiry_date": "",
    }

    # 提取冒号后的值，遇到下一个 "Key:" 或 "Key：" 模式时截断
    def extract(keywords):
        for keyword in keywords:
            esc = re.escape(keyword)
            pattern = rf"\b{esc}\.?\s*[:：]\s*(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                val = match.group(1).strip().lstrip(":：")
                sub = re.match(r"(.+?)\s+\w+\s*[:：]", val)
                if sub:
                    return sub.group(1).strip()
                return val
            pattern = rf"\b{esc}\s+(.+?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            # 兜底：关键词与值直接相连无分隔符（如 LOTNOHYE230413-11）
            pattern = rf"(?<!\w){esc}([A-Z0-9].*?)(?:\n|$)"
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    # 生产厂家
    result["manufacturer"] = extract([
        "SUPPLIER", "Supplier", "supplier",
        "生产厂家", "厂家", "生产厂商", "制造商", "厂商",
    ])

    # 规格
    name_val = extract(["Name", "name", "NAME", "ITEM", "Item", "item", "品名", "产品名称", "名称"])
    type_val = extract(["Type", "type", "TYPE", "型号", "产品型号"])
    spec_val = extract(["Spec", "spec", "SPEC", "规格", "规格型号"])
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

    # 批号
    result["batch_no"] = extract([
        "Lot No", "Lot No.", "LOT NO", "Lot Number", "lot no",
        "LOTNO", "LotNo", "lot", "Lot", "LOT",
        "批号", "批次号", "批次", "产品批号", "生产批号",
    ])

    # 数量
    qty_raw = extract(["Q'ty", "Qty", "qty", "QTY", "数量", "件数", "总数"])
    if qty_raw:
        qty_raw = qty_raw.strip()
        if "/" in qty_raw:
            parts = qty_raw.split("/", 1)
            qty_raw = next((p.strip() for p in parts if re.search(r'\d\s*[kK]', p)), parts[-1].strip())
        if re.match(r"^[\d.]+$", qty_raw):
            for kw in ["Q'ty", "Qty", "qty", "QTY", "数量", "件数", "总数"]:
                m = re.search(
                    rf"\b{re.escape(kw)}\s*[:：]?\s*{re.escape(qty_raw)}\s*\n+\s*(条|PCS|pcs|只|万)",
                    clean_text,
                )
                if m:
                    qty_raw = qty_raw + m.group(1)
                    break
        result["quantity"] = _normalize_qty(qty_raw)

    # 生产日期
    result["production_date"] = _normalize_date(extract([
        "PD", "pd", "Pd",
        "PLATED DATE", "Plated Date", "plated date",
        "MFGDATE", "MFG DATE", "MFG date", "mfg date", "MFG. DATE", "MfgDate",
        "ProductionDate", "Production DATE", "production date", "Production date",
        "生产日期", "制造日期", "生产时间",
    ]))

    # 有效日期
    result["expiry_date"] = _normalize_date(extract([
        "EXP", "exp", "Exp",
        "EXPDATE", "EXP DATE", "EXP date", "exp date", "EXP. DATE", "ExpDate",
        "VALID DATE", "Valid Date", "valid date",
        "ExpirationDate", "Expiration DATE", "expiration date", "Expiration date",
        "ExpiryDate", "Expiry DATE", "expiry date", "Expiry date",
        "有效期至", "有效日期", "过期日期", "失效日期", "保质期至", "到期日期",
    ]))

    return result


async def recognize_image(image_bytes: bytes) -> dict:
    """调用 PaddleOCR PP-OCRv5 异步 API 对图片执行 OCR 识别"""
    if not TOKEN:
        return {"error": "未配置 PaddleOCR API TOKEN，请设置环境变量 PADDLEOCR_TOKEN（或兼容的 PADDOLEOCR_TOKEN）"}

    try:
        headers = {"Authorization": f"bearer {TOKEN}"}

        # 第一步：提交 OCR 任务
        data = {
            "model": MODEL,
            "optionalPayload": json.dumps({
                "markdownIgnoreLabels": [],
                "useDocOrientationClassify": True,
                "useDocUnwarping": True,
                "useTextlineOrientation": True,
                "textDetLimitType": "min",
                "textDetLimitSideLen": 64,
                "textDetThresh": 0.3,
                "textDetBoxThresh": 0.6,
                "textDetUnclipRatio": 1.5,
                "textRecScoreThresh": 0,
                "parseLanguage": "default",
            }),
        }
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}

        response = await _http_client.post(API_URL, headers=headers, data=data, files=files)

        if response.status_code != 200:
            logger.error("PaddleOCR submit error: %s %s", response.status_code, response.text)
            return {"error": f"OCR 提交失败: {response.status_code}"}

        job_id = response.json()["data"]["jobId"]
        logger.info("OCR job submitted: %s", job_id)

        # 第二步：轮询任务状态
        poll_url = f"{API_URL}/{job_id}"
        max_attempts = 60  # 最多轮询 60 次，每次 3 秒 = 最多 3 分钟
        done_data = None
        for _ in range(max_attempts):
            await asyncio.sleep(3)
            poll_resp = await _http_client.get(poll_url, headers=headers)
            if poll_resp.status_code != 200:
                logger.warning("OCR poll error: %s", poll_resp.status_code)
                continue
            poll_data = poll_resp.json()["data"]
            state = poll_data["state"]
            if state == "done":
                done_data = poll_data
                break
            if state == "failed":
                error_msg = poll_data.get("errorMsg", "未知错误")
                logger.error("OCR job failed: %s", error_msg)
                return {"error": f"OCR 识别失败: {error_msg}"}

        if not done_data:
            return {"error": "OCR 识别超时，请重试"}

        # 第三步：获取结果
        jsonl_url = done_data["resultUrl"]["jsonUrl"]
        jsonl_resp = await _http_client.get(jsonl_url)
        jsonl_resp.raise_for_status()
        raw_jsonl_text = jsonl_resp.text

        # 解析 JSONL 结果，收集带坐标的文本块
        text_blocks = []
        for line in raw_jsonl_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            result = json.loads(line).get("result", {})
            for res in result.get("ocrResults", []):
                pruned = res.get("prunedResult", {})
                rec_texts = pruned.get("rec_texts", [])
                rec_boxes = pruned.get("rec_boxes", [])
                for idx, text in enumerate(rec_texts):
                    text = text.strip()
                    if not text:
                        continue
                    box = None
                    if rec_boxes and idx < len(rec_boxes):
                        box = _normalize_box(rec_boxes[idx])
                    text_blocks.append({"text": text, "box": box})

        # 有坐标时用 Y 轴分行合并，否则退化为冒号拼接
        coord_blocks = [b for b in text_blocks if b["box"] is not None]
        no_coord_texts = [b["text"] for b in text_blocks if b["box"] is None]
        if coord_blocks and len(coord_blocks) / max(len(text_blocks), 1) > 0.7:
            lines = _merge_blocks_by_coords(coord_blocks)
            lines.extend(no_coord_texts)
        else:
            lines = _merge_by_colon([b["text"] for b in text_blocks])

        full_text = "\n".join(lines)

        # 去除 HTML 标签和图片引用
        clean_raw = re.sub(r"<[^>]+>", "", full_text)
        clean_raw = re.sub(r"!\[.*?\]\(.*?\)", "", clean_raw)
        clean_raw = re.sub(r"\n{3,}", "\n\n", clean_raw).strip()

        # 传入 text_blocks 与原始 JSONL 启用空间/表格解析
        parsed = parse_ocr_markdown(full_text, text_blocks=text_blocks, jsonl_text=raw_jsonl_text)
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
