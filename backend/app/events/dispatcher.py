from collections import defaultdict
from typing import Callable

_handlers: dict[type, list[Callable]] = defaultdict(list)


def on(event_type):
    def register(fn):
        _handlers[event_type].append(fn)
        return fn
    return register


def publish(event) -> None:
    for handler in _handlers[type(event)]:
        handler(event)