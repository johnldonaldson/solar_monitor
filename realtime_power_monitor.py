#!/usr/bin/env python3
"""
Real-time Chilicon Power Monitor
Focuses on extracting current real-time power from microinverter data arrays
"""

import requests
import re
import json
from datetime import datetime
from urllib.parse import urljoin
from bs4 import BeautifulSoup

def login_and_get_installation_page(username, password, installation_url):
    """Login and get installation page"""
    session = requests.Session()
    base_url = "https://cloud.chiliconpower.com"
    login_url = f"{base_url}/login"
    
    # Set browser headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    
    # Get login page and CSRF token
    response = session.get(login_url)
    csrf_match = re.search(r'name=["\']csrfmiddlewaretoken["\'][^>]*value=["\']([^"\']+)["\']', response.text)
    csrf_token = csrf_match.group(1) if csrf_match else None
    
    # Login
    login_data = {
        'username': username,
        'password': password,
        'csrfmiddlewaretoken': csrf_token
    }
    
    session.headers.update({
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': login_url,
        'Origin': base_url
    })
    
    login_response = session.post(login_url, data=login_data, allow_redirects=True)
    
    if 'login' not in login_response.url.lower():
        print("✅ Login successful!")
        
        # Get installation page
        page_response = session.get(installation_url)
        return page_response.text
    else:
        print("❌ Login failed!")
        return None

def extract_microinverter_power_arrays(html_content):
    """Extract and analyze microinverter power data arrays"""
    # Look for arrays in JavaScript
    array_pattern = r'\[([-\d,\s]+)\]'
    matches = re.finditer(array_pattern, html_content)
    
    power_arrays = []
    microinverter_serials = []
    
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
                
                if len(numbers) >= 20:  # Arrays with reasonable microinverter count
                    # Analyze what type of data this might be
                    array_info = {
                        'array_index': i,
                        'values': numbers,
                        'count': len(numbers),
                        'min_value': min(numbers),
                        'max_value': max(numbers),
                        'sum_value': sum(numbers),
                        'context': html_content[max(0, match.start()-50):match.end()+50]
                    }
                    
                    # Classify the array type
                    if all(n < -1000000000 for n in numbers):
                        array_info['type'] = 'microinverter_serials'
                        microinverter_serials = numbers
                    elif all(0 <= n <= 500 for n in numbers):
                        array_info['type'] = 'current_power_watts'
                    elif all(0 <= n <= 5000 for n in numbers):
                        array_info['type'] = 'possible_power_or_voltage'
                    elif all(n == 0 for n in numbers):
                        array_info['type'] = 'zeros_array'
                    else:
                        array_info['type'] = 'unknown'
                    
                    power_arrays.append(array_info)
        except Exception:
            continue
    
    return power_arrays, microinverter_serials

def find_current_power_display(html_content):
    """Find the current power display value"""
    # Look for common patterns where current power is displayed
    power_patterns = [
        r'(\d+\.?\d*)\s*kW',  # X.X kW
        r'(\d+\.?\d*)\s*KW',  # X.X KW  
        r'(\d+,?\d*)\s*W',    # XXXX W or X,XXX W
        r'Current.*?(\d+\.?\d*)\s*[kK]?[Ww]',  # Current: X.X kW
        r'Real.*?time.*?(\d+\.?\d*)\s*[kK]?[Ww]',  # Real-time: X.X kW
        r'Live.*?(\d+\.?\d*)\s*[kK]?[Ww]',  # Live: X.X kW
        r'Production.*?(\d+\.?\d*)\s*[kK]?[Ww]',  # Production: X.X kW
    ]
    
    current_power_candidates = []
    
    for pattern in power_patterns:
        matches = re.finditer(pattern, html_content, re.IGNORECASE)
        for match in matches:
            try:
                value_str = match.group(1).replace(',', '')
                value = float(value_str)
                unit = 'kW' if 'k' in match.group(0).lower() else 'W'
                
                # Convert to watts
                watts = value * 1000 if unit == 'kW' else value
                
                # Only consider reasonable power values for a 7kW system
                if 0 <= watts <= 8000:
                    current_power_candidates.append({
                        'value': value,
                        'unit': unit,
                        'watts': watts,
                        'text': match.group(0),
                        'context': html_content[max(0, match.start()-100):match.end()+100]
                    })
            except:
                continue
    
    return current_power_candidates

