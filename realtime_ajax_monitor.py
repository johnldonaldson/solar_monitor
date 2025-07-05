#!/usr/bin/env python3
"""
Real-time Chilicon Power AJAX Monitor
Polls the AJAX status endpoint for real-time power data
"""

import requests
import re
import json
import time
from datetime import datetime

class ChiliconAjaxMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.gateway_id = None
        self.csrf_token = None
        
    def login(self):
        """Login and get session"""
        try:
            # Get login page
            login_response = self.session.get("https://cloud.chiliconpower.com/login")
            csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_response.text)
            
            if not csrf_match:
                print("❌ Could not find CSRF token")
                return False
                
            self.csrf_token = csrf_match.group(1)
            
            # Submit login
            login_data = {
                'csrfmiddlewaretoken': self.csrf_token,
                'username': 'johnldonaldson@gmail.com',
                'password': 'P0pc0rn1'
            }
            
            login_submit = self.session.post("https://cloud.chiliconpower.com/login", data=login_data)
            
            if "dashboard" not in login_submit.url:
                print("❌ Login failed")
                return False
                
            print("✅ Login successful")
            return True
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_gateway_id(self):
        """Extract gateway ID from installation page"""
        try:
            installation_url = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
            response = self.session.get(installation_url)
            
            # Look for gateway ID in various patterns
            patterns = [
                r'gateway["\']?\s*:\s*["\']([a-f0-9]{64})["\']',
                r'gatewayId["\']?\s*:\s*["\']([a-f0-9]{64})["\']',
                r'gateway_id["\']?\s*:\s*["\']([a-f0-9]{64})["\']',
                r'([a-f0-9]{64})',  # Any 64-char hex string
            ]
            
            for pattern in patterns:
                matches = re.finditer(pattern, response.text, re.IGNORECASE)
                for match in matches:
                    candidate = match.group(1)
                    if len(candidate) == 64 and all(c in '0123456789abcdef' for c in candidate.lower()):
                        self.gateway_id = candidate
                        print(f"🔍 Found gateway ID: {candidate[:20]}...")
                        return True
            
            print("❌ Could not find gateway ID")
            return False
            
        except Exception as e:
            print(f"❌ Error getting gateway ID: {e}")
            return False
    
    def poll_ajax_status(self):
        """Poll the AJAX status endpoint for real-time data"""
        if not self.gateway_id:
            print("❌ No gateway ID available")
            return None
            
        ajax_url = f"https://cloud.chiliconpower.com/installation/gateway/{self.gateway_id}/status"
        
        try:
            print(f"📊 Polling AJAX endpoint: {ajax_url}")
            
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': 'https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7'
            }
            
            if self.csrf_token:
                headers['X-CSRFToken'] = self.csrf_token
            
            response = self.session.get(ajax_url, headers=headers)
            
            print(f"📨 Response status: {response.status_code}")
            print(f"📄 Response length: {len(response.text)} chars")
            print(f"🔍 Response preview: {response.text[:200]}...")
            
            if response.status_code == 200:
                # Try to parse as JSON
                try:
                    data = response.json()
                    print("✅ Got JSON response")
                    return data
                except json.JSONDecodeError:
                    # If not JSON, return as text
                    print("📝 Got text response")
                    return {'text_data': response.text}
            else:
                print(f"❌ HTTP error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ AJAX polling error: {e}")
            return None
    
    def try_alternative_endpoints(self):
        """Try various AJAX endpoints that might have real-time data"""
        if not self.gateway_id:
            return []
            
        endpoints = [
            f"/installation/gateway/{self.gateway_id}/status",
            f"/installation/gateway/{self.gateway_id}/realtime",
            f"/installation/gateway/{self.gateway_id}/power",
            f"/installation/gateway/{self.gateway_id}/current",
            f"/ajax/gateway/{self.gateway_id}/status",
            f"/ajax/gateway/{self.gateway_id}/power",
            f"/api/gateway/{self.gateway_id}/status",
            f"/api/installation/{self.gateway_id}/realtime",
            f"/installation/{self.gateway_id}/ajax/status",
            f"/gateway/{self.gateway_id}/status",
        ]
        
        results = []
        base_url = "https://cloud.chiliconpower.com"
        
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7'
        }
        
        if self.csrf_token:
            headers['X-CSRFToken'] = self.csrf_token
        
        print(f"🔍 Trying {len(endpoints)} alternative endpoints...")
        
        for endpoint in endpoints:
            try:
                url = base_url + endpoint
                response = self.session.get(url, headers=headers, timeout=5)
                
                result = {
                    'endpoint': endpoint,
                    'status_code': response.status_code,
                    'content_length': len(response.text),
                    'content_preview': response.text[:100],
                    'success': response.status_code == 200
                }
                
                if response.status_code == 200:
                    print(f"✅ {endpoint}: {len(response.text)} chars")
                    
                    # Try to extract power values
                    power_matches = re.findall(r'(\d+\.?\d*)\s*(k?W|watts?)', response.text, re.IGNORECASE)
                    if power_matches:
                        result['power_values'] = power_matches
                        print(f"   💡 Power values found: {power_matches}")
                        
                    # Try to parse as JSON
                    try:
                        json_data = response.json()
                        result['json_data'] = json_data
                        print(f"   📊 JSON data keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'Not a dict'}")
                    except:
                        pass
                        
                else:
                    print(f"❌ {endpoint}: {response.status_code}")
                
                results.append(result)
                time.sleep(0.5)  # Be nice to the server
                
            except Exception as e:
                print(f"❌ {endpoint}: Error - {str(e)[:50]}")
                results.append({
                    'endpoint': endpoint,
                    'error': str(e),
                    'success': False
                })
        
        return results
    
    def monitor_realtime(self, duration_minutes=5, poll_interval=30):
        """Monitor real-time power for a specified duration"""
        print(f"🕐 Starting {duration_minutes}-minute real-time monitoring...")
        print(f"⏱️  Polling every {poll_interval} seconds")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        readings = []
        
        while time.time() < end_time:
            timestamp = datetime.now()
            print(f"\n📅 {timestamp.strftime('%H:%M:%S')} - Polling for real-time data...")
            
            # Poll main status endpoint
            status_data = self.poll_ajax_status()
            
            reading = {
                'timestamp': timestamp.isoformat(),
                'status_data': status_data
            }
            
            # Look for power values in the response
            if status_data:
                if isinstance(status_data, dict):
                    # Extract any numeric values that could be power
                    for key, value in status_data.items():
                        if isinstance(value, (int, float)) and 100 < value < 10000:
                            print(f"   💡 Potential power value '{key}': {value}")
                
                elif 'text_data' in status_data:
                    # Look for power patterns in text
                    power_matches = re.findall(r'(\d+\.?\d*)\s*(k?W|watts?)', status_data['text_data'], re.IGNORECASE)
                    if power_matches:
                        print(f"   💡 Power patterns found: {power_matches}")
                        reading['power_patterns'] = power_matches
            
            readings.append(reading)
            
            # Wait for next poll
            if time.time() < end_time:
                print(f"⏳ Waiting {poll_interval} seconds for next poll...")
                time.sleep(poll_interval)
        
        # Save all readings
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"realtime_ajax_monitor_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(readings, f, indent=2)
        
        print(f"\n💾 Real-time monitoring complete. {len(readings)} readings saved to {filename}")
        return readings

