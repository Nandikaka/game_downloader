"""Sequential batch runner: overall + per-file progress, delay, retry-at-end."""
import time
from dataclasses import dataclass

from rich.console import Console, Group
from rich.live import Live
from rich.markup import escape
from rich.progress import (BarColumn, DownloadColumn, MofNCompleteColumn, Progress,
                           TextColumn, TimeElapsedColumn, TimeRemainingColumn,
                           TransferSpeedColumn)
from rich.table import Column

from downloader import DownloadResult, ProgressSink, ResolvedLink, download_file


@dataclass
class BatchItem:
    name: str            # name shown / fallback filename (the page's part name)
    link: ResolvedLink


@dataclass
class BatchSummary:
    ok: int = 0
    skipped: int = 0
    failed: int = 0
    interrupted: bool = False


class _RichSink(ProgressSink):
    def __init__(self, progress: Progress):
        self.progress = progress
        self.task = None

    def begin(self, name: str) -> None:
        self.task = self.progress.add_task(escape(name), total=None)

    def end(self) -> None:
        if self.task is not None:
            self.progress.remove_task(self.task)
            self.task = None

    def file_start(self, name, total, offset):
        self.progress.update(self.task, description=escape(name), total=total, completed=offset)

    def advance(self, n):
        self.progress.advance(self.task, n)

    def status(self, msg):
        self.progress.update(self.task, description=f"[yellow]{escape(msg)}")


def _default_confirm(n: int) -> bool:
    import questionary
    return bool(questionary.confirm(f"Retry {n} failed part(s)?", default=True).ask())


def _run_round(indexed, dest_dir, retries, delay, backoff, console):
    overall = Progress(
        TextColumn("[bold]Overall", table_column=Column(width=8)),
        BarColumn(bar_width=None), MofNCompleteColumn(), TimeElapsedColumn(), expand=True)
    files = Progress(
        TextColumn("{task.description}",
                   table_column=Column(width=42, no_wrap=True, overflow="ellipsis")),
        BarColumn(bar_width=None), DownloadColumn(), TransferSpeedColumn(),
        TimeRemainingColumn(), expand=True)
    sink = _RichSink(files)
    results: dict[int, DownloadResult] = {}
    task = overall.add_task("overall", total=len(indexed))

    with Live(Group(overall, files), console=console, refresh_per_second=10) as live:
        for pos, (idx, item) in enumerate(indexed):
            sink.begin(item.name)
            try:
                res = download_file(item.link, dest_dir, item.name, retries, sink, backoff)
            finally:
                sink.end()
            results[idx] = res
            overall.advance(task)
            if res.status == "failed":
                live.console.print(f"[red]FAILED[/] {escape(res.name)}: {escape(res.error)}")
            if res.status == "ok" and delay > 0 and pos < len(indexed) - 1:
                time.sleep(delay)
    return results


def run_batch(items, dest_dir, retries=3, delay=1.0, backoff=2.0,
              confirm_retry=_default_confirm, console=None) -> BatchSummary:
    console = console or Console()
    final: dict[int, DownloadResult] = {}
    pending = list(enumerate(items))
    summary = BatchSummary()

    try:
        while pending:
            final.update(_run_round(pending, dest_dir, retries, delay, backoff, console))
            failed = [(i, it) for i, it in pending if final[i].status == "failed"]
            if not failed or not confirm_retry(len(failed)):
                break
            pending = failed
    except KeyboardInterrupt:
        summary.interrupted = True
        console.print("\n[yellow]Interrupted.[/] Partial files (*.part) are kept and will resume next run.")

    summary.ok = sum(r.status == "ok" for r in final.values())
    summary.skipped = sum(r.status == "skipped" for r in final.values())
    summary.failed = sum(r.status == "failed" for r in final.values())
    console.print(f"\n[bold]Done:[/] {summary.ok} downloaded, {summary.skipped} already complete, "
                  f"{summary.failed} failed")
    for r in final.values():
        if r.status == "failed":
            console.print(f"  [red]FAILED[/] {escape(r.name)}: {escape(r.error)}")
    return summary