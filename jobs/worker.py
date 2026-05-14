"""RQ worker entry point for offline web correction jobs."""

from __future__ import annotations

import os
from importlib import import_module, util


def main() -> int:
    """Start an RQ worker bound to the xiuyin queue."""

    if util.find_spec("redis") is None or util.find_spec("rq") is None:
        print("ERROR: 服务器未安装 Redis/RQ 依赖，请先执行 pip install -r requirements.txt")
        return 1
    redis_mod = import_module("redis")
    rq_mod = import_module("rq")
    redis_url = os.getenv("XIUYIN_REDIS_URL", "redis://localhost:6379/0")
    connection = redis_mod.Redis.from_url(redis_url)
    try:
        connection.ping()
    except Exception as exc:
        print(f"ERROR: Redis 不可用，无法启动 worker：{exc}")
        return 1
    worker = rq_mod.Worker(["xiuyin"], connection=connection)
    worker.work()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
