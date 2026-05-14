import os

ITEMS_FILE = 'items.txt'


def parse_item_line(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    stattrak = False
    if line.upper().startswith('ST '):
        stattrak = True
        line = line[3:].strip()

    if ',' in line:
        parts = line.split(',', 1)
        name = parts[0].strip()
        wear = parts[1].strip() if parts[1].strip() else None
    else:
        name = line.strip()
        wear = None

    name = name.lstrip('\u2605 ').strip()

    if not name:
        return None

    return {"name": name, "wear": wear, "stattrak": stattrak}


def format_item_line(item):
    prefix = 'ST ' if item.get('stattrak') else ''
    name = item.get('name', '')
    wear = item.get('wear')
    if wear:
        return f"{prefix}{name}, {wear}"
    return f"{prefix}{name}"


def load_items(path=ITEMS_FILE):
    items = []
    try:
        with open(path, 'r') as f:
            for line in f:
                item = parse_item_line(line)
                if item:
                    items.append(item)
    except FileNotFoundError:
        return None
    return items


def save_items(items, path=ITEMS_FILE):
    with open(path, 'w') as f:
        for item in items:
            f.write(format_item_line(item) + '\n')


def get_items_mtime(path=ITEMS_FILE):
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0