def main():
    """Main monitoring function"""
    monitor = ChiliconAjaxMonitor()
    
    # Login
    if not monitor.login():
        return
    
    # Get gateway ID
    if not monitor.get_gateway_id():
        return
    
    # Try the known working endpoint first
    print("\n" + "="*60)
    print("🎯 TESTING KNOWN AJAX ENDPOINT")
    print("="*60)
    
    status_data = monitor.poll_ajax_status()
    if status_data:
        print("✅ AJAX endpoint is working!")
        
        # Save the current data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ajax_status_data_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(status_data, f, indent=2)
        print(f"💾 Data saved to {filename}")
    else:
        print("❌ AJAX endpoint not responding")
    
    # Try alternative endpoints
    print("\n" + "="*60)
    print("🔍 SEARCHING FOR ALTERNATIVE ENDPOINTS")
    print("="*60)
    
    endpoint_results = monitor.try_alternative_endpoints()
    
    working_endpoints = [r for r in endpoint_results if r.get('success')]
    print(f"\n📊 Summary: {len(working_endpoints)}/{len(endpoint_results)} endpoints working")
    
    # Start real-time monitoring if we have working endpoints
    if working_endpoints:
        print("\n" + "="*60)
        print("⏱️  STARTING REAL-TIME MONITORING")
        print("="*60)
        
        readings = monitor.monitor_realtime(duration_minutes=2, poll_interval=15)
        
        # Analyze readings for power data
        print("\n" + "="*60)
        print("📊 POWER ANALYSIS")
        print("="*60)
        
        target_power = 4.475  # kW
        
        for reading in readings:
            timestamp = reading['timestamp']
            print(f"\n📅 {timestamp}")
            
            # Look for power values
            if 'power_patterns' in reading:
                for value, unit in reading['power_patterns']:
                    power_kw = float(value)
                    if 'k' not in unit.lower():
                        power_kw /= 1000
                    
                    diff = abs(power_kw - target_power)
                    print(f"   💡 Power: {power_kw:.3f} kW (diff: {diff:.3f} kW)")
                    
                    if diff < 0.1:
                        print(f"   🎯 VERY CLOSE to target {target_power} kW!")
                    elif diff < 0.5:
                        print(f"   ⚡ Close to target {target_power} kW")
    
    print("\n✅ Monitoring complete!")

if __name__ == "__main__":
    main()
