"""推出开车业务规则：一次签名确认、状态单向流转与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "pushback"
REQUIRED_FIELDS = ["推出编号", "对应航班", "推出方向"]
STATUS_ORDER = ["待推出", "已推出", "已取消"]
PENDING_STATUS, CONFIRMED_STATUS, CANCELLED_STATUS = STATUS_ORDER
# 确认时一并写入的字段；缺失时保留原值并在确认备注里写明原因
CONFIRM_WRITE_FIELDS = ["推出方向", "牵引车编号"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PushbackService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("推出编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def status_counts(self) -> dict[str, int]:
        """按明细重算各状态条数，总览卡片与列表页统计都以此为准。"""
        counts = {status: 0 for status in STATUS_ORDER}
        for row in store.rows(MODULE):
            status = str(row.get("status", ""))
            if status in counts:
                counts[status] += 1
        counts["total"] = sum(counts[status] for status in STATUS_ORDER)
        return counts

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: str(values.get(field)).strip() for field in REQUIRED_FIELDS})
        for field in ("牵引车编号", "牵引车司机", "通信频道", "推出时段"):
            entry[field] = str(values.get(field) or "").strip()
        entry["实际推出时段"] = ""
        entry["确认人"] = ""
        entry["确认时间"] = ""
        entry["确认备注"] = ""
        entry["status"] = PENDING_STATUS
        self._sync_flags(entry)
        rows.append(entry)
        return entry, []

    def confirm_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """一次签名确认：方向、车号、实际时段与签名同时落库，状态只进不退。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"推出任务 {entry_id} 不存在或已归档"
        status = str(entry.get("status", ""))
        if status == CANCELLED_STATUS:
            return None, f"推出任务 {entry_id} 已取消，不再接受确认"
        if status == CONFIRMED_STATUS:
            return None, f"推出任务 {entry_id} 已确认，不接受第二次确认"
        if status != PENDING_STATUS:
            return None, f"推出任务 {entry_id} 当前状态「{status}」不允许确认，仅待推出可确认"

        signer = str(values.get("确认人") or "").strip()
        if not signer:
            return None, "签名确认必须填写确认人"

        notes: list[str] = []
        for field in CONFIRM_WRITE_FIELDS:
            incoming = str(values.get(field) or "").strip()
            if incoming:
                entry[field] = incoming
            else:
                notes.append(f"确认时未提供{field}，保留原值")

        actual = str(values.get("实际推出时段") or "").strip()
        entry["实际推出时段"] = actual or _now()
        entry["确认人"] = signer
        entry["确认时间"] = _now()
        entry["status"] = CONFIRMED_STATUS
        self._sync_flags(entry)

        superseded = self._supersede_same_flight(entry)
        if superseded:
            notes.append(f"同一航班此前的确认（{'、'.join(superseded)}）已被本次确认取代")
        entry["确认备注"] = "；".join(notes) if notes else "签名确认完成"
        return entry, f"推出任务 {entry_id} 已签名确认（确认人：{signer}）"

    def _supersede_same_flight(self, entry: dict[str, Any]) -> list[str]:
        """同一架航班只留最新一版确认：此前已确认的记录作废为已取消。"""
        flight = str(entry.get("对应航班", "")).strip()
        superseded: list[str] = []
        if not flight:
            return superseded
        for row in store.rows(MODULE):
            if row is entry or int(row.get("id", 0)) == int(entry.get("id", 0)):
                continue
            if str(row.get("对应航班", "")).strip() != flight:
                continue
            if row.get("status") != CONFIRMED_STATUS:
                continue
            row["status"] = CANCELLED_STATUS
            row["确认备注"] = f"被同一航班最新确认（{entry.get('推出编号', '')}）取代"
            self._sync_flags(row)
            superseded.append(str(row.get("推出编号", row.get("id"))))
        return superseded

    @staticmethod
    def _sync_flags(entry: dict[str, Any]) -> None:
        """pending 跟着明细状态走，总览页待推出条数按明细重算才对得上。"""
        entry["pending"] = entry.get("status") == PENDING_STATUS
        entry["abnormal"] = False
