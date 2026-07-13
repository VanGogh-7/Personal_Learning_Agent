from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.observability.latency import measure_latency, measure_latency_sync

logger = logging.getLogger(__name__)


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
        try:
            with measure_latency_sync("checkpoint_load"):
                return self._delegate.get_tuple(config)
        except Exception:
            logger.exception("checkpoint_load_failed")
            raise

    def list(self, config: Any, **kwargs: Any) -> Iterator[Any]:
        try:
            with measure_latency_sync("checkpoint_load"):
                rows = list(self._delegate.list(config, **kwargs))
        except Exception:
            logger.exception("checkpoint_load_failed")
            raise
        return iter(rows)

    def put(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        try:
            with measure_latency_sync("checkpoint_persist"):
                return self._delegate.put(config, checkpoint, metadata, new_versions)
        except Exception:
            logger.exception("checkpoint_persist_failed")
            raise

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        try:
            with measure_latency_sync("checkpoint_persist"):
                self._delegate.put_writes(config, writes, task_id, task_path)
        except Exception:
            logger.exception("checkpoint_persist_failed")
            raise

    def delete_thread(self, thread_id: str) -> None:
        self._delegate.delete_thread(thread_id)

    async def aget_tuple(self, config: Any) -> Any:
        try:
            async with measure_latency("checkpoint_load"):
                try:
                    return await self._delegate.aget_tuple(config)
                except NotImplementedError:
                    return await asyncio.to_thread(self._delegate.get_tuple, config)
        except Exception:
            logger.exception("checkpoint_load_failed")
            raise

    async def alist(self, config: Any, **kwargs: Any) -> AsyncIterator[Any]:
        try:
            async with measure_latency("checkpoint_load"):
                try:
                    rows = [row async for row in self._delegate.alist(config, **kwargs)]
                except NotImplementedError:
                    rows = await asyncio.to_thread(
                        lambda: list(self._delegate.list(config, **kwargs))
                    )
        except Exception:
            logger.exception("checkpoint_load_failed")
            raise
        for row in rows:
            yield row

    async def aput(
        self,
        config: Any,
        checkpoint: Any,
        metadata: Any,
        new_versions: Any,
    ) -> Any:
        try:
            async with measure_latency("checkpoint_persist"):
                try:
                    return await self._delegate.aput(
                        config, checkpoint, metadata, new_versions
                    )
                except NotImplementedError:
                    return await asyncio.to_thread(
                        self._delegate.put,
                        config,
                        checkpoint,
                        metadata,
                        new_versions,
                    )
        except Exception:
            logger.exception("checkpoint_persist_failed")
            raise

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        try:
            async with measure_latency("checkpoint_persist"):
                try:
                    await self._delegate.aput_writes(config, writes, task_id, task_path)
                except NotImplementedError:
                    await asyncio.to_thread(
                        self._delegate.put_writes,
                        config,
                        writes,
                        task_id,
                        task_path,
                    )
        except Exception:
            logger.exception("checkpoint_persist_failed")
            raise

    async def adelete_thread(self, thread_id: str) -> None:
        try:
            await self._delegate.adelete_thread(thread_id)
        except NotImplementedError:
            await asyncio.to_thread(self._delegate.delete_thread, thread_id)
