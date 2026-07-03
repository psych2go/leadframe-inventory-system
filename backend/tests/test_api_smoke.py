"""端到端 API 冒烟测试。

通过 FastAPI TestClient 走真实 HTTP 流程，验证重构后的处理函数
（_audit 封装、group_key_match、merge_inventory_on_conflict、Excel 导出服务）
在请求链路中协同工作。使用临时数据库，不污染真实 inventory.db。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 import main / 触发 lifespan 之前覆盖 DB_PATH，使 init_db 建在临时库
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

import database as db
db.DB_PATH = _tmp_db.name

from fastapi.testclient import TestClient
import main  # noqa: E402  创建 app 实例

_AUDIT_USER_COUNT = 0  # 占位，避免 lint


def _stockin_payload(**overrides):
    base = dict(
        package_type="QFP", spec="14x20", plating_zone="不镀银",
        surface_treatment="粗化", manufacturer="AAMI", batch_no="LOT1",
        production_date="2024-01-01", expiry_date="2025-01-01",
        quantity="5",
    )
    base.update(overrides)
    return base


class TestApiFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_cm = TestClient(main.app)
        cls.client = cls._client_cm.__enter__()  # 触发 lifespan → init_db

    @classmethod
    def tearDownClass(cls):
        cls._client_cm.__exit__(None, None, None)
        db.DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "inventory.db")
        try:
            os.unlink(_tmp_db.name)
        except OSError:
            pass

    def test_1_health_and_config(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        cfg = self.client.get("/api/config").json()
        self.assertIn("auth_required", cfg)

    def test_2_stock_in_creates_record_and_audits(self):
        r = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-A", quantity="5"))
        self.assertEqual(r.status_code, 200, r.text)
        inv_id = r.json()["id"]
        self.assertIsNotNone(inv_id)
        # 审计日志应写入（_audit 封装路径）
        logs = self.client.get("/api/audit-logs?action=stock_in").json()
        self.assertGreaterEqual(logs["total"], 1)

    def test_3_same_key_accumulates(self):
        self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-ACC", quantity="5"))
        r2 = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-ACC", quantity="3"))
        # 第二次累加到同一记录，返回相同 id
        item = self.client.get(f"/api/inventory/{r2.json()['id']}").json()
        self.assertEqual(db.qty_to_num(item["quantity"]), 8.0)

    def test_4_list_grouped_export(self):
        # 列表
        lst = self.client.get("/api/inventory").json()
        self.assertGreaterEqual(lst["total"], 1)
        # 分组查询（group_key_match / GROUP_BY_KEY 路径）
        g = self.client.get("/api/inventory-grouped").json()
        self.assertGreaterEqual(g["total"], 1)
        self.assertIn("total_quantity", g["items"][0])
        # Excel 导出（services/export.build_inventory_excel 路径）
        exp = self.client.get("/api/inventory/export")
        self.assertEqual(exp.status_code, 200)
        self.assertIn("spreadsheet", exp.headers.get("content-type", ""))

    def test_5_merge_on_conflict_via_put(self):
        # 两条同组不同批号
        ra = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-MRG-A", quantity="5",
                                                                      manufacturer="MERGE-MFR"))
        rb = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-MRG-B", quantity="3",
                                                                      manufacturer="MERGE-MFR"))
        id_b = rb.json()["id"]
        # 把 B 的批号改为 A → 唯一键冲突 → 自动合并到 A
        r = self.client.put(f"/api/inventory/{id_b}", json={"batch_no": "SMK-MRG-A"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertIn("merged_into", body, body)
        # B 已被删除
        self.assertEqual(self.client.get(f"/api/inventory/{id_b}").status_code, 404)
        # 目标记录数量为 5+3=8
        target = self.client.get(f"/api/inventory/{body['merged_into']}").json()
        self.assertEqual(db.qty_to_num(target["quantity"]), 8.0)

    def test_6_stock_out_and_undo(self):
        ri = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-OUT", quantity="10",
                                                                      manufacturer="OUT-MFR"))
        inv_id = ri.json()["id"]
        # 出库 4
        ro = self.client.post("/api/stock-out", json={"inventory_id": inv_id, "quantity": "4"})
        self.assertEqual(ro.status_code, 200, ro.text)
        item = self.client.get(f"/api/inventory/{inv_id}").json()
        self.assertEqual(db.qty_to_num(item["quantity"]), 6.0)
        # 撤销那条出库日志 → 数量恢复到 10
        log = self.client.get(f"/api/stock-logs?inventory_id={inv_id}").json()["items"][0]
        # 找到 out 类型的日志
        out_log = next(l for l in self.client.get(f"/api/stock-logs?inventory_id={inv_id}").json()["items"]
                       if l["type"] == "out")
        rd = self.client.delete(f"/api/stock-logs/{out_log['id']}")
        self.assertEqual(rd.status_code, 200, rd.text)
        item2 = self.client.get(f"/api/inventory/{inv_id}").json()
        self.assertEqual(db.qty_to_num(item2["quantity"]), 10.0)

    def test_7_insufficient_stock_blocked(self):
        ri = self.client.post("/api/stock-in", json=_stockin_payload(batch_no="SMK-INSUF", quantity="2",
                                                                      manufacturer="INSUF-MFR"))
        inv_id = ri.json()["id"]
        ro = self.client.post("/api/stock-out", json={"inventory_id": inv_id, "quantity": "100"})
        self.assertEqual(ro.status_code, 400)
        # 数量未被改动
        item = self.client.get(f"/api/inventory/{inv_id}").json()
        self.assertEqual(db.qty_to_num(item["quantity"]), 2.0)


if __name__ == "__main__":
    unittest.main()
