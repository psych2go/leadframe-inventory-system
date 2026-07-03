import sqlite3
import os
import re
import json
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")

# 复合分组键：以"封装形式+规格+镀银区域+表面处理+厂家"为分组的业务定义。
# 集中定义一次，所有 GROUP BY / 精确匹配 WHERE 都从这里派生，避免 5 个字段散落各处。
# 注意：inventory 表的"唯一约束"还包含 batch_no（库存记录的唯一键），这里只覆盖【分组】维度。
COMPOSITE_KEY = ("package_type", "spec", "plating_zone", "surface_treatment", "manufacturer")
# GROUP BY 列串（纯字符串，无参数），供聚合查询复用
GROUP_BY_KEY = ", ".join(COMPOSITE_KEY)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
    # journal_mode 是数据库级别设置，只需执行一次
    init_conn = sqlite3.connect(DB_PATH)
    init_conn.execute("PRAGMA journal_mode=WAL")
    init_conn.close()

    with get_db() as conn:
        # 建 inventory 表（若不存在则按新结构创建）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                package_type TEXT NOT NULL DEFAULT '',
                spec TEXT NOT NULL DEFAULT '',
                plating_zone TEXT NOT NULL DEFAULT '',
                surface_treatment TEXT NOT NULL DEFAULT '',
                manufacturer TEXT,
                batch_no TEXT,
                production_date TEXT,
                expiry_date TEXT,
                quantity TEXT DEFAULT '0',
                note TEXT,
                image_path TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                updated_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                UNIQUE(package_type, spec, plating_zone, surface_treatment, manufacturer, batch_no)
            )
        """)

        # 迁移旧表：从 material_code 结构迁移到新结构
        cursor = conn.execute("PRAGMA table_info(inventory)")
        cols = [row["name"] for row in cursor.fetchall()]
        if "material_code" in cols and "package_type" not in cols:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                DROP TABLE IF EXISTS inventory_new;
                CREATE TABLE inventory_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_type TEXT NOT NULL DEFAULT '',
                    spec TEXT NOT NULL DEFAULT '',
                    plating_zone TEXT NOT NULL DEFAULT '',
                    surface_treatment TEXT NOT NULL DEFAULT '',
                    manufacturer TEXT,
                    batch_no TEXT,
                    production_date TEXT,
                    expiry_date TEXT,
                    quantity TEXT DEFAULT '0',
                    note TEXT,
                    image_path TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                    updated_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                    UNIQUE(package_type, spec, plating_zone, surface_treatment, manufacturer, batch_no)
                );
                INSERT INTO inventory_new (id, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path, created_at, updated_at)
                    SELECT id, spec, manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path, created_at, updated_at FROM inventory;
                DROP TABLE inventory;
                ALTER TABLE inventory_new RENAME TO inventory;
            """)
            conn.execute("PRAGMA foreign_keys=ON")

        # 迁移：唯一约束加入 manufacturer
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='inventory'")
        table_sql = cursor.fetchone()
        if table_sql and 'manufacturer' not in table_sql["sql"].split("UNIQUE")[1].split(")")[0]:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                DROP TABLE IF EXISTS inventory_new;
                CREATE TABLE inventory_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_type TEXT NOT NULL DEFAULT '',
                    spec TEXT NOT NULL DEFAULT '',
                    plating_zone TEXT NOT NULL DEFAULT '',
                    surface_treatment TEXT NOT NULL DEFAULT '',
                    manufacturer TEXT,
                    batch_no TEXT,
                    production_date TEXT,
                    expiry_date TEXT,
                    quantity TEXT DEFAULT '0',
                    note TEXT,
                    image_path TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                    updated_at TIMESTAMP DEFAULT (datetime('now','+8 hours')),
                    UNIQUE(package_type, spec, plating_zone, surface_treatment, manufacturer, batch_no)
                );
                INSERT OR IGNORE INTO inventory_new
                    SELECT * FROM inventory;
                DROP TABLE inventory;
                ALTER TABLE inventory_new RENAME TO inventory;
            """)
            conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inventory_id INTEGER REFERENCES inventory(id),
                type TEXT NOT NULL,
                quantity TEXT NOT NULL,
                note TEXT,
                operator TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now','+8 hours'))
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

        # 迁移：stock_log.quantity 从 INTEGER 改为 TEXT（匹配 inventory.quantity）
        stock_schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stock_log'").fetchone()
        if stock_schema and "quantity INTEGER" in stock_schema["sql"]:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript("""
                DROP TABLE IF EXISTS stock_log_new;
                CREATE TABLE stock_log_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inventory_id INTEGER REFERENCES inventory(id),
                    type TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    note TEXT,
                    operator TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now','+8 hours'))
                );
                INSERT INTO stock_log_new SELECT * FROM stock_log;
                DROP TABLE stock_log;
                ALTER TABLE stock_log_new RENAME TO stock_log;
            """)
            conn.execute("PRAGMA foreign_keys=ON")

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
                created_at TIMESTAMP DEFAULT (datetime('now','+8 hours'))
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
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inventory_updated
            ON inventory(updated_at DESC)
        """)


