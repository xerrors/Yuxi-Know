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
) -> bool:
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
                f"[bold cyan]Ingestion queued for {server_file_path}{extra}. Track progress in the task center.[/bold cyan]"
            )
            return True

        # Check if the overall request was successful for synchronous responses
        if overall_status != "success":
            console.print(
                f"[bold yellow]Processing warning for {server_file_path}: {result.get('message')}[/bold yellow]"
            )
            return False

        # Check the specific file's processing status in the items array
        items = result.get("items", [])
        if not items:
            console.print(f"[bold red]No processing result for {server_file_path}[/bold red]")
            return False

        # Since we only sent one file, check the first item
        item = items[0]
        # Check for both 'success' and 'done' status (different APIs might use different status values)
        if item.get("status") in ["success", "done"]:
            return True
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
            return False

    except httpx.HTTPStatusError as e:
        console.print(
            f"[bold red]Failed to process {server_file_path}: {e.response.status_code} - {e.response.text}[/bold red]"
        )
        return False
    except httpx.RequestError as e:
        console.print(f"[bold red]Failed to process {server_file_path}: {e}[/bold red]")
        return False


async def worker(
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    file_path: pathlib.Path,
    file_hash: str,
    progress: Progress,
    upload_task_id: int,
    process_task_id: int,
    enable_ocr: str = "paddlex_ocr",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    use_qa_split: bool = False,
    qa_separator: str = "\n\n\n",
):
    """A worker task that uploads and then processes a single file."""
    async with semaphore:
        # 1. Upload file
        server_file_path = await upload_file(client, base_url, db_id, file_path)
        progress.update(upload_task_id, advance=1, postfix=f"Uploaded {file_path.name}")

        if not server_file_path:
            progress.update(process_task_id, advance=1)  # Mark as processed to not hang the progress bar
            return file_path, file_hash, "upload_failed"

        # 2. Process file
        success = await process_document(
            client,
            base_url,
            db_id,
            server_file_path,
            enable_ocr=enable_ocr,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            use_qa_split=use_qa_split,
            qa_separator=qa_separator,
        )
        progress.update(process_task_id, advance=1, postfix=f"Processed {file_path.name}")

        return file_path, file_hash, "success" if success else "processing_failed"


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


async def convert_to_markdown(
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    server_file_path: str,
) -> str | None:
    """Calls the file-to-markdown conversion endpoint."""
    try:
        response = await client.post(
            f"{base_url}/knowledge/files/markdown",
            json={"db_id": db_id, "file_path": server_file_path},
            timeout=600,  # 10 minutes timeout for conversion
        )
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "success":
            return result.get("markdown_content")
        else:
            console.print(f"[bold red]Failed to convert {server_file_path}: {result.get('message')}[/bold red]")
            return None
    except httpx.HTTPStatusError as e:
        console.print(
            f"[bold red]Failed to convert {server_file_path}: {e.response.status_code} - {e.response.text}[/bold red]"
        )
        return None
    except httpx.RequestError as e:
        console.print(f"[bold red]Request failed for {server_file_path}: {e}[/bold red]")
        return None


async def trans_worker(
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    base_url: str,
    db_id: str,
    file_path: pathlib.Path,
    output_dir: pathlib.Path,
    progress: Progress,
    task_id: int,
):
    """A worker task that uploads a file and converts it to markdown."""
    async with semaphore:
        # 1. Upload file
        server_file_path = await upload_file(client, base_url, db_id, file_path)
        if not server_file_path:
            progress.update(task_id, advance=1, postfix=f"[red]Upload failed for {file_path.name}[/red]")
            return file_path, "upload_failed"

        # 2. Convert file to markdown
        markdown_content = await convert_to_markdown(client, base_url, db_id, server_file_path)
        if not markdown_content:
            progress.update(task_id, advance=1, postfix=f"[yellow]Conversion failed for {file_path.name}[/yellow]")
            return file_path, "conversion_failed"

        # 3. Save markdown content to output directory
        try:
            output_path = output_dir / file_path.with_suffix(".md").name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            progress.update(task_id, advance=1, postfix=f"[green]Converted {file_path.name}[/green]")
            return file_path, "success"
        except OSError as e:
            console.print(f"[bold red]Error saving markdown for {file_path.name}: {e}[/bold red]")
            progress.update(task_id, advance=1, postfix=f"[red]Save failed for {file_path.name}[/red]")
            return file_path, "save_failed"


