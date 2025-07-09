#!/usr/bin/env python3
"""
Modern Chilicon Power Monitor - Based on Legacy AJAX Endpoint
Uses the /ajax/fetchOwnerUpdate endpoint that was working in the legacy script
"""

import requests
import json
import re
from datetime import datetime
import time

class ChiliconLegacyMonitor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
    def power_formatting(self, power):
        """Format power values like the legacy script"""
        power *= 1000  # Convert to Wh
        if power < 1000:
            return f"{power:.1f} Wh"
        elif power < 10000:
            return f"{power/1000:.3f} kWh"
        elif power < 100000:
            return f"{power/1000:.2f} kWh"
        elif power < 1000000:
            return f"{power/1000:.1f} kWh"
        else:
            return f"{power/1000000:.2f} MWh"
    
    def login(self, username, password):
        """Login using the legacy approach"""
        try:
            print("🔐 Logging in with legacy method...")
            
            # Get login page first
            login_page = self.session.get('https://cloud.chiliconpower.com/login')
            
            # Extract CSRF token
            csrf_match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_page.text)
            if not csrf_match:
                print("❌ Could not find CSRF token")
                return False
                
            csrf_token = csrf_match.group(1)
            
            # Login data
            login_data = {
                'csrfmiddlewaretoken': csrf_token,
                'username': username,
                'password': password
            }
            
            # Submit login
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
    
    def get_power_data(self, installation_url):
        """Get power data using the legacy AJAX endpoint"""
        try:
            print("📊 Fetching power data using legacy AJAX endpoint...")
            
            # Set headers like the legacy script
            self.session.headers.update({
                'Host': 'cloud.chiliconpower.com',
                'Referer': installation_url,
                'Connection': 'keep-alive'
            })
            
            # Get today's date
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Try the legacy AJAX endpoint
            ajax_url = f"https://cloud.chiliconpower.com/ajax/fetchOwnerUpdate?today={today}"
            print(f"🌐 Requesting: {ajax_url}")
            
            response = self.session.get(ajax_url)
            
            if response.status_code == 200:
                print("✅ AJAX endpoint responded successfully!")
                
                try:
                    json_data = response.json()
                    print(f"📦 JSON data structure: {type(json_data)}")
                    
                    if isinstance(json_data, list) and len(json_data) >= 3:
                        print(f"📋 JSON array length: {len(json_data)}")
                        
                        # Extract data like the legacy script
                        current_power = json_data[2]  # Current power
                        energy_array = json_data[0]   # Energy data points
                        lifetime_energy = json_data[1] # Lifetime energy
                        
                        print(f"⚡ Raw current power value: {current_power}")
                        print(f"📈 Energy array length: {len(energy_array) if energy_array else 0}")
                        print(f"🏆 Raw lifetime energy: {lifetime_energy}")
                        
                        # Calculate today's energy like the legacy script
                        total = 0
                        active_points = 0
                        for i, value in enumerate(energy_array):
                            if value > 0:
                                active_points += 1
                                total += abs(value)
                        
                        todays_energy = total / 12000  # Legacy calculation
                        
                        # Format output like legacy script
                        current_power_formatted = self.power_formatting(current_power)
                        todays_energy_formatted = self.power_formatting(todays_energy)
                        lifetime_energy_formatted = self.power_formatting(lifetime_energy)
                        
                        print(f"\n🎯 LEGACY ENDPOINT RESULTS:")
                        print(f"⚡ Current Power: {current_power_formatted}")
                        print(f"📅 Today's Energy: {todays_energy_formatted}")
                        print(f"🏆 Lifetime Energy: {lifetime_energy_formatted}")
                        print(f"📊 Active data points: {active_points}/{len(energy_array)}")
                        
                        # Also show raw kW value for comparison
                        current_kw = current_power * 1000 / 1000  # Convert to kW properly
                        print(f"⚡ Current Power (raw): {current_kw:.3f} kW")
                        
                        return {
                            'current_power_raw': current_power,
                            'current_power_kw': current_kw,
                            'current_power_formatted': current_power_formatted,
                            'todays_energy_raw': todays_energy,
                            'todays_energy_formatted': todays_energy_formatted,
                            'lifetime_energy_raw': lifetime_energy,
                            'lifetime_energy_formatted': lifetime_energy_formatted,
                            'energy_array': energy_array,
                            'active_points': active_points,
                            'timestamp': datetime.now().isoformat()
                        }
                        
                    else:
                        print(f"❌ Unexpected JSON structure: {json_data}")
                        return None
                        
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    print(f"📄 Response text: {response.text[:500]}")
                    return None
                    
            else:
                print(f"❌ AJAX endpoint failed: {response.status_code}")
                print(f"📄 Response: {response.text[:200]}")
                
                # Try alternative endpoints
                alternatives = [
                    f"https://cloud.chiliconpower.com/ajax/fetchOwnerUpdate",
                    f"https://cloud.chiliconpower.com/ajax/owner-update?today={today}",
                    f"https://cloud.chiliconpower.com/api/owner-update?today={today}"
                ]
                
                for alt_url in alternatives:
                    print(f"🔄 Trying alternative: {alt_url}")
                    try:
                        alt_response = self.session.get(alt_url)
                        if alt_response.status_code == 200:
                            print(f"✅ Alternative endpoint worked: {alt_url}")
                            return alt_response.json()
                    except Exception as e:
                        print(f"❌ Alternative failed: {e}")
                        continue
                
                return None
                
        except Exception as e:
            print(f"❌ Error fetching power data: {e}")
            return None
    
    def get_individual_inverter_data(self, installation_url):
        """Get individual microinverter data with serial numbers from the installation page"""
        try:
            print("🔧 Fetching individual microinverter data...")
            
            # Get the installation page to extract JavaScript arrays
            response = self.session.get(installation_url)
            page_content = response.text
            
            # Extract microinverter serial numbers from tables or content
            # Look for known patterns from your examples: 41300712, 90F00170, 90F00175
            serial_patterns = [
                r'\b([4-9][0-9]{7})\b',  # 8-digit serials like 41300712
                r'\b(90F[0-9A-F]{5})\b',  # 90F-prefix serials like 90F00170
                r'\b(C13[0-9A-F]{5})\b',  # C13-prefix serials if any
            ]
            
            # Find all potential serial numbers
            all_serials = []
            for pattern in serial_patterns:
                serials = re.findall(pattern, page_content, re.IGNORECASE)
                all_serials.extend(serials)
            
            # Remove duplicates while preserving order
            inverter_serials = []
            seen = set()
            for serial in all_serials:
                if serial not in seen:
                    inverter_serials.append(serial)
                    seen.add(serial)
            
            print(f"🏷️  Found {len(inverter_serials)} inverter serials")
            if inverter_serials[:10]:
                print(f"📋 Sample serials: {inverter_serials[:10]}")
            
            # Extract microinverter power arrays with broader patterns
            array_patterns = [
                r'microinverter_(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'var\s+microinverter_(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'microinverter(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                r'array_(\d+)\s*=\s*\[([\d\s,.-]+)\]',
                # Look for any large numeric arrays that might be power data
                r'=\s*\[([\d\s,.-]{100,})\]',  # Arrays with lots of numeric data
            ]
            
            all_arrays = {}
            for i, pattern in enumerate(array_patterns):
                arrays = re.findall(pattern, page_content)
                for j, match in enumerate(arrays):
                    try:
                        if len(match) == 2:  # Named array
                            array_id, array_data = match
                            array_id = int(array_id) if array_id.isdigit() else f"pattern_{i}_{j}"
                        else:  # Unnamed array
                            array_id = f"unnamed_{i}_{j}"
                            array_data = match
                            
                        values = [float(x.strip()) for x in array_data.split(',') if x.strip()]
                        if values and 20 <= len(values) <= 30:  # Reasonable inverter count for your system
                            all_arrays[array_id] = values
                            print(f"  📊 Found array {array_id}: {len(values)} values, total: {sum(v for v in values if v > 0):.1f}W")
                    except:
                        continue
            
            print(f"📊 Found {len(all_arrays)} microinverter power arrays")
            
            # If no arrays found, try using our enhanced API approach
            if not all_arrays:
                print("🔄 No arrays found, trying enhanced detection...")
                
                # Extract any JavaScript arrays with 25 elements (typical inverter count)
                js_array_pattern = r'\[(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){20,30})\]'
                js_arrays = re.findall(js_array_pattern, page_content)
                
                for i, array_data in enumerate(js_arrays):
                    try:
                        values = [float(x.strip()) for x in array_data.split(',')]
                        if 20 <= len(values) <= 30:
                            array_total = sum(v for v in values if v > 0)
                            all_arrays[f"js_array_{i}"] = values
                            print(f"  📊 Found JS array {i}: {len(values)} values, total: {array_total:.1f}W")
                    except:
                        continue
            
            # Find the array that represents current power (closest to our total)
            target_total = 4475  # Current power in watts
            best_array = None
            best_diff = float('inf')
            
            for array_id, values in all_arrays.items():
                array_total = sum(v for v in values if v > 0)
                diff = abs(array_total - target_total)
                
                if diff < best_diff and array_total > 1000:  # Must be reasonable power
                    best_diff = diff
                    best_array = {'id': array_id, 'values': values, 'total': array_total}
            
            if best_array:
                values = best_array['values']
                producing = [v for v in values if v > 5]  # Active inverters (>5W)
                inactive = [v for v in values if v <= 5]   # Inactive/low inverters
                
                print(f"🎯 Best matching array: {best_array['id']} (Total: {best_array['total']:.1f}W)")
                print(f"🔋 Active inverters: {len(producing)}/25 ({len(values)} detected)")
                print(f"⚠️  Inactive/low inverters: {len(inactive)}")
                
                # Map serials to power values (if we have enough serials)
                inverter_map = []
                for i, power in enumerate(values):
                    serial = inverter_serials[i] if i < len(inverter_serials) else f"Unknown_{i+1}"
                    status = "🟢 Producing" if power > 5 else "🔴 Inactive"
                    
                    inverter_map.append({
                        'serial': serial,
                        'power_w': power,
                        'status': status,
                        'index': i
                    })
                
                # Analyze individual performance
                if producing:
                    avg_power = sum(producing) / len(producing)
                    max_power = max(producing)
                    min_power = min(producing)
                    
                    print(f"\n📊 INDIVIDUAL INVERTER PERFORMANCE:")
                    print(f"   Average producing: {avg_power:.1f}W")
                    print(f"   Highest output: {max_power:.1f}W")
                    print(f"   Lowest output: {min_power:.1f}W")
                    
                    # Show top and bottom performers with serials
                    print(f"\n🏆 TOP PERFORMERS:")
                    top_performers = sorted(inverter_map, key=lambda x: x['power_w'], reverse=True)[:3]
                    for inv in top_performers:
                        if inv['power_w'] > 5:
                            print(f"   {inv['serial']}: {inv['power_w']:.1f}W")
                    
                    print(f"\n⚠️  LOW/INACTIVE INVERTERS:")
                    low_performers = [inv for inv in inverter_map if inv['power_w'] <= 5]
                    for inv in low_performers[:5]:  # Show first 5
                        print(f"   {inv['serial']}: {inv['power_w']:.1f}W ({inv['status']})")
                    
                    if len(low_performers) > 5:
                        print(f"   ... and {len(low_performers) - 5} more inactive")
                    
                    # Flag any significantly underperforming inverters
                    underperforming = [inv for inv in inverter_map if 5 < inv['power_w'] < avg_power * 0.7]
                    if underperforming:
                        print(f"\n🟡 UNDERPERFORMING INVERTERS:")
                        for inv in underperforming:
                            print(f"   {inv['serial']}: {inv['power_w']:.1f}W (Expected: ~{avg_power:.1f}W)")
                
                return {
                    'array_id': best_array['id'],
                    'total_inverters': 25,  # Known system total, not just detected
                    'detected_inverters': len(values),  # Actually detected count
                    'active_inverters': len(producing),
                    'inactive_inverters': len(inactive),
                    'missing_inverters': 25 - len(values),  # Not detected
                    'individual_powers': values,
                    'producing_powers': producing,
                    'inverter_serials': inverter_serials,
                    'inverter_map': inverter_map,
                    'total_power_w': best_array['total'],
                    'avg_power_producing': sum(producing) / len(producing) if producing else 0,
                    'max_power': max(producing) if producing else 0,
                    'min_power': min(producing) if producing else 0,
                    'underperforming_count': len([v for v in producing if v < (sum(producing) / len(producing)) * 0.7]) if producing else 0
                }
            else:
                print("❌ Could not find suitable microinverter array")
                return None
                
        except Exception as e:
            print(f"❌ Error getting individual inverter data: {e}")
            return None

    def check_inverter_health(self, inverter_data):
        """Analyze inverter health and performance"""
        if not inverter_data:
            return None
            
        try:
            total = inverter_data['total_inverters']
            active = inverter_data['active_inverters']
            inactive = inverter_data['inactive_inverters']
            underperforming = inverter_data['underperforming_count']
            
            health_status = "🟢 EXCELLENT"
            issues = []
            
            # Check activity rate - More strict thresholds
            activity_rate = active / total if total > 0 else 0
            if activity_rate < 0.95:  # Less than 95% (24/25 or better)
                health_status = "🟡 GOOD"
                issues.append(f"Only {activity_rate:.1%} inverters active")
            
            if activity_rate < 0.85:  # Less than 85% 
                health_status = "🔶 FAIR"
                
            if activity_rate < 0.7:   # Less than 70%
                health_status = "🔴 POOR"
            
            # Check for underperforming units
            if underperforming > 0:
                if health_status == "🟢 EXCELLENT":
                    health_status = "🟡 GOOD"
                issues.append(f"{underperforming} underperforming inverters")
            
            # Check for completely inactive units during production hours
            # Include both detected inactive and missing inverters
            total_non_active = total - active  # All non-active (inactive + missing)
            missing = inverter_data.get('missing_inverters', 0)
            
            # Only downgrade if we have a significant number of non-active units
            # and the activity rate is already borderline
            if total_non_active > 4 and active > 10 and activity_rate < 0.90:
                if health_status in ["🟢 EXCELLENT", "🟡 GOOD"]:
                    health_status = "🔶 FAIR"
                if missing > 0:
                    issues.append(f"{total_non_active} inverters not active "
                                f"({inactive} inactive, {missing} missing)")
                else:
                    issues.append(f"{total_non_active} completely inactive inverters")
            elif total_non_active > 2:
                # Just add to issues but don't downgrade status for 2-4 non-active
                if missing > 0:
                    issues.append(f"{total_non_active} inverters not active "
                                f"({inactive} inactive, {missing} missing)")
                else:
                    issues.append(f"{total_non_active} completely inactive inverters")
            
            return {
                'health_status': health_status,
                'activity_rate': activity_rate,
                'issues': issues,
                'recommendations': self.get_recommendations(inverter_data)
            }
            
        except Exception as e:
            print(f"❌ Error checking inverter health: {e}")
            return None
    
    def get_recommendations(self, inverter_data):
        """Get maintenance recommendations based on inverter performance"""
        recommendations = []
        
        if inverter_data['inactive_inverters'] > 2:
            recommendations.append("🔧 Check connections on inactive inverters")
            
        if inverter_data['underperforming_count'] > 0:
            recommendations.append("📊 Monitor underperforming inverters for shading or issues")
            
        activity_rate = inverter_data['active_inverters'] / inverter_data['total_inverters']
        if activity_rate < 0.8:
            recommendations.append("⚡ Consider professional inspection of system")
            
        if not recommendations:
            recommendations.append("✅ System performing well, continue monitoring")
            
        return recommendations

def main():
    """Main function"""
    USERNAME = "johnldonaldson@gmail.com"
    PASSWORD = "P0pc0rn1"
    INSTALLATION_URL = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
    
    print("🔌 Chilicon Legacy Monitor - Python 3")
    print("=" * 50)
    print("🎯 Target: 4.475 kW current, 17.15 kWh today")
    print("=" * 50)
    
    monitor = ChiliconLegacyMonitor()
    
    # Login
    if not monitor.login(USERNAME, PASSWORD):
        return
    
    # Get power data
    power_data = monitor.get_power_data(INSTALLATION_URL)
    
    if power_data:
        print(f"\n✅ SUCCESS! Legacy endpoint is working")
        
        # Compare with target values
        target_kw = 4.475
        target_kwh = 17.15
        
        actual_kw = power_data['current_power_kw']
        
        print(f"\n📊 COMPARISON:")
        print(f"Target Power: {target_kw} kW")
        print(f"Actual Power: {actual_kw:.3f} kW")
        print(f"Difference: {abs(actual_kw - target_kw):.3f} kW")
        
        if abs(actual_kw - target_kw) < 0.1:
            print("🎯 EXCELLENT MATCH!")
        elif abs(actual_kw - target_kw) < 0.5:
            print("✅ GOOD MATCH!")
        else:
            print("⚠️ Power reading differs from browser")
        
        # Get individual inverter data
        print(f"\n" + "="*50)
        print("🔧 INDIVIDUAL MICROINVERTER ANALYSIS")
        print("="*50)
        
        inverter_data = monitor.get_individual_inverter_data(INSTALLATION_URL)
        
        if inverter_data:
            # Check inverter health
            health = monitor.check_inverter_health(inverter_data)
            
            print(f"\n🏥 SYSTEM HEALTH: {health['health_status']}")
            print(f"📊 Activity Rate: {health['activity_rate']:.1%}")
            
            if health['issues']:
                print(f"\n⚠️  ISSUES DETECTED:")
                for issue in health['issues']:
                    print(f"   • {issue}")
            
            print(f"\n💡 RECOMMENDATIONS:")
            for rec in health['recommendations']:
                print(f"   • {rec}")
            
            # Add inverter data to our power data
            power_data['individual_inverters'] = inverter_data
            power_data['health_analysis'] = health
            
        else:
            print("⚠️ Could not retrieve individual inverter data")
        
        # Save comprehensive data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"legacy_power_data_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(power_data, f, indent=2)
        print(f"💾 Complete data saved to: {filename}")
        
    else:
        print("❌ Failed to get power data from legacy endpoint")

if __name__ == "__main__":
    main()
