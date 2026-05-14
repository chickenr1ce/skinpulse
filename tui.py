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

def draw_price_col(stdscr, y, x, price, prev_price):
    delta = None
    if prev_price is not None and price is not None:
        delta = price - prev_price

    if delta is not None and abs(delta) >= 0.01:
        price_part = f"{price:>7.2f}("
        delta_part = f"{delta:+.2f}"
        color = curses.color_pair(1) if delta < 0 else curses.color_pair(2)
        stdscr.addstr(y, x, price_part, curses.A_NORMAL)
        stdscr.addstr(y, x + len(price_part), delta_part, color)
        stdscr.addstr(y, x + len(price_part) + len(delta_part), ")", curses.A_NORMAL)
    else:
        text = f"{price:>7.2f}(  ~  )"
        stdscr.addstr(y, x, text, curses.A_NORMAL)


def get_sort_value(item, prices, sort_column):
    mhn = format_market_hash_name(item)
    item_data = prices.get(mhn, {})
    price_dict = item_data.get('prices', {})

    if sort_column == 0:
        return mhn.lower()
    elif sort_column == 1:
        return price_dict.get('buff163', {}).get('price', 0.0) or 0.0
    elif sort_column == 2:
        return price_dict.get('skins', {}).get('price', 0.0) or 0.0
    elif sort_column == 3:
        all_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                      if isinstance(v, dict) and v.get('price', 0.0) > 0]
        return min(all_prices) if all_prices else 0.0
    return 0.0


def draw_menu(stdscr):
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)

    k = 0

    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(100)

    config_data = load_config()
    api_key = "YOUR_API_KEY"
    items_to_track = []

    if isinstance(config_data, dict):
        api_key = config_data.get("api_key", api_key)
        items_to_track = config_data.get("items", [])
    elif isinstance(config_data, list):
        items_to_track = config_data

    scraper = PriceEmpireScraper(api_key)

    last_update = 0
    prices = {}
    prev_prices = {}
    loading = False
    error_message = ""
    sort_column = 0
    sort_ascending = True

    while k != ord('q'):
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        header = "CS2 Skin Price Scraper (PriceEmpire API)"
        stdscr.addstr(0, (width - len(header)) // 2, header, curses.A_BOLD | curses.A_UNDERLINE)

        stdscr.addstr(height - 1, 0, "'q' quit | 'r' refresh | '1'-'4' sort column | same key toggles asc/desc")

        current_time = time.time()

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

            prev_prices = prices
            api_response = scraper.get_prices()

            last_update = current_time

            if isinstance(api_response, dict) and "error" in api_response:
                error_message = api_response["error"]
            else:
                prices = api_response
                error_message = ""
            loading = False

        if k in (ord('1'), ord('2'), ord('3'), ord('4')):
            col = k - ord('1')
            if col == sort_column:
                sort_ascending = not sort_ascending
            else:
                sort_column = col
                sort_ascending = True

        if error_message:
            stdscr.addstr(2, 2, f"Error: {error_message[:width-10]}", curses.A_BOLD)

        # Header row
        y = 4
        col_headers = ["Item Name", "Buff 163", "Skins.com", "Lowest"]
        arrows = ["", "", "", ""]
        if sort_column < len(col_headers):
            arrows[sort_column] = " ▲" if sort_ascending else " ▼"

        price_width = 14
        name_width = max(20, width - (price_width * 3 + 3 * 3 + 2 + 2))

        header_fmt = f"{{:<{name_width}}} | {{:>{price_width}}} | {{:>{price_width}}} | {{:>{price_width}}}"
        header_str = header_fmt.format(
            col_headers[0] + arrows[0],
            col_headers[1] + arrows[1],
            col_headers[2] + arrows[2],
            col_headers[3] + arrows[3],
        )
        stdscr.addstr(y, 2, header_str, curses.A_REVERSE)
        y += 1

        sorted_items = sorted(items_to_track, key=lambda i: get_sort_value(i, prices, sort_column),
                              reverse=not sort_ascending)

        for item in sorted_items:
            if y >= height - 3:
                break

            mhn = format_market_hash_name(item)
            item_data = prices.get(mhn, {})
            prev_item_data = prev_prices.get(mhn, {})
            price_dict = item_data.get('prices', {})
            prev_price_dict = prev_item_data.get('prices', {})

            buff_price = price_dict.get('buff163', {}).get('price', 0.0) or 0.0
            skins_price = price_dict.get('skins', {}).get('price', 0.0) or 0.0
            all_provider_prices = [v.get('price', 0.0) for k, v in price_dict.items()
                                   if isinstance(v, dict) and v.get('price', 0.0) > 0]
            min_price = min(all_provider_prices) if all_provider_prices else 0.0

            prev_buff = prev_price_dict.get('buff163', {}).get('price') if prev_prices else None
            prev_skins = prev_price_dict.get('skins', {}).get('price') if prev_prices else None

            x = 2
            stdscr.addstr(y, x, f"{mhn[:name_width]:<{name_width}}")
            x += name_width + 3

            draw_price_col(stdscr, y, x, buff_price, prev_buff)
            x += price_width + 3

            draw_price_col(stdscr, y, x, skins_price, prev_skins)
            x += price_width + 3

            draw_price_col(stdscr, y, x, min_price, None)

            y += 1

        if loading:
            stdscr.addstr(height - 2, 2, "Refreshing...")
        elif last_update > 0:
            time_since = int(current_time - last_update)
            stdscr.addstr(height - 2, 2, f"Last update: {time_since}s ago")
        else:
            stdscr.addstr(height - 2, 2, "No data loaded.")

        stdscr.refresh()
        k = stdscr.getch()

if __name__ == "__main__":
    curses.wrapper(draw_menu)
