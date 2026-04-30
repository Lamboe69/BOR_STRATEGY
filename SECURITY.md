# Security Model - BOR Bot

## 🔒 CRITICAL SECURITY UPDATE

Your BOR Bot now has **enterprise-grade security** to protect your trading account from unauthorized access.

---

## Security Features

### 1. **Single Admin Account (Owner Only)**
- ✅ **First user to register = Admin** (YOU)
- ✅ **Registration automatically disabled** after first account created
- ✅ **No one else can create accounts**
- ✅ **Full control over bot and settings**

### 2. **Admin-Only Actions**
Only the admin (you) can:
- ✅ Change MT5 settings (login, password, server)
- ✅ Start/Stop the trading bot
- ✅ Modify risk settings
- ✅ Add/remove trading symbols
- ✅ Change session times

### 3. **Protected Routes**
- `/settings` (POST) - Admin only
- `/bot/start` - Admin only
- `/bot/stop` - Admin only
- All other pages - Login required

---

## First-Time Setup

### Step 1: Create Your Admin Account

1. Start the dashboard:
   ```bash
   python ui\dashboard.py
   ```

2. Open browser: `http://localhost:5000`

3. You'll see the **Login/Register** page

4. Click **Register** tab

5. Create your admin account:
   - Username: `your_username`
   - Password: `strong_password_123` (min 6 characters)
   - Confirm password

6. Click **"Create Account"**

7. You'll see: **"✅ Admin account created! You can now login."**

8. Switch to **Login** tab and login

---

### Step 2: What Happens Next

After you create your account:
- ✅ Registration is **permanently disabled**
- ✅ Anyone trying to register will see: **"🔒 Registration is disabled. Only the owner can access this system."**
- ✅ Only YOU can login with your credentials
- ✅ Only YOU can control the bot

---

## Security Best Practices

### 1. **Strong Password**
- ❌ DON'T use: `123456`, `password`, `admin`
- ✅ DO use: `MyTr@d1ng!B0t2024` (mix of letters, numbers, symbols)
- Minimum 8 characters recommended (system requires 6)

### 2. **Keep Credentials Secret**
- ❌ Don't share your username/password
- ❌ Don't write them down in plain text
- ✅ Use a password manager (LastPass, 1Password, Bitwarden)

### 3. **Secure Remote Access**
When using Cloudflare Tunnel:
- ✅ Use HTTPS (tunnel provides this automatically)
- ✅ Don't share your tunnel URL publicly
- ✅ Logout when done on shared devices
- ✅ Use private/incognito mode on public computers

### 4. **Session Security**
- Sessions expire when you close browser
- Logout button in sidebar for manual logout
- Each login creates a new secure session

---

## What If Someone Tries to Access?

### Scenario 1: Someone tries to register
**Result:** ❌ Blocked
```
🔒 Registration is disabled. Only the owner can access this system.
```

### Scenario 2: Someone tries to login with wrong password
**Result:** ❌ Blocked
```
❌ Invalid username or password
```

### Scenario 3: Someone tries to access dashboard without login
**Result:** ❌ Redirected to login page

### Scenario 4: Someone tries to change settings without admin role
**Result:** ❌ Blocked
```json
{"ok": false, "msg": "Admin access required"}
```

---

## Password Reset (If You Forget)

If you forget your password:

1. **Stop the dashboard**

2. **Delete the users file:**
   ```bash
   del users.json
   ```

3. **Restart dashboard**

4. **Register again** (you'll be admin again)

**⚠️ WARNING:** This will delete ALL user accounts. Since you're the only user, this is safe.

---

## Multi-User Setup (Future Enhancement)

If you want to add **view-only users** later (family, friends, investors):

### Option 1: Manual Addition
Edit `users.json` and add:
```json
{
  "users": [
    {
      "username": "admin",
      "password": "hashed_password",
      "role": "admin"
    },
    {
      "username": "viewer",
      "password": "hashed_password",
      "role": "viewer"
    }
  ]
}
```

**Viewer role can:**
- ✅ View dashboard
- ✅ View performance
- ✅ View open trades
- ❌ Cannot change settings
- ❌ Cannot start/stop bot

### Option 2: Admin Panel (Not Yet Implemented)
Future feature: Admin can create viewer accounts from dashboard.

---

## Security Checklist

Before going live:

- [ ] Created strong admin password
- [ ] Tested login/logout
- [ ] Verified registration is disabled
- [ ] Tested remote access via tunnel
- [ ] Saved password in password manager
- [ ] Tested that settings require admin access
- [ ] Tested that bot control requires admin access

---

## Technical Details

### Password Hashing
- Algorithm: SHA-256
- Passwords are NEVER stored in plain text
- Even if someone steals `users.json`, they can't see your password

### Session Management
- Secure session cookies
- Random 32-byte secret key (generated on startup)
- Sessions tied to browser
- Logout clears session completely

### Role-Based Access Control (RBAC)
```python
@admin_required  # Only admin can access
def settings_save():
    # Change MT5 settings
    pass

@login_required  # Any logged-in user can access
def performance_page():
    # View performance
    pass
```

---

## Emergency: Account Compromised

If you suspect someone has your password:

1. **Immediately stop the bot:**
   ```bash
   # Kill all Python processes
   taskkill /F /IM python.exe
   ```

2. **Change your password:**
   - Delete `users.json`
   - Restart dashboard
   - Create new admin account with new password

3. **Check for unauthorized trades:**
   - Review trade history
   - Check MT5 account for unknown orders

4. **Secure your system:**
   - Run antivirus scan
   - Change MT5 password
   - Enable 2FA on MT5 if available

---

## Summary

**Your BOR Bot is now secure:**
- 🔒 Single admin account (you)
- 🔒 Registration disabled after first user
- 🔒 Admin-only bot control
- 🔒 Password hashing
- 🔒 Session management
- 🔒 Protected routes

**No one can:**
- ❌ Create new accounts
- ❌ Access without login
- ❌ Change settings without admin role
- ❌ Start/stop bot without admin role
- ❌ See your password (even in database)

**You're protected!** 🛡️