def build_search_conditions(search: str = None,
                              package_type: str = None,
                              spec: str = None,
                              plating_zone: str = None,
                              surface_treatment: str = None,
                              manufacturer: str = None):
    """构建搜索 + 筛选 WHERE 条件和参数"""
    where = ""
    params = []
    if search:
        where = """ AND (package_type LIKE ? OR spec LIKE ? OR plating_zone LIKE ?
                   OR surface_treatment LIKE ? OR manufacturer LIKE ? OR batch_no LIKE ?)"""
        term = f"%{search}%"
        params = [term, term, term, term, term, term]
    if package_type:
        where += " AND package_type LIKE ?"
        params.append(f"%{package_type}%")
    if spec:
        where += " AND spec LIKE ?"
        params.append(f"%{spec}%")
    if plating_zone:
        where += " AND plating_zone = ?"
        params.append(plating_zone)
    if surface_treatment:
        where += " AND surface_treatment = ?"
        params.append(surface_treatment)
    if manufacturer:
        where += " AND manufacturer = ?"
        params.append(manufacturer)
    return where, params


def group_key_match(key_values: dict, prefix: str = "",
                    extra_clauses: list = None, extra_params: list = None):
    """构造匹配复合分组键的精确 WHERE 片段。

    从 COMPOSITE_KEY 派生，避免 5 个字段名散落各处。返回 (clause, params)：
    - clause：形如 "package_type = ? AND spec = ? ... AND manufacturer = ?"，
              可带前缀（如联表查询的 "i."）和追加的额外条件（batch_no / id != ? 等）。
    - params：按 COMPOSITE_KEY 顺序绑定键值，再追加 extra_params。

    示例：
        clause, params = group_key_match(
            {"package_type": pt, "spec": sp, "plating_zone": pz,
             "surface_treatment": st, "manufacturer": mf},
            extra_clauses=["batch_no = ?", "id != ?"],
            extra_params=[batch_no, item_id],
        )
        conn.execute(f"SELECT ... WHERE {clause}", params)
    """
    parts = []
    params = []
    for f in COMPOSITE_KEY:
        parts.append(f"{prefix}{f} = ?")
        params.append(key_values[f])
    for clause in (extra_clauses or []):
        parts.append(clause)
    params.extend(extra_params or [])
    return " AND ".join(parts), params


