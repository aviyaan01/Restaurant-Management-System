# BanglaPOS (বাংলা পিওএস) 🇧🇩

> **Modern, High-Performance, Tablet-First Multi-Restaurant Point of Sale & Management Platform**  
> Tailored specifically for Bangladeshi dining establishments, cafes, and multi-tenant restaurant chains.

---

## 📋 Table of Contents
1. [Overview & Highlights](#-overview--highlights)
2. [The 7 Non-Negotiable Architectural Rules](#-the-7-non-negotiable-architectural-rules)
3. [Technology Stack](#-technology-stack)
4. [Role-Based Access Control (RBAC)](#-role-based-access-control-rbac)
5. [Quick Start & Installation](#-quick-start--installation)
6. [Demo Accounts & Portals](#-demo-accounts--portals)
7. [Core Modules Overview](#-core-modules-overview)
8. [Automated Testing Suite](#-automated-testing-suite)
9. [Project Directory Structure](#-project-directory-structure)
10. [Production Deployment Guide](#-production-deployment-guide)

---

## 🌟 Overview & Highlights

**BanglaPOS** is an end-to-end Restaurant Management and POS application engineered to operate flawlessly on 10-inch touch tablets and desktop browsers. Built with a responsive **Tailwind CSS** frontend, dynamic **HTMX** interactions (zero heavy SPA overhead), and a hardened **Flask/SQLAlchemy** backend, BanglaPOS delivers sub-second POS cart updates, sub-2-second live kitchen display synchronization, exact BDT financial reconciliation, and robust multi-tenant data separation.

- 🪑 **Visual Dining Floor & Table Board**: Live occupancy indicators (Open vs Occupied) with automated 5-second HTMX polling and bulk table generator.
- 🛍️ **Touch-Friendly POS Terminal**: 44px+ touch targets supporting Dine In, Take Away, and Quick Billing with reactive search, item notes, and instant bill previews.
- 🍳 **Kitchen Display System (KDS)**: Real-time FIFO ticket queue ordered oldest-first, wait-time urgency color badges (amber >10 min, red >20 min), and one-tap ticket/item bumping.
- 💳 **Bangladeshi Billing & Payments**: Standard NBR `ROUND_HALF_UP` decimal calculations, support for both Exclusive and Inclusive VAT modes, cover charges, split payments (Cash, bKash, Nagad, Card), and live change-due calculator.
- 🖨️ **Thermal Receipt & KOT Printing**: Pixel-accurate `@media print` layouts for 80mm and 58mm thermal rolls, zero-price-leakage Kitchen Order Tickets (KOT), and browser kiosk print guide.
- 📊 **Finance Cashbook & Analytics Dashboard**: Daily/monthly ledger (sales, raw ingredient market purchases, operating expenses), Day-over-Day comparisons (Today vs Yesterday), Chart.js trends, and Top 5 selling dishes.
- 🔒 **Compliance & Audit Logging**: Immutable audit log viewer with user, action, and date filters; mathematical CSV exports; defense-in-depth security headers; 5-attempt rate-limiting lockout; and self-service onboarding.

---

## 🛡️ The 7 Non-Negotiable Architectural Rules

Every line of code in BanglaPOS adheres strictly to seven foundational rules:

1. **Rule 1: Multi-Tenancy Isolation**  
   Every business entity (`User`, `Category`, `Dish`, `Space`, `Table`, `Order`, `OrderItem`, `Payment`, `FinanceEntry`, `AuditLog`) inherits `TenantMixin` with an indexed `restaurant_id`. Every query explicitly filters by `restaurant_id`. Cross-tenant ID/URL guessing yields a strict **HTTP 404 Not Found** without leaking data existence.
2. **Rule 2: Server-Side Role Gating**  
   All routes enforce permissions on the server using `@role_required(...)`. Client-side hiding is paired with strict server-side blocking (HTTP 403 Forbidden).
3. **Rule 3: Currency Exactness in BDT (৳)**  
   Money is stored as `Numeric(12, 2)` / Python `Decimal`, never floating-point. Rounding uses standard Bangladesh NBR `ROUND_HALF_UP`.
4. **Rule 4: Server-Side Validation**  
   Forms reject negative prices, discounts exceeding menu prices, zero quantities, and invalid phone numbers on the server before database commits.
5. **Rule 5: Comprehensive Audit Logging**  
   Every staff creation, demotion, deactivation, setting change, dish price edit, order cancellation, and manual finance modification is logged to `AuditLog` with user ID, UTC timestamp, IP, and previous vs updated JSON states.
6. **Rule 6: Environment Secrets & Hardened Authentication**  
   Secrets live in environment variables. Login supports dual-identifiers (email or Bangladeshi mobile). 5 consecutive failed logins trigger an automated 15-minute account lockout.
7. **Rule 7: Tablet-First Ergonomics**  
   Every interactive button, tab, and input element satisfies a minimum **44px × 44px** touch target for effortless operation on 10-inch tablets.

---

## 💻 Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend Framework** | Python 3.14+, Flask 3.1 (Application Factory Pattern) |
| **Database & ORM** | PostgreSQL (Production) / SQLite (Local Zero-Config Run), SQLAlchemy 2.0, Flask-Migrate (Alembic) |
| **Authentication & Security** | Flask-Login, Flask-WTF (CSRF), Werkzeug Password Hashing (pbkdf2:sha256), ProxyFix |
| **Frontend Reactive Layer** | HTMX 1.9 (server-driven partial HTML updates without full page reloads) |
| **Styling & Icons** | Tailwind CSS (CDN), responsive utility classes, custom thermal print `@media` rules |
| **Analytics & Charts** | Chart.js 4.4 for dynamic sales trend visualization |
| **Testing Engine** | Pytest 9.2, Flask Test Client (74 automated tests covering all 12 phases) |

---

## 👥 Role-Based Access Control (RBAC)

BanglaPOS provides 4 distinct user roles with tailored interfaces and strict server-side boundaries:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                               BanglaPOS                                 │
└──────┬───────────────────┬───────────────────┬───────────────────┬──────┘
       │                   │                   │                   │
  [ 👑 Owner ]       [ 👔 Manager ]       [ 💳 Cashier ]      [ 🍳 Kitchen ]
       │                   │                   │                   │
  Full Admin Suite    Operations View      Tablet Register     Wall-Mounted KDS
  Settings & Taxes    Menu & Dishes        Dine In / Takeaway  FIFO Ticket Queue
  Staff Management    Tables & Spaces      Cash / bKash Pay    Item Bumping
  Finance Cashbook    Finance & Audit      Thermal Printing    Completed History
  Audit CSV Exports   Orders Directory     Table Occupancy     Wait Urgency Badges
```

| Role | Accessible Modules | Restricted / Blocked |
| :--- | :--- | :--- |
| **Owner** | Full Admin, Dashboard, Staff CRUD, Settings & VAT, Menu, Tables, POS, KDS, Finance Cashbook, Audit Logs, CSV Exports | None |
| **Manager** | Operational Dashboard, Menu, Tables, Spaces, POS, KDS, Finance Cashbook, Audit Logs (View-Only), Orders | Staff Management, Restaurant Profile Settings, Audit CSV Export |
| **Cashier** | Tablet POS Terminal, Orders Directory, Order Detail, Payment Collection, Customer Receipt & KOT Printing, Table Board (View) | Admin Dashboard, Settings, Staff, Menu Management, Finance, Audit, KDS |
| **Kitchen Chef** | Kitchen Display System (KDS), Ticket Bumping, Item Bumping, Order KOT Slip Printing, Completed History | POS Terminal, Order Payment, Admin Dashboard, Finance, Settings, Staff |

---

## 🚀 Quick Start & Installation

### 1. Prerequisites
- Python 3.10 or higher (Python 3.12 / 3.14 recommended)
- Git

### 2. Clone Repository & Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/your-username/Restaurant-Management-System.git
cd Restaurant-Management-System

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat
# Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` (or use the preconfigured default):
```ini
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=dev-pos-secret-bd-2026-very-secure-key

# Database Connection:
# For local zero-config run:
DATABASE_URL=sqlite:///restaurant_pos.db
# For PostgreSQL (production or local Docker):
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/restaurant_pos_db
```

### 5. Seed Demonstration Data
Run the built-in seed utility to create initial restaurant tenants, staff accounts, spaces, tables, dishes, active kitchen tickets, and sample orders:
```bash
python seed_demo.py --reset
```

### 6. Start Development Server
```bash
python run.py
```
Open your web browser and navigate to:  
👉 **http://127.0.0.1:5000** (or **http://localhost:5000**)

---

## 🔑 Demo Accounts & Portals

The seed script (`python seed_demo.py --reset`) sets up two independent restaurant tenants to demonstrate both day-to-day operations and multi-tenant data separation:

### Tenant 1: Kacchi Bhai (Banani) — Primary Restaurant
- **VAT Mode:** 5.00% Exclusive | **BIN:** `123456789-0101`

| Role | Login Identifier | Password | Primary Portal / Purpose |
| :--- | :--- | :--- | :--- |
| **Owner** | `owner@kacchi.com` | `owner123` | [Admin Dashboard & Settings](http://127.0.0.1:5000/admin/) |
| **Manager** | `manager@kacchi.com` | `manager123` | [Operations & Menu Control](http://127.0.0.1:5000/admin/) |
| **Cashier** | `cashier@kacchi.com` | `cashier123` | [Tablet POS Register](http://127.0.0.1:5000/pos/) |
| **Kitchen** | `kitchen@kacchi.com` | `kitchen123` | [Kitchen Display Screen (KDS)](http://127.0.0.1:5000/kitchen/) |

### Tenant 2: Sultan's Feast (Dhanmondi) — Multi-Tenancy Isolation Demo
- **VAT Mode:** 7.50% Inclusive | **BIN:** `987654321-0202`

| Role | Login Identifier | Password | Primary Portal / Purpose |
| :--- | :--- | :--- | :--- |
| **Owner** | `owner@sultans.com` | `owner123` | Dedicated Admin (Independent data & cashbook) |
| **Cashier** | `cashier@sultans.com`| `cashier123` | Dedicated POS (Separate `order_no` sequence) |

---

## 📦 Core Modules Overview

### 1. Self-Service Onboarding & Authentication (`/auth`)
- **Register New Restaurant (`/auth/register`)**: Self-service onboarding creating a restaurant tenant, primary owner, default dining space, starter tables, and instant login redirect.
- **Dual-Identifier Login (`/auth/login`)**: Sign in via email (`owner@kacchi.com`) or 11-digit Bangladeshi mobile number (`01711223301`).
- **Rate-Limiting Lockout**: 5 failed login attempts trigger an automated 15-minute lockout with audit log alert.

### 2. Tablet POS Register (`/pos`)
- **Order Types**: Select between **Dine In** (with visual table selector), **Take Away**, and **Quick Billing**.
- **Reactive HTMX Cart**: Add dishes, step quantities (`+`/`-`), enter special kitchen notes (e.g. *"Extra aloo"*, *"No chili"*), and clear cart without full page reload.
- **Price Snapshots**: When an order is placed, `dish_name_snapshot` and `unit_price_snapshot` are frozen in `order_items`, ensuring historical financial immutability regardless of future dish price edits.
- **Append to Open Orders**: Cashier can easily add additional items to existing open dine-in table orders.
- **Order Cancellation**: Requires owner or manager credentials and a mandatory cancellation reason (audited).

### 3. Kitchen Display System (`/kitchen`)
- **FIFO Chronological Queue**: Active orders ordered strictly oldest-first (`created_at ASC`).
- **Live HTMX Polling**: Auto-refreshes every 2 seconds (`hx-trigger="every 2s"`).
- **Wait Time Urgency Badges**: 
  - 🟢 Normal: < 10 mins
  - 🟡 Warning: 10 - 20 mins (Amber)
  - 🔴 Urgent: > 20 mins (Pulsing Red)
- **Bump Actions**: Start preparing individual dishes or entire tickets (`new` &rarr; `preparing` &rarr; `ready`). Ready orders automatically move to the **History** feed.

### 4. Billing, Split Payments & Change Calculator
- **Calculation Engine**:
  $$\text{Taxable Base} = (\text{Subtotal} - \text{Discount}) + \text{Cover Charge}$$
  - **Exclusive Mode**: $\text{Total} = \text{Taxable Base} + (\text{Taxable Base} \times \text{VAT Rate})$
  - **Inclusive Mode**: $\text{VAT} = \text{Taxable Base} - \frac{\text{Taxable Base}}{1 + \text{VAT Rate}}$, $\text{Total} = \text{Taxable Base}$
- **Split Payments**: Collect partial payment via bKash/Nagad and settle the remainder in Cash.
- **Change Calculator**: Enter cash tendered to calculate exact change due.
- **Paid-Order Lock**: Fully paid orders transition to `paid`, release the dining table back to `open`, create a `FinanceEntry(type='sale')`, and lock against further modifications by cashiers.

### 5. Dining Tables & Live Status Board (`/admin/tables`)
- **Space Management**: Group tables into physical areas (e.g., *Ground Floor*, *AC Dining*, *Rooftop*).
- **Bulk Table Generator**: Generate consecutive tables (e.g. `T-01` to `T-10`) with specified capacity and cover charge in a single action, automatically skipping existing names.
- **Live Floor Status Board**: Auto-refreshes every 5 seconds displaying real-time Open and Occupied counts.
- **Delete Safety Guards**: Tables with active open orders or marked as occupied cannot be deleted.

### 6. Menu & Dish Management (`/admin/dishes`)
- **Categories**: Create, edit, and reorder categories with live dish count indicators.
- **Dishes**: Name, category, BDT price, discount, vegetarian flag (`veg` / `non_veg`), and prep time.
- **Instant Availability Toggle**: One-tap HTMX toggle switches stock availability on the POS in real-time.
- **Soft-Archiving**: Dishes referenced in existing orders cannot be hard-deleted; they are safely archived (`is_archived=True`) to preserve order history while hiding them from future POS catalog views.

### 7. Finance Cashbook & Executive Dashboard (`/admin`)
- **Daily Cashbook (`/admin/finance`)**: Record petty-cash market purchases (mutton, rice, spices) and operating expenses (LP gas, electricity, wages). Automated POS sales entries are strictly read-only.
- **Executive Dashboard (`/admin/`)**: Real-time KPI summary cards comparing Today vs Yesterday for Sales, Paid Orders, Unpaid Orders, Purchases, Expenses, and Net Operating Balance.
- **Top 5 Selling Dishes**: Ranked table displaying portions sold and revenue contribution.
- **Sales Trend Graph**: Chart.js visualization of daily and weekly revenue.

### 8. Thermal Printing (`/pos/orders/<id>/receipt` & `/pos/orders/<id>/kot`)
- **Thermal Receipts**: Optimized for 80mm and 58mm thermal printers with restaurant branding, BIN, itemized snapshots, VAT breakdown, payment details, cash change returned, and Bengali receipt footer.
- **Kitchen Order Ticket (KOT)**: Clean kitchen slip showing Order #, Table, Server, items, and preparation notes with **zero price or currency leakage**.

---

## 🧪 Automated Testing Suite

The repository contains a comprehensive automated test suite with **74 passing tests** across 10 test modules, verifying every requirement, edge case, and architectural constraint:

```bash
# Run the complete test suite
pytest -v

# Run with short test output
pytest -q

# Run specific test modules
pytest tests/test_auth_roles.py -v
pytest tests/test_step7_pos.py -v
pytest tests/test_step8_billing.py -v
pytest tests/test_step9_kitchen.py -v
pytest tests/test_step11_finance.py -v
pytest tests/test_step12_hardening.py -v
```

### Test Suite Overview:
- `tests/test_auth_roles.py`: Dual-identifier login, 5-attempt lockout, role-based redirects, self-service registration.
- `tests/test_step4_settings_staff.py`: Restaurant profile update, staff CRUD, HTMX active toggle, last-owner demotion guard.
- `tests/test_step5_menu.py`: Category CRUD, dish validation (negative price rejection, discount <= price), HTMX availability toggle, soft-archiving.
- `tests/test_step6_tables.py`: Space CRUD, table CRUD, bulk generator (1-100 batch limit), occupancy service, delete safety invariants.
- `tests/test_step7_pos.py`: Touch cart, sequential `order_no`, price snapshots, order append, manager order cancellation.
- `tests/test_step8_billing.py`: 17 pure unit and integration tests covering NBR rounding, inclusive/exclusive VAT, split payments, change due, paid-order immutability.
- `tests/test_step9_kitchen.py`: FIFO queue ordering, wait time urgency tiers (<10m, 10-20m, >20m), ticket/item bumping, multi-tenant ticket isolation.
- `tests/test_step10_printing.py`: 80mm and 58mm customer receipts, zero-price-leakage KOT slip, cross-tenant 404 URL guessing.
- `tests/test_step11_finance.py`: Manual finance CRUD, read-only sales lock, exact financial reconciliation, day-over-day comparisons, top 5 dishes.
- `tests/test_step12_hardening.py`: 5-attempt account lockout, role boundaries, cross-tenant 404 URL guessing across all modules, immutable audit log, CSV export reconciliation, security headers.

---

## 📁 Project Directory Structure

```text
Restaurant-Management-System/
├── .env                              # Local environment variables
├── .env.example                      # Template for environment variables
├── config.py                         # Environment-driven configuration classes
├── requirements.txt                  # Pinned production and development dependencies
├── run.py                            # Development server entry point
├── seed_demo.py                      # Multi-tenant demo database seeder (--reset support)
├── track.md                          # Phase 1 build tracker and specifications
├── README.md                         # Comprehensive project documentation
├── app/
│   ├── __init__.py                   # Application Factory (create_app), Security Headers, ProxyFix
│   ├── extensions.py                 # SQLAlchemy, Migrate, LoginManager, CSRF instances
│   ├── cli.py                        # Custom Flask CLI commands (create-owner, create-staff)
│   ├── models/                       # Multi-tenant SQLAlchemy Data Models
│   │   ├── base.py                   # TenantMixin (id, restaurant_id, created_at, updated_at)
│   │   ├── restaurant.py             # Restaurant tenant root entity
│   │   ├── user.py                   # User entity with Werkzeug password hashing and RBAC
│   │   ├── menu.py                   # Category and Dish entities with soft-archive
│   │   ├── table.py                  # Space and Table entities with occupancy status
│   │   ├── order.py                  # Order and OrderItem (with historical price snapshots)
│   │   ├── payment.py                # Payment records supporting split payment methods
│   │   ├── finance.py                # FinanceEntry cashbook (sales, purchases, expenses)
│   │   └── audit.py                  # Immutable AuditLog model
│   ├── forms/                        # Flask-WTF Forms with Server-Side Validation
│   │   ├── auth.py                   # LoginForm and RegisterForm
│   │   ├── settings.py               # RestaurantSettingsForm
│   │   ├── staff.py                  # StaffCreateForm and StaffEditForm
│   │   ├── menu.py                   # CategoryForm and DishForm
│   │   ├── table.py                  # SpaceForm, TableForm, BulkTableForm
│   │   ├── order.py                  # OrderCancelForm and OrderFilterForm
│   │   ├── payment.py                # OrderPaymentForm
│   │   ├── finance.py                # FinanceEntryForm and FinanceFilterForm
│   │   └── audit.py                  # AuditFilterForm
│   ├── routes/                       # Modular Flask Blueprints
│   │   ├── main.py                   # Home overview and /health database probe
│   │   ├── auth.py                   # Login, Logout, and Self-Service Register routes
│   │   ├── admin.py                  # Dashboard, Settings, Staff, Menu, Tables, Finance, Audit
│   │   ├── pos.py                    # Touch register, Cart HTMX endpoints, Orders, Receipts
│   │   └── kitchen.py                # Kitchen display system (KDS), Ticket feed, Bump actions
│   ├── services/                     # Reusable Domain Business Logic
│   │   ├── billing_service.py        # NBR bill calculation, change due, payment recording
│   │   ├── order_service.py          # POS order creation, append items, cancellation
│   │   ├── kitchen_service.py        # KDS active tickets, urgency calculations, bumping
│   │   ├── table_service.py          # set_table_status, table/space delete safety checks
│   │   ├── finance_service.py        # Cashbook CRUD, dashboard reconciliation metrics
│   │   ├── audit_service.py          # Audit log query engine and CSV exporter
│   │   └── export_service.py         # Orders and Finance CSV exporters with totals reconciliation
│   ├── utils/                        # Helpers and Decorators
│   │   ├── decorators.py             # @role_required decorator
│   │   └── audit.py                  # Reusable log_audit helper
│   └── templates/                    # Jinja2 Templates with Tailwind CSS & HTMX
│       ├── base.html                 # Main layout shell with navbar, flash alerts, CSRF header
│       ├── home.html                 # Landing page
│       ├── auth/                     # login.html, register.html
│       ├── admin/                    # layout.html, dashboard.html, settings.html
│       │   ├── staff/                # index.html, form.html, _status_cell.html
│       │   ├── menu/                 # categories.html, dishes.html, forms
│       │   ├── tables/               # board.html, index.html, bulk_form.html, partials
│       │   ├── finance/              # index.html, form.html
│       │   └── audit/                # index.html
│       ├── pos/                      # terminal.html, _catalog.html, _cart.html
│       │   ├── orders/               # index.html, detail.html, pay.html
│       │   └── printing/             # receipt.html (80mm/58mm), kot.html
│       ├── kitchen/                  # display.html, _ticket_grid.html, _history_list.html
│       └── errors/                   # 403.html, 404.html, 500.html
└── tests/                            # Automated Pytest Suite (74 tests)
```

---

## 🚀 Production Deployment Guide

### 1. Production Architecture
```
Internet / Mobile Tablet
          │  HTTPS (Port 443)
          ▼
   [ Nginx Reverse Proxy ]
   • SSL Termination (Let's Encrypt)
   • Static Assets Caching & Compression
   • WebSocket / HTMX Streaming
          │  HTTP (Unix Socket or 127.0.0.1:8000)
          ▼
   [ Gunicorn WSGI Server ]
   • Worker Processes: (2 * CPUs) + 1
   • Preload App & ProxyFix Middleware
          │
          ▼
  [ PostgreSQL 16+ Database ]
   • Connection Pool: SQLAlchemy Engine
   • Nightly Encrypted Backups
```

### 2. Gunicorn Configuration
Create systemd service file `/etc/systemd/system/banglapos.service`:
```ini
[Unit]
Description=BanglaPOS Gunicorn Application Server
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/banglapos
Environment="PATH=/var/www/banglapos/venv/bin"
EnvironmentFile=/var/www/banglapos/.env
ExecStart=/var/www/banglapos/venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --timeout 60 \
    --access-logfile /var/log/banglapos/access.log \
    --error-logfile /var/log/banglapos/error.log \
    "app:create_app()"

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3. Nginx Reverse Proxy Configuration
Create `/etc/nginx/sites-available/banglapos`:
```nginx
server {
    listen 80;
    server_name pos.yourrestaurant.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name pos.yourrestaurant.com;

    ssl_certificate /etc/letsencrypt/live/pos.yourrestaurant.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/pos.yourrestaurant.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # HTMX / Event Stream support
        proxy_buffering off;
        proxy_read_timeout 120s;
    }
}
```

### 4. Database Backups & Recovery
Set up automated daily encrypted PostgreSQL backups via cron:
```bash
# Daily Backup Command:
pg_dump -U postgres -d restaurant_pos_db -Fc -f "/var/backups/db/pos_$(date +\%F).dump"

# Restore Command:
pg_restore -U postgres -d restaurant_pos_db --clean --no-owner "/var/backups/db/pos_2026-11-12.dump"
```

---

## 📄 License & Credits
- **Developed by:** Google Deepmind Antigravity Team
- **Target Market:** Bangladesh Food & Beverage Industry
- **Default Currency:** BDT (৳) &bull; Standard NBR VAT Ready
- **License:** Proprietary / Commercial License &copy; 2026

