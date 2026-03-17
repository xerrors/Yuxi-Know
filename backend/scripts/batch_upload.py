import asyncio
import hashlib
import json
import pathlib

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

app = typer.Typer()
console = Console()


async def login(client: httpx.AsyncClient, base_url: str, username: str, password: str) -> str | None:
    """Logs in to the API and returns the access token."""
    try:
        response = await client.post(
            f"{base_url}/auth/token",
            data={"username": username, "password": password},
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except httpx.HTTPStatusError as e:
        console.print(f"[bold red]Login failed: {e.response.status_code} - {e.response.text}[/bold red]")
        return None
    except httpx.RequestError as e:
        console.print(f"[bold red]Login request failed: {e}[/bold red]")
        return None


async def check_task_status(client: httpx.AsyncClient, base_url: str, task_id: str) -> str | None:
    """Check the status of a task. Returns status string or None if failed."""
    try:
        response = await client.get(f"{base_url}/tasks/{task_id}")
        response.raise_for_status()
        task_data = response.json().get("task", {})
        return task_data.get("status")
    except httpx.HTTPStatusError as e:
        console.print(f"[bold yellow]Warning: Failed to check task {task_id}: {e.response.status_code}[/bold yellow]")
        return None
    except httpx.RequestError as e:
        console.print(f"[bold yellow]Warning: Failed to check task {task_id}: {e}[/bold yellow]")
        return None


async def upload_file(
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    file_path: pathlib.Path,
) -> str | None:
    """Uploads a single file and returns its server-side path."""
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            response = await client.post(
                f"{base_url}/knowledge/files/upload",
                params={"db_id": db_id},
                files=files,
                timeout=300,  # 5 minutes timeout for large files
            )
        response.raise_for_status()
        return response.json().get("file_path")
    except httpx.HTTPStatusError as e:
        console.print(
            f"[bold red]Failed to upload {file_path.name}: {e.response.status_code} - {e.response.text}[/bold red]"
        )
        return None
    except httpx.RequestError as e:
        console.print(f"[bold red]Failed to upload {file_path.name}: {e}[/bold red]")
        return None


async def process_document(
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    server_file_path: str,
    enable_ocr: str = "paddlex_ocr",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    use_qa_split: bool = False,
    qa_separator: str = "\n\n\n",
) -> tuple[bool, str | None]:
    """Triggers the processing of an uploaded file in the knowledge base."""
    # Prepare processing parameters
    params = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "enable_ocr": enable_ocr,
        "use_qa_split": use_qa_split,
        "qa_separator": qa_separator,
        "content_type": "file",
    }

    try:
        response = await client.post(
            f"{base_url}/knowledge/databases/{db_id}/documents",
            json={"items": [server_file_path], "params": params},
            timeout=600,  # 10 minutes timeout for processing
        )
        response.raise_for_status()
        result = response.json()

        # Handle asynchronous ingest response
        overall_status = result.get("status")
        if overall_status == "queued":
            task_id = result.get("task_id")
            extra = f" (task id: {task_id})" if task_id else ""
            console.print(
                f"[bold cyan]Ingestion queued for {server_file_path}{extra}. "
                "Track progress in the task center.[/bold cyan]"
            )
            return True, task_id

        # Check if the overall request was successful for synchronous responses
        if overall_status != "success":
            console.print(
                f"[bold yellow]Processing warning for {server_file_path}: {result.get('message')}[/bold yellow]"
            )
            return False, None

        # Check the specific file's processing status in the items array
        items = result.get("items", [])
        if not items:
            console.print(f"[bold red]No processing result for {server_file_path}[/bold red]")
            return False, None

        # Since we only sent one file, check the first item
        item = items[0]
        # Check for both 'success' and 'done' status (different APIs might use different status values)
        if item.get("status") in ["success", "done"]:
            return True, None
        else:
            # Get more detailed error information
            error_msg = item.get("message", "")
            error_detail = item.get("detail", "")
            error_reason = item.get("reason", "")

            # Combine all available error information
            error_info = []
            if error_msg:
                error_info.append(error_msg)
            if error_detail:
                error_info.append(error_detail)
            if error_reason:
                error_info.append(error_reason)

            if not error_info:
                error_info = ["Unknown error"]

            full_error = " | ".join(error_info)
            console.print(f"[bold red]Failed to process {server_file_path}: {full_error}[/bold red]")

            # Also log the full item for debugging
            console.print(f"[dim]Debug - Full item response: {item}[/dim]")
            return False, None

    except httpx.HTTPStatusError as e:
        console.print(
            f"[bold red]Failed to process {server_file_path}: {e.response.status_code} - {e.response.text}[/bold red]"
        )
        return False, None
    except httpx.RequestError as e:
        console.print(f"[bold red]Failed to process {server_file_path}: {e}[/bold red]")
        return False, None


