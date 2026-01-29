"""Download orchestration and file management."""

import asyncio
import zipfile
from pathlib import Path
from typing import Tuple, Optional

from playwright.async_api import Page, BrowserContext, Download

from config import (
    DOWNLOAD_DIR,
    DOWNLOAD_TIMEOUT_MS,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
)
from utils.sanitizer import sanitize_folder_name, sanitize_filename, make_unique_path


class DownloadManager:
    """Manages file downloads with retries and organization."""

    def __init__(self, download_dir: str = DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    async def download_file(
        self,
        page: Page,
        file_id: str,
        author: str,
        name: str,
        description: Optional[str] = None,
    ) -> Tuple[bool, int, str]:
        """
        Download a single ensemble file, save description, and compress if .ens.

        Args:
            page: Playwright page
            file_id: File ID from data-id attribute
            author: Author name for folder organization
            name: Ensemble name for filename
            description: Optional description text to save alongside the file

        Returns:
            Tuple of (success, file_size_bytes, error_message)
        """
        for attempt in range(MAX_RETRIES):
            try:
                success, size, dest_path, error = await self._attempt_download(
                    page, file_id, author, name
                )
                if success:
                    # Save description as text file if provided
                    if description and dest_path:
                        self._save_description(dest_path, description, name)

                    # Compress .ens files to save disk space
                    if dest_path and dest_path.suffix.lower() == '.ens':
                        compressed_size = self._compress_ens_file(dest_path)
                        if compressed_size:
                            size = compressed_size

                    return True, size, ""

                # If it's an auth error, don't retry
                if "auth" in error.lower() or "login" in error.lower():
                    return False, 0, error

            except Exception as e:
                error = str(e)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        return False, 0, f"Failed after {MAX_RETRIES} attempts: {error}"

    async def _attempt_download(
        self,
        page: Page,
        file_id: str,
        author: str,
        name: str,
    ) -> Tuple[bool, int, Optional[Path], str]:
        """
        Single download attempt using direct download URL.

        Returns:
            Tuple of (success, file_size, dest_path, error_message)
        """
        from config import BASE_URL
        from playwright.async_api import Error as PlaywrightError

        # Construct direct download URL
        download_url = (
            f"{BASE_URL}/de/reaktor-community/reaktor-user-library/entry/download/"
            f"?tx_niuserlib_niuserlib[file]={file_id}"
        )

        # Create a new page for the download to avoid losing the listing page
        context = page.context
        download_page = await context.new_page()

        try:
            download: Optional[Download] = None

            # Set up download event handler
            async def handle_download(d: Download):
                nonlocal download
                download = d

            download_page.on('download', handle_download)

            # Navigate to download URL - this may throw if download starts
            try:
                await download_page.goto(download_url, wait_until='commit', timeout=DOWNLOAD_TIMEOUT_MS)
            except PlaywrightError as e:
                # Ignore navigation errors when download starts
                if "download" not in str(e).lower():
                    raise

            # Wait a bit for download to be captured
            for _ in range(30):  # Wait up to 3 seconds
                if download is not None:
                    break
                await asyncio.sleep(0.1)

            if download is None:
                return False, 0, None, "No download started"

            # Prepare destination
            sanitized_author = sanitize_folder_name(author)
            author_dir = self.download_dir / sanitized_author
            author_dir.mkdir(parents=True, exist_ok=True)

            # Get filename from download or construct one
            suggested = download.suggested_filename
            if suggested:
                filename = sanitize_filename(suggested)
            else:
                filename = sanitize_filename(f"{name}.ens")

            # Ensure unique path
            name_part, ext = self._split_filename(filename)
            dest_path = Path(make_unique_path(str(author_dir), name_part, ext))

            # Save the file
            await download.save_as(str(dest_path))

            # Get file size
            file_size = dest_path.stat().st_size

            return True, file_size, dest_path, ""

        except Exception as e:
            error_msg = str(e)

            # Check for timeout (download didn't start)
            if "timeout" in error_msg.lower():
                return False, 0, None, "Download timeout - file may require authentication"

            return False, 0, None, error_msg

        finally:
            await download_page.close()

    def _split_filename(self, filename: str) -> Tuple[str, str]:
        """Split filename into name and extension."""
        path = Path(filename)
        return path.stem, path.suffix

    def _save_description(self, file_path: Path, description: str, name: str) -> None:
        """
        Save ensemble description as a text file alongside the download.

        Args:
            file_path: Path to the downloaded file
            description: Description text to save
            name: Ensemble name for the text file
        """
        try:
            # Create description file with same base name
            desc_filename = file_path.stem + "_description.txt"
            desc_path = file_path.parent / desc_filename

            # Write description with metadata header
            content = f"Ensemble: {name}\n"
            content += f"File: {file_path.name}\n"
            content += "-" * 40 + "\n\n"
            content += description

            desc_path.write_text(content, encoding='utf-8')

        except Exception as e:
            # Don't fail the download if description save fails
            print(f"    Warning: Could not save description: {e}")

    def _compress_ens_file(self, file_path: Path) -> Optional[int]:
        """
        Compress an .ens file to .zip to save disk space.

        Args:
            file_path: Path to the .ens file

        Returns:
            Size of the compressed file in bytes, or None if compression failed
        """
        if not file_path.exists() or file_path.suffix.lower() != '.ens':
            return None

        zip_path = file_path.with_suffix('.zip')

        try:
            # Create zip file with the .ens file inside
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
                # Add .ens file to zip with just the filename (not full path)
                zf.write(file_path, file_path.name)

            # Get compressed size
            compressed_size = zip_path.stat().st_size
            original_size = file_path.stat().st_size

            # Only keep zip if it's actually smaller (some files may already be compressed)
            if compressed_size < original_size:
                # Remove original .ens file
                file_path.unlink()
                return compressed_size
            else:
                # Compression didn't help, keep original
                zip_path.unlink()
                return original_size

        except Exception as e:
            # If compression fails, keep the original file
            print(f"    Warning: Could not compress file: {e}")
            if zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception:
                    pass
            return None


async def prompt_continue(
    session_downloaded: int,
    total_downloaded: int,
    total_files: int,
) -> bool:
    """
    Prompt user to continue downloading.

    Args:
        session_downloaded: Bytes downloaded this session
        total_downloaded: Total bytes downloaded overall
        total_files: Total files downloaded

    Returns:
        True to continue, False to stop
    """
    from utils.state import SizeTracker

    print("\n" + "=" * 60)
    print(f"  Downloaded this session: {SizeTracker.format_size(session_downloaded)}")
    print(f"  Total downloaded: {SizeTracker.format_size(total_downloaded)}")
    print(f"  Total files: {total_files}")
    print("=" * 60)

    # Use asyncio to handle input in async context
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: input("Continue downloading? (y/n): ").strip().lower()
    )

    return response in ('y', 'yes', '')
