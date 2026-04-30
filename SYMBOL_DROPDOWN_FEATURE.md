# Symbol Dropdown Selection Feature

## Problem

When manually entering symbol names in the settings page, the bot didn't recognize them because:
- Users typed incorrect symbol names (e.g., "XAUUSD" when broker uses "GOLD")
- Typos in symbol names
- Different brokers use different naming conventions

## Solution

Replaced the manual text input with a **dropdown menu** that fetches available symbols directly from your MT5 platform.

## Changes Made

### 1. Settings Page UI (`ui/templates/settings.html`)

**Before:**
```html
<input type="text" id="sym-input" placeholder="e.g. EURUSDm, XAUUSD, US30">
```

**After:**
```html
<select id="sym-select">
  <option value="">-- Select a symbol --</option>
  <option value="EURUSD">EURUSD</option>
  <option value="XAUUSD">XAUUSD</option>
  <!-- ... all symbols from your MT5 -->
</select>
```

### 2. JavaScript Changes

Added function to load symbols from MT5:
```javascript
async function loadAvailableSymbols() {
  const r = await fetch('/backtest/symbols');
  const j = await r.json();
  availableSymbols = j.symbols || [];
  // Populate dropdown with actual MT5 symbols
}
```

Updated `addSymbol()` to use dropdown instead of text input:
```javascript
function addSymbol() {
  const sel = document.getElementById('sym-select');
  const v = sel.value.trim().toUpperCase();
  // Add selected symbol to list
}
```

## How It Works

1. **Page loads** → Fetches all available symbols from your MT5 platform
2. **Dropdown populates** → Shows exact symbol names as they appear in MT5
3. **Select symbol** → Choose from the dropdown (no typing needed)
4. **Click "Add Symbol"** → Symbol added to your trading list
5. **Save settings** → Bot will use the correct symbol names

## Benefits

✅ **No more typos** - Select from a list instead of typing
✅ **Exact names** - Uses your broker's exact MT5 symbol names
✅ **Easy discovery** - See all available symbols in one place
✅ **Same as backtest** - Consistent with the backtest page dropdown

## Usage

### Adding Symbols

1. Go to **Settings** page
2. Scroll to **Traded Symbols** section
3. Click the dropdown menu
4. Select a symbol (e.g., XAUUSD)
5. Click **Add Symbol**
6. Repeat for all symbols you want to trade
7. Click **Save All Settings**

### Removing Symbols

- Click the **×** button on any symbol tag to remove it
- Don't forget to **Save** after removing

## Symbol Name Examples by Broker

Different brokers use different naming conventions:

| Instrument | Common Names |
|------------|--------------|
| Gold | XAUUSD, GOLD, XAUUSDm |
| EUR/USD | EURUSD, EURUSDm, EURUSD.a |
| Dow Jones | US30, US30.cash, DJ30, DOWJONES |
| Nasdaq 100 | USTEC, NAS100, NAS100.cash, US100 |
| GBP/USD | GBPUSD, GBPUSDm |

The dropdown will show **exactly** what your broker uses, so you don't have to guess!

## Troubleshooting

### Dropdown shows "Loading symbols..."
- Make sure MT5 is running
- Check your MT5 credentials in settings
- Verify MT5 connection settings are correct

### Dropdown shows "Error loading symbols"
- MT5 connection failed
- Check MT5 login, password, and server
- Ensure MT5 terminal is installed and accessible

### Dropdown shows "No symbols available"
- MT5 returned no symbols
- Try restarting MT5 terminal
- Check if your account has access to symbols

## Fallback Behavior

If MT5 connection fails, the dropdown will still work but show a default list:
- EURUSD
- XAUUSD
- US30
- USTEC

You can still add these, but they might not match your broker's exact names.

## Testing

After adding symbols:
1. Save settings
2. Start the bot
3. Check logs for: "BOR Bot started — symbols: ['XAUUSD', 'EURUSD', ...]"
4. Verify symbols are recognized (no "symbol not found" errors)

## Notes

- The dropdown fetches symbols **every time** you open the settings page
- Symbols are fetched from the same MT5 connection used for trading
- If you change brokers, the dropdown will automatically show the new broker's symbols
