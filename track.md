# Restaurant POS: Build Tracker

## Project Summary
- Stack: Flask, PostgreSQL, SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, HTMX, Tailwind
- Scope: Phase 1 MVP (one outlet per restaurant, multi-restaurant data separation)
- Last updated: 2026-11-11
- Current step: Step 10

## Non-Negotiable Rules
1. Every business table has restaurant_id and every query filters by it.
2. Role checks happen on the server for every route.
3. Money is BDT (৳), stored as Numeric/integer, never float.
4. Server-side validation; reject negative prices and quantities.
5. Financial and staff changes are written to AuditLog.
6. Secrets live in environment variables.
7. UI works on a 10-inch tablet and desktop; touch targets at least 44px.

## Progress Overview

| Step | Name | Status | Date done | Commit |
| :---: | :--- | :---: | :---: | :---: |
| 1 | Project setup | Done | 2026-11-11 | |
| 2 | Database models | Done | 2026-11-11 | |
| 3 | Authentication and roles | Done | 2026-11-11 | |
| 4 | Settings and staff | Done | 2026-11-11 | |
| 5 | Menu | Done | 2026-11-11 | |
| 6 | Tables | Done | 2026-11-11 | |
| 7 | POS screen | Done | 2026-11-11 | |
| 8 | Billing and payment | Done | 2026-11-11 | |
| 9 | Kitchen display | Done | 2026-11-11 | |
| 10 | Receipt and KOT printing | In progress | | |
| 11 | Finance and dashboard | Not started | | |
| 12 | Audit log, hardening and deploy | Not started | | |

## Step Details

### Step 1: Project Setup
- **Goal:** Initialize a scalable Flask application using the application factory pattern, modular blueprints, Tailwind CSS CDN, HTMX, and database health verification.
- **Checklist:**
  - [x] Application factory pattern (`create_app`)
  - [x] Blueprints registered: `auth`, `admin`, `pos`, `kitchen`, `main`
  - [x] Environment configuration loaded from `.env` (`SECRET_KEY`, `DATABASE_URL`, `FLASK_DEBUG`)
  - [x] Database connection setup with SQLAlchemy and Flask-Migrate
  - [x] Base layout (`base.html`) with Tailwind CDN, HTMX, flash alerts, and CSRF token header
  - [x] `/health` route confirming PostgreSQL database connectivity via `SELECT 1`
  - [x] Dependency management (`requirements.txt`) and `.gitignore`
- **Files touched:**
  - `.env`
  - `.env.example`
  - `.gitignore`
  - `config.py`
  - `requirements.txt`
  - `run.py`
  - `app/__init__.py`
  - `app/extensions.py`
  - `app/routes/__init__.py`
  - `app/routes/main.py`
  - `app/routes/auth.py`
  - `app/routes/admin.py`
  - `app/routes/pos.py`
  - `app/routes/kitchen.py`
  - `app/templates/base.html`
  - `app/templates/home.html`
- **Manual test checklist:**
  - [x] App starts on `http://127.0.0.1:5000`
  - [x] Base layout renders with Tailwind CSS and responsive container
  - [x] HTMX database health check button queries `/health` without reload
  - [x] Direct `/health` endpoint responds with 200/503 JSON payload
  - [x] All blueprint routes navigate without 404 errors
- **Notes / decisions:**

---

### Step 2: Database Models
- **Goal:** Construct multi-tenant PostgreSQL data models inheriting `TenantMixin`, implement historical price snapshots, and generate the initial Alembic migration.
- **Checklist:**
  - [x] Models: `Restaurant`, `User`, `Category`, `Dish`, `Space`, `Table`, `Order`, `OrderItem`, `Payment`, `FinanceEntry`, `AuditLog`
  - [x] `TenantMixin` enforcing `id`, `restaurant_id` (indexed foreign key), `created_at`, `updated_at` (Rule 1)
  - [x] `OrderItem` snapshots: `dish_name_snapshot` and `unit_price_snapshot` for financial immutability
  - [x] Currency stored as `Numeric(12, 2)` in BDT (৳) (Rule 3)
  - [x] Server-side check constraints: non-negative prices, discounts, and positive quantities (Rule 4)
  - [x] Unique constraints for tenant-scoped emails (`uq_user_restaurant_email`) and order numbers (`uq_order_restaurant_order_no`)
  - [x] Initial migration environment and script generated
