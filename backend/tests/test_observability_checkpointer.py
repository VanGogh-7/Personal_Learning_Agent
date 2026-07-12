from __future__ import annotations

import asyncio
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.observability.checkpointer import TimedCheckpointer


class SyncOnlySaver(BaseCheckpointSaver):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, Any]] = []

    def get_tuple(self, config: Any) -> str:
        self.calls.append(("get_tuple", config))
        return "checkpoint"

    def list(self, config: Any, **kwargs: Any):
        self.calls.append(("list", (config, kwargs)))
        return iter(["first", "second"])

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any):
        self.calls.append(("put", config))
        return {"configurable": {"checkpoint_id": "saved"}}

    def put_writes(
        self,
        config: Any,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.calls.append(("put_writes", task_id))

    def delete_thread(self, thread_id: str) -> None:
        self.calls.append(("delete_thread", thread_id))


def test_async_methods_bridge_sync_only_checkpoint_saver() -> None:
    async def exercise() -> None:
        delegate = SyncOnlySaver()
        saver = TimedCheckpointer(delegate)
        config = {"configurable": {"thread_id": "thread-1"}}

        assert await saver.aget_tuple(config) == "checkpoint"
        assert [row async for row in saver.alist(config, limit=2)] == [
            "first",
            "second",
        ]
        assert await saver.aput(config, {}, {}, {}) == {
            "configurable": {"checkpoint_id": "saved"}
        }
        await saver.aput_writes(config, [("channel", "value")], "task-1")
        await saver.adelete_thread("thread-1")

        assert [name for name, _ in delegate.calls] == [
            "get_tuple",
            "list",
            "put",
            "put_writes",
            "delete_thread",
        ]

    asyncio.run(exercise())
