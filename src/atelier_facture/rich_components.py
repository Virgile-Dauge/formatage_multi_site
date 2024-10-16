from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree
from rich.table import Table
from rich.progress import (
    Progress, 
    TextColumn, 
    BarColumn, 
    TaskProgressColumn, 
    TimeRemainingColumn,
    SpinnerColumn
)
from typing import Any
from pathlib import Path
from extraction import process_zipped_pdfs

def rich_status_table(batch_status: dict[dict[str, Any]])-> Table:
    table = Table(title="Batch Processing Status")
    table.add_column("Batch", style="cyan", no_wrap=True)
    table.add_column("Fusion", style="magenta")
    table.add_column("Facturx", style="magenta")
    
    for batch, status in batch_status.items():
        fusion_status = "✅" if status.get('fusion') else "❌"
        facturx_status = "✅" if isinstance(status.get('facturx'), bool) else status.get('facturx')
        table.add_row(str(batch), fusion_status, facturx_status)

    return table

def process_with_rich_progress(zip_path: Path, indiv_dir: Path, batch_dir: Path, regex_dict, console: Console):

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        tasks = {}

        def update_progress(task: str, current: int, total: int, details: str):
            if task not in tasks:
                if total == 1:
                    # Create a spinner task
                    tasks[task] = progress.add_task(f"[cyan]{task}", total=1)
                else:
                    # Create a progress bar task
                    tasks[task] = progress.add_task(f"[cyan]{task}", total=total)
            
            task_id = tasks[task]
            
            if total == 1:
                if current == 0:
                    # Task started
                    progress.update(task_id, completed=0, description=f"[cyan]{task}: {details}")
                elif current == 1:
                    # Task completed
                    progress.update(task_id, completed=1, description=f"[bold green]{task}: {details} (Done)")
            else:
                if current < total:
                    progress.update(task_id, completed=current, description=f"[cyan]{task}: {details}")
                else :
                    progress.update(task_id, completed=current, description=f"[bold green]{task}: (Done)")

            # Force a refresh of the display
            progress.refresh()

        group_pdfs, individual_pdfs, errors = process_zipped_pdfs(
            zip_path, indiv_dir, batch_dir, regex_dict, progress_callback=update_progress
        )
    
    return group_pdfs, individual_pdfs, errors

def rich_directory_tree(directory: Path, max_items:int=5) -> Tree:
        console = Console(width=100, color_system="auto")
        tree = Tree(
            f"[bold magenta]:file_folder: {directory.name}",
            guide_style="bold bright_blue",
        )

        def add_directory(tree, directory):
            paths = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for path in paths[:max_items]:
                if path.is_dir():
                    branch = tree.add(f"[bold yellow]:file_folder: {path.name}")
                    add_directory(branch, path)
                else:
                    tree.add(f"[bold green]:page_facing_up: {path.name}")
            
            if len(paths) > max_items:
                tree.add(f"[bold red]... and {len(paths) - max_items} more items")

        add_directory(tree, directory)
        return tree