- **Files touched:**
  - `app/models/__init__.py`
  - `app/models/base.py`
  - `app/models/restaurant.py`
  - `app/models/user.py`
  - `app/models/menu.py`
  - `app/models/table.py`
  - `app/models/order.py`
  - `app/models/payment.py`
  - `app/models/finance.py`
  - `app/models/audit.py`
  - `app/__init__.py`
  - `migrations/alembic.ini`
  - `migrations/env.py`
  - `migrations/versions/6405a80f1e86_create_initial_pos_models.py`
- **Manual test checklist:**
  - [x] All 11 models register in SQLAlchemy metadata
  - [x] Migration script contains table creation, foreign keys with cascade, and indexes
  - [x] Verification query inspects table names in engine
  - [x] Foreign key constraints enforce tenant ownership
- **Notes / decisions:**

---

### Step 3: Authentication and Roles
- **Goal:** Implement secure dual-identifier login, rate-limited account lockout, server-side RBAC with 403 gating, session security, and an interactive owner onboarding CLI.
- **Checklist:**
  - [x] Dual-identifier login (email or Bangladeshi phone) with Werkzeug password hashing (min 8 characters)
  - [x] Rate limiting and temporary lockout after 5 consecutive failures (`failed_login_count`, `locked_until`)
  - [x] Cookie hardening (`HttpOnly`, `SameSite=Lax`, inactivity session timeout)
  - [x] Safe logout clearing session and logging audit trail
  - [x] Reusable `@role_required` decorator returning HTTP 403 on server for unauthorized roles (Rule 2)
  - [x] `before_request` hook terminating deactivated user sessions immediately
  - [x] Role-based post-login redirects (owner/manager -> admin, cashier -> pos, kitchen -> kds)
  - [x] `flask create-owner` CLI command prompting for secure credentials (Rule 6)
  - [x] Placeholder landing screens for admin, pos, kitchen, and role-aware 403 error page
  - [x] Automated test suite verifying full auth workflow (`tests/test_auth_roles.py`)
- **Files touched:**
  - `config.py`
  - `app/__init__.py`
  - `app/cli.py`
  - `app/forms/__init__.py`
  - `app/forms/auth.py`
  - `app/routes/auth.py`
  - `app/routes/admin.py`
  - `app/routes/pos.py`
  - `app/routes/kitchen.py`
  - `app/utils/__init__.py`
  - `app/utils/decorators.py`
  - `app/utils/audit.py`
  - `app/templates/base.html`
  - `app/templates/auth/login.html`
  - `app/templates/errors/403.html`
  - `app/templates/admin/dashboard.html`
  - `app/templates/admin/owner_only.html`
  - `app/templates/pos/terminal.html`
  - `app/templates/kitchen/display.html`
  - `tests/test_auth_roles.py`
- **Manual test checklist:**
  - [x] Incorrect password reduces remaining attempts and rejects login
  - [x] 5 consecutive failures trigger 15-minute account lockout
  - [x] Correct password during lockout window remains blocked
  - [x] Successful login resets failure counters and redirects by role
  - [x] Manager attempting `/admin/owner-only` receives 403 Forbidden
  - [x] Cashier attempting `/admin/` receives 403 Forbidden
  - [x] Kitchen staff attempting `/pos/` receives 403 Forbidden
  - [x] Deactivated user is logged out immediately on next request
- **Notes / decisions:**

---

### Step 4: Settings and Staff
- **Goal:** Build owner-only restaurant profile/tax settings management and staff CRUD with role assignments, active toggles, and audit logging.
- **Checklist:**
  - [x] Restaurant profile settings page (name, address, phone, BIN, VAT rate, price mode inclusive/exclusive, receipt footer)
  - [x] Setting changes apply strictly to new orders (existing order snapshots unchanged)
  - [x] Staff management CRUD (list, create, edit, role dropdown: owner/manager/cashier/kitchen)
  - [x] Instant active/deactive toggle for staff
  - [x] Owner-only route enforcement on settings and staff actions
  - [x] AuditLog integration tracking every staff and settings modification with user and timestamp (Rule 5)
- **Files touched:**
  - `app/forms/__init__.py`
  - `app/forms/settings.py`
  - `app/forms/staff.py`
  - `app/routes/admin.py`
  - `app/templates/base.html`
  - `app/templates/admin/dashboard.html`
  - `app/templates/admin/settings.html`
  - `app/templates/admin/staff/index.html`
  - `app/templates/admin/staff/_status_cell.html`
  - `app/templates/admin/staff/form.html`
  - `tests/test_step4_settings_staff.py`
