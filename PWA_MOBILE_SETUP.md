# PWA Mobile App Setup Guide

Your BOR Bot dashboard is now a **Progressive Web App (PWA)** that can be installed on your phone like a native app!

---

## ✅ What's New

1. **Login/Registration System** — Secure authentication to protect your trading account
2. **PWA Support** — Install on iOS/Android home screen
3. **Offline Capability** — Service worker caching for faster loads
4. **Mobile Optimized** — Already responsive, now installable
5. **Logout Button** — Secure session management

---

## 📱 Step 1: Create Your Account

1. Start the dashboard:
   ```bash
   python ui\dashboard.py
   ```

2. Open browser: `http://localhost:5000`

3. You'll see the **Login/Register** screen

4. Click **Register** tab:
   - Enter username
   - Enter password (min 6 characters)
   - Click "Create Account"

5. Switch to **Login** tab and login

---

## 🌐 Step 2: Access from Your Phone (Same WiFi)

### Find Your Computer's Local IP:

**Windows:**
```bash
ipconfig
```
Look for "IPv4 Address" (e.g., `192.168.1.100`)

**Mac/Linux:**
```bash
ifconfig | grep inet
```

### Access from Phone:
1. Connect phone to **same WiFi** as computer
2. Open phone browser: `http://192.168.1.100:5000` (use your IP)
3. Login with your credentials
4. Tap browser menu → **"Add to Home Screen"**
5. App icon appears on home screen!

---

## 🚀 Step 3: Access from Anywhere (Internet)

Use **Cloudflare Tunnel** (FREE, secure, no port forwarding needed)

### Install Cloudflare Tunnel:

**Windows:**
1. Download: https://github.com/cloudflare/cloudflared/releases
2. Extract `cloudflared.exe` to `C:\cloudflared\`
3. Add to PATH or run from that folder

**Mac:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

**Linux:**
```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
```

### Start the Tunnel:

1. **Start your dashboard first:**
   ```bash
   python ui\dashboard.py
   ```

2. **In a NEW terminal, start tunnel:**
   ```bash
   cloudflared tunnel --url http://localhost:5000
   ```

3. You'll see output like:
   ```
   Your quick Tunnel has been created! Visit it at:
   https://random-name-1234.trycloudflare.com
   ```

4. **Copy that URL** — this is your public link!

5. **Open on your phone** (from anywhere with internet):
   - Open browser
   - Go to: `https://random-name-1234.trycloudflare.com`
   - Login
   - Add to home screen

---

## 📲 Installing the PWA

### iOS (iPhone/iPad):
1. Open Safari (must use Safari, not Chrome)
2. Go to your dashboard URL
3. Tap **Share** button (square with arrow)
4. Scroll down → tap **"Add to Home Screen"**
5. Name it "BOR Bot" → tap **Add**
6. App appears on home screen with icon!

### Android:
1. Open Chrome
2. Go to your dashboard URL
3. Tap **menu** (3 dots)
4. Tap **"Add to Home screen"** or **"Install app"**
5. Confirm
6. App appears on home screen!

---

## 🔒 Security Best Practices

1. **Use Strong Password** — Min 8 characters, mix of letters/numbers/symbols
2. **Don't Share Credentials** — Each user should have their own account
3. **HTTPS Only for Public Access** — Cloudflare Tunnel provides this automatically
4. **Logout When Done** — Especially on shared devices
5. **Keep Tunnel Private** — Don't share your tunnel URL publicly

---

## 🎯 Usage Workflow

### Daily Use:
1. **Computer stays on** with bot running
2. **Access from phone** anywhere via tunnel URL
3. **Monitor trades** in real-time
4. **Adjust settings** remotely
5. **Check performance** on the go

### When Computer Restarts:
1. Start dashboard: `python ui\dashboard.py`
2. Start tunnel: `cloudflared tunnel --url http://localhost:5000`
3. Use the NEW tunnel URL (it changes each time with free tier)

---

## 💡 Pro Tips

### Permanent Tunnel URL (Optional):
Free tier gives random URLs. For a permanent URL:
1. Create Cloudflare account (free)
2. Set up named tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
3. Get permanent URL like: `https://bor-bot.yourdomain.com`

### Auto-Start on Boot:
Create a batch file `start_bot_and_tunnel.bat`:
```batch
@echo off
start "BOR Dashboard" python ui\dashboard.py
timeout /t 5
start "Cloudflare Tunnel" cloudflared tunnel --url http://localhost:5000
```

### Keep Computer Awake:
**Windows:** Settings → Power → Never sleep when plugged in
**Mac:** System Preferences → Energy Saver → Prevent sleep

---

## 🐛 Troubleshooting

### Can't access from phone (same WiFi):
- Check Windows Firewall allows port 5000
- Try: `python ui\dashboard.py --host=0.0.0.0`

### Tunnel not working:
- Make sure dashboard is running FIRST
- Check internet connection
- Try restarting tunnel

### Login not working:
- Clear browser cache
- Check `users.json` exists in project root
- Restart dashboard

### PWA not installing:
- **iOS:** Must use Safari browser
- **Android:** Must use Chrome browser
- Make sure you're on HTTPS (tunnel provides this)

---

## 📊 What You Can Do from Phone

✅ View live dashboard with real-time updates
✅ Monitor open trades and P&L
✅ Check session status (Tokyo/London)
✅ Start/Stop bot remotely
✅ View performance charts
✅ Run backtests
✅ Change settings (MT5 credentials, risk, symbols)
✅ View trade history

---

## 🎉 You're All Set!

Your BOR Bot is now accessible from anywhere in the world via your phone!

**Questions?** Check the main README.md or create an issue on GitHub.

**Security Note:** Your MT5 credentials are stored locally on your computer, not transmitted through the tunnel. The tunnel only provides access to your dashboard interface.
