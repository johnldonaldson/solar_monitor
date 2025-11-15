#!/usr/bin/env python3
"""
Real-time Power Monitor
Continuously monitors for the highest power values to catch dynamic updates
"""

from final_microinverter_extractor import MicroinverterPowerExtractor
import time
from datetime import datetime


def monitor_realtime_power(duration_minutes=5):
    """Monitor power values continuously for the specified duration"""
    print(f"🔄 CONTINUOUS POWER MONITORING")
    print(f"=" * 60)
    print(f"⏱️  Monitoring for {duration_minutes} minutes...")
    print(f"🎯 Looking for power values higher than 12.20W")
    
    extractor = MicroinverterPowerExtractor(
        'johnldonaldson@gmail.com', 
        'P0pc0rn1'
    )
    
    max_power_seen = 0
    best_data = None
    check_count = 0
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    while time.time() < end_time:
        check_count += 1
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n🕐 Check #{check_count} at {current_time}")
        
        try:
            # Get current power data
            power_data = extractor.extract_individual_power()
            
            if power_data:
                current_max = max(power_data['individual_power'])
                total_power = power_data['total_power']
                active_count = power_data['active_inverters']
                
                print(f"   📊 Current max: {current_max:.2f}W")
                print(f"   ⚡ Total: {total_power:.1f}W") 
                print(f"   🔋 Active: {active_count}/25")
                
                # Track the highest values seen
                if current_max > max_power_seen:
                    max_power_seen = current_max
                    best_data = power_data.copy()
                    print(f"   🆕 NEW HIGH: {current_max:.2f}W!")
                    
                    # Show the detailed data for high values
                    if current_max > 20:  # Higher than expected
                        detailed_data = extractor.get_detailed_inverter_data()
                        print(f"   📋 High-power inverters:")
                        for inv in detailed_data:
                            if inv['power_w'] > 15:
                                print(f"      {inv['serial']}: {inv['power_w']:.2f}W")
                
                # Look for any changes in the extraction method or array type
                if hasattr(power_data, 'array_type'):
                    print(f"   🎯 Array type: {power_data.get('array_type', 'unknown')}")
                
            else:
                print(f"   ❌ No data extracted")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Wait before next check
        if time.time() < end_time:
            print(f"   ⏳ Waiting 30 seconds...")
            time.sleep(30)
    
    print(f"\n" + "=" * 60)
    print(f"📈 MONITORING SUMMARY:")
    print(f"   🕐 Duration: {duration_minutes} minutes")
    print(f"   🔍 Total checks: {check_count}")
    print(f"   🏆 Highest power seen: {max_power_seen:.2f}W")
    
    if best_data:
        print(f"\n📊 BEST DATA CAPTURED:")
        print(f"   📅 Timestamp: {best_data['timestamp']}")
        print(f"   ⚡ Max individual: {max_power_seen:.2f}W")
        print(f"   🔋 Total power: {best_data['total_power']:.1f}W")
        print(f"   🟢 Active inverters: {best_data['active_inverters']}/25")
        print(f"   🎯 Method: {best_data.get('extraction_method', 'unknown')}")
        
        # Save the best data
        import json
        filename = f"best_power_data_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(best_data, f, indent=2)
        print(f"   💾 Saved to: {filename}")
    
    return best_data


if __name__ == "__main__":
    monitor_realtime_power(duration_minutes=3)  # Monitor for 3 minutes
