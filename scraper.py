import logging
import json
import asyncio
from typing import Dict, List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError
from api import api_fallback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)

async def fetch_stock_data() -> Dict[str, List[Dict]]:
    """
    Scrapes the Grow A Garden Stock website for current inventory using Playwright.
    Falls back to API if scraping fails.
    Returns a dictionary containing lists of items with their details for each category.
    """
    # Check if we should use the fallback API
    if api_fallback.should_use_fallback():
        logging.info("Using fallback API as main website is temporarily unavailable")
        api_data = await api_fallback.fetch_stock_data()
        if api_data:
            return api_data
        else:
            logging.error("Fallback API also failed")
            return {
                "seeds": [],
                "gears": [],
                "eggs": [],
                "weather": [],
                "event_shop": []
            }

    try:
        url = "https://growagardenvalues.com/stock/stocks.php"
        
        async with async_playwright() as p:
            # Launch browser with optimized settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-sandbox',
                    '--disable-extensions',
                    '--disable-component-extensions-with-background-pages',
                    '--disable-default-apps',
                    '--mute-audio',
                    '--no-default-browser-check',
                    '--no-first-run',
                    '--disable-background-networking',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-breakpad',
                    '--disable-client-side-phishing-detection',
                    '--disable-hang-monitor',
                    '--disable-ipc-flooding-protection',
                    '--disable-popup-blocking',
                    '--disable-prompt-on-repost',
                    '--disable-renderer-backgrounding',
                    '--disable-sync',
                    '--force-color-profile=srgb',
                    '--metrics-recording-only',
                    '--no-experiments',
                    '--safebrowsing-disable-auto-update'
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                java_script_enabled=True,
                bypass_csp=True
            )
            
            try:
                # Create a new page
                page = await context.new_page()
                
                # Set default timeout to 30 seconds
                page.set_default_timeout(30000)
                
                # Try to load the page with retries
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    try:
                        # Navigate to the page with increased timeout
                        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                        
                        # Wait for the stock sections to be visible with a more lenient timeout
                        try:
                            await page.wait_for_selector('section.stock-section', timeout=15000)
                        except TimeoutError:
                            # If we timeout waiting for sections, try to get content anyway
                            logging.warning("Timeout waiting for stock sections, proceeding with available content")
                        
                        # Get the page content
                        content = await page.content()
                        
                        # Verify we have some content
                        if 'stock-section' in content:
                            # Only reset fallback if we successfully got fresh data
                            # Don't reset immediately - let the main bot logic handle this
                            break
                        else:
                            raise Exception("Page content doesn't contain stock sections")
                            
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logging.error(f"All attempts failed: {e}")
                            # Don't switch to fallback here - let the bot handle fallback decisions
                            # Just return empty data and let the bot's logic handle the fallback
                            return {
                                "seeds": [],
                                "gears": [],
                                "eggs": [],
                                "weather": [],
                                "event_shop": []
                            }
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # Initialize results dictionary with more detailed categories
                results = {
                    "seeds": [],
                    "gears": [],
                    "eggs": [],
                    "weather": [],
                    "event_shop": []
                }
                
                # Map section IDs to category names
                section_to_category = {
                    "seeds-section": "seeds",
                    "gears-section": "gears",
                    "eggs-section": "eggs",
                    "weather-section": "weather",
                    "event-shop-stock-section": "event_shop"
                }
                
                # Find all stock sections and filter out cosmetics
                stock_sections = soup.find_all('section', class_='stock-section')
                valid_sections = [section for section in stock_sections 
                                if section.get('id') in section_to_category]
                logging.info(f"Found {len(valid_sections)} sections")
                
                for section in valid_sections:
                    try:
                        # Get the section ID to determine category
                        section_id = section.get('id', '')
                        if not section_id:
                            continue
                            
                        # Map section ID to category name
                        category = section_to_category.get(section_id)
                        if not category:
                            continue
                            
                        # Find all items in this section
                        items = section.find_all('div', class_='stock-item')
                        
                        for item in items:
                            try:
                                # Get item details
                                name_elem = item.find('div', class_='item-name')
                                quantity_elem = item.find('div', class_='item-quantity')
                                
                                if not name_elem:
                                    continue
                                    
                                item_name = name_elem.text.strip()
                                quantity = quantity_elem.text.strip() if quantity_elem else "x0"
                                
                                # Remove 'x' prefix and convert to integer
                                quantity = int(quantity.replace('x', '')) if quantity.startswith('x') else 0
                                
                                # Format item name with quantity
                                formatted_name = f"{item_name} (x{quantity})"
                                
                                item_data = {
                                    "name": formatted_name,
                                    "quantity": quantity,
                                    "original_name": item_name
                                }
                                
                                # Add image URL if available
                                img_elem = item.find('img')
                                if img_elem and img_elem.get('src'):
                                    item_data["image_url"] = img_elem['src']
                                
                                # Handle special cases
                                if category == 'weather':
                                    # Weather items have emoji and time information
                                    emoji_elem = item.find('span', style="font-size: 2em;")
                                    if emoji_elem:
                                        item_data["emoji"] = emoji_elem.text.strip()
                                    if quantity_elem:
                                        item_data["time_info"] = quantity_elem.text.strip()
                                        formatted_name = f"{item_name} - {quantity_elem.text.strip()}"
                                        item_data["name"] = formatted_name
                                
                                # Add to appropriate category
                                results[category].append(item_data)
                                    
                            except Exception as e:
                                logging.debug(f"Failed to process item in {category}: {e}")
                                continue
                            
                    except Exception as e:
                        logging.debug(f"Failed to process section: {e}")
                        continue
                
                # Log summary of items found
                for category, items in results.items():
                    if items:
                        logging.info(f"Found {len(items)} items in {category}")
                
                return results
                
            finally:
                # Ensure browser is closed even if an error occurs
                await browser.close()
            
    except Exception as e:
        logging.error(f"Failed to fetch stock data: {e}")
        # Don't switch to fallback here - let the bot handle fallback decisions
        # Just return empty data and let the bot's logic handle the fallback
        return {
            "seeds": [],
            "gears": [],
            "eggs": [],
            "weather": [],
            "event_shop": []
        }

def main():
    """
    Test function to verify the scraper works
    """
    stock_data = asyncio.run(fetch_stock_data())
    print(json.dumps(stock_data, indent=2))

if __name__ == "__main__":
    main()