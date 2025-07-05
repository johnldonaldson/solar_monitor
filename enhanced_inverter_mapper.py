#!/usr/bin/env python3
"""
Enhanced Microinverter Mapping System
Improved serial number to power mapping with multiple data sources
"""

import json
import re
from datetime import datetime
from legacy_chilicon_monitor import ChiliconLegacyMonitor


class EnhancedInverterMapper:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = "johnldonaldson@gmail.com"
        self.password = "P0pc0rn1"
        self.installation_url = (
            "https://cloud.chiliconpower.com/installation/"
            "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
        )
        
    def extract_all_javascript_arrays(self, page_content):
        """Extract all JavaScript arrays that might contain inverter data"""
        arrays = {}
        
        # Look for various array patterns
        patterns = [
            r'var\s+(\w+)\s*=\s*(\[[^\]]*\])',
            r'(\w+):\s*(\[[^\]]*\])',
            r'\.(\w+)\s*=\s*(\[[^\]]*\])',
            r'"(\w+)":\s*(\[[^\]]*\])',
        ]
        
        for pattern in patterns:
            matches = re.finditer(
                pattern, page_content, re.IGNORECASE | re.MULTILINE
            )
            for match in matches:
                var_name = match.group(1)
                array_content = match.group(2)
                
                # Try to parse as JSON
                try:
                    parsed_array = json.loads(array_content)
                    if (isinstance(parsed_array, list) and
                            len(parsed_array) > 0):
                        arrays[var_name] = parsed_array
                except json.JSONDecodeError:
                    continue
        
        return arrays
    
    def find_serial_power_correlations(self, arrays, serial_numbers):
        """Find correlations between serial numbers and power arrays"""
        correlations = {}
        
        for array_name, array_data in arrays.items():
            if not isinstance(array_data, list):
                continue
                
            # Check if array length matches expected inverter count
            if len(array_data) != len(serial_numbers):
                continue
            
            # Check if array contains numeric values (potential power data)
            if all(isinstance(x, (int, float)) for x in array_data):
                correlations[array_name] = {
                    'data': array_data,
                    'type': 'numeric',
                    'length': len(array_data),
                    'max_value': max(array_data) if array_data else 0,
                    'sum': sum(array_data) if array_data else 0
                }
            
            # Check if array contains objects with power-like properties
            elif all(isinstance(x, dict) for x in array_data):
                sample = array_data[0] if array_data else {}
                power_keys = [
                    k for k in sample.keys()
                    if 'power' in k.lower() or 'watt' in k.lower()
                ]
                if power_keys:
                    correlations[array_name] = {
                        'data': array_data,
                        'type': 'object',
                        'power_keys': power_keys,
                        'length': len(array_data)
                    }
        
        return correlations
    
    def create_enhanced_inverter_map(self):
        """Create enhanced mapping with multiple data sources"""
        try:
            # Login
            if not self.monitor.login(self.username, self.password):
                return None
            
            # Get page content
            response = self.monitor.session.get(self.installation_url)
            if response.status_code != 200:
                return None
            
            page_content = response.text
            
            # Extract serial numbers using existing method
            serials = self.monitor.extract_serial_numbers(page_content)
            if not serials:
                print("❌ No serial numbers found")
                return None
            
            print(f"🔍 Found {len(serials)} serial numbers")
            
            # Extract all JavaScript arrays
            arrays = self.extract_all_javascript_arrays(page_content)
            print(f"📊 Found {len(arrays)} JavaScript arrays")
            
            # Find correlations
            correlations = self.find_serial_power_correlations(arrays, serials)
            print(f"🔗 Found {len(correlations)} potential power correlations")
            
            # Try to get real-time power data from AJAX
            power_data = self.monitor.get_power_data(self.installation_url)
            current_total_power = (
                power_data.get('current_power_kw', 0) if power_data else 0
            )
            
            # Create enhanced mapping
            enhanced_map = {
                'timestamp': datetime.now().isoformat(),
                'total_inverters': len(serials),
                'current_total_power_kw': current_total_power,
                'serial_numbers': serials,
                'javascript_arrays': arrays,
                'power_correlations': correlations,
                'inverter_map': []
            }
            
            # Try to map individual inverters
            best_power_array = self.find_best_power_array(
                correlations, current_total_power
            )
            
            if best_power_array:
                print(f"✅ Found best power array: {best_power_array['name']}")
                power_values = best_power_array['data']
                
                for i, serial in enumerate(serials):
                    power = power_values[i] if i < len(power_values) else 0
                    
                    # Convert power to watts if needed
                    if isinstance(power, (int, float)):
                        # Assume values > 10 are in watts, < 10 are in kW
                        power_watts = power if power > 10 else power * 1000
                    else:
                        power_watts = 0
                    
                    enhanced_map['inverter_map'].append({
                        'index': i,
                        'serial': serial,
                        'power_watts': power_watts,
                        'power_kw': power_watts / 1000,
                        'status': 'active' if power_watts > 10 else 'inactive',
                        'data_source': best_power_array['name']
                    })
            else:
                print("⚠️ No suitable power array found, creating basic map")
                # Create basic map without power data
                for i, serial in enumerate(serials):
                    enhanced_map['inverter_map'].append({
                        'index': i,
                        'serial': serial,
                        'power_watts': 0,
                        'power_kw': 0,
                        'status': 'unknown',
                        'data_source': 'none'
                    })
            
            # Add health analysis
            active_count = sum(
                1 for inv in enhanced_map['inverter_map']
                if inv['status'] == 'active'
            )
            enhanced_map['health_analysis'] = {
                'active_inverters': active_count,
                'inactive_inverters': len(serials) - active_count,
                'activity_rate': active_count / len(serials) if serials else 0,
                'total_mapped_power': sum(
                    inv['power_watts'] for inv in enhanced_map['inverter_map']
                ),
                'health_status': self.calculate_health_status(
                    active_count, len(serials)
                )
            }
            
            return enhanced_map
            
        except Exception as e:
            print(f"❌ Error creating enhanced inverter map: {e}")
            return None
    
    def find_best_power_array(self, correlations, target_total_power):
        """Find the best power array that matches current total power"""
        target_watts = target_total_power * 1000  # Convert to watts
        
        best_match = None
        best_score = float('inf')
        
        for name, correlation in correlations.items():
            if correlation['type'] != 'numeric':
                continue
            
            data = correlation['data']
            array_sum = sum(data)
            
            # Check different interpretations of the data
            interpretations = [
                ('watts', array_sum),
                ('kilowatts', array_sum * 1000),
                ('normalized', array_sum * target_watts / max(array_sum, 1))
            ]
            
            for interp_name, interpreted_sum in interpretations:
                diff = abs(interpreted_sum - target_watts)
                score = diff / max(target_watts, 1)  # Relative error
                
                # Within 50% is acceptable
                if score < best_score and score < 0.5:
                    best_score = score
                    best_match = {
                        'name': f"{name}_{interp_name}",
                        'data': data if interp_name == 'watts' else [x * 1000 for x in data] if interp_name == 'kilowatts' else [x * target_watts / max(array_sum, 1) for x in data],
                        'score': score,
                        'interpretation': interp_name
                    }
        
        return best_match
    
    def calculate_health_status(self, active_count, total_count):
        """Calculate system health status"""
        if total_count == 0:
            return "Unknown"
        
        activity_rate = active_count / total_count
        
        if activity_rate >= 0.95:
            return "Excellent"
        elif activity_rate >= 0.85:
            return "Good"
        elif activity_rate >= 0.70:
            return "Warning"
        else:
            return "Critical"

