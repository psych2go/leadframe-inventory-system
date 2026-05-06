import os
import io
import re
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, HTTPException
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
def list_inventory(search: str = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    items, total, total_quantity = db.inventory_list(search, page, size)
    return {"items": items, "total": total, "total_quantity": total_quantity, "page": page, "size": size}


ALERT_THRESHOLD = 2  # 单位: K（2K = 2000 只）


@router.get("/inventory/alerts")
def get_inventory_alerts():
    """获取低库存预警列表（数量 < 2K）"""
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM inventory WHERE CAST(quantity AS REAL) < ? ORDER BY updated_at DESC",
            (ALERT_THRESHOLD,),
        ).fetchall()
    return {"items": [dict(r) for r in rows], "threshold": ALERT_THRESHOLD}


@router.get("/inventory/export")
def export_inventory(search: str = None):
    """导出库存为 Excel 文件"""
    import openpyxl

    with db.get_db() as conn:
        query = "SELECT * FROM inventory WHERE 1=1"
        params = []
        if search:
            query += """ AND (package_type LIKE ? OR spec LIKE ? OR plating_zone LIKE ?
                        OR surface_treatment LIKE ? OR manufacturer LIKE ? OR batch_no LIKE ?)"""
            term = f"%{search}%"
            params.extend([term, term, term, term, term, term])
        query += " ORDER BY updated_at DESC"
        rows = conn.execute(query, params).fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "库存清单"

    headers = ["封装形式", "规格", "镀银区域", "表面粗化处理", "厂家", "批号", "生产日期", "有效期", "数量", "备注"]
    ws.append(headers)

    for row in rows:
        ws.append([
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

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)

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

    updates = {}
    if req.package_type is not None:
        updates["package_type"] = req.package_type
    if req.spec is not None:
        updates["spec"] = req.spec
    if req.plating_zone is not None:
        updates["plating_zone"] = req.plating_zone
    if req.surface_treatment is not None:
        updates["surface_treatment"] = req.surface_treatment
    if req.manufacturer is not None:
        updates["manufacturer"] = req.manufacturer
    if req.batch_no is not None:
        updates["batch_no"] = req.batch_no
    if req.production_date is not None:
        updates["production_date"] = req.production_date
    if req.expiry_date is not None:
        updates["expiry_date"] = req.expiry_date

    if updates:
        # 计算变更 diff
        changes = {}
        for k, new_val in updates.items():
            old_val = item.get(k)
            if str(old_val) != str(new_val):
                changes[k] = {"old": old_val, "new": new_val}

        with db.get_db() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [item_id]
            try:
                conn.execute(
                    f"UPDATE inventory SET {set_clause}, updated_at = datetime('now','localtime') WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError:
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
