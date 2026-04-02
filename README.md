# CS2 Skin Price Scraper (PriceEmpire Edition)

A terminal-based tool to track real-time CS2 skin prices across multiple marketplaces using the PriceEmpire API.

## Prerequisites

*   **Python 3.x**: Ensure you have Python 3 installed on your system.
*   **PriceEmpire API Key**: You need a valid API key from [PriceEmpire](https://pricempire.com/api).

## Installation

1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <repository-url>
    cd CS2_SkinPrice_Scraper
    ```

2.  **Verify Dependencies**:
    The project uses the `requests` library. Check if it's installed:
    ```bash
    python3 -c "import requests; print('Requests is installed')"
    ```
    If not installed, install it via:
    ```bash
    pip install requests
    ```

## Configuration

1.  **Open `config.json`** in your preferred text editor.
2.  **Insert your API Key**: Replace `"YOUR_PRICEEMPIRE_API_KEY"` with your actual PriceEmpire API key (Trader plan is free).
3.  **Add your Skins**: Update the `items` list with the skins you want to track.
    *   **Note**: The scraper automatically handles the "★" symbol for knives and formats the name to match the Steam Market Hash Name (e.g., `★ Karambit | Black Laminate (Well-Worn)`).

Example `config.json`:
```json
{
    "api_key": "your-api-key-here",
    "items": [
        {
            "name": "Karambit | Black Laminate",
            "wear": "Well-Worn",
            "stattrak": false
        }
    ]
}
```

## How to Run

1.  **Start the TUI**:
    Run the following command in your terminal:
    ```bash
    python3 tui.py
    ```

2.  **Interface Controls**:
    *   **'r'**: Manually refresh prices (the app also auto-refreshes every 5 minutes).
    *   **'q'**: Quit the application.

## Troubleshooting

*   **API status 403**: This means your API key is invalid or you are accessing an endpoint not covered by your plan. Ensure you have the **Trader (Free)** plan or higher.
*   **API status 429**: Rate limit exceeded. The app is configured to auto-refresh every 5 minutes to stay within free tier limits.
*   **Test with Curl**: 
    ```bash
    curl -H "Authorization: Bearer YOUR_KEY" "https://api.pricempire.com/v4/trader/items/prices?app_id=730&currency=USD"
    ```
