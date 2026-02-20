import requests
import base64
import os
from datetime import datetime

class SmartBillService:
    BASE_URL = "https://ws.smartbill.ro/SBORO/api"
    
    def __init__(self, api_token=None, email=None, company_cif=None):
        self.api_token = api_token or os.getenv('SMARTBILL_API_TOKEN')
        self.email = email or os.getenv('SMARTBILL_EMAIL')
        self.company_cif = company_cif or os.getenv('SMARTBILL_COMPANY_CIF')
    
    def _create_headers(self):
        if not self.email or not self.api_token:
            return None
        
        credentials = f"{self.email}:{self.api_token}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        return {
            'Authorization': f'Basic {encoded_credentials}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def get_document_series(self, document_type='f'):
        """
        Get document series from SmartBill
        
        Args:
            document_type: 'f' for invoice, 'p' for proforma, 'c' for receipt, '' for all
        
        Returns:
            List of series or error dict
        """
        headers = self._create_headers()
        if not headers:
            return {'error': 'Missing SmartBill credentials (email or API token)'}
        
        if not self.company_cif:
            return {'error': 'Missing company CIF'}
        
        params = {
            'cif': self.company_cif,
            'type': document_type
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/series",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                return {'error': 'Invalid SmartBill credentials'}
            elif response.status_code == 403:
                return {'error': 'Access forbidden - check your SmartBill plan or rate limit'}
            else:
                return {'error': f'SmartBill API error: {response.status_code} - {response.text[:200]}'}
        
        except requests.exceptions.RequestException as e:
            return {'error': f'Connection error: {str(e)}'}
    
    def list_invoices(self, series=None, number=None, date=None):
        """
        List invoices from SmartBill
        
        Args:
            series: Invoice series filter (optional)
            number: Invoice number filter (optional)
            date: Date filter in YYYY-MM-DD format (optional)
        
        Returns:
            List of invoices or error dict
        """
        headers = self._create_headers()
        if not headers:
            return {'error': 'Missing SmartBill credentials (email or API token)'}
        
        if not self.company_cif:
            return {'error': 'Missing company CIF'}
        
        params = {'cif': self.company_cif}
        
        if series:
            params['seriesName'] = series
        if number:
            params['number'] = number
        if date:
            params['issueDate'] = date
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/invoice/list",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 400:
                return {'error': f'Bad request - check your parameters: {response.text}'}
            elif response.status_code == 401:
                return {'error': 'Invalid SmartBill credentials'}
            elif response.status_code == 403:
                return {'error': 'Access forbidden - check your SmartBill plan or rate limit'}
            else:
                return {'error': f'SmartBill API error: {response.status_code} - {response.text}'}
        
        except requests.exceptions.RequestException as e:
            return {'error': f'Connection error: {str(e)}'}
    
    def create_invoice(self, invoice_data):
        """
        Create a new invoice in SmartBill
        
        Args:
            invoice_data: Dict containing invoice information
        
        Returns:
            Invoice creation response or error dict
        """
        headers = self._create_headers()
        if not headers:
            return {'error': 'Invalid SmartBill credentials (missing email or API token)'}
        
        if not self.company_cif:
            return {'error': 'Missing company CIF'}
        
        print(f"[DEBUG] SmartBill create_invoice - email: {self.email}, cif (from DB): {self.company_cif}, api_token present: {bool(self.api_token)}")
        print(f"[DEBUG] SmartBill create_invoice - companyVatCode in data: {invoice_data.get('companyVatCode', 'NOT SET')}")
        print(f"[DEBUG] SmartBill create_invoice - seriesName: {invoice_data.get('seriesName', 'NOT SET')}")
        
        try:
            response = requests.post(
                f"{self.BASE_URL}/invoice",
                headers=headers,
                json=invoice_data,
                timeout=30
            )
            
            print(f"[DEBUG] SmartBill create_invoice - status: {response.status_code}, response: {response.text[:500]}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 400:
                return {'error': f'Bad request - invalid invoice data: {response.text}'}
            elif response.status_code == 401:
                return {'error': f'Invalid SmartBill credentials (401): {response.text[:200]}'}
            elif response.status_code == 403:
                return {'error': f'Access forbidden (403): {response.text[:200]}'}
            else:
                return {'error': f'SmartBill API error: {response.status_code} - {response.text[:200]}'}
        
        except requests.exceptions.RequestException as e:
            return {'error': f'Connection error: {str(e)}'}
    
    def get_invoice_pdf(self, series, number):
        """
        Get invoice PDF from SmartBill
        
        Args:
            series: Invoice series
            number: Invoice number
        
        Returns:
            PDF content or error dict
        """
        headers = self._create_headers()
        if not headers:
            return {'error': 'Invalid SmartBill credentials (missing email or API token)'}
        
        if not self.company_cif:
            return {'error': 'Missing company CIF'}
        
        headers['Content-Type'] = 'application/xml'
        headers['Accept'] = 'application/octet-stream'
        
        params = {
            'cif': self.company_cif,
            'seriesname': series,
            'number': number
        }
        
        try:
            response = requests.get(
                f"{self.BASE_URL}/invoice/pdf",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.content
            elif response.status_code == 401:
                return {'error': 'Invalid SmartBill credentials'}
            elif response.status_code == 403:
                return {'error': 'Access forbidden - check your SmartBill plan or permissions'}
            elif response.status_code == 404:
                return {'error': f'Invoice not found: {series}-{number}'}
            else:
                return {'error': f'SmartBill API error: {response.status_code} - {response.text[:200]}'}
        
        except requests.exceptions.RequestException as e:
            return {'error': f'Connection error: {str(e)}'}

    def reverse_invoice(self, series, number, issue_date=None):
        headers = self._create_headers()
        if not headers:
            return {'error': 'Missing SmartBill credentials (email or API token)'}

        if not self.company_cif:
            return {'error': 'Missing company CIF'}

        payload = {
            'companyVatCode': self.company_cif,
            'seriesName': series,
            'number': number
        }

        if issue_date:
            payload['issueDate'] = issue_date
        else:
            payload['issueDate'] = datetime.now().strftime('%Y-%m-%d')

        try:
            response = requests.post(
                f"{self.BASE_URL}/invoice/reverse",
                headers=headers,
                json=payload,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                return {'error': 'Invalid SmartBill credentials'}
            elif response.status_code == 403:
                return {'error': 'Access forbidden - check your SmartBill plan or permissions'}
            elif response.status_code == 404:
                return {'error': f'Invoice not found: {series}-{number}'}
            else:
                return {'error': f'SmartBill API error: {response.status_code} - {response.text[:200]}'}

        except requests.exceptions.RequestException as e:
            return {'error': f'Connection error: {str(e)}'}
