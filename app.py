from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from trendyol_service import TrendyolService
from smartbill_service import SmartBillService
from user_manager import UserManager
from datetime import datetime, timedelta
from functools import wraps
import io
import requests
import time
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

session_secret = os.getenv('SESSION_SECRET')
# if not session_secret or session_secret == 'dev-secret-key':
#     raise ValueError(
#         "SESSION_SECRET environment variable must be set to a strong random value"
#     )

app.secret_key = session_secret

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

user_manager = UserManager()


@login_manager.user_loader
def load_user(user_id):
    return user_manager.get_user_by_id(int(user_id))


def get_trendyol_service():
    if not current_user.is_authenticated:
        return None
    return TrendyolService(api_key=current_user.trendyol_api_key,
                           api_secret=current_user.trendyol_api_secret,
                           supplier_id=current_user.trendyol_supplier_id)


def get_smartbill_service():
    if not current_user.is_authenticated:
        return None
    return SmartBillService(api_token=current_user.smartbill_api_token,
                            email=current_user.smartbill_email,
                            company_cif=current_user.smartbill_company_cif)


def check_credentials():
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin():
        return False
    return bool(current_user.trendyol_api_key
                and current_user.trendyol_api_secret
                and current_user.trendyol_supplier_id)


def check_smartbill_credentials():
    if not current_user.is_authenticated:
        return False
    if current_user.is_admin():
        return False
    return bool(current_user.smartbill_api_token
                and current_user.smartbill_email
                and current_user.smartbill_company_cif)


def cleanup_old_invoices(max_age_days=30):
    """
    Delete invoice PDFs older than max_age_days from static/invoices directory.
    Called automatically during invoice uploads to manage storage.
    """
    try:
        invoices_dir = os.path.join(os.getcwd(), 'static', 'invoices')

        if not os.path.exists(invoices_dir):
            return

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        deleted_count = 0

        for filename in os.listdir(invoices_dir):
            filepath = os.path.join(invoices_dir, filename)

            if os.path.isfile(filepath) and filename.endswith('.pdf'):
                file_modified_time = os.path.getmtime(filepath)

                if file_modified_time < cutoff_time:
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        print(f"[CLEANUP] Deleted old invoice: {filename}")
                    except Exception as e:
                        print(f"[CLEANUP] Failed to delete {filename}: {e}")

        if deleted_count > 0:
            print(
                f"[CLEANUP] Deleted {deleted_count} invoice(s) older than {max_age_days} days"
            )

    except Exception as e:
        print(f"[CLEANUP] Error during invoice cleanup: {e}")


def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('You need admin privileges to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = user_manager.authenticate_user(username, password)

        if user:
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    if current_user.is_admin():
        return redirect(url_for('admin_users'))
    credentials_configured = check_credentials()
    return render_template('index.html',
                           credentials_configured=credentials_configured)


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = user_manager.get_all_users()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        trendyol_api_key = request.form.get('trendyol_api_key',
                                            '').strip() or None
        trendyol_api_secret = request.form.get('trendyol_api_secret',
                                               '').strip() or None
        trendyol_supplier_id = request.form.get('trendyol_supplier_id',
                                                '').strip() or None
        smartbill_api_token = request.form.get('smartbill_api_token',
                                               '').strip() or None
        smartbill_email = request.form.get('smartbill_email',
                                           '').strip() or None
        smartbill_company_cif = request.form.get('smartbill_company_cif',
                                                 '').strip() or None
        smartbill_gestiune = request.form.get('smartbill_gestiune',
                                              '').strip() or None

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return redirect(url_for('admin_add_user'))

        success = user_manager.create_user(
            username=username,
            password=password,
            trendyol_api_key=trendyol_api_key,
            trendyol_api_secret=trendyol_api_secret,
            trendyol_supplier_id=trendyol_supplier_id,
            smartbill_api_token=smartbill_api_token,
            smartbill_email=smartbill_email,
            smartbill_company_cif=smartbill_company_cif,
            smartbill_gestiune=smartbill_gestiune,
            role=role)

        if success:
            flash(f'User {username} created successfully.', 'success')
            return redirect(url_for('admin_users'))
        else:
            flash(f'User {username} already exists.', 'danger')

    return render_template('admin_add_user.html')


@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = user_manager.get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'user')
        trendyol_api_key = request.form.get('trendyol_api_key',
                                            '').strip() or None
        trendyol_api_secret = request.form.get('trendyol_api_secret',
                                               '').strip() or None
        trendyol_supplier_id = request.form.get('trendyol_supplier_id',
                                                '').strip() or None
        smartbill_api_token = request.form.get('smartbill_api_token',
                                               '').strip() or None
        smartbill_email = request.form.get('smartbill_email',
                                           '').strip() or None
        smartbill_company_cif = request.form.get('smartbill_company_cif',
                                                 '').strip() or None
        smartbill_gestiune = request.form.get('smartbill_gestiune',
                                              '').strip() or None

        update_data = {
            'username': username,
            'role': role,
            'trendyol_api_key': trendyol_api_key,
            'trendyol_api_secret': trendyol_api_secret,
            'trendyol_supplier_id': trendyol_supplier_id,
            'smartbill_api_token': smartbill_api_token,
            'smartbill_email': smartbill_email,
            'smartbill_company_cif': smartbill_company_cif,
            'smartbill_gestiune': smartbill_gestiune
        }

        if password:
            update_data['password'] = password

        success = user_manager.update_user(user_id, **update_data)

        if success:
            flash(f'User {username} updated successfully.', 'success')
            return redirect(url_for('admin_users'))
        else:
            flash('Failed to update user.', 'danger')

    return render_template('admin_edit_user.html', user=user)


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if user_id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin_users'))

    user = user_manager.get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin_users'))

    success = user_manager.delete_user(user_id)

    if success:
        flash(f'User {user.username} deleted successfully.', 'success')
    else:
        flash('Failed to delete user.', 'danger')

    return redirect(url_for('admin_users'))


