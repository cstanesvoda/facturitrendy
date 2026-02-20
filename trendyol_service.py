import requests
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO


class TrendyolService:
    BASE_URL = "https://api.trendyol.com/sapigw"
    INTEGRATION_BASE_URL = "https://apigw.trendyol.com/integration"

    def __init__(self, api_key, api_secret, supplier_id):
        self.api_key = api_key
        self.api_secret = api_secret
        self.supplier_id = supplier_id
        self.headers = self._create_headers()

    def _create_headers(self):
        if not self.api_key or not self.api_secret:
            return {}

        credentials = f"{self.api_key}:{self.api_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        return {
            'Authorization': f'Basic {encoded_credentials}',
            'User-Agent': 'Trendyol-Order-Manager',
            'Content-Type': 'application/json'
        }

    def get_orders(self,
                   page=0,
                   size=50,
                   status='',
                   start_date='',
                   end_date='',
                   order_number='',
                   sku=''):
        # Use the recommended integration endpoint
        url = f"{self.INTEGRATION_BASE_URL}/order/sellers/{self.supplier_id}/orders"

        print(
            f"[DEBUG] get_orders called with: page={page}, size={size}, status='{status}', start_date='{start_date}', end_date='{end_date}', order_number='{order_number}', sku='{sku}'"
        )

        # Handle multiple statuses (comma-separated)
        if status and ',' in status:
            statuses = [s.strip() for s in status.split(',')]
            print(f"[DEBUG] Multiple statuses detected: {statuses}")
            return self._get_orders_multiple_statuses(
                statuses, page, size, start_date, end_date, order_number, sku
            )

        params: dict = {
            'page': page, 
            'size': size,
            'orderByField': 'CreatedDate',
            'orderByDirection': 'ASC'
        }

        if status:
            params['status'] = status

        if start_date:
            formatted_start = self._format_date(start_date)
            params['startDate'] = formatted_start
            print(f"[DEBUG] Start date: {start_date} -> {formatted_start}")
        else:
            print(f"[DEBUG] No start_date provided")

        if end_date:
            formatted_end = self._format_date(end_date)
            params['endDate'] = formatted_end
            print(f"[DEBUG] End date: {end_date} -> {formatted_end}")
        else:
            print(f"[DEBUG] No end_date provided")

        if order_number:
            params['orderNumber'] = order_number

        print(f"[DEBUG] Trendyol API URL: {url}")
        print(f"[DEBUG] Trendyol API params: {params}")

        # If SKU filter is provided, fetch ALL pages first, then filter client-side
        if sku:
            print(f"[DEBUG] SKU filter detected: '{sku}' - fetching all pages for client-side filtering")
            all_orders = []
            fetch_page = 0
            fetch_size = 200  # Use max page size for efficiency
            
            while True:
                fetch_params = params.copy()
                fetch_params['page'] = fetch_page
                fetch_params['size'] = fetch_size
                
                try:
                    response = requests.get(url, headers=self.headers, params=fetch_params)
                    response.raise_for_status()
                    result = response.json()
                    
                    content = result.get('content', [])
                    all_orders.extend(content)
                    
                    print(f"[DEBUG] Fetched page {fetch_page}: {len(content)} orders")
                    
                    # Stop if we got fewer results than requested (last page)
                    if len(content) < fetch_size:
                        break
                    
                    fetch_page += 1
                except requests.exceptions.HTTPError as e:
                    # If first page fails, propagate error to caller
                    if fetch_page == 0:
                        status_code = e.response.status_code if e.response else 500
                        return {
                            'error': f'Failed to fetch orders: {str(e)}',
                            'status': status_code
                        }
                    # Subsequent page failures: log and continue with partial results
                    print(f"[DEBUG] Error fetching page {fetch_page}: {e} - continuing with partial results")
                    break
                except requests.exceptions.RequestException as e:
                    # If first page fails, propagate error to caller
                    if fetch_page == 0:
                        return {
                            'error': f'Failed to fetch orders: {str(e)}',
                            'status': 500
                        }
                    # Subsequent page failures: log and continue with partial results
                    print(f"[DEBUG] Error fetching page {fetch_page}: {e} - continuing with partial results")
                    break
            
            print(f"[DEBUG] Total orders fetched: {len(all_orders)}")
            
            # Apply SKU filter to all orders
            filtered_orders = []
            for order in all_orders:
                lines = order.get('lines', [])
                for line in lines:
                    merchant_sku = line.get('merchantSku', '')
                    barcode = line.get('barcode', '')
                    
                    if sku.lower() in merchant_sku.lower() or sku.lower() in barcode.lower():
                        filtered_orders.append(order)
                        break
            
            print(f"[DEBUG] SKU filter: {len(all_orders)} orders -> {len(filtered_orders)} orders")
            
            # Apply pagination to filtered results
            start_idx = page * size
            end_idx = start_idx + size
            paginated_orders = filtered_orders[start_idx:end_idx]
            
            total_filtered = len(filtered_orders)
            total_pages = (total_filtered + size - 1) // size if size > 0 else 0
            
            return {
                'content': paginated_orders,
                'page': page,
                'size': len(paginated_orders),
                'totalElements': total_filtered,
                'totalPages': total_pages
            }

        # No SKU filter - use standard single-page fetch
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            result = response.json()

            # Debug: Show response details
            content_count = len(result.get('content', []))
            total_elements = result.get('totalElements', 'N/A')
            print(f"[DEBUG] API Response: Requested size={size}, Received={content_count} orders, Total available={total_elements}")
            
            # Debug: Show first order date if available
            if result.get('content') and len(result['content']) > 0:
                first_order = result['content'][0]
                print(
                    f"[DEBUG] First order date: {first_order.get('orderDate')} (Order: {first_order.get('orderNumber')})"
                )

            return result
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            return {
                'error': f'Failed to fetch orders: {str(e)}',
                'status': status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Failed to fetch orders: {str(e)}',
                'status': 500
            }

    def _get_orders_multiple_statuses(self, statuses, page, size, start_date, end_date, order_number, sku=''):
        """Fetch orders for multiple statuses and combine results."""
        all_orders = []
        seen_order_ids = set()
        
        # Fetch ALL available orders for each status to get accurate totals
        # API max is 200 per request, so we'll fetch multiple pages
        fetch_size = 200
        
        for status in statuses:
            url = f"{self.INTEGRATION_BASE_URL}/order/sellers/{self.supplier_id}/orders"
            
            # Fetch all pages for this status until no more data
            fetch_page = 0
            while True:
                params: dict = {
                    'page': fetch_page,
                    'size': fetch_size,
                    'orderByField': 'CreatedDate',
                    'orderByDirection': 'ASC',
                    'status': status
                }
                
                if start_date:
                    params['startDate'] = self._format_date(start_date)
                
                if end_date:
                    params['endDate'] = self._format_date(end_date)
                
                if order_number:
                    params['orderNumber'] = order_number
                
                try:
                    response = requests.get(url, headers=self.headers, params=params)
                    response.raise_for_status()
                    result = response.json()
                    
                    content = result.get('content', [])
                    if content:
                        for order in content:
                            # Avoid duplicates (same order might have multiple statuses)
                            order_id = order.get('id') or order.get('orderNumber')
                            if order_id not in seen_order_ids:
                                all_orders.append(order)
                                seen_order_ids.add(order_id)
                    
                    # If we got fewer results than requested, no more pages for this status
                    if len(content) < fetch_size:
                        break
                    
                    # Move to next page
                    fetch_page += 1
                        
                except requests.exceptions.RequestException as e:
                    print(f"[DEBUG] Error fetching orders for status '{status}', page {fetch_page}: {e}")
                    break
        
        # Client-side SKU filtering (Trendyol API doesn't support SKU filter)
        if sku:
            print(f"[DEBUG] Applying client-side SKU filter to multi-status results: '{sku}'")
            original_count = len(all_orders)
            filtered_orders = []
            
            for order in all_orders:
                # Check if any line item in the order has matching SKU
                lines = order.get('lines', [])
                for line in lines:
                    # Match against merchantSku or barcode
                    merchant_sku = line.get('merchantSku', '')
                    barcode = line.get('barcode', '')
                    
                    if sku.lower() in merchant_sku.lower() or sku.lower() in barcode.lower():
                        filtered_orders.append(order)
                        break  # Found match, no need to check other lines
            
            all_orders = filtered_orders
            print(f"[DEBUG] SKU filter (multi-status): {original_count} orders -> {len(all_orders)} orders")
        
        # Sort combined results by CreatedDate (oldest first / ascending)
        all_orders.sort(
            key=lambda x: x.get('orderDate', 0), 
            reverse=False
        )
        
        # Apply pagination to combined results
        start_idx = page * size
        end_idx = start_idx + size
        paginated_orders = all_orders[start_idx:end_idx]
        
        total_unique = len(all_orders)
        total_pages = (total_unique + size - 1) // size if size > 0 else 0
        
        print(f"[DEBUG] Combined {total_unique} unique orders from {len(statuses)} statuses")
        print(f"[DEBUG] Returning page {page}/{total_pages} ({start_idx}-{end_idx}) with {len(paginated_orders)} orders")
        
        return {
            'content': paginated_orders,
            'page': page,
            'size': len(paginated_orders),
            'totalElements': total_unique,
            'totalPages': total_pages
        }

    def get_shipping_label(self, package_id):
        url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/shipment-packages/{package_id}/cargo-label"
        print(f"[DEBUG] Fetching label from URL: {url}")

        try:
            response = requests.get(url, headers=self.headers)
            print(
                f"[DEBUG] Response status: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}"
            )
            response.raise_for_status()

            if response.status_code == 204 or not response.content:
                return (None, 404)

            return (BytesIO(response.content), response.status_code)
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            return (None, status_code)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching shipping label: {e}")
            return (None, 500)

    def get_shipment_packages(self,
                              page=0,
                              size=50,
                              status='',
                              start_date='',
                              end_date='',
                              order_number=''):
        url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/shipment-packages"

        params: dict = {'page': page, 'size': size}

        if status:
            params['status'] = status

        if start_date:
            params['startDate'] = self._format_date(start_date)

        if end_date:
            params['endDate'] = self._format_date(end_date)

        if order_number:
            params['orderNumber'] = order_number

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            return {
                'error': f'Failed to fetch shipment packages: {str(e)}',
                'status': status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Failed to fetch shipment packages: {str(e)}',
                'status': 500
            }

    def send_invoice_link(self,
                          shipment_package_id,
                          invoice_link,
                          invoice_number=None,
                          invoice_datetime=None):
        url = f"{self.INTEGRATION_BASE_URL}/sellers/{self.supplier_id}/seller-invoice-links"

        payload = {
            'shipmentPackageId': int(shipment_package_id),
            'invoiceLink': invoice_link
        }

        if invoice_number:
            payload['invoiceNumber'] = invoice_number

        if invoice_datetime:
            payload['invoiceDateTime'] = invoice_datetime

        print(f"[DEBUG] Sending invoice link to URL: {url}")
        print(f"[DEBUG] Payload: {payload}")
        print(f"[DEBUG] Headers: {self.headers}")

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            print(f"[DEBUG] Response status: {response.status_code}")
            print(f"[DEBUG] Response body: {response.text}")
            response.raise_for_status()
            return {'success': True, 'status': response.status_code}
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            error_msg = f'Failed to send invoice link: {str(e)}'
            if e.response:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('message', error_msg)
                    print(f"[DEBUG] Error response JSON: {error_data}")
                except:
                    print(f"[DEBUG] Error response text: {e.response.text}")
                    pass
            return {'error': error_msg, 'status': status_code}
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Failed to send invoice link: {str(e)}',
                'status': 500
            }

    def upload_invoice_file(self,
                            shipment_package_id,
                            pdf_content,
                            filename='invoice.pdf',
                            invoice_number=None,
                            invoice_datetime=None):
        url = f"{self.INTEGRATION_BASE_URL}/sellers/{self.supplier_id}/seller-invoice-file"

        auth_str = f"{self.api_key}:{self.api_secret}"
        auth_header = base64.b64encode(auth_str.encode()).decode()

        headers = {
            'Authorization': f'Basic {auth_header}',
            'Accept': 'application/json'
        }

        files = {
            'file': (filename, pdf_content, 'application/pdf')
        }

        data = {
            'shipmentPackageId': str(int(shipment_package_id))
        }

        if invoice_number:
            data['invoiceNumber'] = invoice_number

        if invoice_datetime:
            data['invoiceDateTime'] = str(invoice_datetime)

        print(f"[DEBUG] Uploading invoice file to URL: {url}")
        print(f"[DEBUG] shipmentPackageId: {shipment_package_id}, filename: {filename}")

        try:
            response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
            print(f"[DEBUG] Upload response status: {response.status_code}")
            print(f"[DEBUG] Upload response body: {response.text}")
            response.raise_for_status()
            return {'success': True, 'status': response.status_code}
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            error_msg = f'Failed to upload invoice file: {str(e)}'
            if e.response:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('message', error_msg)
                    print(f"[DEBUG] Upload error response JSON: {error_data}")
                except:
                    print(f"[DEBUG] Upload error response text: {e.response.text}")
                    pass
            return {'error': error_msg, 'status': status_code}
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Failed to upload invoice file: {str(e)}',
                'status': 500
            }

    def get_products(self, page=0, size=50, barcode='', approved=None):
        url = f"{self.BASE_URL}/suppliers/{self.supplier_id}/products"

        params: dict = {'page': page, 'size': size}

        if barcode:
            params['barcode'] = barcode

        if approved is not None:
            params['approved'] = approved

        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            return {
                'error': f'Failed to fetch products: {str(e)}',
                'status': status_code
            }
        except requests.exceptions.RequestException as e:
            return {
                'error': f'Failed to fetch products: {str(e)}',
                'status': 500
            }

    def _format_date(self, date_str):
        try:
            # Parse date string and treat as Romanian timezone (Europe/Bucharest)
            # Expected format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

            # If no timezone info, treat as Romanian time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo('Europe/Bucharest'))

            # Convert to epoch milliseconds
            return int(dt.timestamp() * 1000)
        except:
            return date_str
