# Reaktor User Library Downloader

Downloads all ensembles from the [Native Instruments Reaktor User Library](https://www.native-instruments.com/de/reaktor-community/reaktor-user-library/), organized into folders by author name.

## Features

- **Batch download** all 6,500+ ensembles across 435 pages
- **Organized by author** - files saved to `downloads/{Author Name}/`
- **Automatic compression** - `.ens` files compressed to `.zip` (saves ~60% disk space)
- **Description saving** - save full descriptions or short captions alongside files
- **Resumable** - tracks progress in `state.json`, resume anytime with `--resume`
- **10 GB checkpoints** - prompts for confirmation every 10 GB downloaded
- **Graceful shutdown** - Ctrl+C saves state before exiting

## Requirements

- Python 3.9+
- Native Instruments account with access to the Reaktor User Library
- Fresh browser cookies exported after login

## Installation

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install playwright rich

# Install browser
python -m playwright install chromium
```

## Cookie Setup

The downloader requires authentication cookies from your browser. Export them after logging in to native-instruments.com.

### Option 1: Browser Console Export

1. Log in to [native-instruments.com](https://www.native-instruments.com)
2. Navigate to the [Reaktor User Library](https://www.native-instruments.com/de/reaktor-community/reaktor-user-library/)
3. Open browser DevTools (F12) → Console
4. Run this snippet and copy the output:
   ```javascript
   JSON.stringify({
     documentCookies: Object.fromEntries(document.cookie.split('; ').map(c => c.split('='))),
     domain: window.location.hostname,
     url: window.location.href,
     timestamp: new Date().toISOString()
   }, null, 2)
   ```
5. Save to `cookies.json` in the project directory

### Option 2: Browser Extension

Use a cookie export extension (e.g., "EditThisCookie" or "Cookie-Editor") to export cookies in JSON format.

**Important:** Cookies expire after ~24 hours. Re-export if you see authentication errors.

## Usage

```bash
# Activate virtual environment
source venv/bin/activate

# Basic usage (downloads all pages)
python main.py --cookies cookies.json --no-headless

# Download specific page range
python main.py --cookies cookies.json --no-headless --start-page 1 --end-page 10

# Resume interrupted download
python main.py --cookies cookies.json --no-headless --resume
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--cookies FILE` | Path to cookies JSON file (default: `cookies.json`) |
| `--start-page N` | Starting page number (default: 1) |
| `--end-page N` | Ending page number (default: 435) |
| `--resume` | Resume from last saved state |
| `--no-headless` | Show browser window (required for bot detection bypass) |
| `--headless` | Run browser headless (may trigger bot detection) |

### Description Options

| Option | Description |
|--------|-------------|
| `--descriptions` | Fetch full descriptions from detail pages (default, slower) |
| `--captions` | Use short captions from listing page (faster) |
| `--no-descriptions` | Skip saving descriptions entirely (fastest) |

**Example with captions only:**
```bash
python main.py --cookies cookies.json --no-headless --captions
```

## Output Structure

```
downloads/
├── Rick Scott/
│   ├── kreLL_beatBox_v2.zip
│   ├── kreLL_beatBox_v2_description.txt
│   ├── xEDy_v5.zip
│   └── xEDy_v5_description.txt
├── Colin Brown/
│   ├── velour_1_2.zip
│   └── velour_1_2_description.txt
└── ...
```

## State & Resume

Progress is saved to `state.json` after each page:

```json
{
  "last_page": 42,
  "downloaded_ids": ["29691", "29685", ...],
  "total_bytes": 1234567890,
  "total_files": 500,
  "failed_ids": []
}
```

Use `--resume` to continue from where you left off. Already-downloaded files are automatically skipped.

## Troubleshooting

### 403 Forbidden Error
- Use `--no-headless` flag (headless mode triggers bot detection)
- Re-export fresh cookies (they expire after ~24 hours)

### Downloads Not Starting
- Check that your NI account has access to the Reaktor User Library
- Verify cookies include the `access-token` cookie
- Try re-logging in and exporting cookies again

### Authentication Failed
- Cookies have expired - export fresh cookies from browser
- Make sure you're logged in when exporting cookies

## License

MIT

## Disclaimer

This tool is for personal use only. Respect Native Instruments' terms of service. The ensembles downloaded are created by community members and subject to their individual licenses.
