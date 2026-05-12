import os
import io
import re
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import database as db
from routers.auth import get_current_user_optional

router = APIRouter()

_QTY_PATTERN = re.compile(r"^[\d.]+\s*(K|KPC|KPD|k|kpc|kpd|M|PCS|pcs|只|万)?\s*$", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_quantity(quantity: str):
    if not _QTY_PATTERN.match(quantity.strip()):
        raise HTTPException(400, f"数量格式无效: {quantity}")


def _validate_date(date_str: str, field_name: str):
    if date_str and not _DATE_PATTERN.match(date_str.strip()):
        raise HTTPException(400, f"{field_name}格式无效，请使用 YYYY-MM-DD")


class StockInRequest(BaseModel):
    package_type: str = ""
    spec: str
    plating_zone: str = ""
    surface_treatment: str = ""
    manufacturer: str = ""
    batch_no: str = ""
    production_date: str = ""
    expiry_date: str = ""
    quantity: str
    note: str = None
    image_path: str = None
    operator: str = None


class StockOutRequest(BaseModel):
    inventory_id: int
    quantity: str
    note: str = None
    operator: str = None


class InventoryUpdateRequest(BaseModel):
    package_type: str = None
    spec: str = None
    plating_zone: str = None
    surface_treatment: str = None
    manufacturer: str = None
    batch_no: str = None
    production_date: str = None
    expiry_date: str = None


@router.get("/inventory")
def list_inventory(search: str = None,
                   package_type: str = None, spec: str = None,
                   plating_zone: str = None, surface_treatment: str = None,
                   page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    items, total, total_quantity = db.inventory_list(
        search, page, size,
        package_type=package_type, spec=spec,
        plating_zone=plating_zone, surface_treatment=surface_treatment,
    )
    return {"items": items, "total": total, "total_quantity": total_quantity, "page": page, "size": size}


ALERT_THRESHOLD = 2  # 单位: K（2K = 2000 只）


@router.get("/inventory/filter-options")
def get_filter_options():
    with db.get_db() as conn:
        pkg_rows = conn.execute(
            "SELECT DISTINCT package_type FROM inventory WHERE package_type != '' ORDER BY package_type"
        ).fetchall()
        spec_rows = conn.execute(
            "SELECT DISTINCT spec FROM inventory WHERE spec != '' ORDER BY spec"
        ).fetchall()
    return {
        "package_types": [r["package_type"] for r in pkg_rows],
        "specs": [r["spec"] for r in spec_rows],
    }


@router.get("/inventory/alerts")
def get_inventory_alerts():
    """获取低库存预警列表（分组总量 < 2K）"""
    with db.get_db() as conn:
        rows = conn.execute(
            """SELECT package_type, spec, plating_zone, surface_treatment, manufacturer,
                      COUNT(*) as batch_count,
                      COALESCE(SUM(CAST(quantity AS REAL)), 0) as total_quantity
               FROM inventory
               GROUP BY package_type, spec, plating_zone, surface_treatment, manufacturer
               HAVING COALESCE(SUM(CAST(quantity AS REAL)), 0) < ?
               ORDER BY total_quantity ASC""",
            (ALERT_THRESHOLD,),
        ).fetchall()
        items = []
        for r in rows:
            g = dict(r)
            g["total_quantity"] = db._num_to_qty(g["total_quantity"])
            items.append(g)
    return {"items": items, "threshold": ALERT_THRESHOLD}


@router.get("/inventory-grouped")
def list_inventory_grouped(search: str = None,
                            package_type: str = None, spec: str = None,
                            plating_zone: str = None, surface_treatment: str = None,
                            alert: bool = Query(False),
                            page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    groups, total = db.inventory_list_grouped(
        search, page, size,
        package_type=package_type, spec=spec,
        plating_zone=plating_zone, surface_treatment=surface_treatment,
        alert_only=alert,
    )
    return {"items": groups, "total": total, "page": page, "size": size}


@router.get("/inventory-grouped/detail")
def get_inventory_grouped_detail(package_type: str = Query(""),
                                  spec: str = Query(""),
                                  plating_zone: str = Query(""),
                                  surface_treatment: str = Query(""),
                                  manufacturer: str = Query("")):
    batches = db.inventory_grouped_detail(package_type, spec, plating_zone, surface_treatment, manufacturer)
    if not batches:
        raise HTTPException(404, "未找到匹配的库存记录")
    total_qty = db._num_to_qty(sum(db._qty_to_num(b["quantity"]) for b in batches))
    return {
        "package_type": package_type,
        "spec": spec,
        "plating_zone": plating_zone,
        "surface_treatment": surface_treatment,
        "manufacturer": manufacturer,
        "total_quantity": total_qty,
        "batch_count": len(batches),
        "batches": batches,
    }


@router.put("/inventory-grouped/update")
def update_inventory_grouped(body: dict):
    old = body.get("old", {})
    new = body.get("new", {})
    required = ["package_type", "spec", "plating_zone", "surface_treatment", "manufacturer"]
    for k in required:
        if k not in old:
            raise HTTPException(400, f"缺少原始字段: {k}")
    if not new:
        raise HTTPException(400, "缺少更新内容")
    db.inventory_update_grouped(old, new)
    return {"detail": "更新成功"}


@router.get("/inventory/export")
def export_inventory(search: str = None,
                     package_type: str = None, spec: str = None,
                     plating_zone: str = None, surface_treatment: str = None):
    """导出库存为 Excel 文件（两个 sheet：汇总 + 明细）"""
    import openpyxl

    with db.get_db() as conn:
        where, params = db._build_search_conditions(
            search, package_type, spec, plating_zone, surface_treatment,
        )
        rows = conn.execute(
            f"SELECT * FROM inventory WHERE 1=1{where} ORDER BY updated_at DESC",
            params,
        ).fetchall()

    wb = openpyxl.Workbook()

    # Sheet 1: 汇总（按分组聚合，无批号/日期/备注）
    ws1 = wb.active
    ws1.title = "库存汇总"
    ws1.append(["封装形式", "规格", "镀银区域", "表面粗化处理", "厂家", "总数量(K)", "批次数"])
    groups = {}
    for row in rows:
        key = (row["package_type"], row["spec"], row["plating_zone"],
               row["surface_treatment"], row["manufacturer"])
        if key not in groups:
            groups[key] = {"qty": 0, "count": 0}
        groups[key]["qty"] += db._qty_to_num(row["quantity"])
        groups[key]["count"] += 1
    for (pt, sp, pz, st, mf), g in groups.items():
        ws1.append([pt, sp, pz, st, mf, db._num_to_qty(g["qty"]), g["count"]])
    for col in ws1.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws1.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

    # Sheet 2: 明细（完整字段）
    ws2 = wb.create_sheet("库存明细")
    ws2.append(["封装形式", "规格", "镀银区域", "表面粗化处理", "厂家", "批号", "生产日期", "有效期", "数量", "备注"])
    for row in rows:
        ws2.append([
            row["package_type"],
            row["spec"],
            row["plating_zone"],
            row["surface_treatment"],
            row["manufacturer"],
            row["batch_no"],
            row["production_date"],
            row["expiry_date"],
            row["quantity"],
            row["note"] or "",
        ])
    for col in ws2.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws2.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"inventory_{date_str}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/inventory/{item_id}")
def get_inventory(item_id: int):
    item = db.inventory_get(item_id)
    if not item:
        raise HTTPException(404, "库存记录不存在")
    return item


def _audit_user(request: Request):
    """从请求中提取审计用的用户信息"""
    user = get_current_user_optional(request)
    return (
        user["user_id"] if user else None,
        user.get("name") if user else None,
    )


@router.post("/stock-in")
def do_stock_in(req: StockInRequest, request: Request):
    user_id, user_name = _audit_user(request)
    if not req.quantity:
        raise HTTPException(400, "入库数量不能为空")
    _validate_quantity(req.quantity)
    if not req.spec.strip():
        raise HTTPException(400, "规格不能为空")
    _validate_date(req.production_date, "生产日期")
    _validate_date(req.expiry_date, "有效日期")
    with db.get_db() as conn:
        inv_id = db.stock_in(
            package_type=req.package_type.strip(),
            spec=req.spec.strip(),
            plating_zone=req.plating_zone.strip(),
            surface_treatment=req.surface_treatment.strip(),
            manufacturer=req.manufacturer.strip(),
            batch_no=req.batch_no.strip(),
            production_date=req.production_date.strip(),
            expiry_date=req.expiry_date.strip(),
            quantity=req.quantity,
            note=req.note,
            image_path=req.image_path,
            operator=user_name,
            conn=conn,
        )
        db.write_audit(
            conn, user_id, user_name, "stock_in", "inventory", inv_id,
            detail=f"入库 {req.quantity}K | {req.spec} | 批号:{req.batch_no}",
            ip_address=request.client.host if request.client else None,
        )
    return {"id": inv_id, "message": "入库成功"}


@router.post("/stock-out")
def do_stock_out(req: StockOutRequest, request: Request):
    user_id, user_name = _audit_user(request)
    if not req.quantity:
        raise HTTPException(400, "出库数量不能为空")
    _validate_quantity(req.quantity)
    # 记录操作前快照
    old_item = db.inventory_get(req.inventory_id)
    with db.get_db() as conn:
        inv_id, error = db.stock_out(req.inventory_id, req.quantity, req.note, user_name, conn=conn)
        if error:
            raise HTTPException(400, error)
        db.write_audit(
            conn, user_id, user_name, "stock_out", "inventory", inv_id,
            snapshot=old_item,
            detail=f"出库 {req.quantity}K",
            ip_address=request.client.host if request.client else None,
        )
    return {"id": inv_id, "message": "出库成功"}


@router.put("/inventory/{item_id}")
def update_inventory(item_id: int, req: InventoryUpdateRequest, request: Request):
    user_id, user_name = _audit_user(request)
    item = db.inventory_get(item_id)
    if not item:
        raise HTTPException(404, "库存记录不存在")

    updates = {k: v for k, v in {
        "package_type": req.package_type, "spec": req.spec,
        "plating_zone": req.plating_zone, "surface_treatment": req.surface_treatment,
        "manufacturer": req.manufacturer, "batch_no": req.batch_no,
        "production_date": req.production_date, "expiry_date": req.expiry_date,
    }.items() if v is not None}

    if updates:
        # 计算变更 diff
        changes = {}
        for k, new_val in updates.items():
            old_val = item.get(k)
            if str(old_val) != str(new_val):
                changes[k] = {"old": old_val, "new": new_val}

        with db.get_db() as conn:
            try:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [item_id]
                conn.execute(
                    f"UPDATE inventory SET {set_clause}, updated_at = datetime('now','localtime') WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError:
                # 编辑后与已有记录冲突，自动合并：数量累加到已有记录，删除当前记录
                merged = {**item, **updates}
                target = conn.execute(
                    """SELECT id, quantity FROM inventory
                       WHERE package_type = ? AND spec = ? AND plating_zone = ?
                       AND surface_treatment = ? AND batch_no = ? AND id != ?""",
                    (merged["package_type"], merged["spec"], merged["plating_zone"],
                     merged["surface_treatment"], merged["batch_no"], item_id),
                ).fetchone()

                if target:
                    merged_qty = db._num_to_qty(
                        db._qty_to_num(target["quantity"]) + db._qty_to_num(item["quantity"])
                    )
                    conn.execute(
                        """UPDATE inventory SET quantity = ?, manufacturer = ?,
                           production_date = ?, expiry_date = ?,
                           updated_at = datetime('now','localtime') WHERE id = ?""",
                        (merged_qty, merged["manufacturer"], merged["production_date"],
                         merged["expiry_date"], target["id"]),
                    )
                    # 迁移 stock_log 到目标记录
                    conn.execute(
                        "UPDATE stock_log SET inventory_id = ? WHERE inventory_id = ?",
                        (target["id"], item_id),
                    )
                    conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
                    db.write_audit(
                        conn, user_id, user_name, "update", "inventory", target["id"],
                        snapshot=item,
                        changes={"merged_from": item_id, "quantity_added": item["quantity"], "merged_quantity": merged_qty},
                        detail=f"合并记录 #{item_id} → #{target['id']}，数量累加后: {merged_qty}K",
                        ip_address=request.client.host if request.client else None,
                    )
                    return {"message": "已自动合并到已有记录", "merged_into": target["id"]}
                else:
                    raise HTTPException(400, "该组合已存在，不能重复")

            # 审计：更新操作（只记录实际变更的字段）
            if changes:
                db.write_audit(
                    conn, user_id, user_name, "update", "inventory", item_id,
                    snapshot=item,
                    changes=changes,
                    ip_address=request.client.host if request.client else None,
                )
    return {"message": "更新成功"}


@router.delete("/inventory/{item_id}")
def delete_inventory(item_id: int, request: Request):
    user_id, user_name = _audit_user(request)
    item = db.inventory_get(item_id)
    if not item:
        raise HTTPException(404, "库存记录不存在")
    # 审计：删除操作（记录完整快照）
    with db.get_db() as conn:
        db.write_audit(
            conn, user_id, user_name, "delete", "inventory", item_id,
            snapshot=item,
            ip_address=request.client.host if request.client else None,
        )
        conn.execute("DELETE FROM stock_log WHERE inventory_id = ?", (item_id,))
        conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    return {"message": "删除成功"}


@router.get("/stock-logs")
def get_stock_logs(inventory_id: int = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    logs = db.stock_logs(inventory_id, page, size)
    return {"items": logs}


@router.delete("/stock-logs/{log_id}")
def delete_stock_log(log_id: int, request: Request):
    user_id, user_name = _audit_user(request)
    with db.get_db() as conn:
        log = conn.execute("SELECT * FROM stock_log WHERE id = ?", (log_id,)).fetchone()
        if not log:
            raise HTTPException(404, "记录不存在")

        inv = conn.execute("SELECT * FROM inventory WHERE id = ?", (log["inventory_id"],)).fetchone()
        if not inv:
            raise HTTPException(400, "关联的库存记录已不存在，无法撤销")

        log_qty = db._qty_to_num(log["quantity"])
        inv_qty = db._qty_to_num(inv["quantity"])

        if log["type"] == "in":
            if inv_qty < log_qty:
                raise HTTPException(400, f"撤销入库会导致库存为负（当前: {inv['quantity']}K，需扣减: {log['quantity']}K）")
            new_qty = db._num_to_qty(inv_qty - log_qty)
        else:
            new_qty = db._num_to_qty(inv_qty + log_qty)

        conn.execute(
            "UPDATE inventory SET quantity = ?, updated_at = datetime('now','localtime') WHERE id = ?",
            (new_qty, inv["id"]),
        )
        conn.execute("DELETE FROM stock_log WHERE id = ?", (log_id,))

        action_desc = "撤销入库" if log["type"] == "in" else "撤销出库"
        db.write_audit(
            conn, user_id, user_name, "delete", "stock_log", log_id,
            snapshot=dict(log),
            detail=f"{action_desc}：{log['quantity']}K",
            ip_address=request.client.host if request.client else None,
        )
    return {"message": "删除成功"}


@router.get("/audit-logs")
def get_audit_logs(
    action: str = Query(None, description="操作类型: stock_in/stock_out/update/delete"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = db.query_audit_logs(action=action, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/uploads/{filename}")
def get_image(filename: str):
    from fastapi.responses import FileResponse
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "非法文件名")
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    filepath = os.path.join(upload_dir, filename)
    real_path = os.path.realpath(filepath)
    real_upload = os.path.realpath(upload_dir)
    if not real_path.startswith(real_upload + os.sep) and real_path != real_upload:
        raise HTTPException(400, "非法文件路径")
    if not os.path.exists(filepath):
        raise HTTPException(404, "图片不存在")
    return FileResponse(filepath)
