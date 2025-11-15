#!/usr/bin/env python3
"""
Advanced Microinverter Power Data Hunter
Focus on finding the specific endpoint for "Average Output Power" data
"""

from legacy_chilicon_monitor import ChiliconLegacyMonitor
import json
import re
import time
from datetime import datetime, timedelta

class AdvancedMicroinverterHunter:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = 'johnldonaldson@gmail.com'
        self.password = 'P0pc0rn1'
        self.base_url = 'https://cloud.chiliconpower.com'
        self.installation_id = '384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7'
        
    def login(self):
        """Login to the system"""
        print("🔐 Logging in...")
        if not self.monitor.login(self.username, self.password):
            print("❌ Login failed")
            return False
        print("✅ Login successful!")
        return True
    
    def hunt_microinverter_endpoints(self):
        """Hunt for microinverter-specific endpoints using various strategies"""
        print("🔍 HUNTING FOR MICROINVERTER ENDPOINTS")
        print("=" * 80)
        
        if not self.login():
            return
            
        # Strategy 1: Time-based data requests (similar to working endpoint)
        print("\n📅 Strategy 1: Time-based data requests...")
        
        # Try different time formats and endpoints
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        time_formats = [
            today.strftime('%Y-%m-%d'),
            today.strftime('%m/%d/%Y'),
            today.strftime('%d-%m-%Y'),
            yesterday.strftime('%Y-%m-%d'),
            str(int(time.time())),  # Unix timestamp
            str(int(time.time() * 1000)),  # JavaScript timestamp
        ]
        
        microinverter_endpoints = [
            '/ajax/fetchMicroinverterUpdate',
            '/ajax/fetchMicroinverterPower',
            '/ajax/fetchIndividualPowerUpdate',
            '/ajax/getMicroinverterData',
            '/ajax/microinverters/power',
            '/ajax/power/individual',
            '/ajax/individual/power',
            '/ajax/chart/microinverters',
            '/ajax/microinverter/chart',
        ]
        
        for endpoint in microinverter_endpoints:
            for time_value in time_formats:
                url = self.base_url + endpoint
                
                # Try both GET and POST with different parameter names
                for method in ['GET', 'POST']:
                    for param_name in ['today', 'date', 'timestamp', 'time']:
                        try:
                            if method == 'GET':
                                response = self.monitor.session.get(
                                    url, 
                                    params={param_name: time_value}
                                )
                            else:
                                response = self.monitor.session.post(
                                    url, 
                                    data={param_name: time_value}
                                )
                            
                            if response.status_code == 200:
                                print(f"  ✅ {method} {endpoint}?{param_name}={time_value[:10]}")
                                
                                try:
                                    data = response.json()
                                    self._analyze_response_data(data, f"{endpoint}_{method}")
                                except:
                                    if len(response.text) > 100:
                                        print(f"     📄 HTML response ({len(response.text)} chars)")
                                        
                        except Exception as e:
                            continue
        
        # Strategy 2: Installation-specific endpoints
        print("\n🏠 Strategy 2: Installation-specific endpoints...")
        
        installation_endpoints = [
            f'/ajax/installation/{self.installation_id}/microinverters',
            f'/ajax/installation/{self.installation_id}/power/individual',
            f'/ajax/installation/{self.installation_id}/chart/power',
            f'/microinverters/{self.installation_id}',
            f'/microinverters/{self.installation_id}/power',
            f'/microinverters/{self.installation_id}/status',
            f'/installation/{self.installation_id}/microinverters.json',
            f'/installation/{self.installation_id}/ajax/power',
        ]
        
        for endpoint in installation_endpoints:
            try:
                url = self.base_url + endpoint
                response = self.monitor.session.get(url)
                
                if response.status_code == 200:
                    print(f"  ✅ GET {endpoint}")
                    try:
                        data = response.json()
                        self._analyze_response_data(data, endpoint)
                    except:
                        if 'microinverter' in response.text.lower():
                            print(f"     🔍 Contains microinverter content")
                            
            except Exception as e:
                continue
        
        # Strategy 3: Chart/graph-specific endpoints
        print("\n📊 Strategy 3: Chart/graph data endpoints...")
        
        chart_endpoints = [
            '/ajax/fetchBarGraphData',
            '/ajax/fetchChartData', 
            '/ajax/getChartData',
            '/ajax/chart/power',
            '/ajax/chart/individual',
            '/ajax/graphs/microinverters',
            '/ajax/fetchPowerChart',
        ]
        
        chart_params = {
            'installation': self.installation_id,
            'type': 'microinverters',
            'chart': 'power',
            'view': 'individual',
            'today': today.strftime('%Y-%m-%d'),
            'graph': 'averageOutputPower',
        }
        
        for endpoint in chart_endpoints:
            try:
                url = self.base_url + endpoint
                
                # Try with various parameter combinations
                response = self.monitor.session.post(url, data=chart_params)
                
                if response.status_code == 200:
                    print(f"  ✅ POST {endpoint}")
                    try:
                        data = response.json()
                        self._analyze_response_data(data, f"{endpoint}_chart")
                    except:
                        if len(response.text) > 50:
                            print(f"     📄 Response length: {len(response.text)}")
                            
            except Exception as e:
                continue
                
        # Strategy 4: API-style endpoints
        print("\n🔌 Strategy 4: API-style endpoints...")
        
        api_endpoints = [
            f'/api/v1/installations/{self.installation_id}/microinverters',
            f'/api/microinverters/{self.installation_id}',
            f'/api/power/individual/{self.installation_id}', 
            f'/api/installations/{self.installation_id}/power',
            f'/v1/microinverters/{self.installation_id}',
            f'/v2/installations/{self.installation_id}/power',
        ]
        
        for endpoint in api_endpoints:
            try:
                url = self.base_url + endpoint
                response = self.monitor.session.get(url)
                
                if response.status_code == 200:
                    print(f"  ✅ GET {endpoint}")
                    try:
                        data = response.json()
                        self._analyze_response_data(data, f"{endpoint}_api")
                    except:
                        print(f"     📄 Non-JSON response")
                        
            except Exception as e:
                continue
    
    def _analyze_response_data(self, data, source):
        """Analyze response data for microinverter power information"""
        try:
            if isinstance(data, dict):
                # Look for arrays that might contain power data
                for key, value in data.items():
                    if isinstance(value, list):
                        if 20 <= len(value) <= 30:  # Likely inverter count
                            # Check if values look like power data
                            try:
                                numeric_values = [float(v) for v in value if isinstance(v, (int, float))]
                                if numeric_values:
                                    total = sum(v for v in numeric_values if v > 0)
                                    if 50 <= total <= 15000:  # Reasonable power range
                                        print(f"     🎯 POWER DATA FOUND: '{key}' - {len(numeric_values)} inverters")
                                        print(f"        Total power: {total:.1f}W")
                                        print(f"        Sample values: {numeric_values[:5]}...")
                                        
                                        # Save the promising data
                                        self._save_power_data(numeric_values, source, key)
                                        return True
                            except:
                                pass
                                
            elif isinstance(data, list) and 20 <= len(data) <= 30:
                # Direct array of power values
                try:
                    numeric_values = [float(v) for v in data if isinstance(v, (int, float))]
                    if numeric_values:
                        total = sum(v for v in numeric_values if v > 0)
                        if 50 <= total <= 15000:
                            print(f"     🎯 POWER DATA FOUND: Direct array - {len(numeric_values)} inverters")
                            print(f"        Total power: {total:.1f}W") 
                            print(f"        Sample values: {numeric_values[:5]}...")
                            
                            # Save the promising data
                            self._save_power_data(numeric_values, source, "direct_array")
                            return True
                except:
                    pass
                    
        except Exception as e:
            pass
            
        return False
    
    def _save_power_data(self, power_values, source, key):
        """Save discovered power data"""
        timestamp = int(time.time())
        filename = f"discovered_power_data_{timestamp}.json"
        
        data = {
            'timestamp': timestamp,
            'datetime': datetime.now().isoformat(),
            'source': source,
            'data_key': key,
            'power_values': power_values,
            'total_power': sum(v for v in power_values if v > 0),
            'inverter_count': len(power_values),
            'avg_power_per_inverter': sum(v for v in power_values if v > 0) / len(power_values) if power_values else 0
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"        💾 Saved to: {filename}")
    
    def deep_page_analysis(self):
        """Deep analysis of the installation page JavaScript"""
        print("\n🔬 DEEP PAGE ANALYSIS")
        print("=" * 80)
        
        try:
            # Get the main installation page
            installation_url = f"{self.base_url}/installation/{self.installation_id}"
            response = self.monitor.session.get(installation_url)
            
            if response.status_code != 200:
                print(f"❌ Failed to get installation page: {response.status_code}")
                return
                
            content = response.text
            
            # Look for very specific patterns related to microinverter power
            patterns = [
                # Look for Average Output Power specifically
                r'Average\s*Output\s*Power[^}]*?(\[[^\]]+\])',
                r'averageOutputPower[^=]*?=\s*(\[[^\]]+\])',
                
                # Look for microinverter data arrays
                r'microinverter[^=]*?=\s*(\[[^\]]+\])',
                r'microInverter[^=]*?=\s*(\[[^\]]+\])',
                
                # Look for power arrays
                r'power[^=]*?=\s*(\[[\d\s,.-]{100,}\])',
                r'var\s+\w*[Pp]ower\w*\s*=\s*(\[[\d\s,.-]{100,}\])',
                
                # Look for chart data initialization
                r'chart[^{]*?series[^[]*?(\[[\d\s,.-]{100,}\])',
                r'data\s*:\s*(\[[\d\s,.-]{100,}\])',
            ]
            
            found_data = []
            
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    try:
                        # Clean up the match
                        array_str = match.strip()
                        if array_str.startswith('[') and array_str.endswith(']'):
                            # Try to parse as array
                            array_str = array_str[1:-1]  # Remove brackets
                            values = []
                            
                            for val in array_str.split(','):
                                val = val.strip()
                                try:
                                    values.append(float(val))
                                except:
                                    continue
                            
                            if 20 <= len(values) <= 30:
                                total = sum(v for v in values if v > 0)
                                if 50 <= total <= 15000:
                                    print(f"  🎯 Found promising array: {len(values)} values")
                                    print(f"     Total: {total:.1f}W, Pattern: {pattern[:50]}...")
                                    print(f"     Sample: {values[:5]}...")
                                    
                                    found_data.append({
                                        'pattern': pattern,
                                        'values': values,
                                        'total': total
                                    })
                                    
                                    # Save this data
                                    self._save_power_data(values, "javascript_extraction", "pattern_match")
                    except:
                        continue
            
            if not found_data:
                print("  ❌ No microinverter power arrays found in JavaScript")
                
                # Save the page for manual analysis
                timestamp = int(time.time())
                filename = f"installation_page_source_{timestamp}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"  💾 Page source saved to: {filename}")
                
        except Exception as e:
            print(f"❌ Deep analysis error: {e}")
    
    def run_hunt(self):
        """Run the complete hunting process"""
        print("🚀 ADVANCED MICROINVERTER POWER DATA HUNT")
        print("=" * 80)
        
        self.hunt_microinverter_endpoints()
        self.deep_page_analysis()
        
        print("\n" + "=" * 80)
        print("🏁 HUNT COMPLETE")
        print("Check any generated JSON files for discovered power data.")
        print("If no data was found, the individual microinverter power may require:")
        print("  • Browser-based JavaScript execution")
        print("  • Special authentication or timing")
        print("  • Different parameter combinations")

def main():
    hunter = AdvancedMicroinverterHunter()
    hunter.run_hunt()

if __name__ == "__main__":
    main()
