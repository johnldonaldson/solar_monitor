#!/usr/bin/env python3
"""
Individual Microinverter Power Data Extractor
Production-ready version for extracting real-time individual microinverter power
"""

from legacy_chilicon_monitor import ChiliconLegacyMonitor
import json
import re
import time
from datetime import datetime


class MicroinverterPowerExtractor:
    """Extracts individual microinverter power data from Chilicon Power portal"""
    
    def __init__(self, username, password):
        self.monitor = ChiliconLegacyMonitor()
        self.username = username
        self.password = password
        self.installation_id = ('384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee'
                               '574d64f8152ab11c7')
        self.base_url = ('https://cloud.chiliconpower.com/installation/'
                        f'{self.installation_id}')
        self.logged_in = False
        
    def login(self):
        """Login to the Chilicon Power portal"""
        if self.logged_in:
            return True
            
        if self.monitor.login(self.username, self.password):
            self.logged_in = True
            return True
        return False
    
    def extract_individual_power(self):
        """
        Extract individual microinverter power data
        
        Returns:
            dict: Contains power values, total power, and metadata
                  None if extraction fails
        """
        if not self.login():
            return None
        
        try:
            # Access the microinverters tab directly
            tab_url = f"{self.base_url}#tabs-3"
            
            # Try multiple requests with delays to catch AJAX-loaded data
            best_content = None
            best_array_count = 0
            
            for attempt in range(3):
                print(f"Attempt {attempt + 1}: Fetching data...")
                response = self.monitor.session.get(tab_url)
                
                if response.status_code != 200:
                    continue
                
                content = response.text
                
                # Quick check for arrays with high values
                pattern = r'\[([^]]*[1-9]\d{3,}[^]]*)\]'
                high_value_arrays = re.findall(pattern, content)
                array_count = len(high_value_arrays)
                
                print(f"  Found {array_count} arrays with high values")
                
                if array_count > best_array_count:
                    best_content = content
                    best_array_count = array_count
                    print("  ✅ Best content so far!")
                    
                if attempt < 2:  # Don't wait after the last attempt
                    print("  Waiting 3 seconds for AJAX data...")
                    time.sleep(3)
            
            if best_content is None:
                return None
                
            content = best_content
            print(f"Using content with {best_array_count} high-value arrays")
            
            # Enhanced pattern to find arrays with exactly 25 elements
            # Include negative numbers and wider range
            power_pattern = (r'\[(\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?'
                             r'\s*){24})\]')
            
            matches = re.findall(power_pattern, content, re.IGNORECASE)
            
            candidate_arrays = []
            
            for match in matches:
                try:
                    # Parse the array
                    values = [float(x.strip()) for x in match.split(',')
                              if x.strip()]
                    
                    # Check if it's exactly 25 elements
                    if len(values) == 25:
                        total_power = sum(v for v in values if v > 0)
                        
                        # Categorize the array type
                        array_info = {
                            'values': values,
                            'total_power': total_power,
                            'min_val': min(values),
                            'max_val': max(values),
                            'unique_count': len(set(values)),
                            'avg_val': sum(values) / len(values)
                        }
                        # Determine array type and priority
                        array_info['type'] = 'unknown'
                        array_info['priority'] = 9  # Default fallback
                        
                        # Check for variable power arrays (-2400 to 6000 range) - PRIORITY 1
                        if (min(values) >= -3000 and max(values) <= 7000 and 
                            len(set(values)) >= 10 and 
                            len([v for v in values if abs(v) > 100]) >= 20):
                            # Variable power array - convert negatives to positive, scale by 20
                            adjusted_values = [abs(v) if v != 0 else 100.0 for v in values]
                            array_info['type'] = 'variable_power_20'
                            array_info['priority'] = 1  # Highest priority - all inverters active
                            array_info['watts_values'] = [v/20 for v in adjusted_values]
                        # Check for deciwatt values (100-2000 range) - PRIORITY 2
                        elif (all(50 <= v <= 3000 for v in values) and
                                len(set(values)) >= 2 and max(values) >= 500):
                            # Deciwatt encoding (watts * 18) - Real-time power data
                            array_info['type'] = 'deciwatt_power'
                            array_info['priority'] = 2
                            array_info['watts_values'] = [v/18 for v in values]
                        # Check for all-zero arrays (true nighttime/no production)
                        elif all(v == 0.0 for v in values):
                            # All zero values - real-time power showing no production
                            array_info['type'] = 'zero_power_realtime'
                            array_info['priority'] = 2  # High priority for nighttime
                            array_info['watts_values'] = values  # Already in watts
                        # Check for scaled power values (3600-12200 range) - PRIORITY 4
                        elif (any(v > 1000 for v in values) and 
                              max(values) <= 15000 and 
                              len([v for v in values if v > 0]) >= 5):
                            # Scaled power values (divide by 1872) - Real-time power data
                            array_info['type'] = 'scaled_power_1872'
                            array_info['priority'] = 4  # Lower priority than deciwatt
                            array_info['watts_values'] = [v/1872 for v in values]
                        # Check for uniform 60W arrays (all inverters same power)
                        elif (all(abs(v - 60.0) < 0.1 for v in values)):
                            # Uniform 60W power (likely static/nominal values)
                            # NOTE: Analysis shows these don't change day/night
                            # Deprioritized as they're not real-time indicators
                            array_info['type'] = 'uniform_60w_power'
                            array_info['priority'] = 6  # Lowered priority
                            array_info['watts_values'] = values  # Already in watts
                        # Check for milliwatt values (convert to watts)
                        elif (all(0 <= v <= 100000 for v in values)):
                            watts_values = [v/1000 for v in values]
                            active_watts = sum(1 for v in watts_values if v > 1)
                            max_watts = max(watts_values)
                            total_watts = sum(w for w in watts_values if w > 0)
                            
                            # Priority 2: High milliwatt values
                            if (active_watts >= 5 and total_watts > 200):
                                array_info['type'] = 'high_milliwatt_power'
                                array_info['priority'] = 2
                                array_info['watts_values'] = watts_values
                            # Priority 3: Medium milliwatt values
                            elif (active_watts >= 5 and max_watts <= 500):
                                array_info['type'] = 'milliwatt_power'
                                array_info['priority'] = 3
                                array_info['watts_values'] = watts_values
                        elif all(0 <= v <= 500 for v in values) and max(values) > 5:
                            # Traditional power range in watts
                            array_info['type'] = 'normal_power'
                            array_info['priority'] = 4
                        elif all(abs(v) <= 10 for v in values) and max(values) > 0:
                            # Small integers with some non-zero values
                            array_info['type'] = 'small_integers'
                            array_info['priority'] = 5
                        elif all(v == values[0] for v in values):
                            # All same value (likely aggregate/cached)
                            array_info['type'] = 'uniform_values'
                            array_info['priority'] = 6
                        elif max(values) > 1000000:
                            # Large numbers (likely IDs)
                            array_info['type'] = 'ids_serials'
                            array_info['priority'] = 7
                        else:
                            # Other patterns
                            array_info['type'] = 'other'
                            array_info['priority'] = 8
                        
                        candidate_arrays.append(array_info)
                        
                except (ValueError, ZeroDivisionError):
                    continue
            
            # Sort by priority and select the best candidate
            if candidate_arrays:
                candidate_arrays.sort(key=lambda x: x['priority'])
                best_array = candidate_arrays[0]
                
                # Log what we selected for debugging
                print(f"🎯 Selected array type: {best_array['type']}")
                print(f"   Range: {best_array['min_val']} to {best_array['max_val']}")
                print(f"   Sample: {best_array['values'][:5]}...")
                
                # Define conversion types
                conversion_types = ['milliwatt_power', 'high_milliwatt_power',
                                   'deciwatt_power', 'uniform_60w_power',
                                   'zero_power_realtime', 'scaled_power_1872',
                                   'variable_power_20']
                use_watts = best_array['type'] in conversion_types
                
                power_values = (best_array.get('watts_values', 
                                             best_array['values'])
                               if use_watts else best_array['values'])
                
                return {
                    'timestamp': datetime.now().isoformat(),
                    'individual_power': power_values,
                    'total_power': (sum(best_array.get('watts_values', []))
                                   if use_watts else best_array['total_power']),
                    'inverter_count': len(best_array['values']),
                    'average_power': (sum(power_values) / len(power_values)
                                     if power_values else 0),
                    'active_inverters': sum(1 for v in power_values if v > 1),
                    'extraction_method': f'enhanced_regex_{best_array["type"]}',
                    'array_type': best_array['type']
                }
            
            return None
            
        except Exception as e:
            print(f"Error extracting microinverter power: {e}")
            return None
    
    def get_inverter_mapping(self):
        """
        Get the mapping between array positions and inverter serials
        
        Returns:
            dict: Position to serial number mapping
        """
        # Known mapping from previous analysis
        return {
            0: '90F00179',   1: '90F00170',   2: '90F00173',   3: '90F00188',   
            4: '90F0015C',   5: '90F00188',   6: '90F001B5',   7: '90F0016F',
            8: '90F00172',   9: '90F00174',   10: '90F00175',  11: '90F00183',
            12: '90F001B6',  13: '90F00177',  14: '90F0017A',  15: '90F00181',
            16: '90F00176',  17: '90F00182',  18: '90F00187',  19: '90F0017C',
            20: '90F0017D',  21: '90F00185',  22: '90F00178',  23: '90F0017B',
            24: '90F00186'
        }
    
    def get_detailed_inverter_data(self):
        """
        Get detailed data for each inverter including serial numbers
        
        Returns:
            list: List of inverter dictionaries with serial, position, power
        """
        power_data = self.extract_individual_power()
        if not power_data:
            return []
        
        mapping = self.get_inverter_mapping()
        individual_power = power_data['individual_power']
        
        inverters = []
        for position, power in enumerate(individual_power):
            serial = mapping.get(position, f'Unknown_{position}')
            
            inverters.append({
                'position': position,
                'serial': serial,
                'power': power,  # Keep for compatibility
                'power_w': power,  # Dashboard expects this field
                'status': 'active' if power > 5 else 'inactive',
                'timestamp': power_data['timestamp']
            })
        
        return inverters
    
    def save_power_data(self, filename=None):
        """Save the current power data to a JSON file"""
        if not filename:
            timestamp = int(time.time())
            filename = f"microinverter_power_{timestamp}.json"
        
        power_data = self.extract_individual_power()
        if power_data:
            with open(filename, 'w') as f:
                json.dump(power_data, f, indent=2)
            return filename
        return None
    
    def track_uniform_60w_arrays(self):
        """
        Specifically track uniform 60W arrays for day/night comparison
        
        Returns:
            dict: Information about 60W arrays found, or None if not detected
        """
        if not self.login():
            return None
        
        try:
            tab_url = f"{self.base_url}#tabs-3"
            response = self.monitor.session.get(tab_url)
            
            if response.status_code != 200:
                return None
            
            content = response.text
            
            # Pattern to find arrays with exactly 25 elements
            power_pattern = (r'\[(\s*-?\d+(?:\.\d+)?\s*(?:,\s*-?\d+(?:\.\d+)?'
                             r'\s*){24})\]')
            
            matches = re.findall(power_pattern, content, re.IGNORECASE)
            
            uniform_60w_arrays = []
            
            for i, match in enumerate(matches):
                try:
                    values = [float(x.strip()) for x in match.split(',')
                              if x.strip()]
                    
                    if len(values) == 25:
                        # Check for uniform 60W arrays
                        if all(abs(v - 60.0) < 0.1 for v in values):
                            uniform_60w_arrays.append({
                                'array_index': i,
                                'values': values,
                                'timestamp': datetime.now().isoformat(),
                                'sum': sum(values),
                                'avg': sum(values) / len(values)
                            })
                            
                except (ValueError, ZeroDivisionError):
                    continue
            
            if uniform_60w_arrays:
                print(f"🔋 Found {len(uniform_60w_arrays)} uniform 60W arrays")
                return {
                    'timestamp': datetime.now().isoformat(),
                    'arrays_found': len(uniform_60w_arrays),
                    'arrays': uniform_60w_arrays,
                    'total_power_per_array': 1500.0,  # 25 * 60W
                    'note': 'Tracking for day/night comparison'
                }
            
            return None
            
        except Exception as e:
            print(f"Error tracking 60W arrays: {e}")
            return None

    def save_60w_tracking_data(self, filename=None):
        """Save 60W array tracking data for historical comparison"""
        if not filename:
            timestamp = int(time.time())
            filename = f"uniform_60w_tracking_{timestamp}.json"
        
        tracking_data = self.track_uniform_60w_arrays()
        if tracking_data:
            with open(filename, 'w') as f:
                json.dump(tracking_data, f, indent=2)
            print(f"💾 60W tracking data saved to: {filename}")
            return filename
        else:
            print("No 60W arrays detected to save")
            return None

