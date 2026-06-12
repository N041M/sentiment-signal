"""Terminal progress helpers.

We use heartbeat logging rather than an animated spinner. A spinner
(rich.status.Status) runs in a background thread, so it keeps spinning even when
the main thread is blocked on a hung network call — a misleading "it's alive"
signal. A heartbeat only advances when an item is actually processed, so if the
count stops, the work is genuinely stuck. It also works identically in a terminal,
a pipe, a log file, and under the scheduler.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import TypeVar

from loguru import logger

T = TypeVar("T")


def progress(items: Iterable[T], label: str, every: int = 1) -> Iterator[T]:
    """Yield from `items`, logging an advancing `label: i/total` heartbeat.

    Args:
        items:  any iterable (materialised to a list if it has no length).
        label:  prefix for the heartbeat line, e.g. "fed_speeches 2024".
        every:  log every Nth item (use a larger value for very long loops to
                avoid log spam; the first and last item are always logged).
    """
    seq = items if hasattr(items, "__len__") else list(items)
    total = len(seq)  # type: ignore[arg-type]
    if total == 0:
        logger.info(f"{label}: nothing to do")
        return
    for i, item in enumerate(seq, 1):
        if i == 1 or i == total or i % every == 0:
            logger.info(f"{label}: {i}/{total}")
        yield item
