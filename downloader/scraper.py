"""Page scraping and entry extraction."""

import asyncio
from typing import List, Dict, Optional
from playwright.async_api import Page

from config import BASE_URL, PAGINATION_PATTERN


async def extract_entries_from_page(page: Page) -> List[Dict]:
    """
    Extract all ensemble entries from the current library page.

    Args:
        page: Playwright page positioned on a library listing page

    Returns:
        List of entry dictionaries with file_id, name, author, caption, and detail_url
    """
    entries = []

    # Wait for download buttons to be present
    try:
        await page.wait_for_selector('.btn-download', timeout=15000)
    except Exception:
        # Page might be empty or structure changed
        return entries

    # Get all download buttons
    download_buttons = await page.query_selector_all('.btn-download')

    for btn in download_buttons:
        try:
            # Get file ID and name from button attributes
            file_id = await btn.get_attribute('data-id')
            file_name = await btn.get_attribute('data-name')

            if not file_id:
                continue

            # Extract author, caption, and detail URL from the item container
            author, caption, detail_url = await extract_metadata_for_button(page, btn)

            entries.append({
                'file_id': file_id,
                'name': file_name or f"ensemble_{file_id}",
                'author': author,
                'caption': caption,  # Short description from listing page
                'detail_url': detail_url,  # URL for full description
            })

        except Exception as e:
            # Log but continue with other entries
            print(f"  Warning: Failed to extract entry: {e}")
            continue

    return entries


async def extract_metadata_for_button(page: Page, btn) -> tuple:
    """
    Extract the author name, caption, and detail URL for a given download button.

    The page structure is:
    <li class="item-box">
      <div class="item-content">
        <div class="description-title">
          <a href="/de/.../entry/show/ID/">Title</a>
        </div>
        <div class="meta">
          <div>by <a href="...">Author Name</a>, date</div>
        </div>
        <div class="cover">
          <a href="/de/.../entry/show/ID/">
            <div class="caption">Short description text here</div>
          </a>
        </div>
        ...
        <a class="btn-download">

    Args:
        page: Playwright page
        btn: Download button element handle

    Returns:
        Tuple of (author, caption, detail_url)
    """
    try:
        # Use JavaScript to navigate up and find author, caption, and detail URL
        result = await btn.evaluate('''(btn) => {
            let author = null;
            let caption = null;
            let detailUrl = null;

            // Find the item-box (li) container
            let itemBox = btn.closest('li.item-box, li[class*="item"], .item-box');

            // Fallback: go up several levels to find LI
            if (!itemBox) {
                let el = btn;
                for (let i = 0; i < 8; i++) {
                    el = el.parentElement;
                    if (!el) break;
                    if (el.tagName === 'LI') {
                        itemBox = el;
                        break;
                    }
                }
            }

            if (!itemBox) {
                return { author: null, caption: null, detailUrl: null };
            }

            // Extract detail URL from title or cover link
            const detailLink = itemBox.querySelector('.description-title a, .cover a, a[href*="/entry/show/"]');
            if (detailLink) {
                const href = detailLink.getAttribute('href');
                if (href && href.includes('/entry/show/')) {
                    detailUrl = href;
                }
            }

            // Extract author from .meta div
            const metaDiv = itemBox.querySelector('.meta');
            if (metaDiv) {
                const metaLinks = metaDiv.querySelectorAll('a');
                for (const link of metaLinks) {
                    const href = link.getAttribute('href') || '';
                    // Author links have pattern /all/all/all/USERID/
                    if (href.match(/\\/all\\/all\\/all\\/\\d+\\/?$/)) {
                        const text = link.textContent.trim();
                        if (text && text.length > 0) {
                            author = text;
                            break;
                        }
                    }
                }
            }

            // Fallback author extraction
            if (!author) {
                const allLinks = itemBox.querySelectorAll('a');
                for (const link of allLinks) {
                    const href = link.getAttribute('href') || '';
                    if (href.match(/\\/all\\/all\\/all\\/\\d+\\/?$/)) {
                        const text = link.textContent.trim();
                        if (text && text.length > 0 && text.length < 50) {
                            author = text;
                            break;
                        }
                    }
                }
            }

            // Extract caption from .caption div
            const captionDiv = itemBox.querySelector('.caption');
            if (captionDiv) {
                const text = captionDiv.textContent.trim();
                if (text && text.length > 0) {
                    caption = text;
                }
            }

            return { author, caption, detailUrl };
        }''')

        author = result.get('author') if result else None
        caption = result.get('caption') if result else None
        detail_url = result.get('detailUrl') if result else None

        return (
            author.strip() if author else "Unknown_Author",
            caption.strip() if caption else None,
            detail_url
        )

    except Exception:
        pass

    return ("Unknown_Author", None, None)


