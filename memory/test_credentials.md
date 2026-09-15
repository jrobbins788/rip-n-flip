# Rip N' Flip — Test Credentials

## Admin Account
Used for testing the Admin Panel (`/admin`) — CSV import, card DB management, search lookup.

- **Email:** `admin@flipnrip.com`
- **Password:** `AdminPass123!`
- **Tier:** Admin (email is in `ADMIN_EMAILS` in `backend/.env`)
- **Login URL:** `https://sports-card-bot.preview.emergentagent.com/login`
- Brand has been renamed to **Rip N' Flip** (email kept the same domain for continuity)

## Notes for testing agent
- Admin email is set in `backend/.env` as `ADMIN_EMAILS=admin@flipnrip.com`
- Auth uses JWT in HTTPOnly cookie + bearer token returned in body
- For curl tests use `-c cookies.txt` after login then `-b cookies.txt` for protected endpoints

## eBay Browse API
- Keys NOT yet provided (`EBAY_APP_ID`, `EBAY_CERT_ID` are empty in `.env`)
- All eBay-fallback paths gracefully return empty results when keys missing — this is intentional, not a bug
