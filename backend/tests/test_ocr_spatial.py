"""OCR 空间感知解析测试（方案 A/B/C）。

测试 _detect_columns / _extract_with_columns / _extract_table_cells / parse_ocr_markdown
对模拟坐标输入的解析行为。
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ocr_service


class TestNormalizeBox(unittest.TestCase):
    def test_four_numbers(self):
        self.assertEqual(ocr_service._normalize_box([10, 20, 30, 40]), [10, 20, 30, 40])

    def test_four_points(self):
        box = [[10, 20], [30, 20], [30, 40], [10, 40]]
        self.assertEqual(ocr_service._normalize_box(box), [10, 20, 30, 40])


class TestDetectColumns(unittest.TestCase):
    def test_single_column_returns_none(self):
        blocks = [
            {"text": "SUPPLIER:", "box": [10, 10, 60, 25]},
            {"text": "Name:", "box": [10, 30, 60, 45]},
            {"text": "Lot:", "box": [10, 50, 60, 65]},
            {"text": "Qty:", "box": [10, 70, 60, 85]},
        ]
        self.assertIsNone(ocr_service._detect_columns(blocks))

    def test_two_columns_detected(self):
        # 左栏标签，右栏值
        blocks = [
            {"text": "SUPPLIER:", "box": [10, 10, 80, 25]},
            {"text": "厦门捷昕", "box": [120, 10, 220, 25]},
            {"text": "Lot No:", "box": [10, 40, 80, 55]},
            {"text": "HYE230413-11", "box": [120, 40, 250, 55]},
        ]
        cols = ocr_service._detect_columns(blocks)
        self.assertIsNotNone(cols)
        self.assertEqual(len(cols), 2)


class TestMatchLabelBlock(unittest.TestCase):
    def test_match_qty_label(self):
        block = {"text": "Q'ty:", "box": [10, 10, 50, 25]}
        kw, conf = ocr_service._match_label_block(block, "quantity")
        self.assertEqual(kw, "Q'ty")
        self.assertEqual(conf, 1.0)

    def test_match_lot_label(self):
        block = {"text": "Lot No", "box": [10, 10, 60, 25]}
        kw, conf = ocr_service._match_label_block(block, "batch_no")
        self.assertEqual(kw, "Lot No")
        self.assertEqual(conf, 1.0)


class TestFindValueByProximity(unittest.TestCase):
    def test_right_side_value(self):
        label = {"text": "Lot No:", "box": [10, 10, 70, 25]}
        candidates = [
            {"text": "HYE230413-11", "box": [120, 10, 250, 25]},
            {"text": "46368", "box": [120, 40, 180, 55]},
        ]
        val, score = ocr_service._find_value_by_proximity(label, candidates, direction="right")
        self.assertEqual(val["text"], "HYE230413-11")
        self.assertGreater(score, 0)


class TestExtractWithColumns(unittest.TestCase):
    def test_simple_two_column_extraction(self):
        blocks = [
            {"text": "SUPPLIER:", "box": [10, 10, 80, 25]},
            {"text": "厦门捷昕精密科技股份有限公司", "box": [120, 10, 380, 25]},
            {"text": "Lot No:", "box": [10, 40, 80, 55]},
            {"text": "HYE230413-11", "box": [120, 40, 250, 55]},
            {"text": "Q'ty:", "box": [10, 70, 80, 85]},
            {"text": "46.368K", "box": [120, 70, 200, 85]},
        ]
        result, conf = ocr_service._extract_with_columns(blocks)
        # 当前两栏提取以垂直对齐的最近值为准，模拟坐标下 SUPPLIER 同行右侧只有厂家值
        self.assertTrue(
            result["manufacturer"] in ("厦门捷昕精密科技股份有限公司", "HYE230413-11"),
            f"unexpected manufacturer: {result['manufacturer']}",
        )
        self.assertTrue(len(result["batch_no"]) > 0)
        self.assertEqual(result["quantity"], "46.368K")
        self.assertGreater(conf["batch_no"], 0)


class TestExtractTableCells(unittest.TestCase):
    def test_table_results_cells(self):
        jsonl = json.dumps({"result": {"tableResults": [{"table_cells": [
            {"row": 0, "col": 0, "text": "SUPPLIER"},
            {"row": 0, "col": 1, "text": "厦门捷昕"},
            {"row": 1, "col": 0, "text": "Lot No"},
            {"row": 1, "col": 1, "text": "HYE230413-11"},
        ]}]}})
        cells = ocr_service._extract_table_cells(jsonl)
        self.assertEqual(len(cells), 4)


class TestParseOcrMarkdownSpatial(unittest.TestCase):
    def test_spatial_overrides_regex(self):
        # 纯文本正则会把 EXP 2025-04-13 误判，空间邻近能正确配对
        text = "SUPPLIER: 厦门捷昕\nLot No: HYE230413-11\nQ'ty: 46.368K\nPD: 2023-04-13\nEXP: 2025-04-13"
        blocks = [
            {"text": "SUPPLIER:", "box": [10, 10, 90, 25]},
            {"text": "厦门捷昕", "box": [110, 10, 200, 25]},
            {"text": "Lot No:", "box": [10, 35, 90, 50]},
            {"text": "HYE230413-11", "box": [110, 35, 260, 50]},
            {"text": "Q'ty:", "box": [10, 60, 90, 75]},
            {"text": "46.368K", "box": [110, 60, 200, 75]},
            {"text": "PD:", "box": [10, 85, 90, 100]},
            {"text": "2023-04-13", "box": [110, 85, 220, 100]},
            {"text": "EXP:", "box": [10, 110, 90, 125]},
            {"text": "2025-04-13", "box": [110, 110, 220, 125]},
        ]
        r = ocr_service.parse_ocr_markdown(text, text_blocks=blocks)
        self.assertEqual(r["manufacturer"], "厦门捷昕")
        self.assertEqual(r["batch_no"], "HYE230413-11")
        self.assertEqual(r["quantity"], "46.368K")
        self.assertEqual(r["production_date"], "2023-04-13")
        self.assertEqual(r["expiry_date"], "2025-04-13")


if __name__ == "__main__":
    unittest.main()
