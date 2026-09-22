# Waste2Worth – Circular Economy Marketplace

A fully functional Flask + SQLite prototype for connecting businesses that generate reusable/recyclable materials with buyers, recyclers and upcyclers.

## Features

- Customer Gmail signup/login with persistent SQLite storage and hashed passwords.
- Separate admin login.
- Admin dashboard: users, stores, listings, orders and reports.
- Admin can blacklist/unblacklist customer sellers; active listings are blocked when a seller is blacklisted.
- Customer dashboard with Sell / Buy / Orders / Impact views.
- Store onboarding with unique W2W Store ID and printable owner identity card.
- Seller item listings with picture upload, category, quantity, unit, price and description.
- Marketplace search and filtering.
- Buy workflow that checks stock and prevents self-purchase.
- Order status updates for sellers.
- Buyer reviews/ratings and listing reports.
- Sustainability/circularity impact dashboard.
- Responsive green/yellow theme.

## Run in VS Code

1. Open this folder in VS Code.
2. Open Terminal.
3. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\\Scripts\\Activate.ps1
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Start the app:

```bash
python app.py
```

6. Open http://127.0.0.1:5000

The SQLite database is created automatically in `instance/waste2worth.db`.

## Admin credentials for this prototype

- ID: `rahulssharma3009@gmail.com`
- Password: `Rahul@3009`

For a deployed/public version, change these credentials and `W2W_SECRET_KEY` via environment variables.

## Customer test flow

1. Create a Gmail account from Customer Sign Up.
2. Log in.
3. Create a Store ID.
4. Add a listing with an optional image.
5. Open Buy from another customer account and place an order.
6. From the seller account, update the order status.
7. From the buyer account, review the completed order.
8. Use Admin > Reports or Sellers to review platform activity.

## Notes

This is a competition/demo prototype. It does not process real payments, perform real GST/licence verification, or certify environmental claims. For production, add real payment integration, identity/document verification, CSRF protection, stronger authorization policies, audit logs, HTTPS, external object storage, database migrations, rate limiting and compliance workflows.