- **Manual test checklist:**
  - [x] Owner can update restaurant profile, BIN, and VAT rate
  - [x] Price mode change does not alter past completed orders
  - [x] Owner creates new staff with role selection
  - [x] Manager or cashier attempting to open staff settings gets 403
  - [x] Deactivating staff prevents them from logging in
  - [x] AuditLog table records staff creation, role change, and profile update
- **Notes / decisions:**

---

### Step 5: Menu Management
- **Goal:** Build category and dish CRUD with live HTMX availability toggles, search/filtering, pagination, and role-based menu controls.
- **Checklist:**
  - [x] Category CRUD with automatic dish counter
  - [x] Dish CRUD (name, category, price in BDT Numeric, discount, veg type, prep time)
  - [x] Instant dish availability toggle via HTMX
  - [x] Soft-archive for dishes referenced in existing orders
  - [x] Menu search, category filter, and pagination
  - [x] Admin sidebar navigation showing permitted links by role
- **Files touched:**
  - `app/forms/__init__.py`
  - `app/forms/menu.py`
  - `app/routes/admin.py`
  - `app/templates/admin/layout.html`
  - `app/templates/admin/dashboard.html`
  - `app/templates/admin/settings.html`
  - `app/templates/admin/staff/index.html`
  - `app/templates/admin/staff/form.html`
  - `app/templates/admin/menu/categories.html`
  - `app/templates/admin/menu/category_form.html`
  - `app/templates/admin/menu/dishes.html`
  - `app/templates/admin/menu/dish_form.html`
  - `app/templates/admin/menu/_dish_availability_cell.html`
  - `tests/test_step5_menu.py`
- **Manual test checklist:**
  - [x] Create categories and assign dishes
  - [x] Toggle dish availability via HTMX button without full page reload
  - [x] Attempting negative price or discount is rejected on server
  - [x] Deleting an ordered dish archives it instead of foreign-key crash
  - [x] Search bar and filter filter menu items correctly
- **Notes / decisions:**

---

### Step 6: Tables and Dining Spaces
- **Goal:** Provide space and table management with bulk table generation, visual live status board, and table occupancy service.
- **Checklist:**
  - [x] Space CRUD (e.g., Ground Floor, AC Dining, Rooftop)
  - [x] Table CRUD (name, capacity, cover charge, status open/occupied)
  - [x] Bulk table creation tool (e.g. create tables T-01 through T-10 in one action)
  - [x] Live table status board with open vs occupied indicators
  - [x] `set_table_status(table_id, status)` service method
- **Files touched:**
  - `app/forms/table.py`
  - `app/forms/__init__.py`
  - `app/models/table.py`
  - `app/routes/admin.py`
  - `app/routes/pos.py`
  - `app/services/__init__.py`
  - `app/services/table_service.py`
  - `app/templates/base.html`
  - `app/templates/admin/layout.html`
  - `app/templates/admin/spaces/index.html`
  - `app/templates/admin/spaces/form.html`
  - `app/templates/admin/tables/index.html`
  - `app/templates/admin/tables/board.html`
  - `app/templates/admin/tables/_board_grid.html`
  - `app/templates/admin/tables/_table_status_card.html`
  - `app/templates/admin/tables/form.html`
  - `app/templates/admin/tables/bulk_form.html`
  - `tests/test_step6_tables.py`
- **Manual test checklist:**
  - [x] Create spaces and assign tables
  - [x] Bulk generate 10 tables and verify consecutive names
  - [x] Visual status updates when table status changes
  - [x] Cover charge applies correctly according to table setting
- **Notes / decisions:**

---

### Step 7: POS Screen & Order Management
- **Goal:** Develop touch-first POS register supporting Dine In, Take Away, and Quick Billing, reactive cart via HTMX, and order creation with snapshots.
- **Checklist:**
  - [x] POS mode selection: Dine In, Take Away, Quick Billing
  - [x] Reactive POS cart via HTMX with 44px tablet touch targets
  - [x] Place order with sequential tenant `order_no`
  - [x] Freeze `dish_name_snapshot` and `unit_price_snapshot` in `OrderItem`
  - [x] Append items to open Dine In table orders
  - [x] Order list and order detail modal/drawer
  - [x] Order cancellation requiring mandatory reason and audit log
