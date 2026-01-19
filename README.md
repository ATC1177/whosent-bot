# Whosent — anonymous messages bot

## Files in repo
- `bot.py` — main bot code (aiogram v2)
- `requirements.txt` — dependencies
- `runtime.txt` — Python version for Render (3.11.8)
- `.gitignore`
- `example.env` — example env (DO NOT commit actual `.env`)

## Quick start (Replit)
1. Create new Python Repl.
2. Upload `bot.py` and `requirements.txt`.
3. In Shell run: `pip install -r requirements.txt`
4. Add secret: `BOT_TOKEN` (Replit → Secrets).
5. Run the repl. Send `/start` to your bot in Telegram.

## Quick start (Render)
1. Create project → choose repo.
2. **Use Background Worker** (recommended) or Web Service only if you host HTTP.
3. Ensure `runtime.txt` exists (`python-3.11.8`).
4. Add Environment Variables in Render:
   - BOT_TOKEN, ADMIN_ID, ADMIN_USERNAME, SUPPORT_USERNAME, REVEAL_PRICE_STARS
5. Deploy → Manual Deploy → Clear build cache & deploy.
6. Watch logs. Bot should start and show "Start polling".

## Security
- Never push real `.env` to GitHub.
- If token was leaked — revoke it in `@BotFather` and generate a new one.