def inventory_list(search: str = None, page: int = 1, size: int = 20,
                    package_type: str = None, spec: str = None,
                    plating_zone: str = None, surface_treatment: str = None,
                    manufacturer: str = None):
    with get_db() as conn:
        where, params = build_search_conditions(search, package_type, spec, plating_zone, surface_treatment, manufacturer)

        rows = conn.execute(
            f"SELECT * FROM inventory WHERE 1=1{where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()

        total_qty_info = conn.execute(
            f"SELECT COUNT(*) as total, COALESCE(SUM(CAST(quantity AS REAL)), 0) as total_qty FROM inventory WHERE 1=1{where}", params
        ).fetchone()
        total = total_qty_info["total"]
        total_quantity = total_qty_info["total_qty"]

        return [dict(r) for r in rows], total, total_quantity


def inventory_list_grouped(search: str = None, page: int = 1, size: int = 20,
                           package_type: str = None, spec: str = None,
                           plating_zone: str = None, surface_treatment: str = None,
                           manufacturer: str = None,
                           alert_only: bool = False):
    with get_db() as conn:
        where, params = build_search_conditions(search, package_type, spec, plating_zone, surface_treatment, manufacturer)

        having = " HAVING COALESCE(SUM(CAST(quantity AS REAL)), 0) < 2" if alert_only else ""

        rows = conn.execute(
            f"""SELECT package_type, spec, plating_zone, surface_treatment, manufacturer,
                       COUNT(*) as batch_count,
                       COALESCE(SUM(CAST(quantity AS REAL)), 0) as total_quantity
                FROM inventory WHERE 1=1{where}
                GROUP BY {GROUP_BY_KEY}
                {having}
                ORDER BY MAX(updated_at) DESC
                LIMIT ? OFFSET ?""",
            params + [size, (page - 1) * size],
        ).fetchall()

        total = conn.execute(
            f"""SELECT COUNT(*) as total FROM (
                   SELECT 1 FROM inventory WHERE 1=1{where}
                   GROUP BY {GROUP_BY_KEY}
                   {having}
               )""",
            params,
        ).fetchone()["total"]

        groups = []
        for r in rows:
            g = dict(r)
            g["total_quantity"] = num_to_qty(g["total_quantity"])
            groups.append(g)
        return groups, total


def inventory_grouped_detail(package_type: str, spec: str, plating_zone: str,
                              surface_treatment: str, manufacturer: str):
    with get_db() as conn:
        where, params = group_key_match({
            "package_type": package_type, "spec": spec, "plating_zone": plating_zone,
            "surface_treatment": surface_treatment, "manufacturer": manufacturer,
        })
        rows = conn.execute(
            f"""SELECT * FROM inventory
               WHERE {where}
               ORDER BY batch_no""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def inventory_update_grouped(old_fields: dict, new_fields: dict):
    """批量更新一个分组的公共基本信息字段（同组的所有批次）"""
    with get_db() as conn:
        # SET 子句与 WHERE 子句都从 COMPOSITE_KEY 派生，避免字段名散落
        set_clause = ", ".join(f"{f} = ?" for f in COMPOSITE_KEY)
        set_values = [new_fields.get(f, "") for f in COMPOSITE_KEY]
        where, where_params = group_key_match(old_fields)
        conn.execute(
            f"""UPDATE inventory SET {set_clause},
               updated_at = datetime('now','+8 hours')
               WHERE {where}""",
            set_values + where_params,
        )


def inventory_get(item_id: int):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None


def qty_to_num(val) -> float:
    """将数量字符串转为数字（系统以 K 为单位存储，忽略 K/M 后缀）"""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    m = re.search(r"([\d.]+)", s)
    return float(m.group(1)) if m else 0


def num_to_qty(val) -> str:
    """将数字转为 K 单位的数量字符串（纯数字，不再加 K 后缀）"""
    v = round(float(val), 3)
    return str(int(v)) if v == int(v) else f"{v:.3f}".rstrip("0").rstrip(".")


def merge_inventory_on_conflict(conn, item_id: int, item: dict, merged_fields: dict) -> dict:
    """编辑后与已有记录唯一键冲突时的自动合并。

    把当前记录（item_id）的数量累加到目标记录、迁移 stock_log、删除当前记录。
    必须在调用方事务中执行（conn 由调用方提供并已持有 BEGIN IMMEDIATE）。

    参数：
      item_id: 当前被编辑的记录 id
      item: 当前记录的原始快照（dict，含 quantity 等）
      merged_fields: 合并后的字段集合（{**item, **updates}），用于定位目标记录与回填

    返回：
      命中目标 → {"merged": True, "target_id": int,
                  "merged_quantity": str, "quantity_added": str}
      未命中   → {"merged": False}（调用方据此抛"该组合已存在"错误）
    """
    key = {f: merged_fields[f] for f in COMPOSITE_KEY}
    batch_no = merged_fields.get("batch_no", "")
    where, params = group_key_match(
        key, extra_clauses=["batch_no = ?", "id != ?"],
        extra_params=[batch_no, item_id],
    )
    target = conn.execute(
        f"SELECT id, quantity FROM inventory WHERE {where}", params,
    ).fetchone()
    if not target:
        return {"merged": False}

    merged_quantity = num_to_qty(
        qty_to_num(target["quantity"]) + qty_to_num(item["quantity"])
    )
    # 注意：保持原有字段更新范围（quantity + manufacturer + production_date + expiry_date）
    conn.execute(
        """UPDATE inventory SET quantity = ?, manufacturer = ?,
           production_date = ?, expiry_date = ?,
           updated_at = datetime('now','+8 hours') WHERE id = ?""",
        (merged_quantity, merged_fields["manufacturer"], merged_fields["production_date"],
         merged_fields["expiry_date"], target["id"]),
    )
    # 迁移 stock_log 到目标记录
    conn.execute(
        "UPDATE stock_log SET inventory_id = ? WHERE inventory_id = ?",
        (target["id"], item_id),
    )
    conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    return {
        "merged": True,
        "target_id": target["id"],
        "merged_quantity": merged_quantity,
        "quantity_added": item["quantity"],
    }


def stock_in(package_type: str, spec: str, plating_zone: str, surface_treatment: str,
             manufacturer: str, batch_no: str,
             production_date: str, expiry_date: str,
             quantity: str, note: str = None,
             image_path: str = None, operator: str = None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
        conn.execute("BEGIN IMMEDIATE")
    try:
        key = {
            "package_type": package_type, "spec": spec, "plating_zone": plating_zone,
            "surface_treatment": surface_treatment, "manufacturer": manufacturer,
        }
        where, params = group_key_match(
            key, extra_clauses=["batch_no = ?"], extra_params=[batch_no],
        )
        existing = conn.execute(
            f"""SELECT id, quantity FROM inventory
               WHERE {where}""",
            params,
        ).fetchone()

        if existing:
            new_num = qty_to_num(existing["quantity"]) + qty_to_num(quantity)
            new_qty = num_to_qty(new_num)
            conn.execute(
                """UPDATE inventory SET quantity = ?, plating_zone = ?, surface_treatment = ?,
                   manufacturer = ?, production_date = ?, expiry_date = ?,
                   note = COALESCE(?, note), image_path = COALESCE(?, image_path),
                   updated_at = datetime('now','+8 hours') WHERE id = ?""",
                (new_qty, plating_zone, surface_treatment,
                 manufacturer, production_date, expiry_date, note, image_path, existing["id"])
            )
            inv_id = existing["id"]
        else:
            cursor = conn.execute(
                """INSERT INTO inventory (package_type, spec, plating_zone, surface_treatment,
                   manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (package_type, spec, plating_zone, surface_treatment,
                 manufacturer, batch_no, production_date, expiry_date, quantity, note, image_path)
            )
            inv_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO stock_log (inventory_id, type, quantity, operator, created_at) VALUES (?, 'in', ?, ?, datetime('now','+8 hours'))",
            (inv_id, quantity, operator)
        )
        if own_conn:
            conn.commit()
        return inv_id
    finally:
        if own_conn:
            conn.close()


def stock_out(inventory_id: int, quantity: str, note: str = None, operator: str = None, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        item = conn.execute("SELECT quantity FROM inventory WHERE id = ?", (inventory_id,)).fetchone()
        if not item:
            return None, "库存记录不存在"
        current_num = qty_to_num(item["quantity"])
        out_num = qty_to_num(quantity)
        if current_num < out_num:
            return None, f"库存不足（当前: {item['quantity']}，申请出库: {quantity}）"

        new_qty = num_to_qty(current_num - out_num)
        conn.execute(
            "UPDATE inventory SET quantity = ?, updated_at = datetime('now','+8 hours') WHERE id = ?",
            (new_qty, inventory_id)
        )
        conn.execute(
            "INSERT INTO stock_log (inventory_id, type, quantity, note, operator, created_at) VALUES (?, 'out', ?, ?, ?, datetime('now','+8 hours'))",
            (inventory_id, quantity, note, operator)
        )
        if own_conn:
            conn.commit()
        return inventory_id, None
    finally:
        if own_conn:
            conn.close()


def stock_logs(inventory_id: int = None, page: int = 1, size: int = 20):
    with get_db() as conn:
        query = """
            SELECT sl.*, i.spec, i.batch_no, i.package_type, i.plating_zone,
                   i.surface_treatment, i.manufacturer
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


def stock_logs_grouped(package_type="", spec="", plating_zone="",
                       surface_treatment="", manufacturer="",
                       page=1, size=20):
    with get_db() as conn:
        where = ""
        params = []
        if package_type:
            where += " AND i.package_type = ?"
            params.append(package_type)
        if spec:
            where += " AND i.spec = ?"
            params.append(spec)
        if plating_zone:
            where += " AND i.plating_zone = ?"
            params.append(plating_zone)
        if surface_treatment:
            where += " AND i.surface_treatment = ?"
            params.append(surface_treatment)
        if manufacturer:
            where += " AND i.manufacturer = ?"
            params.append(manufacturer)

        total = conn.execute(
            f"SELECT COUNT(*) FROM stock_log sl JOIN inventory i ON sl.inventory_id = i.id WHERE 1=1{where}",
            params,
        ).fetchone()[0]

        query = f"""
            SELECT sl.*, i.spec, i.batch_no, i.package_type, i.plating_zone,
                   i.surface_treatment, i.manufacturer
            FROM stock_log sl JOIN inventory i ON sl.inventory_id = i.id
            WHERE 1=1{where}
            ORDER BY sl.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([size, (page - 1) * size])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows], total


def write_audit(conn, user_id: str, user_name: str, action: str,
                table_name: str, record_id: int,
                snapshot: dict = None, changes: dict = None,
                detail: str = None, ip_address: str = None):
    """写入审计日志（使用已有连接，随业务事务一起提交）"""
    conn.execute(
        """INSERT INTO audit_log
           (user_id, user_name, action, table_name, record_id,
            snapshot, changes, detail, ip_address, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','+8 hours'))""",
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
        conditions, params = [], []
        if action:
            conditions.append("action = ?")
            params.append(action)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        rows = conn.execute(
            f"SELECT * FROM audit_log{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [size, (page - 1) * size],
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) as total FROM audit_log{where}", params,
        ).fetchone()["total"]

        return [dict(r) for r in rows], total
