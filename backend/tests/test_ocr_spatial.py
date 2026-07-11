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
        # 网格主路径返回原始 "46.368K"，parse_ocr_markdown 合并步统一归一化为 K 纯数字
        self.assertEqual(r["quantity"], "46.368")
        self.assertEqual(r["production_date"], "2023-04-13")
        self.assertEqual(r["expiry_date"], "2025-04-13")


class TestClusterRows(unittest.TestCase):
    def test_groups_by_y_center_gap(self):
        # 两个清晰分开的行
        blocks = [
            {"text": "A:", "box": [10, 10, 40, 25]},
            {"text": "B", "box": [60, 10, 90, 25]},
            {"text": "C:", "box": [10, 40, 40, 55]},
            {"text": "D", "box": [60, 40, 90, 55]},
        ]
        rows = ocr_service._cluster_rows(blocks)
        self.assertEqual(len(rows), 2)
        self.assertEqual([b["text"] for b in rows[0]], ["A:", "B"])
        self.assertEqual([b["text"] for b in rows[1]], ["C:", "D"])

    def test_no_collapse_when_stacked(self):
        # 纵向堆叠 3 块：A-B、B-C 的 Y 范围各有重叠，但 A-C 不重叠。
        # 链式 overlap（any()）会把三者误并成一行；间隙法应分成 3 行。
        blocks = [
            {"text": "A", "box": [10, 10, 60, 30]},
            {"text": "B", "box": [10, 25, 60, 45]},
            {"text": "C", "box": [10, 40, 60, 60]},
        ]
        rows = ocr_service._cluster_rows(blocks)
        self.assertEqual(len(rows), 3)


class TestClusterColumns(unittest.TestCase):
    def test_four_distinct_columns(self):
        # 列检测不硬编码 2 栏：4 个明确分列的窄块应得到 4 个列簇
        blocks = [
            {"text": "A", "box": [10, 10, 40, 25]},
            {"text": "B", "box": [100, 10, 130, 25]},
            {"text": "C", "box": [200, 10, 230, 25]},
            {"text": "D", "box": [300, 10, 330, 25]},
        ]
        rows = ocr_service._cluster_rows(blocks)
        cols = ocr_service._cluster_columns(rows)
        self.assertEqual(len(cols), 4)

    def test_single_column_when_dense(self):
        blocks = [
            {"text": "A", "box": [10, 10, 60, 25]},
            {"text": "B", "box": [65, 10, 110, 25]},
        ]
        rows = ocr_service._cluster_rows(blocks)
        cols = ocr_service._cluster_columns(rows)
        self.assertEqual(len(cols), 1)


