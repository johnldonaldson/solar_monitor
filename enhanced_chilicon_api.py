#!/usr/bin/env python3
"""
Enhanced Chilicon Power API Client
Focused on extracting microinverter data from JavaScript embedded data and AJAX endpoints
"""

import requests
import re
import json
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

class EnhancedChiliconAPIClient:
    def __init__(self):
        """Initialize the enhanced API client"""
        self.session = requests.Session()
        self.base_url = "https://cloud.chiliconpower.com"
        self.login_url = f"{self.base_url}/login"
        
        # Set up headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        self.logged_in = False
        self.csrf_token = None
        
    def get_csrf_token(self, html_content):
        """Extract CSRF token from HTML content"""
        patterns = [
            r'<input[^>]*name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)["\']',
            r'csrf_token["\']?\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                return match.group(1)
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            csrf_inputs = soup.find_all('input', {'name': re.compile(r'csrf', re.I)})
            if csrf_inputs:
                return csrf_inputs[0].get('value')
        except Exception:
            pass
        
        return None
    
    def login(self, username, password):
        """Login to Chilicon Power cloud platform"""
        try:
            print("Fetching login page...")
            response = self.session.get(self.login_url)
            response.raise_for_status()
            
            self.csrf_token = self.get_csrf_token(response.text)
            if self.csrf_token:
                print(f"Found CSRF token: {self.csrf_token[:20]}...")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            login_form = soup.find('form')
            if not login_form:
                print("No form found on login page")
                return False
            
            # Get form action URL
            form_action = login_form.get('action', '')
            if not form_action:
                form_action = self.login_url
            elif not form_action.startswith('http'):
                form_action = urljoin(self.base_url, form_action)
            
            # Find field names
            username_field = None
            password_field = None
            
            for input_tag in login_form.find_all('input'):
                input_type = input_tag.get('type', '').lower()
                input_name = input_tag.get('name', '')
                
                if input_type in ['email', 'text'] and any(keyword in input_name.lower() 
                                                         for keyword in ['username', 'email', 'user']):
                    username_field = input_name
                elif input_type == 'password':
                    password_field = input_name
            
            if not username_field or not password_field:
                print("Could not find username or password field names")
                return False
            
            # Prepare login data
            login_data = {
                username_field: username,
                password_field: password
            }
            
            # Add CSRF token
            if self.csrf_token:
                login_data['csrfmiddlewaretoken'] = self.csrf_token
            
            # Add hidden fields
            for hidden_input in login_form.find_all('input', {'type': 'hidden'}):
                field_name = hidden_input.get('name')
                field_value = hidden_input.get('value', '')
                if field_name and field_name not in login_data:
                    login_data[field_name] = field_value
            
            # Update headers for POST
            self.session.headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.login_url,
                'Origin': self.base_url
            })
            
            # Perform login
            print("Submitting login form...")
            login_response = self.session.post(form_action, data=login_data, allow_redirects=True)
            
            if login_response.status_code == 200 and 'login' not in login_response.url.lower():
                print("Login successful!")
                self.logged_in = True
                return True
            else:
                print("Login failed")
                return False
                
        except Exception as e:
            print(f"Error during login: {e}")
            return False
    
    def extract_microinverter_data(self, installation_url):
        """Extract microinverter data from installation page"""
        try:
            if not self.logged_in:
                print("Not logged in!")
                return None
            
            print(f"Fetching installation page: {installation_url}")
            response = self.session.get(installation_url)
            response.raise_for_status()
            
            html_content = response.text
            
            # Extract JavaScript embedded data
            js_data = self.extract_javascript_data(html_content)
            
            # Extract gateway and microinverter IDs
            gateway_data = self.extract_gateway_data(html_content)
            
            # Extract power and energy data
            power_data = self.extract_power_data(html_content)
            
            # Try to fetch microinverter status using found gateway ID
            ajax_data = {}
            if gateway_data.get('gateway_id'):
                ajax_data = self.try_ajax_endpoints(gateway_data['gateway_id'])
            
            result = {
                'javascript_data': js_data,
                'gateway_data': gateway_data,
                'power_data': power_data,
                'ajax_data': ajax_data,
                'extraction_timestamp': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            print(f"Error extracting microinverter data: {e}")
            return None
    
    def extract_javascript_data(self, html_content):
        """Extract relevant data from JavaScript code"""
        js_data = {}
        
        # Look for microinverter ID arrays - this is the key pattern we found
        array_pattern = r'\[([-\d,\s]+)\]'
        matches = re.finditer(array_pattern, html_content)
        
        for i, match in enumerate(matches):
            match_text = match.group(1).strip()
            try:
                # Clean up and split
                numbers_text = match_text.replace(' ', '').replace('\n', '')
                if ',' in numbers_text:
                    numbers = []
                    for x in numbers_text.split(','):
                        x = x.strip()
                        if x:
                            try:
                                numbers.append(int(x))
                            except ValueError:
                                continue
                    
                    # Only keep arrays with reasonable number of elements that look like device IDs
                    if 10 <= len(numbers) <= 50:  # Reasonable range for microinverter count
                        js_data[f'microinverter_array_{i}'] = {
                            'numbers': numbers,
                            'count': len(numbers),
                            'context': html_content[max(0, match.start()-100):match.end()+100]
                        }
                        print(f"Found microinverter array {i}: {len(numbers)} devices")
                        print(f"  Sample IDs: {numbers[:3]}...")
            except Exception as e:
                continue
        
        return js_data
    
    def extract_gateway_data(self, html_content):
        """Extract gateway ID and related data"""
        gateway_data = {}
        
        # Look for the specific pattern we found: sendCurveCommand('...')
        gateway_patterns = [
            r'sendCurveCommand\([\'"]([a-f0-9]{64,})[\'"]',
            r'fetchMicroinverterStatus\([\'"]([a-f0-9]{64,})[\'"]',
            r'([a-f0-9]{64,})',  # Any long hex string
        ]
        
        for pattern in gateway_patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                potential_id = match.group(1)
                if len(potential_id) >= 64:  # Gateway IDs are typically 64+ chars
                    gateway_data['gateway_id'] = potential_id
                    gateway_data['context'] = html_content[max(0, match.start()-100):match.end()+100]
                    print(f"Found gateway ID: {potential_id}")
                    break
            if gateway_data.get('gateway_id'):
                break
        
        return gateway_data
    
    def extract_power_data(self, html_content):
        """Extract power and energy values"""
        power_data = {}
        
        # Look for power-related values in the JavaScript
        power_patterns = [
            r'(\d+(?:\.\d+)?)\s*(k?W)\b',  # Power values with units
            r'(\d+(?:\.\d+)?)\s*(k?wh?)\b',  # Energy values
            r'currentProduction\s*[*=]\s*(\d+(?:\.\d+)?)',  # Current production
            r'maxValue\s*=\s*[^;]*?(\d+(?:\.\d+)?)',  # Max values
            r'production[^=]*=\s*(\d+(?:\.\d+)?)',  # Production values
            r'System\s+Size:\s*(\d+(?:\.\d+)?)\s*(k?W)',  # System size
        ]
        
        for i, pattern in enumerate(power_patterns):
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for j, match in enumerate(matches):
                try:
                    if len(match.groups()) >= 2:
                        value = float(match.group(1))
                        unit = match.group(2).upper()
                        power_data[f'power_{i}_{j}'] = {
                            'value': value,
                            'unit': unit,
                            'watts': value * 1000 if 'K' in unit else value,
                            'text': match.group(0),
                            'context': html_content[max(0, match.start()-50):match.end()+50]
                        }
                        print(f"Found power value: {value} {unit}")
                    else:
                        value = float(match.group(1))
                        power_data[f'numeric_{i}_{j}'] = {
                            'value': value,
                            'text': match.group(0),
                            'context': html_content[max(0, match.start()-50):match.end()+50]
                        }
                except Exception:
                    continue
        
        return power_data
    
    def try_ajax_endpoints(self, gateway_id):
        """Try different AJAX endpoints to get microinverter data"""
        ajax_data = {}
        
        # Based on the JavaScript we found, try these endpoints
        endpoints = [
            f"/ajax/microinverter-status/{gateway_id}",
            f"/ajax/gateway/{gateway_id}/status", 
            f"/ajax/gateway/{gateway_id}/devices",
            f"/api/gateway/{gateway_id}",
            f"/gateway/{gateway_id}/microinverters",
            f"/installation/gateway/{gateway_id}/status",
        ]
        
        # Also try with different HTTP methods and headers
        ajax_headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/json',
        }
        
        for endpoint in endpoints:
            try:
                url = urljoin(self.base_url, endpoint)
                print(f"Trying AJAX endpoint: {url}")
                
                # Update headers for AJAX request
                original_headers = self.session.headers.copy()
                self.session.headers.update(ajax_headers)
                
                response = self.session.get(url, timeout=10)
                
                # Restore original headers
                self.session.headers = original_headers
                
                if response.status_code == 200:
                    print(f"Success! Got data from {endpoint}")
                    
                    # Try to parse as JSON
                    try:
                        json_data = response.json()
                        ajax_data[endpoint] = {
                            'type': 'json',
                            'data': json_data,
                            'size': len(str(json_data))
                        }
                        
                        # Look for microinverter-specific data
                        json_str = str(json_data).lower()
                        if any(keyword in json_str for keyword in ['microinverter', 'device', 'power', 'serial']):
                            print(f"  Contains microinverter data!")
                            # Print a sample of the data
                            print(f"  Sample: {str(json_data)[:200]}...")
                            
                    except json.JSONDecodeError:
                        # If not JSON, save as text
                        ajax_data[endpoint] = {
                            'type': 'text',
                            'data': response.text[:1000],
                            'size': len(response.text)
                        }
                        print(f"  Got text data: {len(response.text)} chars")
                        
                elif response.status_code == 404:
                    print(f"  404 - Not found")
                elif response.status_code == 403:
                    print(f"  403 - Forbidden")
                else:
                    print(f"  {response.status_code} - {response.reason}")
                    
            except Exception as e:
                print(f"  Error: {e}")
        
        return ajax_data
    
    def save_data(self, data, filename_prefix="chilicon_api_data"):
        """Save extracted data to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        json_filename = f"{filename_prefix}_{timestamp}.json"
        try:
            with open(json_filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"Data saved to {json_filename}")
            return json_filename
        except Exception as e:
            print(f"Error saving JSON: {e}")
            return None
    
    def close(self):
        """Close the session"""
        self.session.close()

def main():
    """Main function to run the enhanced API client"""
    USERNAME = "johnldonaldson@gmail.com"
    PASSWORD = "P0pc0rn1"
    INSTALLATION_URL = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
    
    client = None
    
    try:
        print("Initializing Enhanced Chilicon Power API client...")
        client = EnhancedChiliconAPIClient()
        
        # Login
        if not client.login(USERNAME, PASSWORD):
            print("Login failed!")
            return
        
        # Extract microinverter data
        print("Extracting microinverter data...")
        data = client.extract_microinverter_data(INSTALLATION_URL)
        
        if data:
            # Save the data
            filename = client.save_data(data)
            
            # Print detailed summary
            print(f"\n=== EXTRACTION SUMMARY ===")
            
            # JavaScript data summary
            js_data = data.get('javascript_data', {})
            print(f"JavaScript data objects found: {len(js_data)}")
            
            # Show microinverter arrays found
            total_microinverters = 0
            for key, value in js_data.items():
                if 'microinverter_array' in key and 'numbers' in value:
                    count = value['count']
                    total_microinverters += count
                    print(f"  {key}: {count} microinverters")
                    print(f"    Sample IDs: {value['numbers'][:5]}...")
            
            print(f"Total microinverters found: {total_microinverters}")
            
            # Gateway data summary  
            gateway_data = data.get('gateway_data', {})
            if gateway_data.get('gateway_id'):
                print(f"Gateway ID: {gateway_data['gateway_id']}")
            
            # Power data summary
            power_data = data.get('power_data', {})
            print(f"Power values found: {len(power_data)}")
            
            total_power = 0
            for key, value in power_data.items():
                if 'watts' in value:
                    total_power += value['watts']
                    print(f"  {value['text']} -> {value['watts']} W")
                elif 'value' in value:
                    print(f"  {value['text']} -> {value['value']}")
            
            if total_power > 0:
                print(f"Total power calculated: {total_power} W ({total_power/1000:.2f} kW)")
            
            # AJAX data summary
            ajax_data = data.get('ajax_data', {})
            print(f"AJAX endpoints tried: {len(ajax_data)}")
            for endpoint, result in ajax_data.items():
                print(f"  {endpoint}: {result['type']} data ({result['size']} chars)")
            
            print(f"\nData saved to: {filename}")
            
        else:
            print("No data extracted!")
        
    except Exception as e:
        print(f"Error in main execution: {e}")
        
    finally:
        if client:
            client.close()

if __name__ == "__main__":
    main()