def calculate_power_from_arrays(power_arrays):
    """Calculate total power from microinverter arrays"""
    results = []
    
    for array_info in power_arrays:
        if array_info['type'] == 'current_power_watts':
            total_watts = array_info['sum_value']
            results.append({
                'method': 'microinverter_array_sum',
                'array_index': array_info['array_index'],
                'total_watts': total_watts,
                'total_kw': round(total_watts / 1000, 2),
                'inverter_count': array_info['count'],
                'avg_per_inverter': round(total_watts / array_info['count'], 1),
                'values_sample': array_info['values'][:5]
            })
    
    return results

def main():
    """Main function"""
    USERNAME = "johnldonaldson@gmail.com"
    PASSWORD = "P0pc0rn1"
    INSTALLATION_URL = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
    
    print("🔌 Real-time Chilicon Power Monitor")
    print("=" * 50)
    
    # Get installation page
    html_content = login_and_get_installation_page(USERNAME, PASSWORD, INSTALLATION_URL)
    if not html_content:
        return
    
    # Extract microinverter arrays
    print("📊 Analyzing microinverter data arrays...")
    power_arrays, microinverter_serials = extract_microinverter_power_arrays(html_content)
    
    print(f"Found {len(power_arrays)} data arrays")
    print(f"Found {len(microinverter_serials)} microinverter serial numbers")
    
    # Show array analysis
    for array_info in power_arrays:
        print(f"\nArray {array_info['array_index']}: {array_info['type']}")
        print(f"  Count: {array_info['count']}")
        print(f"  Range: {array_info['min_value']} to {array_info['max_value']}")
        print(f"  Sum: {array_info['sum_value']}")
        print(f"  Sample: {array_info['values'][:5]}...")
        
        if array_info['type'] == 'current_power_watts':
            total_kw = array_info['sum_value'] / 1000
            print(f"  🔥 POSSIBLE CURRENT POWER: {total_kw:.1f} kW")
    
    # Look for current power displays
    print(f"\n⚡ Searching for current power displays...")
    power_displays = find_current_power_display(html_content)
    
    if power_displays:
        print(f"Found {len(power_displays)} power display candidates:")
        for i, display in enumerate(power_displays):
            print(f"  {i+1}: {display['text']} ({display['watts']:.0f} W)")
            print(f"      Context: ...{display['context'][:100]}...")
    else:
        print("No explicit power displays found")
    
    # Calculate power from arrays
    print(f"\n🧮 Calculating power from microinverter arrays...")
    array_calculations = calculate_power_from_arrays(power_arrays)
    
    if array_calculations:
        print("Power calculations from arrays:")
        for calc in array_calculations:
            print(f"  Array {calc['array_index']}: {calc['total_kw']} kW")
            print(f"    {calc['inverter_count']} inverters avg {calc['avg_per_inverter']} W each")
            print(f"    Sample values: {calc['values_sample']}")
    
    # Summary
    print(f"\n📋 SUMMARY")
    print(f"Microinverters detected: {len(microinverter_serials)}")
    
    if power_displays:
        max_display = max(power_displays, key=lambda x: x['watts'])
        print(f"Highest power display: {max_display['watts']:.0f} W ({max_display['watts']/1000:.1f} kW)")
    
    if array_calculations:
        max_array = max(array_calculations, key=lambda x: x['total_watts'])
        print(f"Highest array calculation: {max_array['total_watts']:.0f} W ({max_array['total_kw']} kW)")
    
    # Save detailed results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"realtime_power_analysis_{timestamp}.json"
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'microinverter_serials': microinverter_serials,
        'power_arrays': power_arrays,
        'power_displays': power_displays,
        'array_calculations': array_calculations
    }
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Detailed results saved to: {filename}")
    print("=" * 50)

if __name__ == "__main__":
    main()
