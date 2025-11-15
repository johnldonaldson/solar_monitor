#!/usr/bin/env python3
"""
Enhanced Array Monitor for Real-Time Microinverter Data
Intelligently selects the best real-time power array from multiple options
"""

from legacy_chilicon_monitor import ChiliconLegacyMonitor
import re
import json
from datetime import datetime


class EnhancedArrayMonitor:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = "johnldonaldson@gmail.com"
        self.password = "P0pc0rn1"
        self.installation_url = (
            "https://cloud.chiliconpower.com/installation/"
            "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
        )
        
        # Known power array characteristics for selection
        self.array_selection_criteria = {
            'min_inverters_active': 5,     # At least 5 inverters should be producing
            'min_total_power': 1000,       # At least 1kW total
            'max_individual_power': 400,   # No inverter should exceed 400W
            'reasonable_variance': True,    # Values should vary (not all the same)
        }
    
    def login(self):
        """Login to Chilicon system"""
        print("🔐 Logging in to Chilicon...")
        return self.monitor.login(self.username, self.password)
    
    def get_all_arrays(self):
        """Extract all arrays from the installation page"""
        try:
            print("🌐 Fetching installation page...")
            response = self.monitor.session.get(self.installation_url)
            if response.status_code != 200:
                print(f"❌ Failed to fetch page: {response.status_code}")
                return None
            
            page_content = response.text
            
            # Extract all potential microinverter arrays
            all_arrays = {}
            
            # Pattern for JavaScript arrays with exactly 25 elements
            js_array_pattern = r'\[(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?){24})\]'
            js_arrays = re.findall(js_array_pattern, page_content)
            
            for k, js_array in enumerate(js_arrays):
                try:
                    values = [float(x.strip()) for x in js_array.split(',') if x.strip()]
                    if len(values) == 25:
                        all_arrays[f'js_array_{k}'] = values
                except:
                    continue
            
            return all_arrays
            
        except Exception as e:
            print(f"❌ Error extracting arrays: {e}")
            return None
    
    def analyze_array_quality(self, array_name, values):
        """Analyze an array to determine if it's good for real-time monitoring"""
        try:
            if not values or len(values) != 25:
                return {'score': 0, 'reason': 'Wrong size or empty'}
            
            # Calculate metrics
            positive_values = [v for v in values if v > 0]
            active_count = len([v for v in values if v > 5])  # > 5W considered active
            total_power = sum(positive_values)
            max_power = max(values) if values else 0
            min_power = min(positive_values) if positive_values else 0
            avg_power = sum(positive_values) / len(positive_values) if positive_values else 0
            
            # Calculate variance (are values different?)
            unique_values = len(set(values))
            variance_score = min(unique_values / 25, 1.0)  # Higher is better
            
            # Check against criteria
            score = 0
            reasons = []
            
            # Active inverters criterion
            if active_count >= self.array_selection_criteria['min_inverters_active']:
                score += 30
                reasons.append(f"✅ {active_count} active inverters")
            else:
                reasons.append(f"❌ Only {active_count} active inverters")
            
            # Total power criterion
            if total_power >= self.array_selection_criteria['min_total_power']:
                score += 25
                reasons.append(f"✅ Total power {total_power:.0f}W")
            else:
                reasons.append(f"❌ Total power too low: {total_power:.0f}W")
            
            # Max individual power criterion
            if max_power <= self.array_selection_criteria['max_individual_power']:
                score += 20
                reasons.append(f"✅ Max individual: {max_power:.0f}W")
            else:
                reasons.append(f"❌ Max individual too high: {max_power:.0f}W")
            
            # Variance criterion (not all the same value) - CRITICAL for real-time data
            if variance_score > 0.3:  # At least 30% unique values
                score += 25  # Increased weight
                reasons.append(f"✅ Good variance ({unique_values} unique values)")
            else:
                score -= 20  # Penalty for low variance
                reasons.append(f"❌ Low variance ({unique_values} unique values)")
            
            # Penalize arrays where all values are identical (definitely not real-time)
            if unique_values == 1 and max_power > 0:
                score -= 30
                reasons.append(f"❌ All identical values - likely not real-time")
            
            # Reasonable power range for real solar production
            if 100 <= avg_power <= 250:  # More realistic average for solar
                score += 15
                reasons.append(f"✅ Realistic avg: {avg_power:.0f}W")
            elif 50 <= avg_power <= 300:  # Acceptable range
                score += 5
                reasons.append(f"✅ Acceptable avg: {avg_power:.0f}W")
            else:
                score -= 10
                reasons.append(f"❌ Unusual avg power: {avg_power:.0f}W")
            
            return {
                'score': score,
                'reasons': reasons,
                'active_count': active_count,
                'total_power': total_power,
                'max_power': max_power,
                'avg_power': avg_power,
                'variance_score': variance_score
            }
            
        except Exception as e:
            return {'score': 0, 'reason': f'Analysis error: {e}'}
    
    def select_best_real_time_array(self, all_arrays):
        """Select the best array for real-time monitoring"""
        if not all_arrays:
            return None, None
        
        print(f"\n🔍 ANALYZING {len(all_arrays)} ARRAYS FOR REAL-TIME SUITABILITY:")
        print("=" * 80)
        
        array_scores = []
        
        for array_name, values in all_arrays.items():
            analysis = self.analyze_array_quality(array_name, values)
            array_scores.append((array_name, values, analysis))
            
            print(f"\n📊 {array_name}:")
            print(f"   Score: {analysis['score']}/100")
            if 'reasons' in analysis:
                for reason in analysis['reasons']:
                    print(f"   {reason}")
            elif 'reason' in analysis:
                print(f"   {analysis['reason']}")
        
        # Sort by score and select the best
        array_scores.sort(key=lambda x: x[2]['score'], reverse=True)
        
        if array_scores and array_scores[0][2]['score'] > 50:
            best_name, best_values, best_analysis = array_scores[0]
            print(f"\n🎯 SELECTED ARRAY: {best_name}")
            print(f"   Final Score: {best_analysis['score']}/100")
            print(f"   Active Inverters: {best_analysis['active_count']}/25")
            print(f"   Total Power: {best_analysis['total_power']:.0f}W")
            return best_name, best_values
        else:
            print("\n❌ No suitable real-time array found")
            return None, None
    
    def get_enhanced_inverter_data(self):
        """Get enhanced real-time inverter data using the best array"""
        try:
            if not self.login():
                return None
            
            all_arrays = self.get_all_arrays()
            if not all_arrays:
                return None
            
            best_array_name, best_values = self.select_best_real_time_array(all_arrays)
            if not best_values:
                return None
            
            # Map to known serial numbers
            position_to_serial = {
                0: '90F00179',   1: '90F00170',   2: '90F00173',   3: '90F00188',   4: '90F0015C',
                5: 'Unknown_6',  6: '90F00199',   7: '90F0017B',   8: '90F0016C',   9: '90F00167',
                10: '90F001B1',  11: '90F00185',  12: '90F001B6',  13: '90F00180',  14: '90F0017A',
                15: '90F0017F',  16: '90F001AF',  17: '90F00187',  18: '90F0017E',  19: '90F00175',
                20: 'Unknown_21', 21: '90F001AD', 22: '90F001DA',  23: '90F00174',  24: '90F0017D',
            }
            
            # Create inverter data
            inverter_data = []
            for i, power in enumerate(best_values):
                serial = position_to_serial.get(i, f'Unknown_{i+1}')
                status = "🟢 Producing" if power > 5 else "🔴 Inactive"
                
                inverter_data.append({
                    'serial': serial,
                    'power_w': float(power),
                    'status': status,
                    'index': i,
                    'position': i + 1
                })
            
            # Create summary
            active_inverters = [inv for inv in inverter_data if inv['power_w'] > 5]
            total_power = sum(inv['power_w'] for inv in inverter_data)
            
            result = {
                'timestamp': datetime.now().isoformat(),
                'source_array': best_array_name,
                'total_power_w': total_power,
                'active_inverters': len(active_inverters),
                'total_inverters': len(inverter_data),
                'inverter_map': inverter_data,
                'health_status': 'Good' if len(active_inverters) >= 20 else 'Warning' if len(active_inverters) >= 15 else 'Critical'
            }
            
            print(f"\n✅ ENHANCED DATA EXTRACTED:")
            print(f"   Source: {best_array_name}")
            print(f"   Total Power: {total_power:.1f}W")
            print(f"   Active: {len(active_inverters)}/25 inverters")
            print(f"   Health: {result['health_status']}")
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting enhanced data: {e}")
            import traceback
            traceback.print_exc()
            return None

def main():
    """Test the enhanced array monitor"""
    monitor = EnhancedArrayMonitor()
    
    print("🚀 ENHANCED ARRAY MONITOR TEST")
    print("=" * 50)
    
    data = monitor.get_enhanced_inverter_data()
    
    if data:
        # Save the data
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"enhanced_array_data_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n💾 Data saved to: {filename}")
        
        # Show top performers
        active_inverters = [inv for inv in data['inverter_map'] if inv['power_w'] > 5]
        if active_inverters:
            top_performers = sorted(active_inverters, key=lambda x: x['power_w'], reverse=True)[:5]
            print(f"\n🏆 TOP 5 PERFORMERS:")
            for inv in top_performers:
                print(f"   {inv['serial']}: {inv['power_w']:.1f}W")
    else:
        print("❌ Failed to get enhanced data")

if __name__ == "__main__":
    main()
