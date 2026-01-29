"""State management for download progress and resumability."""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class DownloadState:
    """Manages download state for resumability."""

    def __init__(self, state_file: str = "./state.json"):
        self.state_file = Path(state_file)
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Load existing state or create new."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                # Corrupted state file, start fresh
                pass

        return {
            'last_page': 0,
            'downloaded_ids': [],
            'failed_ids': [],
            'total_bytes': 0,
            'total_files': 0,
            'started_at': datetime.now().isoformat(),
            'last_updated': None
        }

    def save(self) -> None:
        """Persist state to disk."""
        self.state['last_updated'] = datetime.now().isoformat()
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def mark_downloaded(self, file_id: str, size_bytes: int) -> None:
        """Mark a file as successfully downloaded."""
        if file_id not in self.state['downloaded_ids']:
            self.state['downloaded_ids'].append(file_id)
            self.state['total_bytes'] += size_bytes
            self.state['total_files'] += 1

    def mark_failed(self, file_id: str, error: str) -> None:
        """Mark a file as failed."""
        # Remove from failed if retrying
        self.state['failed_ids'] = [
            f for f in self.state['failed_ids']
            if f.get('id') != file_id
        ]
        self.state['failed_ids'].append({
            'id': file_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })

    def is_downloaded(self, file_id: str) -> bool:
        """Check if a file was already downloaded."""
        return file_id in self.state['downloaded_ids']

    def set_last_page(self, page: int) -> None:
        """Update the last successfully processed page."""
        self.state['last_page'] = page

    def get_resume_page(self) -> int:
        """Get the page to resume from."""
        return self.state.get('last_page', 0)

    @property
    def total_bytes(self) -> int:
        """Get total bytes downloaded."""
        return self.state.get('total_bytes', 0)

    @property
    def total_files(self) -> int:
        """Get total files downloaded."""
        return self.state.get('total_files', 0)

    @property
    def failed_count(self) -> int:
        """Get count of failed downloads."""
        return len(self.state.get('failed_ids', []))


class SizeTracker:
    """Track cumulative download size and prompt at thresholds."""

    def __init__(self, threshold_bytes: int, initial_bytes: int = 0):
        self.threshold = threshold_bytes
        self.session_downloaded = 0
        self.total_downloaded = initial_bytes
        self.last_checkpoint = 0

    def add_download(self, size_bytes: int) -> None:
        """Add a download to the running total."""
        self.session_downloaded += size_bytes
        self.total_downloaded += size_bytes

    def needs_confirmation(self) -> bool:
        """Check if we've crossed a threshold boundary since last confirmation."""
        current_block = self.session_downloaded // self.threshold
        last_block = self.last_checkpoint // self.threshold
        return current_block > last_block

    def confirm(self) -> None:
        """Mark that user confirmed continuation."""
        self.last_checkpoint = self.session_downloaded

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"