def main():
    """Test the enhanced inverter mapper"""
    print("🔧 Enhanced Microinverter Mapping System")
    print("=" * 50)
    
    mapper = EnhancedInverterMapper()
    enhanced_map = mapper.create_enhanced_inverter_map()
    
    if enhanced_map:
        print(f"\n✅ Enhanced mapping created successfully!")
        print(f"📊 Total Inverters: {enhanced_map['total_inverters']}")
        print(f"⚡ Current Total Power: {enhanced_map['current_total_power_kw']:.3f} kW")
        print(f"🔴 Active Inverters: {enhanced_map['health_analysis']['active_inverters']}")
        print(f"⚫ Inactive Inverters: {enhanced_map['health_analysis']['inactive_inverters']}")
        print(f"📈 Activity Rate: {enhanced_map['health_analysis']['activity_rate']:.1%}")
        print(f"🏥 Health Status: {enhanced_map['health_analysis']['health_status']}")
        
        # Show first 5 inverters as sample
        print(f"\n🔍 Sample Inverter Data (first 5):")
        for i, inv in enumerate(enhanced_map['inverter_map'][:5]):
            print(f"  #{i+1}: {inv['serial'][:8]}... -> {inv['power_watts']:.1f}W ({inv['status']})")
        
        # Show arrays found
        print(f"\n📊 JavaScript Arrays Found:")
        for name, data in enhanced_map['javascript_arrays'].items():
            if isinstance(data, list) and len(data) > 0:
                sample = data[0] if len(data) > 0 else "empty"
                print(f"  {name}: {len(data)} items, sample: {str(sample)[:50]}...")
        
        # Show correlations
        print(f"\n🔗 Power Correlations:")
        for name, corr in enhanced_map['power_correlations'].items():
            print(f"  {name}: {corr['type']}, {corr['length']} items")
            if corr['type'] == 'numeric':
                print(f"    Sum: {corr['sum']:.1f}, Max: {corr['max_value']:.1f}")
        
        # Save the enhanced map
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"enhanced_inverter_map_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(enhanced_map, f, indent=2)
        
        print(f"\n💾 Enhanced map saved to: {filename}")
        
    else:
        print("❌ Failed to create enhanced mapping")

if __name__ == "__main__":
    main()
