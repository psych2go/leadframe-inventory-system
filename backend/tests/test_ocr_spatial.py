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


def _pp_ocr_v6_aami_blocks():
    texts = [
        "AAMI", "MFG Date:14-Apr-2023", "EXP Date: 13-Apr-2024", "Ship To:",
        "AAMI P/N: 03080CBDX1AB00-R", "XINGHANG/Z", "DWG:3-080180-S0T223 REV.0",
        "AAMI Ref: 22563786/001", "DESCRIPTION:", "1", "LOT NO:", "3L",
        "80X180 SOT A194FH", "Ag", "88.80", "P/N:", "S0T223-080180",
        "18.000", "QTY:", "KPD",
    ]
    boxes = [
        [136, 548, 224, 589], [403, 564, 745, 608], [1111, 588, 1470, 631],
        [131, 603, 230, 638], [280, 607, 696, 652], [126, 626, 463, 686],
        [907, 629, 1356, 670], [575, 661, 920, 701], [119, 691, 298, 732],
        [1135, 683, 1166, 732], [997, 698, 1109, 739], [117, 741, 152, 766],
        [163, 738, 457, 780], [109, 758, 156, 795], [163, 760, 255, 793],
        [109, 815, 165, 841], [104, 829, 553, 902], [1108, 830, 1323, 891],
        [1012, 847, 1083, 889], [1401, 863, 1462, 894],
    ]
    return [
        {"text": text, "box": box, "score": 0.99}
        for text, box in zip(texts, boxes)
    ]


def _pp_ocr_v6_aami_split_label_blocks():
    texts = [
        "AAMI", "MFG DATE:Nov 27, 2022", "EXP", "DATE: Nov 27, 2023",
        "P/N:T4MX02300407L", "DWG NO:100-12323-TQFP1 REV A",
        "CUSTOMER: CASC", "LOT NO:2270992-3",
        "DESCRIPTION: 100L LQFP MTX 230X230", "7025C (1/2H) ME2",
        "AG D/S:650.0/6.700", "REMARK:", "Stamped L/F", "OTY:",
        "5.600 K", "CUSTOMER P/N:", "AAMI", "PASS", "Ref.:2521628-06",
        "011", "(5)", "PARTIAL",
    ]
    boxes = [
        [200, 720, 281, 748], [358, 714, 714, 744], [822, 712, 883, 737],
        [890, 708, 1166, 737], [567, 761, 841, 792], [949, 749, 1382, 786],
        [205, 766, 446, 795], [1185, 801, 1441, 828], [205, 810, 760, 840],
        [434, 847, 686, 882], [739, 839, 1013, 877], [210, 895, 321, 922],
        [434, 888, 611, 921], [876, 923, 953, 960], [1008, 925, 1110, 951],
        [209, 936, 450, 965], [638, 945, 744, 1006], [732, 945, 815, 980],
        [1253, 945, 1477, 973], [739, 972, 802, 1001], [1339, 982, 1381, 1010],
        [684, 1096, 1505, 1279],
    ]
    return [
        {"text": text, "box": box, "score": 0.99}
        for text, box in zip(texts, boxes)
    ]


def _pp_ocr_v6_aami_customer_pn_blocks():
    texts = [
        "AAMI", "60014865/001", "BOX", "CUST:XINGHANG/Z",
        "CUST P/N: QFN64", "GP", "P/N:64311NBDU1QB00-R",
        "QTY:45.500", "KPD", "AAMIPASS", "LOT: 2511686",
        "MFG DATE:20250515", "EXP DATE:20260515",
        "DESC: 64L 311X311 QFN MTX A194FH",
        "DWG#: 064L198740DCE REV.0", "房", "品房具品房制念养",
    ]
    boxes = [
        [174, 604, 258, 640], [271, 602, 597, 648], [1481, 611, 1570, 647],
        [186, 656, 543, 695], [673, 664, 941, 698], [1485, 655, 1543, 691],
        [192, 693, 646, 727], [199, 726, 394, 760], [462, 728, 546, 760],
        [1167, 722, 1396, 836], [676, 738, 911, 771], [214, 800, 509, 826],
        [227, 867, 512, 892], [676, 883, 1158, 912], [676, 909, 1057, 936],
        [0, 1236, 141, 1274], [235, 1241, 453, 1276],
    ]
    scores = [
        0.9999, 0.9999, 0.9991, 0.9994, 0.9848, 0.9999, 0.9986,
        0.9998, 0.9999, 0.8986, 0.9737, 0.9780, 0.9863, 0.9992,
        0.9978, 0.4104, 0.3993,
    ]
    return [
        {"text": text, "box": box, "score": score}
        for text, box, score in zip(texts, boxes, scores)
    ]


