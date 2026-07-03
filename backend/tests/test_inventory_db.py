"""库存核心数据库操作的基线测试。

使用临时 SQLite 文件库，测试 stock_in（同组合累加）、stock_out（扣减+超额校验）
等核心行为。合并逻辑（当前位于 routers/inventory.py）会在被抽取到 database.py 后
补充对应测试。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


def _key_fields(**overrides):
    """构造一组复合键字段，便于测试"""
    base = dict(
        package_type="QFP", spec="14x20", plating_zone="不镀银",
        surface_treatment="粗化", manufacturer="AAMI", batch_no="LOT1",
        production_date="2024-01-01", expiry_date="2025-01-01",
    )
    base.update(overrides)
    return base


class _TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        db.DB_PATH = self._tmp.name
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._orig_path
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass


class TestStockIn(_TempDbTestCase):
    def test_first_insert_creates_record(self):
        inv_id = db.stock_in(operator="tester", quantity="5", **_key_fields())
        self.assertIsNotNone(inv_id)
        item = db.inventory_get(inv_id)
        self.assertEqual(item["quantity"], "5")
        self.assertEqual(item["batch_no"], "LOT1")

    def test_same_key_accumulates_quantity(self):
        # 相同复合键（含批号）入库应累加，而非新建
        id1 = db.stock_in(operator="t", quantity="5", **_key_fields())
        id2 = db.stock_in(operator="t", quantity="3", **_key_fields())
        self.assertEqual(id1, id2, "相同组合应累加到同一条记录")
        item = db.inventory_get(id1)
        self.assertEqual(db.qty_to_num(item["quantity"]), 8.0)

    def test_different_batch_creates_new_record(self):
        id1 = db.stock_in(operator="t", quantity="5", **_key_fields(batch_no="LOT1"))
        id2 = db.stock_in(operator="t", quantity="5", **_key_fields(batch_no="LOT2"))
        self.assertNotEqual(id1, id2)

    def test_stock_in_writes_log(self):
        inv_id = db.stock_in(operator="op1", quantity="5", **_key_fields())
        logs = db.stock_logs(inventory_id=inv_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["type"], "in")
        self.assertEqual(logs[0]["operator"], "op1")


class TestStockOut(_TempDbTestCase):
    def setUp(self):
        super().setUp()
        self.inv_id = db.stock_in(operator="t", quantity="10", **_key_fields())

    def test_successful_out(self):
        inv_id, error = db.stock_out(self.inv_id, "3", operator="t")
        self.assertIsNone(error)
        self.assertEqual(inv_id, self.inv_id)
        item = db.inventory_get(self.inv_id)
        self.assertEqual(db.qty_to_num(item["quantity"]), 7.0)

    def test_out_writes_log(self):
        db.stock_out(self.inv_id, "3", note="出", operator="op2")
        logs = db.stock_logs(inventory_id=self.inv_id)
        out_logs = [l for l in logs if l["type"] == "out"]
        self.assertEqual(len(out_logs), 1)
        self.assertEqual(out_logs[0]["operator"], "op2")

    def test_insufficient_stock_returns_error(self):
        inv_id, error = db.stock_out(self.inv_id, "100", operator="t")
        self.assertIsNone(inv_id)
        self.assertIsNotNone(error)
        # 库存数量未被改动
        item = db.inventory_get(self.inv_id)
        self.assertEqual(db.qty_to_num(item["quantity"]), 10.0)

    def test_nonexistent_item_returns_error(self):
        inv_id, error = db.stock_out(999999, "1", operator="t")
        self.assertIsNone(inv_id)
        self.assertIsNotNone(error)


class TestWriteAudit(_TempDbTestCase):
    def test_audit_record_stored(self):
        inv_id = db.stock_in(operator="t", quantity="5", **_key_fields())
        with db.get_db() as conn:
            db.write_audit(conn, "u1", "张三", "stock_in", "inventory", inv_id,
                           detail="测试", ip_address="127.0.0.1")
        logs, total = db.query_audit_logs()
        self.assertEqual(total, 1)
        self.assertEqual(logs[0]["user_id"], "u1")
        self.assertEqual(logs[0]["ip_address"], "127.0.0.1")

    def test_audit_filter_by_action(self):
        inv_id = db.stock_in(operator="t", quantity="5", **_key_fields())
        with db.get_db() as conn:
            db.write_audit(conn, "u1", "张三", "stock_in", "inventory", inv_id)
            db.write_audit(conn, "u2", "李四", "delete", "inventory", inv_id)
        _, total_in = db.query_audit_logs(action="stock_in")
        self.assertEqual(total_in, 1)


class TestMergeOnConflict(_TempDbTestCase):
    """编辑后与已有记录冲突时的自动合并（database.merge_inventory_on_conflict）"""

    def setUp(self):
        super().setUp()
        # 同组（复合键相同）、不同批号的两条记录
        self.id_a = db.stock_in(operator="t", quantity="5", **_key_fields(batch_no="LOT1"))
        self.id_b = db.stock_in(operator="t", quantity="3", **_key_fields(batch_no="LOT2"))
        self.item_a = db.inventory_get(self.id_a)

    def test_merge_accumulates_and_deletes_source(self):
        # 模拟把 A 的批号改为 LOT2（与 B 冲突），应合并到 B
        merged_fields = {**self.item_a, "batch_no": "LOT2"}
        with db.get_db() as conn:
            result = db.merge_inventory_on_conflict(conn, self.id_a, self.item_a, merged_fields)
        self.assertTrue(result["merged"])
        self.assertEqual(result["target_id"], self.id_b)
        self.assertEqual(db.qty_to_num(result["merged_quantity"]), 8.0)

        # 源记录 A 已删除
        self.assertIsNone(db.inventory_get(self.id_a))
        # 目标记录 B 数量为累加值
        item_b = db.inventory_get(self.id_b)
        self.assertEqual(db.qty_to_num(item_b["quantity"]), 8.0)

    def test_merge_migrates_stock_logs(self):
        # A 与 B 各有 1 条入库日志，合并后 A 的日志迁移到 B
        self.assertEqual(len(db.stock_logs(inventory_id=self.id_a)), 1)
        self.assertEqual(len(db.stock_logs(inventory_id=self.id_b)), 1)
        merged_fields = {**self.item_a, "batch_no": "LOT2"}
        with db.get_db() as conn:
            db.merge_inventory_on_conflict(conn, self.id_a, self.item_a, merged_fields)
        # A 的日志已迁移；B 现持有自己的 + A 迁移过来的，共 2 条
        self.assertEqual(len(db.stock_logs(inventory_id=self.id_a)), 0)
        self.assertEqual(len(db.stock_logs(inventory_id=self.id_b)), 2)

    def test_no_target_returns_not_merged(self):
        # 改为一个不存在的批号 → 无冲突目标 → merged=False
        merged_fields = {**self.item_a, "batch_no": "NONEXISTENT"}
        with db.get_db() as conn:
            result = db.merge_inventory_on_conflict(conn, self.id_a, self.item_a, merged_fields)
        self.assertFalse(result["merged"])
        # 源记录未被删除
        self.assertIsNotNone(db.inventory_get(self.id_a))


class TestGroupedQueries(_TempDbTestCase):
    def test_grouped_detail_returns_batches(self):
        db.stock_in(operator="t", quantity="5", **_key_fields(batch_no="LOT1"))
        db.stock_in(operator="t", quantity="3", **_key_fields(batch_no="LOT2"))
        batches = db.inventory_grouped_detail("QFP", "14x20", "不镀银", "粗化", "AAMI")
        self.assertEqual(len(batches), 2)

    def test_list_grouped_aggregates_quantity(self):
        db.stock_in(operator="t", quantity="5", **_key_fields(batch_no="LOT1"))
        db.stock_in(operator="t", quantity="3", **_key_fields(batch_no="LOT2"))
        groups, total = db.inventory_list_grouped()
        self.assertEqual(total, 1)
        self.assertEqual(db.qty_to_num(groups[0]["total_quantity"]), 8.0)


if __name__ == "__main__":
    unittest.main()
