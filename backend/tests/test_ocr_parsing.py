"""OCR 解析的基线测试。

锁定 ocr_service.parse_ocr_markdown / _normalize_date / _normalize_qty
对典型标签文本的当前解析行为，作为重构 safety net。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ocr_service


class TestNormalizeDate(unittest.TestCase):
    def test_dd_mon_yyyy(self):
        self.assertEqual(ocr_service._normalize_date("17-Jun-2022"), "2022-06-17")
        self.assertEqual(ocr_service._normalize_date("05-March-2024"), "2024-03-05")

    def test_mon_dd_yyyy(self):
        self.assertEqual(ocr_service._normalize_date("Jun 17, 2022"), "2022-06-17")

    def test_yyyy_mm_dd_with_separators(self):
        self.assertEqual(ocr_service._normalize_date("2022/06/17"), "2022-06-17")
        self.assertEqual(ocr_service._normalize_date("2022-06-17"), "2022-06-17")
        self.assertEqual(ocr_service._normalize_date("2022.06.17"), "2022-06-17")

    def test_chinese_date(self):
        self.assertEqual(ocr_service._normalize_date("2022年6月17日"), "2022-06-17")

    def test_compact_8_digits(self):
        self.assertEqual(ocr_service._normalize_date("20220617"), "2022-06-17")

    def test_empty_returns_empty(self):
        self.assertEqual(ocr_service._normalize_date(""), "")
        self.assertEqual(ocr_service._normalize_date("   "), "")

    def test_unparseable_returns_raw(self):
        self.assertEqual(ocr_service._normalize_date("not a date"), "not a date")


class TestParseOcrMarkdown(unittest.TestCase):
    """用接近真实标签的 Markdown 文本验证字段提取"""

    def test_typical_label(self):
        md = """
# SUPPLIER: 厦门捷昕精密科技股份有限公司
Name: QFP-100
Spec: 14x20x1.8
Lot No: HYE230413-11
Q'ty: 46.368K
PD: 2023-04-13
EXP: 2025-04-13
"""
        r = ocr_service.parse_ocr_markdown(md)
        self.assertEqual(r["manufacturer"], "厦门捷昕精密科技股份有限公司")
        self.assertEqual(r["batch_no"], "HYE230413-11")
        self.assertEqual(r["quantity"], "46.368")
        self.assertEqual(r["production_date"], "2023-04-13")
        self.assertEqual(r["expiry_date"], "2025-04-13")
        # spec 由 Name + Spec 拼接
        self.assertIn("QFP-100", r["spec"])
        self.assertIn("14x20x1.8", r["spec"])

    def test_empty_text(self):
        r = ocr_service.parse_ocr_markdown("")
        self.assertEqual(r["manufacturer"], "")
        self.assertEqual(r["spec"], "")
        self.assertEqual(r["quantity"], "")

    def test_quantity_with_pcs_unit(self):
        md = "Q'ty: 46368 PCS\n"
        r = ocr_service.parse_ocr_markdown(md)
        self.assertEqual(r["quantity"], "46.368")

    def test_quantity_split_slash_picks_k_value(self):
        # "46.368K/50000" 形式应取带 K 的部分
        md = "Qty: 46.368K/50000\n"
        r = ocr_service.parse_ocr_markdown(md)
        self.assertEqual(r["quantity"], "46.368")

    def test_lot_no_concatenated(self):
        # 关键词与值直接相连（无分隔符）
        md = "LOTNOHYE230413-11\n"
        r = ocr_service.parse_ocr_markdown(md)
        self.assertEqual(r["batch_no"], "HYE230413-11")

    def test_result_has_all_keys(self):
        r = ocr_service.parse_ocr_markdown("")
        expected_keys = {"manufacturer", "spec", "batch_no", "quantity",
                         "production_date", "expiry_date"}
        self.assertEqual(set(r.keys()), expected_keys)


class TestResolveManufacturer(unittest.TestCase):
    """厂家名归一化"""

    def test_normalizes_alias(self):
        # ASM → AAMI
        r = ocr_service._resolve_manufacturer("ASM", "ASM")
        self.assertEqual(r, "AAMI")

    def test_fusheng_to_zhongshanfusheng(self):
        r = ocr_service._resolve_manufacturer("FUSHENG", "FUSHENG")
        self.assertEqual(r, "中山复盛")

    def test_passthrough_unknown(self):
        r = ocr_service._resolve_manufacturer("", "某厂家")
        self.assertEqual(r, "某厂家")

    def test_empty_when_nothing_found(self):
        r = ocr_service._resolve_manufacturer("", "")
        self.assertEqual(r, "")


if __name__ == "__main__":
    unittest.main()
