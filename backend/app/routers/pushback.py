"""推出开车接口：维护推出任务，签名确认一次写入推出方向、牵引车编号与实际时段。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.pushback import STATUS_ORDER, PushbackService

router = APIRouter(prefix="/api/pushback", tags=["推出开车"])

service = PushbackService()

LIST_FIELDS = ["推出编号", "对应航班", "推出方向", "牵引车编号", "牵引车司机", "通信频道", "推出时段", "实际推出时段", "确认人"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按推出编号检索"),
    status: str | None = Query(default=None, description="待推出、已推出、已取消"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按推出编号与状态过滤推出开车列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def status_stats() -> dict[str, int]:
    """按明细重算各状态条数：待推出条数始终与明细一致。"""
    return service.status_counts()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出推出开车清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "pushback", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条推出任务明细；与列表同源，不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"推出任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条推出任务，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="推出任务已登记", entry=entry)


@router.post("/{entry_id}/confirm", response_model=ActionResult)
def confirm_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """签名确认：一次写入推出方向、牵引车编号与实际时段；已确认或已取消的会被拦下并说明原因。"""
    entry, message = service.confirm_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