- **Files touched:**
  - `app/forms/order.py`
  - `app/forms/__init__.py`
  - `app/services/order_service.py`
  - `app/services/__init__.py`
  - `app/routes/pos.py`
  - `app/templates/base.html`
  - `app/templates/admin/layout.html`
  - `app/templates/pos/terminal.html`
  - `app/templates/pos/_catalog.html`
  - `app/templates/pos/_cart.html`
  - `app/templates/pos/orders/index.html`
  - `app/templates/pos/orders/detail.html`
  - `tests/test_step7_pos.py`
- **Manual test checklist:**
  - [x] Add items to cart on 10-inch tablet emulation
  - [x] Submit Dine In order: verifies table marked occupied and order created
  - [x] Check order_items table in database: snapshots match dish state
  - [x] Add extra item to existing open table order
  - [x] Cancel order: requires cancellation reason and releases table
- **Notes / decisions:**

---

### Step 8: Billing, Split Payments & Finance Automation
- **Goal:** Implement exact BDT bill calculation engine, multi-method payment recording (Cash, bKash, Nagad, Card, Split), change calculation, and paid-order locking.
- **Checklist:**
  - [x] Bill calculation service (inclusive vs exclusive VAT, discounts, cover charge)
  - [x] Payment recording supporting Cash, bKash, Nagad, Card
  - [x] Split payment across multiple payment methods
  - [x] Cash payment change due calculator
  - [x] Automatic `FinanceEntry` creation of type `sale` upon full payment
  - [x] Immutability lock preventing edits to paid orders
  - [x] Pytest unit test suite for tax and split-payment edge cases
- **Files touched:**
  - `app/services/billing_service.py`
  - `app/services/order_service.py`
  - `app/services/__init__.py`
  - `app/forms/payment.py`
  - `app/forms/__init__.py`
  - `app/routes/pos.py`
  - `app/templates/pos/orders/pay.html`
  - `app/templates/pos/orders/detail.html`
  - `app/templates/pos/orders/index.html`
  - `tests/test_step8_billing.py`
  - `requirements.txt`
- **Manual test checklist:**
  - [x] Exclusive VAT adds configured percentage to subtotal
  - [x] Inclusive VAT computes correct embedded VAT without increasing total
  - [x] Record partial bKash payment + remaining in Cash
  - [x] Change due computes correctly for round cash amounts
  - [x] Confirm order status transitions to 'paid' and table is freed
  - [x] Attempting to edit a paid order is blocked by server
- **Notes / decisions:**

---

### Step 9: Kitchen Display System (KDS)
- **Goal:** Deliver a high-contrast, touch-optimized KDS screen with chronological ticket ordering, item bumping, sub-2-second HTMX updates, and completed history.
- **Checklist:**
  - [x] Live ticket display ordered oldest first
  - [x] Action buttons: "Start Preparing" and "Mark Ready" per ticket or item
  - [x] Live refresh under 2 seconds via HTMX polling or SSE
  - [x] Visual indicators for wait times (>10 mins warning, >20 mins urgent)
  - [x] History tab for recently completed orders
- **Files touched:**
  - `app/services/kitchen_service.py`
  - `app/services/__init__.py`
  - `app/routes/kitchen.py`
  - `app/templates/kitchen/display.html`
  - `app/templates/kitchen/_ticket_grid.html`
  - `app/templates/kitchen/_history_list.html`
  - `tests/test_step9_kitchen.py`
- **Manual test checklist:**
  - [x] New POS order appears on KDS within 2 seconds
  - [x] Chef bumps ticket to 'preparing', status updates in DB
  - [x] Chef marks ticket 'ready', ticket moves to completed history
  - [x] Test high contrast and 44px tap targets on tablet view
- **Notes / decisions:**

---

### Step 10: Receipt and KOT Printing
- **Goal:** Generate pixel-accurate 80mm and 58mm thermal receipt layouts and kitchen order tickets (KOT) with browser print integration.
- **Checklist:**
  - [ ] 80mm and 58mm thermal receipt layouts
  - [ ] Receipt content: Restaurant Name, Address, Phone, BIN, Order #, Date/Time, Itemized lines, VAT breakdown, Payment method, and Bengali receipt footer
  - [ ] KOT slip layout: Order #, Table #, Type, Waiter/Cashier, Items with item notes, Timestamp
  - [ ] Dedicated one-tap print buttons on POS and KDS
