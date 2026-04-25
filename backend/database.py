import sqlite3
import os
import re
import json
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        # 建 inventory 表（若不存在则按新结构创建）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_code TEXT NOT NULL DEFAULT '',
                spec TEXT NOT NULL,
                manufacturer TEXT,
                batch_no TEXT,
                production_date TEXT,
                expiry_date TEXT,
                quantity TEXT DEFAULT '0',
                note TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(material_code, batch_no)
            )
        """)

        # 迁移旧表（如果旧表没有 material_code 列）：加列并调整约束
        cursor = conn.execute("PRAGMA table_info(inventory)")
        cols = [row["name"] for row in cursor.fetchall()]
        if "material_code" not in cols:
            conn.execute("ALTER TABLE inventory ADD COLUMN material_code TEXT NOT NULL DEFAULT ''")
            # SQLite 不支持 ALTER 约束，重建表
            conn.executescript("""
                CREATE TABLE inventory_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT NOT NULL DEFAULT '',
                    spec TEXT NOT NULL,
                    manufacturer TEXT,
                    batch_no TEXT,
                    production_date TEXT,
                    expiry_date TEXT,
                    quantity TEXT DEFAULT '0',
                    note TEXT,
                    image_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(material_code, batch_no)
                );
                INSERT INTO inventory_new (id, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path, created_at, updated_at)
                    SELECT id, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path, created_at, updated_at FROM inventory;
                DROP TABLE inventory;
                ALTER TABLE inventory_new RENAME TO inventory;
            """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventory_id INTEGER REFERENCES inventory(id),
                type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                note TEXT,
                operator TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inventory_spec
            ON inventory(spec)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_log_inventory
            ON stock_log(inventory_id)
        """)

        # 审计日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                action TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id INTEGER,
                snapshot TEXT,
                changes TEXT,
                detail TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_created
            ON audit_log(created_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_log_action
            ON audit_log(action)
        """)


def inventory_list(search: str = None, page: int = 1, size: int = 20):
    with get_db() as conn:
        query = "SELECT * FROM inventory WHERE 1=1"
        params = []
        if search:
            query += " AND (material_code LIKE ? OR spec LIKE ? OR manufacturer LIKE ? OR batch_no LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([size, (page - 1) * size])
        rows = conn.execute(query, params).fetchall()

        count_query = "SELECT COUNT(*) as total FROM inventory WHERE 1=1"
        count_params = []
        if search:
            count_query += " AND (material_code LIKE ? OR spec LIKE ? OR manufacturer LIKE ? OR batch_no LIKE ?)"
            term = f"%{search}%"
            count_params.extend([term, term, term, term])
        total = conn.execute(count_query, count_params).fetchone()["total"]

        # 计算总数量（将 K/M 值转为数字求和）
        sum_query = "SELECT quantity FROM inventory WHERE 1=1"
        sum_params = []
        if search:
            sum_query += " AND (material_code LIKE ? OR spec LIKE ? OR manufacturer LIKE ? OR batch_no LIKE ?)"
            term = f"%{search}%"
            sum_params.extend([term, term, term, term])
        qty_rows = conn.execute(sum_query, sum_params).fetchall()
        total_quantity = sum(_qty_to_num(r["quantity"]) for r in qty_rows)

        return [dict(r) for r in rows], total, total_quantity


def inventory_get(item_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def _qty_to_num(val) -> float:
    """将数量字符串转为数字，支持 K/M 单位"""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    m = re.search(r"([\d.]+)\s*[Kk]", s)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"([\d.]+)\s*[Mm]", s)
    if m:
        return float(m.group(1)) * 1000000
    m = re.search(r"([\d.]+)", s)
    if m:
        return float(m.group(1))
    return 0


def _num_to_qty(val) -> str:
    """将数字转为带 K 的显示字符串"""
    v = float(val)
    if v >= 1000 and v == int(v) and v % 1000 == 0:
        k = v / 1000
        if k == int(k):
            return f"{int(k)}K"
        return f"{k}K"
    return str(int(v)) if v == int(v) else str(v)


def stock_in(material_code: str, spec: str, manufacturer: str, batch_no: str,
             production_date: str, expiry_date: str,
             quantity: str, note: str = None,
             image_path: str = None, operator: str = None):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, quantity FROM inventory WHERE material_code = ? AND batch_no = ?",
            (material_code, batch_no)
        ).fetchone()

        if existing:
            new_num = _qty_to_num(existing["quantity"]) + _qty_to_num(quantity)
            new_qty = _num_to_qty(new_num)
            conn.execute(
                """UPDATE inventory SET quantity = ?, spec = ?, manufacturer = ?, production_date = ?,
                   expiry_date = ?, note = COALESCE(?, note),
                   image_path = COALESCE(?, image_path),
                   updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (new_qty, spec, manufacturer, production_date, expiry_date, note, image_path, existing["id"])
            )
            inv_id = existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO inventory (material_code, spec, manufacturer, batch_no, production_date,
                   expiry_date, quantity, note, image_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (material_code, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path)
            )
            inv_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO stock_log (inventory_id, type, quantity, operator) VALUES (?, 'in', ?, ?)",
            (inv_id, quantity, operator)
        )
        return inv_id