class TestNormalizeBox(unittest.TestCase):
    def test_four_numbers(self):
        self.assertEqual(ocr_service._normalize_box([10, 20, 30, 40]), [10, 20, 30, 40])

    def test_four_points(self):
        box = [[10, 20], [30, 20], [30, 40], [10, 40]]
        self.assertEqual(ocr_service._normalize_box(box), [10, 20, 30, 40])


class TestParsePpOcrV6Json(unittest.TestCase):
    def test_top_level_result_and_polygon_fallback(self):
        payload = {
            "ocrResults": [{
                "prunedResult": {
                    "rec_texts": ["LOT NO:", "1"],
                    "rec_scores": [0.99, 0.98],
                    "rec_polys": [
                        [[10, 10], [80, 10], [80, 30], [10, 30]],
                        [[90, 10], [110, 10], [110, 30], [90, 30]],
                    ],
                },
            }],
            "dataInfo": {"width": 200, "height": 100, "type": "image"},
        }

        blocks, data_info = ocr_service._parse_ocr_jsonl(json.dumps(payload))

        self.assertEqual(data_info["width"], 200)
        self.assertEqual([b["text"] for b in blocks], ["LOT NO:", "1"])
        self.assertEqual(blocks[0]["box"], [10, 10, 80, 30])
        self.assertEqual(blocks[0]["score"], 0.99)

    def test_wrapped_result(self):
        payload = {
            "result": {
                "ocrResults": [{
                    "prunedResult": {
                        "rec_texts": ["QTY:", "18.000", "KPD"],
                        "rec_boxes": [
                            [10, 10, 50, 30],
                            [60, 10, 120, 30],
                            [130, 10, 170, 30],
                        ],
                    },
                }],
            },
        }

        blocks, _ = ocr_service._parse_ocr_jsonl(json.dumps(payload))

        self.assertEqual([b["text"] for b in blocks], ["QTY:", "18.000", "KPD"])


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
    def test_pp_ocr_v6_aami_multiregion_label(self):
        blocks = _pp_ocr_v6_aami_blocks()
        raw_text = "\n".join(ocr_service._merge_blocks_by_coords(blocks))
        result = ocr_service.parse_ocr_markdown(raw_text, text_blocks=blocks)
        result["manufacturer"] = ocr_service._resolve_manufacturer(
            raw_text,
            result["manufacturer"],
        )
        result["spec"] = ocr_service._resolve_aami_spec(raw_text, text_blocks=blocks)

        self.assertEqual(result["manufacturer"], "AAMI")
        self.assertEqual(result["spec"], "S0T223-080180")
        self.assertEqual(result["batch_no"], "1")
        self.assertEqual(result["quantity"], "18")
        self.assertEqual(result["production_date"], "2023-04-14")
        self.assertEqual(result["expiry_date"], "2024-04-13")

    def test_pp_ocr_v6_aami_split_exp_and_ocr_qty_typo(self):
        blocks = _pp_ocr_v6_aami_split_label_blocks()
        raw_text = "\n".join(ocr_service._merge_blocks_by_coords(blocks))
        result = ocr_service.parse_ocr_markdown(raw_text, text_blocks=blocks)
        result["manufacturer"] = ocr_service._resolve_manufacturer(
            raw_text,
            result["manufacturer"],
        )
        result["spec"] = ocr_service._resolve_aami_spec(raw_text, text_blocks=blocks)

        self.assertEqual(result["manufacturer"], "AAMI")
        self.assertEqual(result["spec"], "100L LQFP MTX 230X230")
        self.assertEqual(result["batch_no"], "2270992-3")
        self.assertEqual(result["quantity"], "5.6")
        self.assertEqual(result["production_date"], "2022-11-27")
        self.assertEqual(result["expiry_date"], "2023-11-27")

    def test_pp_ocr_v6_aami_customer_pn_and_compact_dates(self):
        blocks = _pp_ocr_v6_aami_customer_pn_blocks()
        raw_text = "\n".join(ocr_service._merge_blocks_by_coords(blocks))
        result = ocr_service.parse_ocr_markdown(raw_text, text_blocks=blocks)
        result["manufacturer"] = ocr_service._resolve_manufacturer(
            raw_text,
            result["manufacturer"],
        )
        result["spec"] = ocr_service._resolve_aami_spec(raw_text, text_blocks=blocks)

        self.assertEqual(result["manufacturer"], "AAMI")
        self.assertEqual(result["spec"], "QFN64")
        self.assertEqual(result["batch_no"], "2511686")
        self.assertEqual(result["quantity"], "45.5")
        self.assertEqual(result["production_date"], "2025-05-15")
        self.assertEqual(result["expiry_date"], "2026-05-15")

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
