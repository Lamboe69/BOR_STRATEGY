# Managing Trading Symbols - User Guide

## How to Add/Remove Trading Pairs

### 📍 Location
Navigate to: **Settings Page** → **Traded Symbols** section

### ➕ Adding a New Symbol

**Method 1: Using the Add Button**
1. Type the symbol name in the input field (e.g., `EURUSDm`, `XAUUSD`, `US30`)
2. Click the **"+ Add Symbol"** button
3. Symbol appears as a tag above the input field
4. Click **"Save All Settings"** at the top to apply changes

**Method 2: Using Enter Key**
1. Type the symbol name in the input field
2. Press **Enter** on your keyboard
3. Symbol is added instantly
4. Click **"Save All Settings"** to apply

### ❌ Removing a Symbol

1. Find the symbol tag you want to remove
2. Click the **×** button on the tag
3. Symbol is removed instantly
4. Click **"Save All Settings"** to apply changes

### ✅ Features

**Validation:**
- ✅ Automatically converts to UPPERCASE
- ✅ Prevents duplicate symbols
- ✅ Shows toast notifications for feedback
- ✅ Empty input validation

**User Feedback:**
- ✅ "Added [SYMBOL]" - when symbol is added
- ✅ "Removed [SYMBOL]" - when symbol is removed
- ✅ "Symbol already exists" - if duplicate
- ✅ "Please enter a symbol name" - if empty

**Visual Design:**
- 🎨 Purple gradient tags
- 🎨 Hover effects
- 🎨 Smooth animations
- 🎨 Mobile-responsive

## Important Notes

### ⚠️ Symbol Name Format

**Must match your broker's EXACT MT5 symbol names:**

| Broker Type | Example Symbols |
|-------------|----------------|
| **Exness** | `EURUSDm`, `XAUUSDm`, `US30m`, `USTECm` |
| **IC Markets** | `EURUSD`, `XAUUSD`, `US30`, `USTEC` |
| **Pepperstone** | `EURUSD`, `GOLD`, `US30.cash`, `NAS100.cash` |
| **FTMO** | `EURUSD`, `XAUUSD`, `US30`, `NAS100` |

### 🔍 How to Find Your Broker's Symbol Names

**Method 1: MT5 Market Watch**
1. Open MetaTrader 5
2. View → Market Watch (Ctrl+M)
3. Right-click → Show All
4. Find your desired symbol
5. Copy the EXACT name (case-sensitive)

**Method 2: MT5 Symbol Info**
1. Right-click on a chart
2. Symbols
3. Search for your instrument
4. Note the exact symbol name

**Method 3: Test in Backtest**
1. Go to Backtest page
2. Click the Symbol dropdown
3. All available symbols from your MT5 are listed
4. Use those exact names

### 💡 Common Symbol Variations

**EUR/USD:**
- `EURUSD` (most brokers)
- `EURUSDm` (Exness)
- `EURUSD.a` (some ECN brokers)

**Gold:**
- `XAUUSD` (most brokers)
- `XAUUSDm` (Exness)
- `GOLD` (some brokers)

**Dow Jones:**
- `US30` (most brokers)
- `US30m` (Exness)
- `US30.cash` (Pepperstone)
- `DJ30` (some brokers)

**Nasdaq 100:**
- `USTEC` (most brokers)
- `USTECm` (Exness)
- `NAS100` (IC Markets)
- `NAS100.cash` (Pepperstone)
- `US100` (some brokers)

## Step-by-Step Example

### Scenario: Replace EURUSD with GBPUSD

**Step 1: Remove EURUSD**
```
1. Find "EURUSD" tag
2. Click the × button
3. Tag disappears
```

**Step 2: Add GBPUSD**
```
1. Type "GBPUSD" in input field
2. Press Enter or click "+ Add Symbol"
3. "GBPUSD" tag appears
```

**Step 3: Save Changes**
```
1. Click "Save All Settings" button at top
2. Wait for "✅ Settings saved successfully" message
3. Restart bot for changes to take effect
```

### Scenario: Add Multiple Symbols at Once

**Quick Method:**
```
1. Type "GBPUSD" → Press Enter
2. Type "USDJPY" → Press Enter
3. Type "AUDUSD" → Press Enter
4. Type "NZDUSD" → Press Enter
5. Click "Save All Settings"
```

## After Changing Symbols

### 🔄 Restart Required

**Changes take effect after bot restart:**

