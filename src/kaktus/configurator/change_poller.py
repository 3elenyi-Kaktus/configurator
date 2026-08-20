from collections.abc import Callable
import logging
from pathlib import Path
from threading import Thread

from typing_extensions import override
from watchdog.events import (
    DirCreatedEvent,
    DirModifiedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver


log: logging.Logger = logging.getLogger(__name__)


class EventsHandler(FileSystemEventHandler):
    def __init__(self, filepath: Path, callback: Callable[[], None]) -> None:
        self.filepath: Path = filepath
        self.callback: Callable[[], None] = callback
        FileSystemEventHandler.__init__(self)

    @override
    def dispatch(self, event: FileSystemEvent) -> None:
        self.on_any_event(event)
        if event.is_directory:
            return
        # Reject any events not related to target file
        if (
            event.event_type == "created"
            and Path(str(event.src_path)) == self.filepath
            or event.event_type == "modified"
            and Path(str(event.src_path)) == self.filepath
            or event.event_type == "moved"
            and Path(str(event.dest_path)) == self.filepath
        ):
            getattr(self, f"on_{event.event_type}")(event)

    @override
    def on_any_event(self, event: FileSystemEvent) -> None:
        log.info(f"EventsHandler: Event occurred: {event}")

    @override
    def on_created(self, event: DirCreatedEvent | FileCreatedEvent) -> None:
        # DirCreatedEvent should be rejected in dispatch & event_filter
        log.info("EventsHandler: Triggered on file creation at targeted filepath")
        self._trigger()

    @override
    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        # DirModifiedEvent should be rejected in dispatch & event_filter
        log.info("EventsHandler: Triggered on file modification at targeted filepath")
        self._trigger()

    @override
    def on_moved(self, event: DirMovedEvent | FileMovedEvent) -> None:
        # DirMovedEvent should be rejected in dispatch & event_filter
        log.info("EventsHandler: Triggered on moving file to targeted filepath")
        self._trigger()

    def _trigger(self) -> None:
        callback_thread: Thread = Thread(target=self.callback)
        callback_thread.start()


class ChangePoller:
    def __init__(self, filepath: Path, callback: Callable[[], None]):
        self.filepath: Path = filepath
        self.callback: Callable[[], None] = callback

        self.stop_requested: bool = False
        self.poller: Thread = Thread(target=self._poll, daemon=True)

    def _poll(self) -> None:
        events_handler: EventsHandler = EventsHandler(self.filepath, self.callback)
        observer: BaseObserver = Observer()
        observer.schedule(
            events_handler,
            str(self.filepath.parent),
            recursive=False,
            event_filter=[FileCreatedEvent, FileModifiedEvent, FileMovedEvent],
        )
        log.info(
            f"ChangePoller: Starting polling for file: '{self.filepath.name}' changes at dir: '{self.filepath.parent}'"
        )
        observer.start()
        try:
            while observer.is_alive():
                if self.stop_requested:
                    log.info("ChangePoller: Stop request acknowledged")
                    break
                observer.join(1)
        except Exception as error:
            log.exception(error)
        observer.stop()
        observer.join()
        log.critical("ChangePoller: Polling for file changes stopped")

    def startPolling(self) -> None:
        log.info("ChangePoller: Starting up")
        self.poller.start()

    def stopPolling(self) -> None:
        log.info("ChangePoller: Stop requested")
        self.stop_requested = True
        self.poller.join()
