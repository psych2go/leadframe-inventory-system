"""数量单位（K）转换的基线测试。

系统所有数量以 K（千）为单位存储。本测试锁定 database 与 ocr_service
中数量解析/格式化的当前行为，作为后续重构的行为基线（safety net）。
"""
import os
import sys
import unittest

# 将 backend/ 加入 sys.path，保证任意工作目录下都能 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import ocr_service


class TestQtyRoundtrip(unittest.TestCase):
    """qty_to_num / num_to_qty（database.py）的往返与边界行为"""

    def test_parse_plain_number(self):
        self.assertEqual(db.qty_to_num("46.368"), 46.368)
        self.assertEqual(db.qty_to_num("500"), 500.0)

    def test_parse_ignores_k_suffix(self):
        # K/M 等后缀被忽略（系统已以 K 为单位）
        self.assertEqual(db.qty_to_num("46.368K"), 46.368)

    def test_parse_numeric_passthrough(self):
        self.assertEqual(db.qty_to_num(0), 0.0)
        self.assertEqual(db.qty_to_num(12.5), 12.5)

    def test_parse_garbage_returns_zero(self):
        # 无数字时返回 0（当前行为：静默兜底，非抛错）
        self.assertEqual(db.qty_to_num(""), 0.0)
        self.assertEqual(db.qty_to_num("abc"), 0.0)

    def test_format_integer(self):
        self.assertEqual(db.num_to_qty(500), "500")
        self.assertEqual(db.num_to_qty(0), "0")

    def test_format_decimal_trims_trailing_zeros(self):
        self.assertEqual(db.num_to_qty(46.368), "46.368")
        self.assertEqual(db.num_to_qty(1.5), "1.5")
        self.assertEqual(db.num_to_qty(5.0), "5")

    def test_format_rounds_to_three_decimals(self):
        self.assertEqual(db.num_to_qty(1.23456), "1.235")

    def test_roundtrip_preserves_value(self):
        for v in ["0", "5", "46.368", "1.5", "100", "999.999"]:
            self.assertEqual(db.num_to_qty(db.qty_to_num(v)), v,
                             f"roundtrip 失败: {v}")


class TestNormalizeQty(unittest.TestCase):
    """ocr_service._normalize_qty：各种原始单位 → K 单位字符串"""

    def test_wan(self):
        self.assertEqual(ocr_service._normalize_qty("3万"), "30")
        self.assertEqual(ocr_service._normalize_qty("1.5万"), "15")

    def test_zhi(self):
        self.assertEqual(ocr_service._normalize_qty("5000只"), "5")
        self.assertEqual(ocr_service._normalize_qty("1500只"), "1.5")

    def test_pcs(self):
        self.assertEqual(ocr_service._normalize_qty("46368 PCS"), "46.368")

    def test_k_suffix(self):
        self.assertEqual(ocr_service._normalize_qty("46.368K"), "46.368")

    def test_pure_number_below_1000_kept_as_is(self):
        # 注意：当前代码对 <1000 的纯数字原样返回（注释写 "500→0.5" 与实现不符）。
        # 这里锁定【实现】的实际行为，避免重构时误改。
        self.assertEqual(ocr_service._normalize_qty("500"), "500")

    def test_pure_number_above_1000_divides_by_1000(self):
        self.assertEqual(ocr_service._normalize_qty("1500"), "1.5")
        self.assertEqual(ocr_service._normalize_qty("46368"), "46.368")

    def test_comma_thousands(self):
        self.assertEqual(ocr_service._normalize_qty("46,368"), "46.368")

    def test_strips_whitespace(self):
        self.assertEqual(ocr_service._normalize_qty("  5K  "), "5")

    def test_no_match_returns_raw(self):
        # 当前行为：完全无法匹配时返回原始字符串（后续可考虑抛错）
        self.assertEqual(ocr_service._normalize_qty("N/A"), "N/A")


class TestFormatK(unittest.TestCase):
    def test_format_k_integer(self):
        self.assertEqual(ocr_service._format_k(30.0), "30")

    def test_format_k_decimal(self):
        self.assertEqual(ocr_service._format_k(46.368), "46.368")


if __name__ == "__main__":
    unittest.main()