1. **Stop the bot** (if running)
   - Dashboard → Click "Stop Bot" button
   - Wait for "Stopped" status

2. **Save settings**
   - Settings page → "Save All Settings"
   - Wait for success message

3. **Start the bot**
   - Dashboard → Click "Start Bot" button
   - Wait for "Running" status

4. **Verify symbols**
   - Check Dashboard for new symbols
   - Check Open Trades table
   - Check Session stats

### ✅ Verification Checklist

After restarting the bot:

- [ ] New symbols appear in Dashboard
- [ ] Bot connects to MT5 successfully
- [ ] Session stats show for new symbols
- [ ] No error messages in Activity Log
- [ ] Backtest page shows new symbols in dropdown

## Troubleshooting

### ❌ Symbol Not Working

**Problem:** Added symbol but bot shows errors

**Solutions:**
1. **Check spelling** - Must be EXACT match
2. **Check MT5** - Symbol must exist in Market Watch
3. **Check broker** - Symbol must be available on your account
4. **Check suffix** - Some brokers add `.cash`, `m`, `.a` suffixes
5. **Restart MT5** - Sometimes MT5 needs restart
6. **Check logs** - Activity Log shows specific errors

### ❌ Symbol Not Appearing in Backtest

**Problem:** Symbol not in backtest dropdown

**Solutions:**
1. **Refresh page** - Hard refresh (Ctrl+F5)
2. **Check MT5 connection** - Must be connected
3. **Check symbol availability** - Symbol must have historical data
4. **Wait a moment** - Dropdown loads from MT5 on page load

### ❌ Changes Not Saving

**Problem:** Symbols revert after page refresh

**Solutions:**
1. **Click "Save All Settings"** - Must save before leaving page
2. **Wait for confirmation** - Green toast message
3. **Check file permissions** - `bor_settings.json` must be writable
4. **Check browser console** - F12 → Console for errors

## Best Practices

### ✅ Do's

✅ **Test one symbol first** - Add one, test, then add more
✅ **Use exact names** - Copy from MT5 Market Watch
✅ **Save frequently** - Save after each change
✅ **Verify in backtest** - Run backtest to confirm symbol works
✅ **Keep it simple** - Start with 2-4 symbols max
✅ **Document your symbols** - Keep a list of your broker's names

### ❌ Don'ts

❌ **Don't use generic names** - "EURUSD" might be "EURUSDm" on your broker
❌ **Don't add too many** - More symbols = more complexity
❌ **Don't forget to save** - Changes won't apply without saving
❌ **Don't skip testing** - Always backtest new symbols first
❌ **Don't mix brokers** - Use symbols from ONE broker only

## Mobile Usage

### 📱 On Mobile Devices

**Adding Symbols:**
- Input field is full-width
- "Add Symbol" button is full-width
- Tap to add, swipe to scroll tags

**Removing Symbols:**
- Tap the × button on any tag
- Tags wrap to multiple lines on small screens

**Saving:**
- "Save All Settings" button is always visible at top
- Sticky bar stays visible while scrolling

## Advanced Tips

### 💡 Quick Symbol Management

**Keyboard Shortcuts:**
- `Enter` - Add symbol from input field
- `Escape` - Clear input field (browser default)
- `Tab` - Navigate between fields

**Bulk Operations:**
1. Remove all unwanted symbols first
2. Add all new symbols in sequence
3. Save once at the end

### 💡 Symbol Testing Workflow

**Before going live:**
```
1. Add symbol in Settings
2. Save settings
3. Go to Backtest page
4. Run backtest on new symbol
5. Check win rate and performance
6. If good → Start live bot
7. If bad → Remove symbol
```

### 💡 Symbol Organization

**Recommended groupings:**
- **Forex Major**: EURUSD, GBPUSD, USDJPY
- **Forex Minor**: AUDUSD, NZDUSD, USDCAD
- **Commodities**: XAUUSD (Gold), XAGUSD (Silver)
- **Indices**: US30, USTEC, UK100
- **Crypto**: BTCUSD, ETHUSD (if broker supports)

## Summary

✅ **Easy to use** - Click × to remove, type and Enter to add
✅ **Visual feedback** - Toast notifications for all actions
✅ **Mobile-friendly** - Works great on phones and tablets
✅ **Validation** - Prevents duplicates and empty entries
✅ **Persistent** - Saves to `bor_settings.json`
✅ **Flexible** - Add/remove as many symbols as needed

**Remember:** Always save settings and restart the bot for changes to take effect! 🚀