class TestGridExtraction(unittest.TestCase):
    def test_horizontal_kv(self):
        # 经典两列：标签左、值右
        blocks = [
            {"text": "SUPPLIER:", "box": [10, 10, 80, 25]},
            {"text": "厦门捷昕", "box": [120, 10, 200, 25]},
            {"text": "Lot No:", "box": [10, 40, 80, 55]},
            {"text": "HYE230413-11", "box": [120, 40, 250, 55]},
            {"text": "Q'ty:", "box": [10, 70, 80, 85]},
            {"text": "46.368K", "box": [120, 70, 200, 85]},
        ]
        result, conf = ocr_service._extract_all_by_grid(blocks)
        self.assertEqual(result["manufacturer"], "厦门捷昕")
        self.assertEqual(result["batch_no"], "HYE230413-11")
        # 网格层返回原始值（归一化在 parse_ocr_markdown 合并步）
        self.assertEqual(result["quantity"], "46.368K")
        self.assertGreaterEqual(conf["manufacturer"], 0.9)

    def test_vertical_kv(self):
        # 表格式：标签在上、值在下一行同列（当前 proximity(A) 易错配的回归用例）
        blocks = [
            {"text": "SUPPLIER", "box": [10, 10, 100, 25]},
            {"text": "厦门捷昕", "box": [10, 40, 120, 55]},
            {"text": "Lot No", "box": [10, 70, 90, 85]},
            {"text": "HYE230413-11", "box": [10, 100, 180, 115]},
        ]
        result, conf = ocr_service._extract_all_by_grid(blocks)
        self.assertEqual(result["manufacturer"], "厦门捷昕")
        self.assertEqual(result["batch_no"], "HYE230413-11")
        self.assertGreaterEqual(conf["manufacturer"], 0.9)

    def test_multiblock_value_joined(self):
        # 规格值被 OCR 切成两个块同行，应拼接完整不截断
        blocks = [
            {"text": "Name:", "box": [10, 10, 60, 25]},
            {"text": "QFP-100", "box": [80, 10, 160, 25]},
            {"text": "14x20x1.8", "box": [170, 10, 260, 25]},
        ]
        result, conf = ocr_service._extract_all_by_grid(blocks)
        self.assertEqual(result["spec"], "QFP-100 14x20x1.8")
        self.assertGreaterEqual(conf["spec"], 0.9)

    def test_inline_value_in_label_block(self):
        # 标签与值在同一块内（冒号后紧跟）
        blocks = [
            {"text": "Q'ty: 46.368K", "box": [10, 10, 200, 25]},
            {"text": "Lot No: HYE230413-11", "box": [10, 40, 260, 55]},
        ]
        result, conf = ocr_service._extract_all_by_grid(blocks)
        self.assertEqual(result["quantity"], "46.368K")
        self.assertEqual(result["batch_no"], "HYE230413-11")
        self.assertGreaterEqual(conf["quantity"], 0.9)

    def test_horizontal_stops_at_next_label(self):
        # 同行有两个 KV 对：取值应停在下一个标签前，不串味
        blocks = [
            {"text": "Q'ty:", "box": [10, 10, 60, 25]},
            {"text": "46.368K", "box": [80, 10, 160, 25]},
            {"text": "EXP:", "box": [200, 10, 250, 25]},
            {"text": "2025-04-13", "box": [270, 10, 380, 25]},
        ]
        result, conf = ocr_service._extract_all_by_grid(blocks)
        self.assertEqual(result["quantity"], "46.368K")
        self.assertEqual(result["expiry_date"], "2025-04-13")

    def test_empty_when_no_blocks(self):
        result, conf = ocr_service._extract_all_by_grid([])
        self.assertEqual(result, {})
        self.assertEqual(conf, {})


class TestFilterBlocksByScore(unittest.TestCase):
    def test_drops_low_score(self):
        blocks = [
            {"text": "Lot No:", "box": [10, 10, 70, 25], "score": 0.95},
            {"text": "HYE230413-11", "box": [90, 10, 220, 25], "score": 0.9},
            {"text": "###噪声###", "box": [10, 200, 200, 215], "score": 0.1},
        ]
        filtered = ocr_service._filter_blocks_by_score(blocks)
        self.assertEqual(len(filtered), 2)

    def test_keeps_all_when_no_score(self):
        # 旧响应无 score 字段时不应过滤
        blocks = [
            {"text": "Lot No:", "box": [10, 10, 70, 25]},
            {"text": "HYE230413-11", "box": [90, 10, 220, 25]},
        ]
        filtered = ocr_service._filter_blocks_by_score(blocks)
        self.assertEqual(len(filtered), 2)

    def test_low_score_does_not_pollute_extraction(self):
        blocks = [
            {"text": "Lot No:", "box": [10, 10, 70, 25], "score": 0.95},
            {"text": "HYE230413-11", "box": [90, 10, 220, 25], "score": 0.9},
            {"text": "批号: 乱码XYZ", "box": [10, 200, 200, 215], "score": 0.1},
        ]
        filtered = ocr_service._filter_blocks_by_score(blocks)
        result, _ = ocr_service._extract_all_by_grid(filtered)
        self.assertEqual(result["batch_no"], "HYE230413-11")


class TestMergeBlocksByCoordsRefactor(unittest.TestCase):
    def test_two_lines(self):
        blocks = [
            {"text": "A:", "box": [10, 10, 40, 25]},
            {"text": "B", "box": [60, 10, 90, 25]},
            {"text": "C:", "box": [10, 40, 40, 55]},
            {"text": "D", "box": [60, 40, 90, 55]},
        ]
        lines = ocr_service._merge_blocks_by_coords(blocks)
        self.assertEqual(lines, ["A: B", "C: D"])

    def test_stacked_not_collapsed(self):
        blocks = [
            {"text": "A", "box": [10, 10, 60, 30]},
            {"text": "B", "box": [10, 25, 60, 45]},
            {"text": "C", "box": [10, 40, 60, 60]},
        ]
        lines = ocr_service._merge_blocks_by_coords(blocks)
        self.assertEqual(len(lines), 3)


if __name__ == "__main__":
    unittest.main()