def get_material_code_suggestions(spec: str) -> list:
    """根据厂家规格查询历史物料编码"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT material_code FROM inventory
               WHERE spec = ? AND material_code != ''
               ORDER BY updated_at DESC""",
            (spec,)
        ).fetchall()
        return [r["material_code"] for r in rows]


def stock_out(inventory_id: int, quantity: str, note: str = None, operator: str = None):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        item = conn.execute("SELECT quantity FROM inventory WHERE id = ?", (inventory_id,)).fetchone()
        if not item:
            return None, "库存记录不存在"
        current_num = _qty_to_num(item["quantity"])
        out_num = _qty_to_num(quantity)
        if current_num < out_num:
            return None, f"库存不足（当前: {item['quantity']}，申请出库: {quantity}）"

        new_qty = _num_to_qty(current_num - out_num)
        conn.execute(
            "UPDATE inventory SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_qty, inventory_id)
        )
        conn.execute(
            "INSERT INTO stock_log (inventory_id, type, quantity, note, operator) VALUES (?, 'out', ?, ?, ?)",
            (inventory_id, quantity, note, operator)
        )
        return inventory_id, None


def stock_logs(inventory_id: int = None, page: int = 1, size: int = 20):
    with get_db() as conn:
        query = """
            SELECT sl.*, i.spec, i.batch_no
            FROM stock_log sl JOIN inventory i ON sl.inventory_id = i.id
            WHERE 1=1
        """
        params = []
        if inventory_id:
            query += " AND sl.inventory_id = ?"
            params.append(inventory_id)
        query += " ORDER BY sl.created_at DESC LIMIT ? OFFSET ?"
        params.extend([size, (page - 1) * size])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def inventory_delete(item_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM stock_log WHERE inventory_id = ?", (item_id,))
        conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))


def write_audit(conn, user_id: str, user_name: str, action: str,
                table_name: str, record_id: int,
                snapshot: dict = None, changes: dict = None,
                detail: str = None, ip_address: str = None):
    """写入审计日志（使用已有连接，随业务事务一起提交）"""
    conn.execute(
        """INSERT INTO audit_log
           (user_id, user_name, action, table_name, record_id,
            snapshot, changes, detail, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            user_name,
            action,
            table_name,
            record_id,
            json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
            json.dumps(changes, ensure_ascii=False) if changes else None,
            detail,
            ip_address,
        ),
    )


def query_audit_logs(action: str = None, user_id: str = None,
                     page: int = 1, size: int = 20):
    with get_db() as conn:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if action:
            query += " AND action = ?"
            params.append(action)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([size, (page - 1) * size])
        rows = conn.execute(query, params).fetchall()

        count_query = "SELECT COUNT(*) as total FROM audit_log WHERE 1=1"
        count_params = []
        if action:
            count_query += " AND action = ?"
            count_params.append(action)
        if user_id:
            count_query += " AND user_id = ?"
            count_params.append(user_id)
        total = conn.execute(count_query, count_params).fetchone()["total"]

        return [dict(r) for r in rows], total