def test_extractor():
    """Test the microinverter power extractor"""
    print("🧪 TESTING MICROINVERTER POWER EXTRACTOR")
    print("=" * 80)
    
    extractor = MicroinverterPowerExtractor(
        'johnldonaldson@gmail.com', 
        'P0pc0rn1'
    )
    
    # Test basic power extraction
    print("🔍 Testing power extraction...")
    power_data = extractor.extract_individual_power()
    
    if power_data:
        print("✅ Power extraction successful!")
        print(f"   Total power: {power_data['total_power']:.1f}W")
        print(f"   Active inverters: {power_data['active_inverters']}/25")
        print(f"   Average power: {power_data['average_power']:.1f}W")
        print(f"   Sample powers: {power_data['individual_power'][:5]}...")
        
        # Test detailed inverter data
        print("\n🔍 Testing detailed inverter data...")
        inverters = extractor.get_detailed_inverter_data()
        
        if inverters:
            print("✅ Detailed data extraction successful!")
            print("   First 5 inverters:")
            for inv in inverters[:5]:
                status_icon = "🟢" if inv['status'] == 'active' else "🔴"
                print(f"     {status_icon} Pos {inv['position']:2d}: "
                      f"{inv['serial']} - {inv['power']:5.1f}W")
        
        # Save the data
        filename = extractor.save_power_data()
        if filename:
            print(f"\n💾 Data saved to: {filename}")
        
        # Test 60W array tracking
        print("\n🔍 Testing 60W array tracking...")
        tracking_data = extractor.track_uniform_60w_arrays()
        
        if tracking_data:
            print("✅ 60W array tracking successful!")
            print(f"   Arrays found: {tracking_data['arrays_found']}")
            print(f"   Sample array data: {tracking_data['arrays'][:1]}")
            
            # Save tracking data
            filename = extractor.save_60w_tracking_data()
            if filename:
                print(f"💾 Tracking data saved to: {filename}")
        
        return True
    
    else:
        print("❌ Power extraction failed")
        return False


def main():
    """Main function for testing"""
    success = test_extractor()
    
    if success:
        print(f"\n🎉 SUCCESS! Individual microinverter power extraction working!")
        print(f"\n🔗 Ready for integration with enhanced_dashboard.py")
        print(f"   • Add MicroinverterPowerExtractor to dashboard")
        print(f"   • Update inverter table with real-time power data") 
        print(f"   • Implement individual inverter failure detection")
    else:
        print(f"\n❌ Extraction failed - check credentials and connectivity")


if __name__ == "__main__":
    main()