async def upload_single_file(
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    file_path: pathlib.Path,
    progress: Progress,
    task_id: int,
) -> str | None:
    """Upload a single file and return server file path."""
    server_file_path = await upload_file(client, base_url, db_id, file_path)
    if server_file_path:
        progress.update(task_id, advance=1, postfix=f"Uploaded {file_path.name}")
    else:
        progress.update(task_id, advance=1, postfix=f"Failed: {file_path.name}")
    return server_file_path


async def add_batch_to_knowledge_base(
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    server_file_paths: list[str],
    enable_ocr: str = "paddlex_ocr",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    use_qa_split: bool = False,
    qa_separator: str = "\n\n\n",
) -> tuple[bool, str | None]:
    """Add a batch of files to knowledge base and return task_id."""
    if not server_file_paths:
        return True, None

    # Prepare processing parameters
    params = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "enable_ocr": enable_ocr,
        "use_qa_split": use_qa_split,
        "qa_separator": qa_separator,
        "content_type": "file",
    }

    try:
        response = await client.post(
            f"{base_url}/knowledge/databases/{db_id}/documents",
            json={"items": server_file_paths, "params": params},
            timeout=600,  # 10 minutes timeout for processing
        )
        response.raise_for_status()
        result = response.json()

        overall_status = result.get("status")
        if overall_status == "queued":
            task_id = result.get("task_id")
            extra = f" (task id: {task_id})" if task_id else ""
            console.print(
                f"[bold cyan]Batch of {len(server_file_paths)} files queued for processing{extra}. "
                "Track progress in the task center.[/bold cyan]"
            )
            return True, task_id
        elif overall_status == "success":
            console.print(f"[bold green]Batch of {len(server_file_paths)} files processed successfully[/bold green]")
            return True, None
        else:
            console.print(f"[bold yellow]Batch processing warning: {result.get('message')}[/bold yellow]")
            return False, None

    except httpx.HTTPStatusError as e:
        console.print(f"[bold red]Failed to process batch: {e.response.status_code} - {e.response.text}[/bold red]")
        return False, None
    except httpx.RequestError as e:
        console.print(f"[bold red]Failed to process batch: {e}[/bold red]")
        return False, None


async def wait_for_tasks_completion(
    client: httpx.AsyncClient,
    base_url: str,
    task_ids: list[str],
    poll_interval: int = 5,
) -> dict[str, str]:
    """Wait for all tasks to complete and return their final statuses."""
    if not task_ids:
        return {}

    console.print(f"[bold cyan]Waiting for {len(task_ids)} tasks to complete...[/bold cyan]")

    pending_tasks = task_ids.copy()
    completed_tasks = {}

    while pending_tasks:
        for task_id in pending_tasks.copy():
            status = await check_task_status(client, base_url, task_id)
            if status:
                if status in ["success", "failed", "cancelled"]:
                    completed_tasks[task_id] = status
                    pending_tasks.remove(task_id)
                    console.print(f"[dim]Task {task_id} completed with status: {status}[/dim]")

        if pending_tasks:
            await asyncio.sleep(poll_interval)

    console.print(f"[bold green]All {len(task_ids)} tasks completed[/bold green]")
    return completed_tasks