- **Files touched:**
- **Manual test checklist:**
  - [ ] [ ] Print preview on 80mm roll matches layout width without horizontal overflow
  - [ ] [ ] Print preview on 58mm roll wraps text cleanly
  - [ ] [ ] BIN number and VAT breakdown display accurately on customer receipt
  - [ ] [ ] KOT prints only kitchen-relevant items and kitchen notes
- **Notes / decisions:**

---

### Step 11: Finance Cashbook & Analytics Dashboard
- **Goal:** Implement daily operational finance tracking (sales, market purchases, operating expenses) and high-level management analytics.
- **Checklist:**
  - [ ] Finance entries CRUD for purchases and expenses with categorization
  - [ ] Date-range filters and daily/monthly income vs expense totals
  - [ ] Analytics dashboard: Gross sales, Net sales, VAT collected, Order count
  - [ ] Day-over-day comparison cards (Today vs Yesterday)
  - [ ] Top 5 selling dishes table
  - [ ] Automated tests verifying financial totals reconcile exactly
- **Files touched:**
- **Manual test checklist:**
  - [ ] [ ] Record daily kitchen market purchase: balance updates correctly
  - [ ] [ ] Filter finance entries by date range
  - [ ] [ ] Confirm sales totals on dashboard reconcile 100% with paid orders
  - [ ] [ ] Top 5 dishes reflect actual quantity sold
- **Notes / decisions:**

---

### Step 12: Audit Log, Hardening & Production Deployment
- **Goal:** Complete compliance audit logging with CSV exports, security hardening, automated test regression, database backup procedures, and deployment guide.
- **Checklist:**
  - [ ] Dedicated Audit Log viewer page with user, action, and date filters
  - [ ] CSV export for audit logs and financial records
  - [ ] Security hardening review (CSRF, XSS, headers, SQL injection checks)
  - [ ] Automated regression test suite passing 100%
  - [ ] Database backup and restore verification scripts (`pg_dump`, `pg_restore`)
  - [ ] Production deployment guide (Gunicorn, Nginx, PostgreSQL, systemd / Docker)
- **Files touched:**
- **Manual test checklist:**
  - [ ] [ ] Staff and financial changes display in audit log with user and timestamp
  - [ ] [ ] Export audit log to CSV and verify format
  - [ ] [ ] Run full test suite: all unit and integration tests pass
  - [ ] [ ] Execute database backup and restore test to secondary database
- **Notes / decisions:**

---

## Phase 1 Definition of Done
- [ ] Works on tablet and desktop browser
- [ ] Each acceptance criterion passes a manual test
- [ ] Role permissions and restaurant data separation verified with two test restaurants
- [ ] Financial changes record user and time
- [ ] Code committed and documented

## Open Decisions
- [ ] Can managers edit dish prices, or only toggle availability?
- [ ] Which thermal printer model will the pilot restaurant use?
- [ ] Pilot restaurant confirmed?
- [ ] Hosting provider chosen?
- [ ] VAT and invoice rules confirmed for Bangladesh?

## Later Phases (not now)
- **Phase 2:** delivery and pick up, QR ordering, online payment gateway, inventory, reports, offline mode, PIN quick switch, thermal ESC/POS printing.
- **Phase 3:** loyalty, full accounting, NBR compliance, multi-outlet, granular permissions, add-ons and combos.

## Change Log

| Date | Step | What changed | Commit |
| :---: | :---: | :--- | :---: |
| 2026-11-11 | 1 - 3 | Initialized Flask app factory, PostgreSQL models, Alembic migrations, dual-identifier auth, RBAC, lockout, and CLI | |
| 2026-11-11 | 4 | Owner-only settings page, staff CRUD with search & pagination, HTMX active toggle, last owner protection | |
| 2026-11-11 | 5 | Category and dish management, BDT pricing validation, HTMX availability toggle, soft-archiving, role-gated admin sidebar shell | |
| 2026-11-11 | 6 | Space & table CRUD, bulk generator, set_table_status service, delete guards, live HTMX board | |
| 2026-11-11 | 7 | Tablet POS register, HTMX cart, sequential tenant order_no, price snapshots, order directory & cancellation | |
| 2026-11-11 | 8 | NBR-compliant bill calculation, multi-method/split payments, cash change calculator, paid-order locking and finance automation | |
| 2026-11-11 | 9 | Real-time Kitchen Display System (KDS), FIFO queue, wait urgency badges, ticket/item bumping, and history feed | |

