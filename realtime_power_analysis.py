#!/usr/bin/env python3
"""
Real-time Power Analysis - Find the correct array matching browser display
"""

import requests
import re
import json
from datetime import datetime
import time

class RealtimePowerAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.gateway_id = None
        
    def login(self, username, password):
        """Login to Chilicon Power"""
        try:
            # Get login page and CSRF token
            login_page = self.session.get('https://cloud.chiliconpower.com/login')
            csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page.text)
            
            if not csrf_match:
                print("❌ Could not find CSRF token")
                return False
                
            csrf_token = csrf_match.group(1)
            print(f"✅ Found CSRF token: {csrf_token[:20]}...")
            
            # Submit login
            login_data = {
                'csrfmiddlewaretoken': csrf_token,
                'username': username,
                'password': password
            }
            
            response = self.session.post('https://cloud.chiliconpower.com/login', 
                                       data=login_data,
                                       allow_redirects=True)
            
            if 'dashboard' in response.url:
                print("✅ Login successful!")
                return True
            else:
                print("❌ Login failed")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def analyze_all_power_arrays(self, installation_url):
        """Analyze all power arrays to find the real-time one"""
        try:
            print("🔍 Fetching installation page...")
            response = self.session.get(installation_url)
            page_content = response.text
            
            # Extract gateway ID
            gateway_match = re.search(r'gateway["\']?\s*:\s*["\']([^"\']+)["\']', page_content)
            if gateway_match:
                self.gateway_id = gateway_match.group(1)
                print(f"🌐 Gateway ID: {self.gateway_id[:20]}...")
            
            # Find all microinverter arrays with multiple patterns
            patterns = [
                r'microinverter_(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'var\s+microinverter_(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'microinverter(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'(\d+):\s*\[([\d\s,.-]+)\]',
                r'array_(\d+)\s*=\s*\[([\d\s,.-]+)\]'
            ]
            
            arrays = []
            for pattern in patterns:
                found = re.findall(pattern, page_content)
                arrays.extend(found)
                if found:
                    print(f"  Found {len(found)} arrays with pattern: {pattern}")
            
            # Also search for any numeric arrays
            general_array_pattern = r'\[(\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?){10,})\]'
            general_arrays = re.findall(general_array_pattern, page_content)
            
            print(f"  Found {len(general_arrays)} general numeric arrays")
            
            # Add general arrays with index
            for i, array_data in enumerate(general_arrays):
                arrays.append((f"general_{i}", array_data))
            
            print(f"📊 Found {len(arrays)} microinverter arrays")
            
            array_analysis = []
            
            for array_id, array_data in arrays:
                try:
                    # Parse the array values
                    values = [float(x.strip()) for x in array_data.split(',') if x.strip()]
                    
                    if values:
                        total_power = sum(values)
                        avg_power = total_power / len(values)
                        max_power = max(values)
                        min_power = min(values)
                        non_zero_count = len([v for v in values if v > 0])
                        
                        analysis = {
                            'array_id': int(array_id),
                            'device_count': len(values),
                            'total_power_w': total_power,
                            'total_power_kw': round(total_power / 1000, 3),
                            'avg_power_w': round(avg_power, 2),
                            'max_power_w': max_power,
                            'min_power_w': min_power,
                            'active_devices': non_zero_count,
                            'sample_values': values[:5],
                            'all_values': values,
                            'is_realistic': self.is_realistic_power_array(values, total_power)
                        }
                        
                        array_analysis.append(analysis)
                        
                        print(f"  Array {array_id}: {len(values)} devices, {total_power/1000:.2f} kW total")
                        print(f"    Sample values: {values[:5]}")
                        print(f"    Realistic: {'✅' if analysis['is_realistic'] else '❌'}")
                        
                except Exception as e:
                    print(f"  ⚠️ Error parsing array {array_id}: {e}")
                    continue
            
            # Sort by how realistic they are and power level
            realistic_arrays = [a for a in array_analysis if a['is_realistic']]
            realistic_arrays.sort(key=lambda x: abs(x['total_power_kw'] - 4.47))  # Sort by closeness to target
            
            print(f"\n🎯 POWER ARRAY ANALYSIS (Target: 4.47 kW)")
            print("=" * 60)
            
            for i, array in enumerate(array_analysis):
                status = "🎯 BEST MATCH" if i == 0 and array in realistic_arrays else ""
                print(f"Array {array['array_id']}: {array['total_power_kw']} kW ({array['active_devices']}/{array['device_count']} active) {status}")
                
                if array['total_power_kw'] > 3.0 and array['total_power_kw'] < 8.0:  # Reasonable range
                    print(f"  ⭐ CANDIDATE: Close to target 4.47 kW!")
                    print(f"  Individual powers: {array['sample_values'][:10]}...")
            
            # Save detailed analysis
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"realtime_power_analysis_{timestamp}.json"
            
            analysis_data = {
                'timestamp': datetime.now().isoformat(),
                'target_power_kw': 4.47,
                'gateway_id': self.gateway_id,
                'total_arrays_found': len(arrays),
                'realistic_arrays': len(realistic_arrays),
                'array_analysis': array_analysis,
                'best_candidates': [a for a in array_analysis if 3.0 < a['total_power_kw'] < 8.0]
            }
            
            with open(filename, 'w') as f:
                json.dump(analysis_data, f, indent=2)
            print(f"\n💾 Analysis saved to: {filename}")
            
            # Return the best candidate
            candidates = [a for a in array_analysis if 3.0 < a['total_power_kw'] < 8.0]
            if candidates:
                best = min(candidates, key=lambda x: abs(x['total_power_kw'] - 4.47))
                print(f"\n🏆 BEST MATCH: Array {best['array_id']} with {best['total_power_kw']} kW")
                return best
            else:
                print("❌ No arrays found in reasonable power range")
                return None
                
        except Exception as e:
            print(f"❌ Error analyzing arrays: {e}")
            return None
    
    def is_realistic_power_array(self, values, total_power):
        """Determine if a power array looks realistic"""
        if not values:
            return False
            
        # Check for reasonable individual values (5W to 400W per inverter)
        reasonable_values = [v for v in values if 5 <= v <= 400]
        if len(reasonable_values) < len(values) * 0.5:  # At least 50% reasonable
            return False
            
        # Check for reasonable total power (0.5kW to 10kW for residential system)
        total_kw = total_power / 1000
        if not (0.5 <= total_kw <= 10.0):
            return False
            
        # Check for variation (not all identical values)
        unique_values = len(set(values))
        if unique_values < 2 and total_power > 100:  # Allow identical for very low power
            return False
            
        return True

def main():
    """Main analysis function"""
    USERNAME = "johnldonaldson@gmail.com"
    PASSWORD = "P0pc0rn1"
    INSTALLATION_URL = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
    
    analyzer = RealtimePowerAnalyzer()
    
    print("🔌 Real-time Power Array Analyzer")
    print("=" * 50)
    print(f"🎯 Target Power: 4.47 kW (from browser)")
    print("=" * 50)
    
    # Login
    if not analyzer.login(USERNAME, PASSWORD):
        return
    
    # Analyze all arrays
    best_array = analyzer.analyze_all_power_arrays(INSTALLATION_URL)
    
    if best_array:
        print(f"\n✅ SUCCESS: Found array {best_array['array_id']} with {best_array['total_power_kw']} kW")
        print(f"   Difference from browser: {abs(best_array['total_power_kw'] - 4.47):.2f} kW")
        print(f"   Active devices: {best_array['active_devices']}/{best_array['device_count']}")
        print(f"   Average per device: {best_array['avg_power_w']:.1f} W")
    else:
        print("\n❌ Could not find a good matching array")

if __name__ == "__main__":
    main()
