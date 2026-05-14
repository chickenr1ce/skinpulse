#!/usr/bin/env python3
import sys
import json
from items import load_items, save_items, format_item_line

CONFIG_FILE = 'config.json'


def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def sync_config(items):
    config = load_config()
    config['items'] = items
    save_config(config)


def get_all_items():
    items = load_items()
    if items is not None:
        return items
    config = load_config()
    if isinstance(config, list):
        return config
    return config.get('items', [])


def cmd_list():
    items = get_all_items()
    if not items:
        items_missing = load_items() is None
        if items_missing:
            print("No items.txt found and config.json has no items.")
        else:
            print("No items tracked.")
        print("Run 'python3 manage.py add' to add one.")
        return
    for i, item in enumerate(items):
        print(f"{i}: {format_item_line(item)}")


def cmd_add():
    print("Add a new item. Press Enter with empty input to cancel at any prompt.\n")

    name = input("Name (e.g. 'AK-47 | Redline'): ").strip()
    if not name:
        print("Cancelled.")
        return

    wear = input("Wear (e.g. 'Field-Tested') [none]: ").strip()
    if not wear:
        wear = None

    st_input = input("StatTrak? (y/N): ").strip().lower()
    stattrak = st_input.startswith('y')

    item = {"name": name, "wear": wear, "stattrak": stattrak}
    line = format_item_line(item)
    print(f"\nPreview: {line}")

    confirm = input("Add this item? (Y/n): ").strip().lower()
    if confirm and confirm != 'y':
        print("Cancelled.")
        return

    items = get_all_items()
    items.append(item)
    save_items(items)
    sync_config(items)
    print(f"Added: {line}")


def cmd_remove(args):
    items = get_all_items()
    if not items:
        print("No items to remove.")
        return

    if not args:
        print("Usage: manage.py remove <index|name>")
        return

    target = ' '.join(args)

    # try index first
    try:
        idx = int(target)
        if 0 <= idx < len(items):
            item = items.pop(idx)
            save_items(items)
            sync_config(items)
            print(f"Removed: {format_item_line(item)}")
            return
        else:
            print(f"Index {idx} out of range (0-{len(items) - 1}).")
            return
    except ValueError:
        pass

    # search by name substring
    matches = []
    for i, item in enumerate(items):
        if target.lower() in format_item_line(item).lower():
            matches.append((i, item))

    if not matches:
        print(f"No items matching '{target}'.")
        return

    if len(matches) > 1:
        print("Multiple matches — use the index number:")
        for idx, item in matches:
            print(f"  {idx}: {format_item_line(item)}")
        return

    idx, item = matches[0]
    confirm = input(f"Remove '{format_item_line(item)}'? (y/N): ").strip().lower()
    if confirm != 'y':
        print("Cancelled.")
        return

    items.pop(idx)
    save_items(items)
    sync_config(items)
    print(f"Removed: {format_item_line(item)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 manage.py <list|add|remove> [args]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == 'list':
        cmd_list()
    elif cmd == 'add':
        cmd_add()
    elif cmd == 'remove':
        cmd_remove(sys.argv[2:])
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python3 manage.py <list|add|remove> [args]")
        sys.exit(1)


if __name__ == '__main__':
    main()
