import curses
import json
import time
import requests
from price_empire_scraper import PriceEmpireScraper, format_market_hash_name

def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}

def draw_menu(stdscr):
    k = 0
    
    # Initialization
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)
    
    # Load config and extract API key if present
    # Expecting config.json to have:
    # { "api_key": "YOUR_KEY", "items": [...] }
    # but the current config.json is a list of items.
    # Let's handle both.
    
    config_data = load_config()
    api_key = "YOUR_API_KEY" # Default or prompt user
    items_to_track = []

    if isinstance(config_data, dict):
        api_key = config_data.get("api_key", api_key)
        items_to_track = config_data.get("items", [])
    elif isinstance(config_data, list):
        items_to_track = config_data

    scraper = PriceEmpireScraper(api_key)
    
    last_update = 0
    prices = {}
    loading = False
    error_message = ""

    while k != ord('q'):
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # Header
        header = "CS2 Skin Price Scraper (PriceEmpire API)"
        stdscr.addstr(0, (width - len(header)) // 2, header, curses.A_BOLD | curses.A_UNDERLINE)
        
        # Help text
        stdscr.addstr(height-1, 0, "Press 'q' to quit | 'r' to refresh")

        current_time = time.time()
        
        # Refresh logic: on start, manual 'r', or every 5 minutes (300 seconds)
        # Added a cooldown to prevent hammering on failure (e.g., retry after 30 seconds if error)
        should_refresh = False
        if last_update == 0:
            should_refresh = True
        elif k == ord('r'):
            should_refresh = True
        elif current_time - last_update > 300:
            should_refresh = True

        if should_refresh:
            loading = True
            stdscr.addstr(2, 2, "Fetching prices from PriceEmpire...")
            stdscr.refresh()
            
            # Fetch prices
            api_response = scraper.get_prices()
            
            # Update last_update regardless of success to prevent 0.1s retry loops
            last_update = current_time
            
            if isinstance(api_response, dict) and "error" in api_response:
                error_message = api_response["error"]
                # If we get an error, maybe keep old prices but show the error
            else:
                prices = api_response
                error_message = ""
            loading = False

        if error_message:
            stdscr.addstr(2, 2, f"Error: {error_message[:width-10]}", curses.color_pair(0) | curses.A_BOLD)

        # Display items
        y = 4
        stdscr.addstr(y, 2, f"{'Item Name':<50} | {'Buff 163':>10} | {'Skinport':>10} | {'Lowest':>10}", curses.A_REVERSE)
        y += 1

        for item in items_to_track:
            if y >= height - 3:
                break
            
            mhn = format_market_hash_name(item)
            item_data = prices.get(mhn, {})
            
            # PriceEmpire v4 structure: item_data['prices']['buff163']['price']
            # Prices are typically returned as floats/doubles in USD (if currency=USD)
            price_dict = item_data.get('prices', {})
            
            buff_price = price_dict.get('buff163', {}).get('price', 0.0)
            skinport_price = price_dict.get('skinport', {}).get('price', 0.0)
            
            # Find lowest price from all providers in the 'prices' dictionary
            all_provider_prices = [v.get('price', 0.0) for k, v in price_dict.items() if isinstance(v, dict) and 'price' in v and v.get('price', 0.0) > 0]
            min_price = min(all_provider_prices) if all_provider_prices else 0.0

            stdscr.addstr(y, 2, f"{mhn[:50]:<50} | {buff_price:>10.2f} | {skinport_price:>10.2f} | {min_price:>10.2f}")
            y += 1

        if loading:
            stdscr.addstr(height-2, 2, "Refreshing...")
        elif last_update > 0:
            time_since = int(current_time - last_update)
            stdscr.addstr(height-2, 2, f"Last update: {time_since}s ago")
        else:
            stdscr.addstr(height-2, 2, "No data loaded.")

        stdscr.refresh()
        k = stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(draw_menu)
