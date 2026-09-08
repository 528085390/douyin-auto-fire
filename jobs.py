"""定时任务条目存取（SCH-001 spec 4.2；userdata/scheduler_jobs.json，原子写）。

写方唯一 = 面板 CRUD 与一键迁移；守护进程只读本文件（运行结果在 scheduler_state.json，
展示时面板合并）。条目 = {id, account, time, targets, texts, enabled, created_at}，
目标/文案为任务创建时的独立副本，与账号手动数据（user_data.yaml targets/message）解耦。

文件形态：{"version": 1, "migrated_from_legacy": true|false, "jobs": [...]}
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from main import USERDATA_DIR, ensure_userdata, list_accounts, load_config

ensure_userdata()

JOBS_PATH = USERDATA_DIR / "scheduler_jobs.json"
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_doc() -> dict:
    return {"version": 1, "migrated_from_legacy": False, "jobs": []}


def _read_doc() -> dict:
    """读整份文档；缺失/损坏（解析失败）→ 默认文档（BAT 读侧兜底纪律，不抛不自杀）。"""
    try:
        raw = JOBS_PATH.read_text(encoding="utf-8")
        doc = json.loads(raw)
        if not isinstance(doc, dict) or not isinstance(doc.get("jobs"), list):
            return _default_doc()
        return doc
    except Exception:  # noqa: BLE001  (FileNotFoundError / JSONDecodeError / 半写文件)
        return _default_doc()


def _atomic_write_doc(doc: dict) -> None:
    """唯一 tmp（带 pid 后缀）+ os.replace 原子替换；Errno 13 共享冲突小重试。"""
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_PATH.with_name(f"scheduler_jobs.json.{os.getpid()}.tmp")
    for attempt in range(3):  # noqa: B007
        try:
            tmp.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, JOBS_PATH)
            return
        except PermissionError:
            if attempt >= 2:
                raise
            time.sleep(0.05)


def load_jobs() -> list[dict]:
    """全部任务条目（含 enabled=false；守护自行过滤）。"""
    return _read_doc().get("jobs", [])


def save_jobs(jobs: list[dict]) -> None:
    """公开原子写入口（面板 CRUD 与迁移统一经它落盘；内部走 _atomic_write_doc）。"""
    doc = _read_doc()
    doc["jobs"] = jobs
    _atomic_write_doc(doc)


def _validate_job(account: str, time_str: str, targets: list, texts: list) -> str | None:
    """校验失败返回中文提示，合法返回 None。"""
    if account not in list_accounts():
        return "账号不存在，请先在账号栏添加该账号。"
    if not isinstance(time_str, str) or not _TIME_RE.match(time_str):
        return "时间格式应为 HH:MM（24 小时制），例如 21:30。"
    hh, mm = time_str.split(":")
    if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        return "时间超出合法范围，应为 00:00–23:59。"
    if not isinstance(targets, list) or not targets:
        return "至少选择一个发送目标。"
    for t in targets:
        if not isinstance(t, dict) or not (t.get("name") or "").strip():
            return "目标格式不正确：每项目标需含非空 name。"
    if not isinstance(texts, list) or not texts:
        return "至少填写一条发送内容。"
    if not any(str(t).strip() for t in texts):
        return "发送内容不能为空。"
    return None


def create_job(account: str, time_str: str, targets: list, texts: list,
               enabled: bool = True) -> dict:
    """新增任务条目（同号同时刻不拦截，由守护错峰顺延——拍板②）。"""
    err = _validate_job(account, time_str, targets, texts)
    if err:
        raise ValueError(err)
    job = {
        "id": uuid4().hex,
        "account": account,
        "time": time_str,
        "targets": [dict(t) for t in targets],
        "texts": [str(t) for t in texts],
        "enabled": bool(enabled),
        "created_at": _now_iso(),
    }
    jobs = load_jobs()
    jobs.append(job)
    save_jobs(jobs)
    return job


def _find(job_id: str) -> tuple[list[dict], dict | None]:
    jobs = load_jobs()
    for job in jobs:
        if job.get("id") == job_id:
            return jobs, job
    return jobs, None


def update_job(job_id: str, *, time: str | None = None, targets: list | None = None,
               texts: list | None = None, enabled: bool | None = None) -> dict | None:
    """全字段可改；不存在返回 None；改完原子落盘（守护每轮重读，改完即生效）。"""
    jobs, job = _find(job_id)
    if job is None:
        return None
    if time is not None:
        err = _validate_job(job["account"], time, targets or job["targets"],
                            texts or job["texts"])
        if err:
            raise ValueError(err)
        job["time"] = time
    if targets is not None:
        err = _validate_job(job["account"], job.get("time"), targets, texts or job["texts"])
        if err:
            raise ValueError(err)
        job["targets"] = [dict(t) for t in targets]
    if texts is not None:
        err = _validate_job(job["account"], job.get("time"), targets or job["targets"], texts)
        if err:
            raise ValueError(err)
        job["texts"] = [str(t) for t in texts]
    if enabled is not None:
        job["enabled"] = bool(enabled)
    save_jobs(jobs)
    return job


def toggle_job(job_id: str, enabled: bool) -> dict | None:
    jobs, job = _find(job_id)
    if job is None:
        return None
    job["enabled"] = bool(enabled)
    save_jobs(jobs)
    return job


def delete_job(job_id: str) -> bool:
    jobs, job = _find(job_id)
    if job is None:
        return False
    jobs = [x for x in jobs if x.get("id") != job_id]
    save_jobs(jobs)
    return True


def has_legacy_schedule() -> bool:
    """任一账号 user_data.yaml 含非空 schedule.time（迁移引导条件）。"""
    for alias in list_accounts():
        try:
            cfg = load_config(alias)
            if (cfg.get("schedule") or {}).get("time"):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def migrate_from_legacy() -> list[dict]:
    """一键迁移（幂等，plan F5）：仅当未迁移且任务库为空时生成任务条目。

    逐号生成 {account, time=历史 schedule.time, targets=该号 targets 副本,
    texts=该号 message.texts 副本, enabled=true}；完成后置 migrated_from_legacy。
    已迁移/已有任务 → 只确保标志存在并返回现状（横幅据此熄灭）。
    """
    doc = _read_doc()
    doc.setdefault("migrated_from_legacy", False)
    if doc["migrated_from_legacy"] or doc.get("jobs"):
        if not doc["migrated_from_legacy"]:
            doc["migrated_from_legacy"] = True
            _atomic_write_doc(doc)
        return doc.get("jobs", [])
    created: list[dict] = []
    for alias in list_accounts():
        try:
            cfg = load_config(alias)
        except Exception:  # noqa: BLE001
            continue
        legacy_time = (cfg.get("schedule") or {}).get("time")
        if not legacy_time:
            continue
        job = {
            "id": uuid4().hex,
            "account": alias,
            "time": str(legacy_time),
            "targets": [dict(t) for t in (cfg.get("targets") or [])],
            "texts": [str(t) for t in (cfg.get("message") or {}).get("texts", [])],
            "enabled": True,
            "created_at": _now_iso(),
        }
        created.append(job)
    doc["jobs"] = created
    doc["migrated_from_legacy"] = True
    _atomic_write_doc(doc)
    return created
