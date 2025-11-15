#!/usr/bin/env python3
"""
Enhanced Real-Time Microinverter Power Extractor
Looks for dynamic/AJAX loaded power data with higher values
"""

from legacy_chilicon_monitor import ChiliconLegacyMonitor
import json
import re
import time
from datetime import datetime


def extract_realtime_power_advanced():
    """Advanced extraction with multiple attempts and wider patterns"""
    monitor = ChiliconLegacyMonitor()
    
    if not monitor.login('johnldonaldson@gmail.com', 'P0pc0rn1'):
        print("❌ Login failed")
        return None
    
    installation_id = '384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7'
    
    # Try multiple URLs and approaches
    urls_to_try = [
        f"https://cloud.chiliconpower.com/installation/{installation_id}#tabs-3",
        f"https://cloud.chiliconpower.com/installation/{installation_id}",
        f"https://cloud.chiliconpower.com/ajax/fetchOwnerUpdate?today={datetime.now().strftime('%Y-%m-%d')}",
    ]
    
    all_arrays = []
    
    for url in urls_to_try:
        try:
            print(f"🌐 Trying URL: {url}")
            response = monitor.session.get(url)
            
            if response.status_code == 200:
                content = response.text
                print(f"📄 Content length: {len(content)}")
                
                # Enhanced patterns to find arrays of 25 values
                patterns = [
                    # Standard pattern with wider range
                    r'\[(\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*){24})\]',
                    # Pattern for arrays with decimal values
                    r'\[(\s*-?\d+\.\d+\s*(?:,\s*-?\d+\.\d+\s*){24})\]',
                    # Pattern for arrays in JSON objects
                    r'"[^"]*":\s*\[(\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?\s*){24})\]',
                ]
                
                for i, pattern in enumerate(patterns):
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    print(f"  Pattern {i+1}: {len(matches)} matches")
                    
                    for j, match in enumerate(matches):
                        try:
                            values = [float(x.strip()) for x in match.split(',') if x.strip()]
                            
                            if len(values) == 25:
                                max_val = max(values)
                                min_val = min(values)
                                total = sum(v for v in values if v > 0)
                                unique_count = len(set(values))
                                
                                # Check if this could contain 51.13W (as 51130 milliwatts)
                                contains_high_values = any(40000 <= v <= 60000 for v in values)
                                
                                array_info = {
                                    'source_url': url,
                                    'pattern_id': f"pattern_{i+1}_match_{j+1}",
                                    'values': values,
                                    'min': min_val,
                                    'max': max_val,
                                    'total': total,
                                    'unique_count': unique_count,
                                    'contains_high_values': contains_high_values,
                                    'watts_if_milliwatts': [v/1000 for v in values]
                                }
                                
                                all_arrays.append(array_info)
                                
                                print(f"    🎯 Array {array_info['pattern_id']}: {min_val} to {max_val}")
                                if contains_high_values:
                                    print(f"        ⚡ HIGH VALUES DETECTED! (40-60k range)")
                                    print(f"        As watts: {[f'{v/1000:.2f}W' for v in values if 40000 <= v <= 60000]}")
                                
                        except (ValueError, IndexError):
                            continue
                
                # Wait a bit for any dynamic content
                time.sleep(2)
            else:
                print(f"  ❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Find the best array with highest values
    if all_arrays:
        # Sort by maximum value to find the most current/highest power array
        high_power_arrays = [arr for arr in all_arrays if arr['max'] > 20000]
        
        if high_power_arrays:
            best_array = max(high_power_arrays, key=lambda x: x['max'])
            print(f"\n🏆 BEST HIGH-POWER ARRAY FOUND:")
            print(f"   Source: {best_array['source_url']}")
            print(f"   Pattern: {best_array['pattern_id']}")
            print(f"   Range: {best_array['min']} to {best_array['max']}")
            print(f"   As watts: {min(best_array['watts_if_milliwatts']):.2f}W to {max(best_array['watts_if_milliwatts']):.2f}W")
            
            # Show individual inverter values in watts
            print(f"\n📊 INDIVIDUAL INVERTER VALUES (Watts):")
            watts_values = best_array['watts_if_milliwatts']
            for i in range(0, 25, 5):
                row = watts_values[i:i+5]
                print(f"   Pos {i:2d}-{min(i+4,24):2d}: {[f'{v:6.2f}W' for v in row]}")
            
            return {
                'individual_power': watts_values,
                'total_power': sum(w for w in watts_values if w > 1),
                'active_inverters': sum(1 for w in watts_values if w > 1),
                'max_power': max(watts_values),
                'source': best_array['source_url'],
                'timestamp': datetime.now().isoformat()
            }
    
    print("❌ No high-power arrays found")
    return None


def main():
    print("🔍 ADVANCED REAL-TIME POWER EXTRACTION")
    print("=" * 80)
    
    result = extract_realtime_power_advanced()
    
    if result:
        print(f"\n🎉 SUCCESS! Found current power data:")
        print(f"   Max power: {result['max_power']:.2f}W")
        print(f"   Total power: {result['total_power']:.1f}W")
        print(f"   Active inverters: {result['active_inverters']}/25")
        print(f"   Source: {result['source']}")
        
        # Save the result
        with open('realtime_power_data.json', 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n💾 Data saved to: realtime_power_data.json")
    else:
        print(f"\n❌ Could not find current high-power data")


if __name__ == "__main__":
    main()
