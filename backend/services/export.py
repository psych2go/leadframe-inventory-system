"""库存 Excel 导出。

把"查询结果 → openpyxl 工作簿"的构建逻辑从 routers/inventory.py 抽出，
使路由只负责查询与响应封装，工作簿构建可独立测试与复用。
"""
import io

import openpyxl

import database as db


def _autosize_columns(ws):
    """根据列内容最大宽度自适应列宽（上限 30）"""
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 30)


def build_inventory_excel(rows) -> io.BytesIO:
    """根据库存记录行（sqlite3.Row 或 dict）构建 Excel，返回可流的 BytesIO。

    Sheet 1「库存汇总」：按复合分组键聚合（总数量 K + 批次数）。
    Sheet 2「库存明细」：完整字段，逐条记录。
    """
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
        groups[key]["qty"] += db.qty_to_num(row["quantity"])
        groups[key]["count"] += 1
    for (pt, sp, pz, st, mf), g in groups.items():
        ws1.append([pt, sp, pz, st, mf, db.num_to_qty(g["qty"]), g["count"]])
    _autosize_columns(ws1)

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
            db.num_to_qty(db.qty_to_num(row["quantity"])),
            row["note"] or "",
        ])
    _autosize_columns(ws2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
