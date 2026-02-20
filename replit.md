# Trendyol Order Manager

## Overview

This Flask-based web application integrates with the Trendyol e-commerce platform API to manage and track supplier orders. It provides a web interface for viewing, filtering, and managing orders, including functionality for querying orders by order number, status, and date range. A key feature is the Invoice JSON generator for Romanian invoicing systems and automated invoice uploads to Trendyol. The application aims to streamline order and invoice management for Trendyol suppliers.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture

The frontend uses server-side rendered HTML templates with Bootstrap 5 for styling and Flatpickr for date picking, following a traditional multi-page application (MPA) approach. It features tab navigation for "All Orders," "Without Invoice," "SmartBill Invoices," "Upload to Trendyol," and "Produse Trendyol." UI elements include responsive tables, order/product search and filters (order number, SKU with client-side filtering, date range, multi-select status, barcode, approval status), pagination, and visual indicators for invoice status. The SKU filter searches across all order pages for matching merchantSku or barcode values. Specific functionalities include an "Invoice JSON" generator for Romanian format, direct PDF download from SmartBill, automated invoice upload to Trendyol, and bulk actions for sending invoices to SmartBill and uploading to Trendyol. The "Products" tab displays all Trendyol products with detailed information.

### Backend Architecture

The application is built with Flask, employing a service layer pattern with `TrendyolService` and `SmartBillService` for API communication. User authentication is handled by Flask-Login with per-user encrypted credentials stored in an SQLite database, using Werkzeug for password hashing and Fernet for API credential encryption.

**Invoice Data Isolation:**
Each user has their own invoice data, completely isolated from other users. The `order_invoices` table includes a `user_id` foreign key that links invoices to specific users, with a unique constraint on (user_id, order_id) ensuring one invoice per order per user. All invoice operations (create, read, update, delete) are automatically filtered by the current user's ID, preventing cross-user data access. Foreign key constraints with CASCADE delete ensure invoice cleanup when users are removed. Admin users can view all invoices from all users in the admin panel with user attribution displayed.

**Key API Endpoints:**
- `/login`, `/logout`: User authentication.
- `/`, `/api/orders`, `/api/products`, `/api/shipment-packages`: Core order and product management.
- `/api/smartbill/series`, `/api/smartbill/invoice/pdf`: SmartBill integration for invoice data and PDF downloads.
- `/api/postal-code/<postal_code>`: Romanian postal code lookup via scraping `coduripostale.net`.
- `/api/upload-smartbill-invoice-to-trendyol`: Automated upload of SmartBill invoices to Trendyol.
- `/api/bulk-send-to-smartbill`, `/api/bulk-upload-to-trendyol`: Bulk processing for invoice creation and upload.

**Features:**
- **User Authentication**: Secure login with encrypted user and API credentials.
- **Multi-Status Filtering**: Allows filtering orders by multiple statuses with combined API calls and pagination.
- **Invoice JSON Generation**: Generates Romanian-formatted invoice JSON with postal code lookup and SmartBill warehouse integration (`useStock`, `warehouseName`).
- **Automated Invoice Upload**: Downloads SmartBill PDFs and uploads them to Trendyol. PDFs are stored in `static/invoices/` directory so Trendyol can download them when needed (PDFs are NOT deleted after upload to prevent "Not Found" errors).
- **Automatic Storage Management**: Auto-cleanup feature deletes invoice PDFs older than 30 days to prevent storage overflow. Runs automatically during upload operations.
- **Bulk Processing**: Batch creation of invoices in SmartBill and bulk uploading of generated invoices to Trendyol with progress tracking modals, designed with error resilience. Bulk operations respect current UI filters (status, date range, order number) for precise control.

### Configuration Management

Environment variables loaded via `python-dotenv` manage configurations such as `SESSION_SECRET`, `ENCRYPTION_KEY`, `TRENDYOL_API_KEY`, `TRENDYOL_API_SECRET`, `TRENDYOL_SUPPLIER_ID`, `SMARTBILL_API_TOKEN`, `SMARTBILL_EMAIL`, `SMARTBILL_COMPANY_CIF`, and `SMARTBILL_GESTIUNE`. Per-user credentials are encrypted and stored in the database.

### Security Design

User authentication uses Flask-Login with PBKDF2-hashed passwords and Fernet-encrypted API credentials. `SESSION_SECRET` and `ENCRYPTION_KEY` are critical environment variables. All API endpoints require authentication. API calls to Trendyol and SmartBill use Basic Authentication with Base64-encoded credentials. Credential validation ensures all required API keys are present before requests.

## External Dependencies

### Third-Party APIs

-   **Trendyol Supplier API**: Used for fetching orders (`/order/sellers/{sellerId}/orders`) and products (`/suppliers/{supplierId}/products`). Uses HTTP Basic Authentication. Supports filtering and pagination. Date filtering uses Romanian timezone.
-   **SmartBill Cloud API**: Integrates for invoice PDF download (`/invoice/pdf`) and series information (`/series`). Uses HTTP Basic Authentication (email + API token).
-   **coduripostale.net Website**: Scraped using BeautifulSoup4 for Romanian postal code lookup to auto-fill invoice addresses.

### Python Libraries

-   **Flask**: Web framework.
-   **Flask-Login**: User authentication.
-   **requests**: HTTP client.
-   **cryptography**: Fernet encryption.
-   **python-dotenv**: Environment variable management.

### Frontend Libraries (CDN-based)

-   **Bootstrap 5.3.0**: CSS framework.
-   **Flatpickr**: Date picker component.

### Runtime Environment

-   Python 3.x
-   pip for package management