@app.command()
def upload(
    db_id: str = typer.Option(..., help="The ID of the knowledge base."),
    directory: pathlib.Path = typer.Option(
        ..., help="The directory containing files to upload.", exists=True, file_okay=False
    ),
    pattern: str = typer.Option("*.md", help="The glob pattern for files to upload (e.g., '*.pdf', '**/*.txt')."),
    base_url: str = typer.Option("http://127.0.0.1:5050/api", help="The base URL of the API server."),
    username: str = typer.Option(..., help="Admin username for login."),
    password: str = typer.Option(..., help="Admin password for login."),
    concurrency: int = typer.Option(1, help="The number of concurrent upload/process tasks."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search for files recursively in subdirectories."),
    record_file: pathlib.Path = typer.Option(
        "scripts/tmp/batch_processed_files.txt", help="File to store processed files record."
    ),
    chunk_size: int = typer.Option(1000, help="Chunk size for document processing."),
    chunk_overlap: int = typer.Option(200, help="Chunk overlap for document processing."),
    enable_ocr: str = typer.Option("paddlex_ocr", help="OCR engine to use (paddlex_ocr, mineru_ocr, disable)."),
    use_qa_split: bool = typer.Option(False, help="Whether to use QA splitting."),
    qa_separator: str = typer.Option("\n\n\n", help="Separator for QA splitting."),
):
    """
    Batch upload and process files into a Yuxi-Know knowledge base.
    """
    console.print(f"[bold green]Starting batch upload for knowledge base: {db_id}[/bold green]")

    # Load previously processed files
    processed_files = load_processed_files(record_file)
    console.print(f"Loaded {len(processed_files)} previously processed files from record.")

    # Discover files
    glob_method = directory.rglob if recursive else directory.glob
    all_files = list(glob_method(pattern))
    if not all_files:
        console.print(f"[bold yellow]No files found in '{directory}' matching '{pattern}'. Aborting.[/bold yellow]")
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

            # Setup concurrency and tasks
            semaphore = asyncio.Semaphore(concurrency)
            tasks = []

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
                upload_task_id = progress.add_task("[bold blue]Uploading...", total=len(files_to_upload), postfix="")
                process_task_id = progress.add_task("[bold cyan]Processing...", total=len(files_to_upload), postfix="")

                for file_path, file_hash in files_to_upload:
                    task = asyncio.create_task(
                        worker(
                            semaphore,
                            client,
                            base_url,
                            db_id,
                            file_path,
                            file_hash,
                            progress,
                            upload_task_id,
                            process_task_id,
                            enable_ocr=enable_ocr,
                            chunk_size=chunk_size,
                            chunk_overlap=chunk_overlap,
                            use_qa_split=use_qa_split,
                            qa_separator=qa_separator,
                        )
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks)

            # Summarize results and update processed files record
            successful_files = []
            upload_failures = []
            processing_failures = []
            newly_processed_hashes = set()

            for file_path, file_hash, status in results:
                if status == "success":
                    successful_files.append(file_path)
                    newly_processed_hashes.add(file_hash)
                elif status == "upload_failed":
                    upload_failures.append(file_path)
                elif status == "processing_failed":
                    processing_failures.append(file_path)
                    # Don't add to processed files if processing failed

            # Save newly processed files to record
            if newly_processed_hashes:
                all_processed_files = processed_files | newly_processed_hashes
                save_processed_files(record_file, all_processed_files)
                console.print(
                    f"[bold green]Updated processed files record with "
                    f"{len(newly_processed_hashes)} new entries.[/bold green]"
                )

            console.print("[bold green]Batch operation complete.[/bold green]")
            console.print(f"  - [green]Successful:[/green] {len(successful_files)}")
            console.print(f"  - [red]Upload Failed:[/red] {len(upload_failures)}")
            if upload_failures:
                for f in upload_failures:
                    console.print(f"    - {f}")
            console.print(f"  - [yellow]Processing Failed:[/yellow] {len(processing_failures)}")
            if processing_failures:
                for f in processing_failures:
                    console.print(f"    - {f}")

    asyncio.run(run())


@app.command()
def trans(
    db_id: str = typer.Option(..., help="The ID of the knowledge base (for temporary file upload)."),
    directory: pathlib.Path = typer.Option(
        ..., help="The directory containing files to convert.", exists=True, file_okay=False
    ),
    output_dir: pathlib.Path = typer.Option("output_markdown", help="The directory to save converted markdown files."),
    pattern: str = typer.Option("*.docx", help="The glob pattern for files to convert (e.g., '*.pdf', '*.docx')."),
    base_url: str = typer.Option("http://127.0.0.1:5050/api", help="The base URL of the API server."),
    username: str = typer.Option(..., help="Admin username for login."),
    password: str = typer.Option(..., help="Admin password for login."),
    concurrency: int = typer.Option(4, help="The number of concurrent conversion tasks."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search for files recursively in subdirectories."),
):
    """
    Batch convert files to Markdown format.
    """
    console.print(f"[bold green]Starting batch conversion for files in: {directory}[/bold green]")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Discover files
    glob_method = directory.rglob if recursive else directory.glob
    files_to_convert = list(glob_method(pattern))
    if not files_to_convert:
        console.print(f"[bold yellow]No files found in '{directory}' matching '{pattern}'. Aborting.[/bold yellow]")
        raise typer.Exit()

    # 过滤掉macos的隐藏文件
    files_to_convert = [f for f in files_to_convert if not f.name.startswith("._")]

    console.print(f"Found {len(files_to_convert)} files to convert.")

    async def run():
        async with httpx.AsyncClient() as client:
            # Login
            token = await login(client, base_url, username, password)
            if not token:
                raise typer.Exit(code=1)

            client.headers = {"Authorization": f"Bearer {token}"}

            # Setup concurrency and tasks
            semaphore = asyncio.Semaphore(concurrency)
            tasks = []

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
                task_id = progress.add_task("[bold blue]Converting...", total=len(files_to_convert), postfix="")

                for file_path in files_to_convert:
                    task = asyncio.create_task(
                        trans_worker(semaphore, client, base_url, db_id, file_path, output_dir, progress, task_id)
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks)

            # Summarize results
            successful_files = []
            failed_files = []

            for file_path, status in results:
                if status == "success":
                    successful_files.append(file_path)
                else:
                    failed_files.append((file_path, status))

            console.print("[bold green]Batch conversion complete.[/bold green]")
            console.print(f"  - [green]Successful:[/green] {len(successful_files)}")
            console.print(f"  - [red]Failed:[/red] {len(failed_files)}")
            if failed_files:
                for f, status in failed_files:
                    console.print(f"    - {f} (Reason: {status})")

    asyncio.run(run())


"""
# Example for upload
uv run scripts/batch_upload.py upload \
    --db-id your_kb_id \
    --directory path/to/your/data \
    --pattern "*.docx" \
    --base-url http://127.0.0.1:5050/api \
    --username your_username \
    --password your_password \
    --concurrency 4 \
    --recursive \
    --record-file scripts/tmp/batch_processed_files.txt

# Example for trans
uv run scripts/batch_upload.py trans \
    --db-id your_kb_id \
    --directory path/to/your/data \
    --output-dir path/to/output_markdown \
    --pattern "*.docx" \
    --base-url http://127.0.0.1:5050/api \
    --username your_username \
    --password your_password \
    --concurrency 4 \
    --recursive
"""
if __name__ == "__main__":
    app()
