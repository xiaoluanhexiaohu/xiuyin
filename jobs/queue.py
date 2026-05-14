"""Redis/RQ queue integration for web upload jobs."""

from __future__ import annotations

import os
from importlib import import_module, util


def enqueue_web_job(user_hash: str, job_id: str) -> str:
    """Enqueue a web job. RQ is the default; inline mode is test-only."""

    mode = os.getenv("XIUYIN_QUEUE_MODE", "rq")
    if mode == "inline":
        from jobs.web_export import process_web_job

        process_web_job(user_hash, job_id)
        return "inline"
    if util.find_spec("redis") is None or util.find_spec("rq") is None:
        raise RuntimeError("服务器未安装 Redis/RQ 依赖，无法创建后台任务。")
    redis_mod = import_module("redis")
    rq_mod = import_module("rq")
    redis_url = os.getenv("XIUYIN_REDIS_URL", "redis://localhost:6379/0")
    connection = redis_mod.Redis.from_url(redis_url)
    try:
        connection.ping()
    except Exception as exc:
        raise RuntimeError("Redis 不可用，无法创建后台修音任务。") from exc
    queue = rq_mod.Queue("xiuyin", connection=connection)
    job = queue.enqueue("jobs.web_export.process_web_job", user_hash, job_id, job_timeout="30m")
    return str(job.id)