def get_file_hash(file_path: pathlib.Path) -> str:
    """Calculate SHA256 hash of a file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def load_processed_files(record_file: pathlib.Path) -> set[str]:
    """Load the set of processed file hashes from the record file."""
    if not record_file.exists():
        return set()

    try:
        with open(record_file) as f:
            data = json.load(f)
            return set(data.get("processed_files", []))
    except (OSError, json.JSONDecodeError) as e:
        console.print(f"[bold yellow]Warning: Could not load processed files record: {e}[/bold yellow]")
        return set()


def save_processed_files(record_file: pathlib.Path, processed_files: set[str]):
    """Save the set of processed file hashes to the record file."""
    # Ensure the directory exists
    record_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(record_file, "w") as f:
            json.dump({"processed_files": list(processed_files)}, f, indent=2)
    except OSError as e:
        console.print(f"[bold red]Error: Could not save processed files record: {e}[/bold red]")


@app.command()
def upload(
    db_id: str = typer.Option(..., help="The ID of the knowledge base."),
    directory: pathlib.Path = typer.Option(
        ..., help="The directory containing files to upload.", exists=True, file_okay=False
    ),
    pattern: list[str] = typer.Option(
        ["*.md"],
        help="The glob patterns for files to upload (e.g., '*.pdf', '**/*.txt'). Can be specified multiple times.",
    ),
    base_url: str = typer.Option("http://127.0.0.1:5050/api", help="The base URL of the API server."),
    username: str = typer.Option(..., help="Admin username for login."),
    password: str = typer.Option(..., help="Admin password for login."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search for files recursively in subdirectories."),
    record_file: pathlib.Path = typer.Option(
        "scripts/tmp/batch_processed_files.txt", help="File to store processed files record."
    ),
    chunk_size: int = typer.Option(1000, help="Chunk size for document processing."),
    chunk_overlap: int = typer.Option(200, help="Chunk overlap for document processing."),
    enable_ocr: str = typer.Option(
        "paddlex_ocr", help="OCR engine to use (onnx_rapid_ocr, mineru_ocr, mineru_official, paddlex_ocr, disable)."
    ),
    use_qa_split: bool = typer.Option(False, help="Whether to use QA splitting."),
    qa_separator: str = typer.Option("\n\n\n", help="Separator for QA splitting."),
    batch_size: int = typer.Option(20, help="Number of files to process in each batch."),
    wait_for_completion: bool = typer.Option(True, help="Whether to wait for tasks to complete before next batch."),
    poll_interval: int = typer.Option(5, help="Polling interval in seconds for checking task status."),
):
    """
    Batch upload and process files into a Yuxi-Know knowledge base.
    """
    console.print(f"[bold green]Starting batch upload for knowledge base: {db_id}[/bold green]")

    # Load previously processed files
    processed_files = load_processed_files(record_file)
    console.print(f"Loaded {len(processed_files)} previously processed files from record.")

    # Discover files from multiple patterns
    glob_method = directory.rglob if recursive else directory.glob
    all_files = []
    for pat in pattern:
        files_for_pat = list(glob_method(pat))
        all_files.extend(files_for_pat)

    # Remove duplicates
    all_files = list(set(all_files))

    if not all_files:
        patterns_str = "', '".join(pattern)
        console.print(
            f"[bold yellow]No files found in '{directory}' matching patterns: '{patterns_str}'. Aborting.[/bold yellow]"
        )
        raise typer.Exit()

    # 过滤掉macos的隐藏文件
    all_files = [f for f in all_files if not f.name.startswith("._")]

    # Filter out already processed files
    files_to_upload = []
    skipped_files = []

    for file_path in all_files:
        file_hash = get_file_hash(file_path)
        if file_hash in processed_files:
            skipped_files.append(file_path)
        else:
            files_to_upload.append((file_path, file_hash))

    if not files_to_upload:
        console.print(
            f"[bold green]All {len(all_files)} files have already been processed. Nothing to do.[/bold green]"
        )
        raise typer.Exit()

    console.print(f"Found {len(all_files)} total files:")
    console.print(f"  - [green]New files to process:[/green] {len(files_to_upload)}")
    console.print(f"  - [blue]Already processed (skipped):[/blue] {len(skipped_files)}")

    async def run():
        async with httpx.AsyncClient() as client:
            # Login
            token = await login(client, base_url, username, password)
            if not token:
                raise typer.Exit(code=1)

            client.headers = {"Authorization": f"Bearer {token}"}

            # Process files in batches: upload 20 -> process 20 -> wait -> repeat
            total_processed_files = []
            total_upload_failures = []
            total_processing_failures = []
            all_successful_hashes = set()

            # Split all files into batches
            for batch_num in range(0, len(files_to_upload), batch_size):
                batch_files = files_to_upload[batch_num : batch_num + batch_size]
                batch_start = batch_num + 1
                batch_end = min(batch_num + batch_size, len(files_to_upload))

                console.print(
                    f"\n[bold yellow]=== Batch {batch_start}-{batch_end} of {len(files_to_upload)} ===[/bold yellow]"
                )

                # Step 1: Upload this batch of files sequentially
                console.print(f"[blue]Step 1: Uploading {len(batch_files)} files...[/blue]")

                successful_uploads = []
                batch_upload_failures = []

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeElapsedColumn(),
                    TextColumn("{task.fields[postfix]}"),
                    console=console,
                    transient=True,
                ) as progress:
                    upload_task_id = progress.add_task(
                        f"Uploading batch {batch_start}-{batch_end}...", total=len(batch_files), postfix=""
                    )

                    for file_path, file_hash in batch_files:
                        server_file_path = await upload_single_file(
                            client, base_url, db_id, file_path, progress, upload_task_id
                        )

                        if server_file_path:
                            successful_uploads.append((file_path, file_hash, server_file_path))
                            all_successful_hashes.add(file_hash)
                        else:
                            batch_upload_failures.append(file_path)

                # Step 2: Process this batch if uploads succeeded
                if successful_uploads:
                    console.print(f"[green]Step 2: Processing {len(successful_uploads)} uploaded files...[/green]")

                    # Extract server file paths
                    server_file_paths = [item[2] for item in successful_uploads]

                    # Submit batch to knowledge base
                    success, task_id = await add_batch_to_knowledge_base(
                        client,
                        base_url,
                        db_id,
                        server_file_paths,
                        enable_ocr=enable_ocr,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        use_qa_split=use_qa_split,
                        qa_separator=qa_separator,
                    )

                    if success:
                        total_processed_files.extend([item[0] for item in successful_uploads])

                        # Step 3: Wait for this batch to complete
                        if wait_for_completion and task_id:
                            console.print(
                                f"[cyan]Step 3: Waiting for batch {batch_start}-{batch_end} to complete...[/cyan]"
                            )
                            await wait_for_tasks_completion(client, base_url, [task_id], poll_interval)
                            console.print(f"[green]Batch {batch_start}-{batch_end} completed![/green]")
                        else:
                            console.print(f"[green]Batch {batch_start}-{batch_end} submitted successfully![/green]")
                    else:
                        total_processing_failures.extend([item[0] for item in successful_uploads])
                        console.print(f"[red]Batch {batch_start}-{batch_end} processing failed[/red]")

                # Record batch failures
                total_upload_failures.extend(batch_upload_failures)

                # Update processed files record after each batch
                if all_successful_hashes:
                    all_processed_files = processed_files | all_successful_hashes
                    save_processed_files(record_file, all_processed_files)

                # Small delay between batches
                if batch_end < len(files_to_upload):
                    console.print("[dim]Waiting 2 seconds before next batch...[/dim]")
                    await asyncio.sleep(2)

            # Final summary
            console.print("\n[bold green]=== All Batches Complete ===[/bold green]")
            console.print(f"  - [green]Files successfully processed:[/green] {len(total_processed_files)}")
            console.print(f"  - [red]Upload failures:[/red] {len(total_upload_failures)}")
            if total_upload_failures:
                for f in total_upload_failures:
                    console.print(f"    - {f}")
            console.print(f"  - [yellow]Processing failures:[/yellow] {len(total_processing_failures)}")
            if total_processing_failures:
                for f in total_processing_failures:
                    console.print(f"    - {f}")

    asyncio.run(run())


"""
# Example for upload
uv run scripts/batch_upload.py upload \
    --db-id your_kb_id \
    --directory path/to/your/data \
    --pattern "*.docx" --pattern "*.pdf" --pattern "*.html" \
    --base-url http://127.0.0.1:5050/api \
    --username your_username \
    --password your_password \
    --batch-size 20 \
    --wait-for-completion \
    --poll-interval 5 \
    --recursive \
    --record-file scripts/tmp/batch_processed_files.txt
"""
if __name__ == "__main__":
    app()
