from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.observability.latency import measure_latency, measure_latency_sync


class TimedCheckpointer(BaseCheckpointSaver):
    """Delegate to a LangGraph saver while measuring checkpoint I/O."""

    def __init__(self, delegate: Any) -> None:
        super().__init__(serde=delegate.serde)
        self._delegate = delegate

    @property
    def config_specs(self) -> list[Any]:
        return self._delegate.config_specs

    def get_next_version(self, current: Any, channel: Any) -> Any:
        return self._delegate.get_next_version(current, channel)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def get_tuple(self, config: Any) -> Any:
        with measure_latency_sync("checkpoint_load"):
            return self._delegate.get_tuple(config)

    def list(self, config: Any, **kwargs: Any) -> Iterator[Any]:
        with measure_latency_sync("checkpoint_load"):
            rows = list(self._delegate.list(config, **kwargs))
        return iter(rows)

    def put(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        with measure_latency_sync("checkpoint_persist"):
            return self._delegate.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with measure_latency_sync("checkpoint_persist"):
            self._delegate.put_writes(config, writes, task_id, task_path)

    def delete_thread(self, thread_id: str) -> None:
        self._delegate.delete_thread(thread_id)

    async def aget_tuple(self, config: Any) -> Any:
        async with measure_latency("checkpoint_load"):
            return await self._delegate.aget_tuple(config)

    async def alist(self, config: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async with measure_latency("checkpoint_load"):
            rows = [row async for row in self._delegate.alist(config, **kwargs)]
        for row in rows:
            yield row

    async def aput(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        async with measure_latency("checkpoint_persist"):
            return await self._delegate.aput(
                config, checkpoint, metadata, new_versions
            )

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        async with measure_latency("checkpoint_persist"):
            await self._delegate.aput_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await self._delegate.adelete_thread(thread_id)
