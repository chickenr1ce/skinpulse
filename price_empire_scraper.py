import requests
import json
import time


class PriceEmpireScraper:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.pricempire.com/v4/trader"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

    @staticmethod
    def _mutate_prices_to_dict(item):
        """Convert item's prices list to a dict keyed by provider_key,
        dividing raw cent values by 100 into euros.
        Also scales avg_7d/30d/60d/90d fields when present."""
        prices_data = item.get('prices', [])
        if isinstance(prices_data, list):
            prices_dict = {}
            for entry in prices_data:
                if isinstance(entry, dict) and 'provider_key' in entry:
                    if entry.get('price') is not None:
                        entry['price'] = entry['price'] / 100
                    for avg_key in ('avg_7', 'avg_30', 'avg_60', 'avg_90'):
                        if entry.get(avg_key) is not None:
                            entry[avg_key] = entry[avg_key] / 100
                    prices_dict[entry['provider_key']] = entry
            item['prices'] = prices_dict

    def get_prices(self):
        """Fetches prices for all items."""
        url = f"{self.base_url}/items/prices"
        params = {
            "app_id": 730,
            "currency": "EUR",
            "sources": "buff163,skins",
            "avg": "true"
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                result = {}
                # If API returns a list, convert it to a dict keyed by name
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        name = item.get('market_hash_name', item.get('name'))
                        self._mutate_prices_to_dict(item)
                        result[name] = item
                    return result

                # If API returns a dict, normalize internal prices structure
                if isinstance(data, dict):
                    for name, item in data.items():
                        if isinstance(item, dict):
                            self._mutate_prices_to_dict(item)
                    return data
                
                return {"error": "Unexpected API response format"}
            else:
                return {"error": f"API status {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def get_portfolio(self, slug):
        url = f"{self.base_url}/portfolios/{slug}"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self._mutate_portfolio_cents_to_euros(data)
                return data
            return {"error": f"API status {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def _mutate_portfolio_cents_to_euros(self, data):
        if not isinstance(data, dict):
            return
        stats = data.get("stats", {})
        if isinstance(stats, dict):
            for key in ("totalValue", "totalInvested", "totalRealizedPL",
                        "totalUnrealizedPL", "totalProfit", "change24h"):
                if key in stats and isinstance(stats[key], (int, float)):
                    stats[key] = stats[key] / 100
        for item in data.get("items", []):
            if isinstance(item, dict):
                if "currentPrice" in item and isinstance(item["currentPrice"], (int, float)):
                    item["currentPrice"] = item["currentPrice"] / 100
                item_stats = item.get("stats", {})
                if isinstance(item_stats, dict):
                    for key in ("avgBuyPrice", "currentValue", "totalInvested",
                                "realizedPL", "unrealizedPL", "totalProfit"):
                        if key in item_stats and isinstance(item_stats[key], (int, float)):
                            item_stats[key] = item_stats[key] / 100