@app.route('/admin/invoices/add', methods=['POST'])
@login_required
@admin_required
def admin_add_invoice():
    try:
        import sqlite3
        order_id = request.form.get('order_id', '').strip()
        series = request.form.get('series', '').strip()
        number = request.form.get('number', '').strip()

        if not order_id or not series or not number:
            return jsonify({'error': 'All fields are required'}), 400

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Check if invoice exists for current user
        c.execute(
            'SELECT id FROM order_invoices WHERE user_id = ? AND order_id = ?',
            (current_user.id, order_id))
        existing = c.fetchone()

        if existing:
            conn.close()
            return jsonify(
                {'error': f'Invoice already exists for order {order_id}'}), 409

        c.execute(
            '''
            INSERT INTO order_invoices (user_id, order_id, invoice_series, invoice_number)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, order_id, series, number))
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Invoice added successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/invoices/edit/<int:invoice_id>', methods=['POST'])
@login_required
@admin_required
def admin_edit_invoice(invoice_id):
    try:
        import sqlite3
        order_id = request.form.get('order_id', '').strip()
        series = request.form.get('series', '').strip()
        number = request.form.get('number', '').strip()

        if not order_id or not series or not number:
            return jsonify({'error': 'All fields are required'}), 400

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Check if invoice exists and belongs to current user
        c.execute('SELECT id FROM order_invoices WHERE id = ? AND user_id = ?',
                  (invoice_id, current_user.id))
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Invoice not found'}), 404

        # Check for duplicate order_id for this user
        c.execute(
            'SELECT id FROM order_invoices WHERE user_id = ? AND order_id = ? AND id != ?',
            (current_user.id, order_id, invoice_id))
        existing = c.fetchone()
        if existing:
            conn.close()
            return jsonify(
                {'error': f'Invoice already exists for order {order_id}'}), 409

        c.execute(
            '''
            UPDATE order_invoices 
            SET order_id = ?, invoice_series = ?, invoice_number = ?
            WHERE id = ? AND user_id = ?
        ''', (order_id, series, number, invoice_id, current_user.id))

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Invoice updated successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/invoices/delete/<int:invoice_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_invoice(invoice_id):
    try:
        import sqlite3
        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Only delete invoices belonging to current user
        c.execute('DELETE FROM order_invoices WHERE id = ? AND user_id = ?',
                  (invoice_id, current_user.id))

        if c.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Invoice not found'}), 404

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Invoice deleted successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/invoices/search', methods=['GET'])
@login_required
@admin_required
def admin_search_invoices():
    try:
        import sqlite3
        search_term = request.args.get('q', '').strip()

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        # Admin can see ALL invoices from ALL users
        if search_term:
            c.execute(
                '''
                SELECT oi.id, oi.order_id, oi.invoice_series, oi.invoice_number, oi.created_at, u.username
                FROM order_invoices oi
                LEFT JOIN users u ON oi.user_id = u.id
                WHERE oi.order_id LIKE ? OR oi.invoice_series LIKE ? OR oi.invoice_number LIKE ?
                ORDER BY oi.created_at DESC
            ''', (f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'))
        else:
            c.execute('''
                SELECT oi.id, oi.order_id, oi.invoice_series, oi.invoice_number, oi.created_at, u.username
                FROM order_invoices oi
                LEFT JOIN users u ON oi.user_id = u.id
                ORDER BY oi.created_at DESC
            ''')

        rows = c.fetchall()
        conn.close()

        invoices = []
        for row in rows:
            invoices.append({
                'id': row[0],
                'order_id': row[1],
                'series': row[2],
                'number': row[3],
                'created_at': row[4],
                'username': row[5] if row[5] else 'Unknown'
            })

        return jsonify({'invoices': invoices})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/orders', methods=['GET'])
@login_required
def get_orders():
    if not check_credentials():
        return jsonify({'error': 'Trendyol credentials not configured.'}), 401

    try:
        trendyol_service = get_trendyol_service()
        page = int(request.args.get('page', 0))
        size = int(request.args.get('size', 50))
        status = request.args.get('status', '')
        start_date = request.args.get('startDate', '')
        end_date = request.args.get('endDate', '')
        order_number = request.args.get('orderNumber', '')
        sku = request.args.get('sku', '')

        print(
            f"[DEBUG app.py] Received: page={page}, size={size}, status='{status}', startDate='{start_date}', endDate='{end_date}', orderNumber='{order_number}', sku='{sku}'"
        )

        result = trendyol_service.get_orders(page=page,
                                             size=size,
                                             status=status,
                                             start_date=start_date,
                                             end_date=end_date,
                                             order_number=order_number,
                                             sku=sku)

        if 'error' in result:
            status_code = result.get('status', 500)
            return jsonify({'error': result['error']}), status_code

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    if not check_credentials():
        return jsonify({'error': 'Trendyol credentials not configured.'}), 401

    try:
        trendyol_service = get_trendyol_service()
        page = int(request.args.get('page', 0))
        size = int(request.args.get('size', 50))
        barcode = request.args.get('barcode', '')
        approved = request.args.get('approved', None)

        if approved is not None:
            approved = approved.lower() == 'true'

        result = trendyol_service.get_products(page=page,
                                               size=size,
                                               barcode=barcode,
                                               approved=approved)

        if 'error' in result:
            status_code = result.get('status', 500)
            return jsonify({'error': result['error']}), status_code

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/shipment-packages', methods=['GET'])
@login_required
def get_shipment_packages():
    if not check_credentials():
        return jsonify({'error': 'Trendyol credentials not configured.'}), 401

    try:
        trendyol_service = get_trendyol_service()
        page = int(request.args.get('page', 0))
        size = int(request.args.get('size', 50))
        status = request.args.get('status', '')
        start_date = request.args.get('startDate', '')
        end_date = request.args.get('endDate', '')
        order_number = request.args.get('orderNumber', '')

        result = trendyol_service.get_shipment_packages(
            page=page,
            size=size,
            status=status,
            start_date=start_date,
            end_date=end_date,
            order_number=order_number)

        if 'error' in result:
            status_code = result.get('status', 500)
            return jsonify({'error': result['error']}), status_code

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/smartbill/series', methods=['GET'])
@login_required
def get_smartbill_series():
    if not check_smartbill_credentials():
        return jsonify(
            {'error': 'SmartBill credentials not fully configured.'}), 401

    try:
        smartbill_service = get_smartbill_service()
        document_type = request.args.get('type', 'f')
        result = smartbill_service.get_document_series(
            document_type=document_type)

        if isinstance(result, dict) and 'error' in result:
            print(f"[DEBUG] SmartBill Series Error: {result['error']}")
            return jsonify(result), 500

        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG] SmartBill Series Exception: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/smartbill/next-invoice-number', methods=['GET'])
@login_required
def get_next_invoice_number():
    if not check_smartbill_credentials():
        return jsonify({'error': 'SmartBill credentials not configured.'}), 401

    try:
        smartbill_service = get_smartbill_service()
        series_result = smartbill_service.get_document_series(
            document_type='f')

        if isinstance(series_result, dict) and 'error' in series_result:
            return jsonify({'error': series_result['error']}), 500

        if 'list' in series_result and len(series_result['list']) > 0:
            first_series = series_result['list'][0]
            series_name = first_series.get('name', '')
            next_number = str(first_series.get('nextNumber', '1')).zfill(4)
            combined = f"{series_name}{next_number}"

            return jsonify({
                'seriesName': series_name,
                'nextNumber': next_number,
                'combined': combined,
                'cif': current_user.smartbill_company_cif or ''
            })
        else:
            return jsonify(
                {'error': 'No invoice series found in SmartBill account'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/smartbill/invoices', methods=['GET'])
@login_required
def list_smartbill_invoices():
    if not check_smartbill_credentials():
        return jsonify(
            {'error': 'SmartBill credentials not fully configured.'}), 401

    try:
        smartbill_service = get_smartbill_service()
        series = request.args.get('series', None)
        number = request.args.get('number', None)
        date = request.args.get('date', None)

        result = smartbill_service.list_invoices(series=series,
                                                 number=number,
                                                 date=date)

        if isinstance(result, dict) and 'error' in result:
            print(f"[DEBUG] SmartBill List Error: {result['error']}")
            return jsonify(result), 500

        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG] SmartBill List Exception: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/smartbill/invoice/pdf', methods=['GET'])
@login_required
def get_smartbill_invoice_pdf():
    if not check_smartbill_credentials():
        return jsonify(
            {'error': 'SmartBill credentials not fully configured.'}), 401

    try:
        smartbill_service = get_smartbill_service()
        series = request.args.get('series', '')
        number = request.args.get('number', '')

        if not series or not number:
            return jsonify({'error':
                            'Both series and number are required'}), 400

        result = smartbill_service.get_invoice_pdf(series, number)

        if isinstance(result, dict) and 'error' in result:
            error_msg = result['error']
            print(f"[DEBUG] SmartBill PDF Error: {error_msg}")
            if 'credentials' in error_msg.lower():
                return jsonify(result), 401
            elif 'forbidden' in error_msg.lower():
                return jsonify(result), 403
            elif 'not found' in error_msg.lower() or '404' in error_msg:
                return jsonify(
                    {'error': f'Invoice {series}-{number} not found'}), 404
            else:
                return jsonify(result), 500

        return send_file(io.BytesIO(result),
                         mimetype='application/pdf',
                         as_attachment=True,
                         download_name=f'invoice_{series}_{number}.pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/smartbill/invoice/reverse', methods=['POST'])
@login_required
def reverse_smartbill_invoice():
    if not check_smartbill_credentials():
        return jsonify({'error': 'SmartBill credentials not configured.'}), 401

    try:
        smartbill_service = get_smartbill_service()
        data = request.get_json()
        series = data.get('series', '').strip()
        number = data.get('number', '').strip()
        issue_date = data.get('issueDate', '').strip()

        if not series or not number:
            return jsonify({'error': 'Both series and number are required'}), 400

        result = smartbill_service.reverse_invoice(series, number, issue_date if issue_date else None)

        if isinstance(result, dict) and 'error' in result:
            error_msg = result['error']
            print(f"[DEBUG] SmartBill Reverse Error for {series}-{number}: {error_msg}")
            if 'credentials' in error_msg.lower():
                return jsonify(result), 401
            elif 'forbidden' in error_msg.lower():
                return jsonify(result), 403
            elif 'not found' in error_msg.lower():
                return jsonify(result), 404
            else:
                return jsonify(result), 500

        print(f"[DEBUG] SmartBill Reverse Success for {series}-{number}: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"[DEBUG] SmartBill Reverse Exception: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/label/<package_id>', methods=['GET'])
@login_required
def download_label(package_id):
    print(f"[DEBUG] Attempting to download label for package_id: {package_id}")
    if not check_credentials():
        return jsonify({'error': 'Trendyol credentials not configured.'}), 401

    try:
        trendyol_service = get_trendyol_service()
        label_data, status_code = trendyol_service.get_shipping_label(
            package_id)
        print(
            f"[DEBUG] Label fetch result - status_code: {status_code}, has_data: {label_data is not None}"
        )

        if label_data and status_code == 200:
            return send_file(label_data,
                             mimetype='application/pdf',
                             as_attachment=True,
                             download_name=f'label_{package_id}.pdf')
        else:
            error_messages = {
                401: 'Unauthorized: Invalid or expired credentials',
                403: 'Forbidden: Access denied',
                404: 'Label not found or not generated yet',
                429: 'Rate limited: Please try again later',
                500: 'Server error while fetching label'
            }
            error_msg = error_messages.get(status_code, 'Label not available')
            return jsonify({'error': error_msg}), status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/postal-code/<postal_code>', methods=['GET'])
@login_required
def lookup_postal_code(postal_code):
    try:
        from bs4 import BeautifulSoup

        url = f'https://www.coduripostale.net/{postal_code}'
        headers = {
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                if len(rows) > 1:
                    cols = rows[1].find_all('td')
                    if len(cols) >= 4:
                        city = cols[2].text.strip()
                        county = cols[3].text.strip()

                        return jsonify({
                            'success': True,
                            'city': city,
                            'county': county
                        })

        return jsonify({
            'success':
            False,
            'error':
            'Postal code not found. Please enter city and county manually.'
        }), 404

    except Exception as e:
        print(f"[DEBUG] Postal code lookup error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Postal code lookup failed: {str(e)}'
        }), 500


@app.route('/api/smartbill/create-invoice', methods=['POST'])
@login_required
def create_smartbill_invoice():
    if not check_smartbill_credentials():
        return jsonify({'error': 'SmartBill credentials not configured.'}), 401

    try:
        import sqlite3
        invoice_data = request.get_json()
        order_id = invoice_data.get('orderNumber')

        if not order_id:
            return jsonify({'error': 'Order number is required'}), 400

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute(
            'SELECT invoice_series, invoice_number FROM order_invoices WHERE user_id = ? AND order_id = ?',
            (current_user.id, str(order_id)))
        existing = c.fetchone()
        conn.close()

        if existing:
            return jsonify({
                'error': f'Invoice already exists for order {order_id}',
                'series': existing[0],
                'number': existing[1]
            }), 409

        smartbill_service = get_smartbill_service()
        result = smartbill_service.create_invoice(invoice_data)
        print(f"[DEBUG] SmartBill create_invoice result: {result}")

        if isinstance(result, dict) and 'error' in result:
            print(f"[ERROR] SmartBill create_invoice error: {result}")
            return jsonify(result), 500

        invoice_series = result.get('series', '')
        invoice_number = result.get('number', '')

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute(
            '''
            INSERT INTO order_invoices (user_id, order_id, invoice_series, invoice_number)
            VALUES (?, ?, ?, ?)
        ''', (current_user.id, str(order_id), invoice_series, invoice_number))
        conn.commit()
        conn.close()

        return jsonify({
            'success':
            True,
            'series':
            invoice_series,
            'number':
            invoice_number,
            'message':
            f'Invoice {invoice_series}-{invoice_number} created successfully'
        })
    except Exception as e:
        print(f"[DEBUG] Create invoice error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/order-invoices/<order_id>', methods=['GET'])
@login_required
def get_order_invoice(order_id):
    try:
        import sqlite3
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute(
            '''
            SELECT invoice_series, invoice_number, created_at 
            FROM order_invoices 
            WHERE user_id = ? AND order_id = ?
        ''', (current_user.id, str(order_id)))
        row = c.fetchone()
        conn.close()

        if row:
            return jsonify({
                'hasInvoice': True,
                'series': row[0],
                'number': row[1],
                'createdAt': row[2]
            })
        else:
            return jsonify({'hasInvoice': False})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/get-gestiune', methods=['GET'])
@login_required
def get_gestiune():
    try:
        gestiune = current_user.smartbill_gestiune if current_user.is_authenticated else ''
        return jsonify({'gestiune': gestiune or ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/order-invoices', methods=['GET'])
@login_required
def get_all_order_invoices():
    try:
        import sqlite3
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute(
            'SELECT order_id, invoice_series, invoice_number, created_at FROM order_invoices WHERE user_id = ?',
            (current_user.id, ))
        rows = c.fetchall()
        conn.close()

        invoices = []
        for row in rows:
            invoices.append({
                'order_number': row[0],
                'series': row[1],
                'number': row[2],
                'created_at': row[3]
            })

        return jsonify({'invoices': invoices})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


@app.route('/api/upload-invoice-to-trendyol', methods=['POST'])
@login_required
def upload_invoice_to_trendyol():
    try:
        order_id = request.form.get('order_id', '').strip()
        pdf_file = request.files.get('pdf_file')

        if not order_id or not pdf_file or not pdf_file.filename:
            return jsonify({'error':
                            'Order ID and PDF file are required'}), 400

        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        if not check_credentials():
            return jsonify({'error':
                            'Trendyol credentials not configured.'}), 401

        user = current_user._get_current_object()
        pdf_content = pdf_file.read()
        filename = secure_filename(f"invoice_{order_id}_{pdf_file.filename}")

        trendyol_service = TrendyolService(user.trendyol_api_key,
                                           user.trendyol_api_secret,
                                           user.trendyol_supplier_id)

        result = trendyol_service.upload_invoice_file(
            order_id, pdf_content, filename=filename)

        if 'error' in result:
            return jsonify({'error':
                            result['error']}), result.get('status', 500)

        return jsonify({
            'success': True,
            'message':
            f'Invoice uploaded successfully for shipment package {order_id}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/upload-smartbill-invoice-to-trendyol', methods=['POST'])
@login_required
def upload_smartbill_invoice_to_trendyol():
    """
    Downloads invoice PDF from SmartBill, uploads directly to Trendyol as file,
    then deletes the temporary PDF from server
    """
    filepath = None
    try:
        data = request.get_json()
        shipment_package_id = str(data.get('shipment_package_id', '')).strip()
        series = str(data.get('series', '')).strip()
        number = str(data.get('number', '')).strip()

        if not shipment_package_id or not series or not number:
            return jsonify({
                'error':
                'Shipment package ID, series, and number are required'
            }), 400

        if not check_credentials():
            return jsonify({'error':
                            'Trendyol credentials not configured.'}), 401

        if not check_smartbill_credentials():
            return jsonify({'error':
                            'SmartBill credentials not configured.'}), 401

        user = current_user._get_current_object()

        smartbill_service = get_smartbill_service()
        pdf_content = smartbill_service.get_invoice_pdf(series, number)

        if isinstance(pdf_content, dict) and 'error' in pdf_content:
            return jsonify({
                'error':
                f'Failed to download invoice from SmartBill: {pdf_content["error"]}'
            }), 500

        filename = f"invoice_{shipment_package_id}_{series}_{number}.pdf"

        trendyol_service = TrendyolService(user.trendyol_api_key,
                                           user.trendyol_api_secret,
                                           user.trendyol_supplier_id)

        result = trendyol_service.upload_invoice_file(
            shipment_package_id,
            pdf_content,
            filename=filename
        )

        if 'error' in result:
            return jsonify({'error':
                            result['error']}), result.get('status', 500)

        return jsonify({
            'success':
            True,
            'message':
            f'Invoice {series}-{number} uploaded directly to Trendyol for package {shipment_package_id}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def generate_invoice_data_from_order(order, user, use_gestiune=True):
    """
    Generate SmartBill invoice data from Trendyol order
    """
    from datetime import date
    import requests
    from bs4 import BeautifulSoup

    if use_gestiune:
        warehouse_name = user.smartbill_gestiune or ''
        foloseste_stock = True
    else:
        warehouse_name = ''
        foloseste_stock = False

    # Format products
    products = []

    for line in order.get('lines', []):
        # codul = line.get('sku', '')
        codul = line.get('merchantSku', '')
        if line.get('merchantSku', '') == "merchantSku":
            codul = line.get('sku', '')
        if line.get('sku', '') == "TYBE5ZISTJCR2Q5O74":
            codul = "6290360593661"
        elif line.get('sku', '') == "TYBZTU26IL7M50OR26":
            codul = "6290360599168"
        elif line.get('sku', '') == "TYBOOEG4YXK6HCXL86":
            codul = "6291108735411"
        elif line.get('sku', '') == "PMPE7SEBBAN4ZPP211":
            codul = "6290360599120"
        elif line.get('sku', '') == "TYBO6S9ZD26OA6NI63":
            codul = "6290360598888"
        elif line.get('sku', '') == "TYB46RAYZ8NJKLLI50":
            codul = "6290362345749"
        elif line.get('sku', '') == "776291108737194":
            codul = "6291108737194"
        elif line.get('sku', '') == "PMPGPLCV5FBWOBKL66":
            codul = "6290306595771"
        elif line.get('sku', '') == "TYB50R0MDLQTMSGA13":
            codul = "6290362345749"
        elif line.get('sku', '') == "TYBMF5JUXY6R2ILI26":
            codul = "6290362345749"
        elif line.get('sku', '') == "TYBG2PCBBTTXM2Z558":
            codul = "6298043160865"
        elif line.get('sku', '') == "TYBOOEG4YXK6HCXL86":
            codul = "6291108735411"
        elif line.get('sku', '') == "TYBUZOW2O04GCF0H47":
            codul = "6290306595771"
        elif line.get('sku', '') == "DH-6290362340362":
            codul = "6290362340362"
        elif line.get('sku', '') == "DH-6291107456485":
            codul = "6291107456485"
        elif line.get('sku', '') == "DH-6290362345749":
            codul = "6290362345749"
        elif line.get('sku', '') == "TYB50R0MDLQTMSGA13":
            codul = "6290362345749"
        elif line.get('sku', '') == "344259RYI9KM4NWZ":
            codul = "6290362340362"
        elif line.get('sku', '') == "TYBDVN19MS50NE4L05":
            codul = "6291108737194"
        elif line.get('sku', '') == "PMPNUJML9VHN1WSL78":
            codul = "6290362346548"
        elif line.get('sku', '') == "TYBY6WXHAX51S4K146":
            codul = "6290362346548"
        elif line.get('sku', '') == "TYBO6S9ZD26OA6NI63":
            codul = "6290360598888"
        elif line.get('sku', '') == "TYBZTU26IL7M50OR26":
            codul = "6290360599168"
        elif line.get('sku', '') == "DH-6295199802700":
            codul = "6295199802700"
        elif line.get('sku', '') == "DH-6294015181272":
            codul = "6294015181272"
        elif line.get('sku', '') == "DH-6291108738504":
            codul = "6291108738504"
        elif line.get('sku', '') == "DH-6290360598918":
            codul = "6290360598918"
        elif line.get('sku', '') == "899365NXPSOQXOR5":
            codul = "6290360599113"
        elif line.get('sku', '') == "344259RYI9KM4NWZ":
            codul = "6290362340362"
        elif line.get('sku', '') == "DH-6290362340638":
            codul = "6290362340638"
        elif line.get('sku', '') == "TYBC9FYOAYWMH5V824":
            codul = "6298043160865"
        elif line.get('sku', '') == "2992155993566":
            codul = "6290362349679"
        elif line.get('sku', '') == "54512289WHIP1":
            codul = "6290362349648"
        elif line.get('sku', '') == "PMPX7MWI02JJOZ5O03":
            codul = "6290360595764"
        elif line.get('sku', '') == "PMPCHUVPFHKM851K80":
            codul = "6290362340638"
        elif line.get('sku', '') == "4064666318097":
            codul = "1100011127"
        elif line.get('sku', '') == "TYBVLGRVD5MIVGV049":
            codul = "6290360598901"
        elif line.get('sku', '') == "TYB1LV9CP4QBMKDL08":
            codul = "6298043160964"
        elif line.get('sku', '') == "PMPIHBSEOOZSJJB821":
            codul = "6290362344506"
        elif line.get('sku', '') == "PMP9V4UX54QSMIVM71":
            codul = "6290362346531"
        elif line.get('sku', '') == "TYBNTUAF3RG4369H97":
            codul = "6291108737194"
        elif line.get('sku', '') == "TYBNTUAF3RG4369H97":
            codul = "6291108730515"
        elif line.get('sku', '') == "TYBN0O65AFCYAWO087":
            codul = "6298043160964"
        elif line.get('sku', '') == "TYB61GZIOG8D9CHN23":
            codul = "6298043160964"
        elif line.get('sku', '') == "TYC14OQK3N169892658027912":
            codul = "6291108738290"


   
         
         
        
        products.append({
            # 'code': line.get('sku', ''),
            # 'code': line.get('merchantSku', ''),
            'code': codul,
            'name': line.get('productName', ''),
            'productDescription': f"Numar comanda Trendyol:{order.get('orderNumber', '')}",
            'measuringUnitName': 'buc',
            'currency': order.get('currencyCode', 'RON'),
            
            
            # pt factura in euro
            # 'currency': order.get('currencyCode', ''),
            # 'exchangeRate': '',
            'quantity': line.get('quantity', 1),
            'price': line.get('price', 0),
            'isTaxIncluded': True,
            'taxPercentage': line.get('vatRate', ''),
            'saveToDb': False,
            # fara gestiune comenteaza
            'warehouseName': warehouse_name
        })

    # Get address info
    invoice_addr = order.get('invoiceAddress', {})
    shipment_addr = order.get('shipmentAddress', {})

    city = invoice_addr.get('city', '') or shipment_addr.get('city', '')
    county = invoice_addr.get('district', '') or shipment_addr.get(
        'district', '')
    postal_code = invoice_addr.get('postalCode', '') or shipment_addr.get(
        'postalCode', '')

    # Postal code lookup
    if postal_code:
        try:
            headers = {
                'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(
                f'https://www.coduripostale.net/{postal_code}',
                headers=headers,
                timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                table = soup.find('table')
                if table:
                    rows = table.find_all('tr')
                    if len(rows) > 1:
                        cols = rows[1].find_all('td')
                        if len(cols) >= 4:
                            if not city:
                                city = cols[2].text.strip()
                            county = cols[3].text.strip()
        except Exception as e:
            print(f"[DEBUG] Postal code lookup error in bulk: {str(e)}")
            pass

    # Get company info
    company_vat_code = user.smartbill_company_cif or 'YOUR_COMPANY_VAT_CODE'
    order_currency = order.get('currencyCode', 'RON')
    is_oss = order_currency != 'RON'

    # Get series name from SmartBill
    series_name = 'SERIE_FACTURA'
    try:
        smartbill_service = get_smartbill_service()
        series_result = smartbill_service.get_document_series('f')
        if series_result and 'list' in series_result and len(
                series_result['list']) > 0:
            first_series = series_result['list'][0]
            series_name = first_series.get('name', series_name)
    except:
        pass

    # Add -OSS suffix to series name for non-RON currencies
    if is_oss:
        base_series = series_name.replace('-OSS', '')
        series_name = base_series + '-OSS'

    # Use today's date
    today = date.today().isoformat()

    # Build invoice data
    customer_first_name = order.get('customerFirstName', '')
    customer_last_name = order.get('customerLastName', '')
    customer_name = f"{customer_first_name} {customer_last_name}".strip(
    ) or 'N/A'

    identity_number = order.get('identityNumber', '')
    # vat_code = identity_number if identity_number and identity_number != '0000000000000' else ''
    vat_code = '-'

    invoice_data = {
        'companyVatCode': company_vat_code,
        'useIntraCif': is_oss,
        'seriesName': series_name,
        'client': {
            'name': customer_name,
            'vatCode': vat_code,
            'isTaxPayer': False,
            'address': invoice_addr.get('address1', '') or shipment_addr.get('address1', ''),
            'city': city,
            'county': county,
            'country': invoice_addr.get('countryCode', '') or shipment_addr.get('countryCode', '') or 'RO',
            'email': order.get('customerEmail', ''),
            'saveToDb': True
        },
        'issueDate': today,
        # "currency": "RON",
        "currency": order.get('currencyCode', ''),
        # fara gestiune comenteaza
        # 'useStock': True,
        'useStock': foloseste_stock,
        'products': products,
        'orderNumber': order.get('orderNumber', '')
    }

    return invoice_data


@app.route('/api/bulk-send-to-smartbill', methods=['POST'])
@login_required
def bulk_send_to_smartbill():
    """
    Bulk send orders to SmartBill - processes orders matching current filters
    """
    try:
        if not check_credentials():
            return jsonify({'error':
                            'Trendyol credentials not configured.'}), 401

        if not check_smartbill_credentials():
            return jsonify({'error':
                            'SmartBill credentials not configured.'}), 401

        # Get parameters from request body
        request_data = request.get_json() or {}
        order_count = request_data.get('order_count', 10)
        status = request_data.get('status', '')
        start_date = request_data.get('startDate', '')
        end_date = request_data.get('endDate', '')
        order_number = request_data.get('orderNumber', '')
        sku = request_data.get('sku', '')

        user = current_user._get_current_object()
        trendyol_service = TrendyolService(user.trendyol_api_key,
                                           user.trendyol_api_secret,
                                           user.trendyol_supplier_id)

        # Get all order IDs that already have invoices in the database for current user
        import sqlite3
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT order_id FROM order_invoices WHERE user_id = ?',
                  (current_user.id, ))
        existing_invoice_orders = set(row[0] for row in c.fetchall())
        conn.close()

        # Get orders with filters applied
        all_orders = []
        page = 0
        while True:
            result = trendyol_service.get_orders(page=page,
                                                 size=200,
                                                 status=status,
                                                 start_date=start_date,
                                                 end_date=end_date,
                                                 order_number=order_number,
                                                 sku=sku)
            if 'error' in result:
                return jsonify(
                    {'error':
                     f'Failed to fetch orders: {result["error"]}'}), 500

            orders = result.get('content', [])
            if not orders:
                break

            all_orders.extend(orders)

            if len(orders) < 200:
                break
            page += 1

        # Filter orders that:
        # 1. Don't have an invoice already created in our database
        # 2. Don't have an invoice uploaded to Trendyol (no invoiceLink)
        orders_without_invoice = [
            order for order in all_orders
            if str(order.get('orderNumber', '')) not in existing_invoice_orders
            and not order.get('invoiceLink')
        ]

        # Limit to requested order count
        orders_to_process = orders_without_invoice[:order_count]

        successful = 0
        failed = 0
        errors = []

        smartbill_service = get_smartbill_service()

        for order in orders_to_process:
            try:
                invoice_data = generate_invoice_data_from_order(order, user)
                result = smartbill_service.create_invoice(invoice_data)

                if 'error' in result:
                    failed += 1
                    errors.append(
                        f"Order {order.get('orderNumber', 'N/A')}: {result['error']}"
                    )
                else:
                    successful += 1
                    # Save invoice info to database
                    series = result.get('series', '')
                    number = result.get('number', '')
                    order_number = order.get('orderNumber', '')

                    if series and number and order_number:
                        import sqlite3
                        conn = sqlite3.connect('users.db')
                        c = conn.cursor()
                        # First, delete any existing invoice for this user/order
                        c.execute(
                            'DELETE FROM order_invoices WHERE user_id = ? AND order_id = ?',
                            (current_user.id, order_number))
                        # Then insert the new invoice
                        c.execute(
                            '''INSERT INTO order_invoices 
                                    (user_id, order_id, invoice_series, invoice_number) 
                                    VALUES (?, ?, ?, ?)''',
                            (current_user.id, order_number, series, number))
                        conn.commit()
                        conn.close()
            except Exception as e:
                failed += 1
                errors.append(
                    f"Order {order.get('orderNumber', 'N/A')}: {str(e)}")
                continue

        return jsonify({
            'success': True,
            'total': len(orders_to_process),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10]  # Limit to first 10 errors
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/bulk-upload-to-trendyol', methods=['POST'])
@login_required
def bulk_upload_to_trendyol():
    """
    Bulk upload invoices to Trendyol - processes orders matching current filters
    Uploads PDF files directly to Trendyol API
    """
    try:
        if not check_credentials():
            return jsonify({'error':
                            'Trendyol credentials not configured.'}), 401

        if not check_smartbill_credentials():
            return jsonify({'error':
                            'SmartBill credentials not configured.'}), 401

        request_data = request.get_json() or {}
        upload_count = request_data.get('upload_count', 10)
        status = request_data.get('status', '')
        start_date = request_data.get('startDate', '')
        end_date = request_data.get('endDate', '')
        order_number = request_data.get('orderNumber', '')
        sku = request_data.get('sku', '')

        # Get all order-invoice mappings from database for current user
        import sqlite3
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute(
            'SELECT order_id, invoice_series, invoice_number FROM order_invoices WHERE user_id = ?',
            (current_user.id, ))
        invoice_mappings = {
            row[0]: {
                'series': row[1],
                'number': row[2]
            }
            for row in c.fetchall()
        }
        conn.close()

        if not invoice_mappings:
            return jsonify(
                {'error': 'No SmartBill invoices found in database'}), 400

        user = current_user._get_current_object()
        trendyol_service = TrendyolService(user.trendyol_api_key,
                                           user.trendyol_api_secret,
                                           user.trendyol_supplier_id)

        # Get orders with filters applied
        all_orders = []
        page = 0
        while True:
            result = trendyol_service.get_orders(page=page,
                                                 size=200,
                                                 status=status,
                                                 start_date=start_date,
                                                 end_date=end_date,
                                                 order_number=order_number,
                                                 sku=sku)
            if 'error' in result:
                return jsonify(
                    {'error':
                     f'Failed to fetch orders: {result["error"]}'}), 500

            orders = result.get('content', [])
            if not orders:
                break

            all_orders.extend(orders)

            if len(orders) < 200:
                break
            page += 1

        # Filter orders that have SmartBill invoices but no Trendyol upload
        orders_to_upload_all = []
        for order in all_orders:
            order_number = order.get('orderNumber')
            if order_number in invoice_mappings and not order.get(
                    'invoiceLink'):
                orders_to_upload_all.append({
                    'order':
                    order,
                    'invoice':
                    invoice_mappings[order_number]
                })

        # Limit to requested upload count
        orders_to_upload = orders_to_upload_all[:upload_count]

        successful = 0
        failed = 0
        errors = []

        smartbill_service = get_smartbill_service()

        for item in orders_to_upload:
            filepath = None
            try:
                order = item['order']
                invoice = item['invoice']
                package_id = str(order.get('id', '')).strip()
                series = invoice['series']
                number = invoice['number']

                # Download PDF from SmartBill
                pdf_content = smartbill_service.get_invoice_pdf(series, number)

                if isinstance(pdf_content, dict) and 'error' in pdf_content:
                    failed += 1
                    errors.append(
                        f"Order {order.get('orderNumber', 'N/A')}: {pdf_content['error']}"
                    )
                    continue

                filename = f"invoice_{package_id}_{series}_{number}.pdf"

                result = trendyol_service.upload_invoice_file(
                    package_id, pdf_content, filename=filename)

                if 'error' in result:
                    failed += 1
                    errors.append(
                        f"Order {order.get('orderNumber', 'N/A')}: {result['error']}"
                    )
                else:
                    successful += 1

            except Exception as e:
                failed += 1
                errors.append(
                    f"Order {order.get('orderNumber', 'N/A')}: {str(e)}")

        return jsonify({
            'success': True,
            'total': len(orders_to_upload),
            'successful': successful,
            'failed': failed,
            'errors': errors[:10]  # Limit to first 10 errors
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
