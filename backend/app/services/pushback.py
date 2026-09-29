"""推出开车业务规则：状态流转、字段校验、签名确认与筛选口径都收在这里。

推出记录采用一次签名确认：确认推出时把推出方向、牵引车编号与实际推出时段一并
写入同一条记录，签名后列表、详情与刷新读到的都是同一份内容；已确认、已取消的
记录不再接受第二次确认。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "pushback"
# 登记时需要带上的字段：所有展示字段一并落库，避免列表与明细各读各的。
REQUIRED_FIELDS = [
    "推出编号",
    "对应航班",
    "推出方向",
    "牵引车编号",
    "牵引车司机",
    "通信频道",
    "推出时段",
]
# 签名确认时必须齐备的关键字段，缺一不写入并保留原有内容。
CONFIRM_FIELDS = ["推出方向", "牵引车编号"]
STATUS_ORDER = ["待推出", "推出中", "已推出", "已取消"]
STATUS_PENDING = "待推出"
STATUS_PUSHING = "推出中"
STATUS_DONE = "已推出"
STATUS_CANCELLED = "已取消"
ACTION_RULES = {"安排推出": "推出中", "开始推出": "推出中", "确认推出": "已推出"}
NEGATIVE_ACTIONS = []


def _text(value: Any) -> str:
    """把提交值收敛成去空白的字符串，None 与空白输入统一按空值处理。"""
    return str(value or "").strip()


def _now_slot() -> str:
    """实际推出时段：签名确认发生的时刻。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


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

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记一条推出任务。

        必填字段缺失时不写入；同一架航班已有未取消的推出记录时去重拦下，只认
        第一次登记（已取消的历史记录不占名额）。
        """
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        rows = store.rows(MODULE)
        flight = _text(values.get("对应航班"))
        existed = next(
            (
                row
                for row in rows
                if _text(row.get("对应航班")) == flight and row.get("status") != STATUS_CANCELLED
            ),
            None,
        )
        if existed is not None:
            return None, (
                f"航班 {flight} 已存在推出记录（推出编号 {existed.get('推出编号', '—')}），"
                "重复登记已去重，只认第一次"
            )
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in REQUIRED_FIELDS:
            entry[field] = _text(values.get(field))
        entry["status"] = STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        entry["signed"] = False
        # 中文状态展示列与内部状态始终同源，列表与详情不会再显示成两套。
        entry["推出状态"] = STATUS_PENDING
        rows.append(entry)
        return entry, ""

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"推出任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于推出开车可执行范围"
        if action == "确认推出":
            return self.confirm_entry(entry, values or {})

        target = ACTION_RULES[action]
        current = entry.get("status")
        if current == STATUS_CANCELLED:
            return None, "推出已取消，不再接受任何确认动作"
        # 只允许顺着 待推出 -> 推出中 推进，终态与同级重复操作都拦下。
        if current == target:
            return None, f"推出任务当前已是「{current}」，无需重复{action}"
        if current == STATUS_DONE:
            return None, "推出已签名确认，状态不可再变更"
        if STATUS_ORDER.index(current) > STATUS_ORDER.index(target):
            return None, f"当前状态「{current}」不能执行{action}"
        entry["status"] = target
        entry["pending"] = target == STATUS_PENDING
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry["推出状态"] = target
        return entry, f"推出任务已{action}"

    def confirm_entry(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """签名确认推出：一次写入方向、牵引车编号与实际推出时段。

        校验全部通过后才落库，任一条件不满足都保留原有内容并写明原因：
        - 已确认的记录不再接受第二次确认（签名幂等）；
        - 已取消的推出不再接受确认；
        - 推出方向或牵引车编号缺失则不写入；
        - 同一架航班只认第一次确认（并发/重复提交去重）。
        """
        status = entry.get("status")
        if entry.get("signed") or status == STATUS_DONE:
            return None, "推出记录已签名确认，不再接受第二次确认"
        if status == STATUS_CANCELLED:
            return None, "推出已取消，不再接受确认"

        flight = _text(entry.get("对应航班"))
        first = next(
            (
                row
                for row in store.rows(MODULE)
                if _text(row.get("对应航班")) == flight
                and row.get("id") != entry.get("id")
                and (row.get("signed") or row.get("status") == STATUS_DONE)
            ),
            None,
        )
        if first is not None:
            return None, (
                f"航班 {flight} 的推出已由 {first.get('推出编号', '—')} 首次确认，"
                "只认第一次确认"
            )

        # 提交值优先，缺省时沿用原有内容；两者都为空才算缺失，此时原样保留。
        resolved: dict[str, str] = {}
        missing: list[str] = []
        for field in CONFIRM_FIELDS:
            text = _text(values.get(field)) or _text(entry.get(field))
            if not text:
                missing.append(field)
            resolved[field] = text
        if missing:
            return None, f"签名确认缺少：{'、'.join(missing)}；原有内容已保留，请补全后再确认"

        slot = _text(values.get("推出时段")) or _now_slot()
        channel = _text(values.get("通信频道")) or _text(entry.get("通信频道"))

        # 校验全部通过后一次性落库，列表、详情与刷新读到的是同一份内容。
        entry["推出方向"] = resolved["推出方向"]
        entry["牵引车编号"] = resolved["牵引车编号"]
        entry["推出时段"] = slot
        entry["通信频道"] = channel
        entry["status"] = STATUS_DONE
        entry["推出状态"] = STATUS_DONE
        entry["pending"] = False
        entry["signed"] = True
        entry["signed_at"] = slot

        # 通信频道改动同时落到该航班的相关（未取消）推出记录上。
        for row in store.rows(MODULE):
            if row.get("id") == entry.get("id"):
                continue
            if _text(row.get("对应航班")) == flight and row.get("status") != STATUS_CANCELLED:
                row["通信频道"] = channel

        return entry, "推出记录已签名确认"