async def extract_author_for_button(page: Page, btn) -> str:
    """
    Legacy function - extract author name only.
    Use extract_metadata_for_button for full metadata.
    """
    author, _, _ = await extract_metadata_for_button(page, btn)
    return author


async def fetch_full_description(page: Page, detail_url: str) -> Optional[str]:
    """
    Fetch the full description from an ensemble's detail page.

    Args:
        page: Playwright page (will open new page in same context)
        detail_url: URL to the detail page

    Returns:
        Full description text, or None if not found
    """
    if not detail_url:
        return None

    # Make absolute URL if relative
    if detail_url.startswith('/'):
        detail_url = BASE_URL + detail_url

    context = page.context
    detail_page = await context.new_page()

    try:
        await detail_page.goto(detail_url, wait_until='domcontentloaded', timeout=30000)

        # Wait a bit for content to load
        await asyncio.sleep(1)

        # Extract the full description from the detail page
        description = await detail_page.evaluate('''() => {
            // Look for description in various possible locations
            const selectors = [
                '.entry-description',
                '.description',
                '.readme',
                '.detail-description',
                '.content-description',
                '.info-text',
                'article .content',
                '.entry-content',
                // The detail page might show the description in a specific section
                '.detail-info .text',
                '.item-detail .description',
            ];

            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const text = el.textContent.trim();
                    if (text && text.length > 10) {
                        return text;
                    }
                }
            }

            // Try to find any substantial text block that might be description
            const mainContent = document.querySelector('.main-content, main, #content');
            if (mainContent) {
                const paragraphs = mainContent.querySelectorAll('p');
                for (const p of paragraphs) {
                    const text = p.textContent.trim();
                    if (text && text.length > 50 && text.length < 5000) {
                        return text;
                    }
                }
            }

            return null;
        }''')

        return description.strip() if description else None

    except Exception as e:
        # Don't fail the download for description fetch errors
        return None

    finally:
        await detail_page.close()


async def debug_page_structure(page: Page) -> None:
    """Debug helper to print page structure around download buttons."""
    try:
        html = await page.evaluate('''() => {
            const btn = document.querySelector('.btn-download');
            if (!btn) return 'No download button found';

            // Get parent elements
            let el = btn;
            let path = [];
            for (let i = 0; i < 6; i++) {
                if (!el) break;
                path.push({
                    tag: el.tagName,
                    classes: el.className,
                    id: el.id
                });
                el = el.parentElement;
            }

            // Get HTML of parent container
            const container = btn.parentElement?.parentElement?.parentElement;
            const html = container ? container.outerHTML.slice(0, 2000) : 'No container';

            return JSON.stringify({path, html}, null, 2);
        }''')
        print(f"DEBUG PAGE STRUCTURE:\n{html}")
    except Exception as e:
        print(f"Debug failed: {e}")


async def navigate_to_page(page: Page, page_num: int) -> bool:
    """
    Navigate to a specific listing page.

    Args:
        page: Playwright page
        page_num: Page number to navigate to

    Returns:
        True if navigation successful, False otherwise
    """
    url = BASE_URL + PAGINATION_PATTERN.format(page=page_num)

    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)

        if response and response.status >= 400:
            print(f"  Warning: Page {page_num} returned status {response.status}")
            return False

        # Wait for the download buttons to appear (indicates page is ready)
        try:
            await page.wait_for_selector('.btn-download', timeout=15000)
        except Exception:
            # Content might still be loading via JS
            await asyncio.sleep(2)

        return True

    except Exception as e:
        print(f"  Error navigating to page {page_num}: {e}")
        return False


async def get_total_pages(page: Page) -> Optional[int]:
    """
    Extract total page count from pagination.

    Args:
        page: Playwright page on the library listing

    Returns:
        Total number of pages, or None if not found
    """
    try:
        # Look for pagination count in JavaScript variable
        total = await page.evaluate('''() => {
            // Check for global pagination variable
            if (typeof paginationCount !== 'undefined') {
                return parseInt(paginationCount, 10);
            }

            // Try to find last page link
            const lastPageLink = document.querySelector('.pagination a:last-child, .pagination li:last-child a');
            if (lastPageLink) {
                const href = lastPageLink.getAttribute('href');
                const match = href && href.match(/\\/([0-9]+)\\/all\\/?$/);
                if (match) {
                    return parseInt(match[1], 10);
                }
            }

            return null;
        }''')

        return total

    except Exception:
        return None
