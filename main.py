#!/usr/bin/env python3
"""
Reaktor User Library Downloader

Downloads all ensembles from the Native Instruments Reaktor User Library,
organizing them into folders by author name.
"""

import asyncio
import argparse
import signal
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from config import (
    BASE_URL,
    PAGINATION_PATTERN,
    TOTAL_PAGES,
    SIZE_CHECK_THRESHOLD,
    PAGE_DELAY_SECONDS,
    DOWNLOAD_DELAY_SECONDS,
    STATE_FILE,
    COOKIES_FILE,
)
from downloader.browser import setup_browser, close_browser, create_page, check_auth_status
from downloader.scraper import extract_entries_from_page, navigate_to_page, get_total_pages, debug_page_structure, fetch_full_description
from downloader.download_manager import DownloadManager, prompt_continue
from utils.state import DownloadState, SizeTracker

console = Console()

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(sig, frame):
    """Handle Ctrl+C for graceful shutdown."""
    global shutdown_requested
    if shutdown_requested:
        console.print("\n[red]Force quit. State may not be saved.[/red]")
        sys.exit(1)
    console.print("\n[yellow]Shutdown requested. Finishing current download...[/yellow]")
    shutdown_requested = True


async def main():
    """Main download orchestration."""
    global shutdown_requested

    parser = argparse.ArgumentParser(
        description='Download Reaktor User Library ensembles'
    )
    parser.add_argument(
        '--start-page', type=int, default=1,
        help='Starting page number (default: 1)'
    )
    parser.add_argument(
        '--end-page', type=int, default=TOTAL_PAGES,
        help=f'Ending page number (default: {TOTAL_PAGES})'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume from last saved state'
    )
    parser.add_argument(
        '--headless', action='store_true', default=True,
        help='Run browser in headless mode (default: True)'
    )
    parser.add_argument(
        '--no-headless', action='store_false', dest='headless',
        help='Show browser window for debugging'
    )
    parser.add_argument(
        '--cookies', type=str, default=COOKIES_FILE,
        help=f'Path to cookies file (default: {COOKIES_FILE})'
    )

    # Description options
    desc_group = parser.add_mutually_exclusive_group()
    desc_group.add_argument(
        '--descriptions', action='store_true', default=True,
        help='Fetch full descriptions from detail pages (default, slower)'
    )
    desc_group.add_argument(
        '--captions', action='store_true',
        help='Use short captions from listing page (faster, less detail)'
    )
    desc_group.add_argument(
        '--no-descriptions', action='store_true',
        help='Skip saving descriptions entirely'
    )

    args = parser.parse_args()

    # Determine description mode
    if args.no_descriptions:
        description_mode = 'none'
    elif args.captions:
        description_mode = 'caption'
    else:
        description_mode = 'full'  # Default: fetch from detail page

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Initialize state management
    state = DownloadState(STATE_FILE)
    size_tracker = SizeTracker(
        threshold_bytes=SIZE_CHECK_THRESHOLD,
        initial_bytes=state.total_bytes
    )
    download_manager = DownloadManager()

    # Determine starting page
    if args.resume and state.get_resume_page() > 0:
        start_page = state.get_resume_page()
        console.print(f"[cyan]Resuming from page {start_page}[/cyan]")
    else:
        start_page = args.start_page

    end_page = args.end_page

    console.print(f"\n[bold green]Reaktor User Library Downloader[/bold green]")
    console.print(f"Pages: {start_page} to {end_page}")
    console.print(f"Descriptions: {description_mode}")
    console.print(f"Previously downloaded: {state.total_files} files ({SizeTracker.format_size(state.total_bytes)})")
    console.print()

    # Verify cookies file exists
    if not Path(args.cookies).exists():
        console.print(f"[red]Error: Cookies file not found: {args.cookies}[/red]")
        console.print("Please export your browser cookies after logging in to native-instruments.com")
        return

    # Set up browser
    console.print("[cyan]Starting browser...[/cyan]")
    try:
        playwright, browser, context = await setup_browser(
            headless=args.headless,
            cookies_file=args.cookies
        )
    except Exception as e:
        console.print(f"[red]Failed to start browser: {e}[/red]")
        return

    page = await create_page(context)

    try:
        # Navigate to first page to verify auth
        console.print("[cyan]Verifying authentication...[/cyan]")
        if not await navigate_to_page(page, start_page):
            console.print("[red]Failed to load library page[/red]")
            return

        if not await check_auth_status(page):
            console.print("[red]Authentication failed. Please refresh your cookies.json[/red]")
            return

        # Get total pages if available
        detected_pages = await get_total_pages(page)
        if detected_pages:
            console.print(f"[dim]Detected {detected_pages} total pages[/dim]")

        console.print("[green]Authentication verified![/green]\n")

        # Main download loop
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:

            page_task = progress.add_task(
                f"[cyan]Pages",
                total=end_page - start_page + 1
            )

            for page_num in range(start_page, end_page + 1):
                if shutdown_requested:
                    break

                progress.update(page_task, description=f"[cyan]Page {page_num}/{end_page}")

                # Navigate to page (skip if we're already on start_page from auth check)
                if page_num > start_page:
                    if not await navigate_to_page(page, page_num):
                        console.print(f"[yellow]Skipping page {page_num} (navigation failed)[/yellow]")
                        continue

                # Extract entries
                entries = await extract_entries_from_page(page)
                if not entries:
                    console.print(f"[dim]No entries found on page {page_num}[/dim]")
                    progress.advance(page_task)
                    continue

                # Process each entry
                for entry in entries:
                    if shutdown_requested:
                        break

                    file_id = entry['file_id']

                    # Skip already downloaded
                    if state.is_downloaded(file_id):
                        continue

                    # Get description based on mode
                    description = None
                    if description_mode == 'full':
                        # Fetch full description from detail page (slower)
                        detail_url = entry.get('detail_url')
                        if detail_url:
                            description = await fetch_full_description(page, detail_url)
                        # Fall back to caption if detail fetch failed
                        if not description:
                            description = entry.get('caption')
                    elif description_mode == 'caption':
                        # Use short caption from listing page (faster)
                        description = entry.get('caption')
                    # else: description_mode == 'none', description stays None

                    # Attempt download (with description and compression)
                    success, file_size, error = await download_manager.download_file(
                        page,
                        file_id,
                        entry['author'],
                        entry['name'],
                        description=description,
                    )

                    if success:
                        state.mark_downloaded(file_id, file_size)
                        size_tracker.add_download(file_size)
                        console.print(
                            f"  [green]\u2713[/green] {entry['name'][:50]} "
                            f"[dim]({SizeTracker.format_size(file_size)})[/dim]"
                        )
                    else:
                        state.mark_failed(file_id, error)
                        console.print(
                            f"  [red]\u2717[/red] {entry['name'][:50]} [dim]{error[:50]}[/dim]"
                        )

                    # Check size threshold
                    if size_tracker.needs_confirmation():
                        should_continue = await prompt_continue(
                            size_tracker.session_downloaded,
                            size_tracker.total_downloaded,
                            state.total_files,
                        )
                        if not should_continue:
                            console.print("[yellow]User requested stop[/yellow]")
                            shutdown_requested = True
                            break
                        size_tracker.confirm()

                    # Rate limiting between downloads
                    await asyncio.sleep(DOWNLOAD_DELAY_SECONDS)

                # Update state after each page
                state.set_last_page(page_num)
                state.save()

                progress.advance(page_task)

                # Rate limiting between pages
                await asyncio.sleep(PAGE_DELAY_SECONDS)

    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()

    finally:
        # Clean up
        console.print("\n[cyan]Cleaning up...[/cyan]")
        await close_browser(playwright, browser)

        # Save final state
        state.save()

        # Print summary
        console.print("\n" + "=" * 60)
        console.print("[bold green]DOWNLOAD SUMMARY[/bold green]")
        console.print(f"  Total files: {state.total_files}")
        console.print(f"  Total size: {SizeTracker.format_size(state.total_bytes)}")
        console.print(f"  Failed: {state.failed_count}")
        console.print(f"  Last page: {state.get_resume_page()}")
        console.print("=" * 60)

        if state.failed_count > 0:
            console.print(f"\n[yellow]Run with --resume to retry failed downloads[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
