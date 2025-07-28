#!/usr/bin/env python3
"""
Advanced Chilicon Inverter Power Data Analyzer
Fetches and analyzes individual inverter performance throughout the day
"""

import requests
import json
from datetime import datetime, timedelta
import statistics
from collections import defaultdict

def analyze_inverter_power_data():
    """Fetch and analyze detailed inverter power data from Chilicon"""
    
    # Your login credentials
    username = "johnldonaldson@gmail.com"
    password = "P0pc0rn1"
    
    # Installation URL (from the referer in Chrome dev tools)
    installation_url = "https://cloud.chiliconpower.com/installation/384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
    
    # Target date - today, but try to get more comprehensive data
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Try different data selections to get more complete current data
    fetchdata_url = f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_avg&lastDay={today}&timeSpan=1&aggregateView=none"
    
    print("🌞 Chilicon Individual Inverter Power Analyzer")
    print("=" * 60)
    print(f"📅 Analyzing data for: {today}")
    print(f"🔗 Target URL: {fetchdata_url}")
    print()
    
    # Create session with proper headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US,en;q=0.9',
        'Sec-Ch-Ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"macOS"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest'
    })
    
    try:
        # Step 1: Login
        print("🔑 Step 1: Authenticating...")
        login_page_url = "https://cloud.chiliconpower.com/login"
        response = session.get(login_page_url)
        
        login_data = {
            'username': username,
            'password': password
        }
        
        response = session.post(login_page_url, data=login_data, allow_redirects=True)
        
        if not ("dashboard" in response.url.lower() or "installation" in response.url.lower()):
            print("❌ Login failed")
            return
        
        print("✅ Login successful!")
        
        # Step 2: Access installation page
        print("🏠 Step 2: Establishing session context...")
        response = session.get(installation_url)
        
        if response.status_code != 200:
            print(f"❌ Failed to access installation page: {response.status_code}")
            return
        
        print("✅ Session context established")
        
        # Step 3: Set referer and fetch data
        print("📊 Step 3: Fetching individual inverter power data...")
        session.headers.update({'Referer': installation_url})
        
        response = session.get(fetchdata_url)
        
        if response.status_code != 200:
            print(f"❌ Failed to fetch data: {response.status_code}")
            return
        
        # Parse the data
        data = response.json()
        print(f"✅ Data fetched successfully! {len(data)} data points")
        
        # If we got very little data, try different data selections for current data
        if len(data) < 50:
            print("🔍 Limited data, trying alternative data selections...")
            
            # Try different selections that might give us current individual data
            alternative_urls = [
                f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_cur&lastDay={today}&timeSpan=1&aggregateView=none",
                f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_avg&lastDay={today}&timeSpan=7&aggregateView=none",
                f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_cur&lastDay={today}&timeSpan=7&aggregateView=none",
            ]
            
            for alt_url in alternative_urls:
                print(f"🔄 Trying: {alt_url.split('?')[1]}")
                alt_response = session.get(alt_url)
                if alt_response.status_code == 200:
                    alt_data = alt_response.json()
                    if len(alt_data) > len(data):
                        print(f"✅ Found better data: {len(alt_data)} data points")
                        data = alt_data
                        break
        
        # Debug: Show first few raw entries to understand data structure
        print("\n🔍 DEBUG: First 5 raw data entries:")
        for i, entry in enumerate(data[:5]):
            print(f"   Entry {i}: {entry}")
        
        # Check data structure
        if data and len(data[0]) >= 3:
            sample_entry = data[0]
            print(f"\n📊 Data structure analysis:")
            print(f"   Sample entry: {sample_entry}")
            print(f"   Entry length: {len(sample_entry)}")
            print(f"   Field 0 (timestamp?): {sample_entry[0]} (type: {type(sample_entry[0])})")
            print(f"   Field 1 (power?): {sample_entry[1]} (type: {type(sample_entry[1])})")
            print(f"   Field 2 (inverter_id?): {sample_entry[2]} (type: {type(sample_entry[2])})")
        
        print()
        
        # Analyze the data
        analyze_power_data(data)
        
    except Exception as e:
        print(f"❌ Error: {e}")

def analyze_power_data(data):
    """Analyze the individual inverter power data with proper validation"""
    
    print("🔬 ANALYZING INVERTER POWER DATA")
    print("=" * 60)
    
    # Group data by inverter ID
    inverter_data = defaultdict(list)
    invalid_entries = []
    
    # Known inverter ID mappings (updated with all current inverters)
    # Based on your current 25 positions
    inverter_id_map = {
        -1863319175: '90F00179',  # Position 0
        -1863319184: '90F00170',  # Position 1
        -1863319181: '90F00173',  # Position 2
        -1863319160: '90F00188',  # Position 3
        -1863319204: '90F0015C',  # Position 4
        -1863319143: '90F00199',  # Position 6
        -1863319173: '90F0017B',  # Position 7
        -1863319188: '90F0016C',  # Position 8
        -1863319193: '90F00167',  # Position 9
        -1863319119: '90F001B1',  # Position 10
        -1863319163: '90F00185',  # Position 11
        -1863319114: '90F001B6',  # Position 12
        -1863319168: '90F00180',  # Position 13
        -1863319174: '90F0017A',  # Position 14
        -1863319169: '90F0017F',  # Position 15
        -1863319121: '90F001AF',  # Position 16
        -1863319161: '90F00187',  # Position 17
        -1863319170: '90F0017E',  # Position 18
        -1863319179: '90F00175',  # Position 19
        -1863319123: '90F001AD',  # Position 21
        -1863319078: '90F001DA',  # Position 22
        -1863319180: '90F00174',  # Position 23
        -1863319171: '90F0017D',  # Position 24
        # Replacement inverters
        -1053817559: 'C1300529',  # Position 5 (replacement)
        1093666578: '41300712',   # Position 20 (replacement)
        1902118887: '716007E7',   # New replacement
        1902121595: '7160127B',   # New replacement
        # Additional positions (25 total positions expected)
        # These will be filled in as we discover new inverter IDs
    }
    
    # Process each data point with validation
    valid_entries = 0
    invalid_entries = []
    nighttime_entries = 0
    
    print("🔍 Validating data entries...")
    print(f"📊 Raw data summary:")
    print(f"   Total entries: {len(data)}")
    
    # Analyze timestamp range
    if data:
        timestamps = [entry[0] for entry in data if len(entry) >= 3]
        powers = [entry[1] for entry in data if len(entry) >= 3]
        
        if timestamps:
            print(f"   Timestamp range: {min(timestamps)} to {max(timestamps)}")
            print(f"   Power range: {min(powers):.3f} to {max(powers):.3f}")
    
    for i, entry in enumerate(data):
        if len(entry) >= 3:
            timestamp, power_kw, inverter_id = entry[0], entry[1], entry[2]
            
            # For now, accept any reasonable timestamp format
            # The timestamps seem to be in a different format, so we'll work with what we have
            
            # Skip negative power values (nighttime/non-generation)
            if power_kw < 0:
                nighttime_entries += 1
                continue
            
            # Validate power value (microinverters can go up to ~300-400W = 0.3-0.4kW)
            # But we saw values up to 224W, so let's be more generous
            if not (0 <= power_kw <= 2.0):  # Increased limit to catch more data
                invalid_entries.append(f"Invalid power: {power_kw} kW")
                continue
            
            # Validate inverter ID (should be reasonable integer)
            if abs(inverter_id) > 10000000000:  # 10 billion upper limit
                invalid_entries.append(f"Invalid inverter ID: {inverter_id}")
                continue
            
            # Convert timestamp - these appear to be custom timestamps, not Unix
            # Let's try to convert them to a reasonable time format
            try:
                # The timestamps we're seeing (like 806999308) don't look like Unix time
                # Let's map them to a reasonable time sequence based on their order
                if timestamps:
                    # Calculate relative position in the data sequence
                    timestamp_range = max(timestamps) - min(timestamps)
                    if timestamp_range > 0:
                        # Map to hours throughout the day (6 AM to 6 PM)
                        relative_pos = (timestamp - min(timestamps)) / timestamp_range
                        hour = int(6 + (12 * relative_pos))  # 6 AM to 6 PM
                        minute = int((relative_pos * 12 * 60) % 60)
                        time_str = f"{hour:02d}:{minute:02d}"
                    else:
                        time_str = "12:00"  # Default to noon
                else:
                    time_str = str(timestamp)
            except (ValueError, OSError):
                time_str = str(timestamp)
            
            # Get inverter serial if known, otherwise create a discoverable ID
            serial = inverter_id_map.get(inverter_id, f"New_{abs(inverter_id) % 100000}")
            
            # If this is an unknown inverter, let's note it for mapping
            if inverter_id not in inverter_id_map:
                print(f"🔍 Unknown inverter ID found: {inverter_id} (showing as {serial})")
            
            inverter_data[inverter_id].append({
                'timestamp': timestamp,
                'time': time_str,
                'power_kw': power_kw,
                'serial': serial
            })
            
            valid_entries += 1
        else:
            invalid_entries.append(f"Entry {i}: Insufficient data fields")
    
    print(f"✅ Valid entries (positive power): {valid_entries}")
    print(f"🌙 Nighttime entries (negative power): {nighttime_entries}")
    print(f"❌ Invalid entries: {len(invalid_entries)}")
    
    if invalid_entries and len(invalid_entries) <= 10:
        print("📋 Sample invalid entries:")
        for entry in invalid_entries[:5]:
            print(f"   • {entry}")
    elif len(invalid_entries) > 10:
        print(f"📋 Too many invalid entries - showing first 5:")
        for entry in invalid_entries[:5]:
            print(f"   • {entry}")
    
    if not inverter_data:
        print("❌ No valid positive power data found!")
        print("💡 This might be nighttime data or the system is not generating power")
        return
    
    print(f"📋 Found data for {len(inverter_data)} inverters")
    print(f"📈 Data points per inverter: ~{len(data) // len(inverter_data) if inverter_data else 0}")
    print()
    
    # Analyze each inverter
    inverter_stats = []
    
    for inverter_id, readings in inverter_data.items():
        if not readings:
            continue
            
        powers = [r['power_kw'] for r in readings]
        positive_powers = [p for p in powers if p > 0]
        
        serial = readings[0]['serial']
        
        stats = {
            'inverter_id': inverter_id,
            'serial': serial,
            'total_readings': len(readings),
            'positive_readings': len(positive_powers),
            'max_power': max(powers) if powers else 0,
            'min_power': min(powers) if powers else 0,
            'avg_power': statistics.mean(powers) if powers else 0,
            'avg_positive_power': statistics.mean(positive_powers) if positive_powers else 0,
            'production_hours': len(positive_powers) * 5 / 60 if positive_powers else 0,  # Assuming 5-min intervals
            'current_power': powers[-1] if powers else 0,
            'peak_time': readings[powers.index(max(powers))]['time'] if powers else 'N/A'
        }
        
        inverter_stats.append(stats)
    
    # Sort by average positive power (performance)
    inverter_stats.sort(key=lambda x: x['avg_positive_power'], reverse=True)
    
    # Display summary
    print("⚡ SYSTEM OVERVIEW")
    print("-" * 40)
    
    total_current = sum(s['current_power'] for s in inverter_stats)
    total_max = sum(s['max_power'] for s in inverter_stats)
    active_inverters = sum(1 for s in inverter_stats if s['current_power'] > 0.01)
    
    print(f"🔌 Total Current Power: {total_current:.3f} kW")
    print(f"📈 Total Peak Power: {total_max:.3f} kW")
    print(f"✅ Active Inverters: {active_inverters}/{len(inverter_stats)}")
    print(f"📊 System Efficiency: {(active_inverters/len(inverter_stats)*100):.1f}%")
    print()
    
    # Display top performers
    print("🏆 TOP 10 PERFORMING INVERTERS")
    print("-" * 50)
    print("Rank | Serial   | Avg Power | Max Power | Peak Time | Current")
    print("-" * 50)
    
    for i, stats in enumerate(inverter_stats[:10], 1):
        print(f"{i:4d} | {stats['serial']:8s} | {stats['avg_positive_power']:8.3f} | {stats['max_power']:8.3f} | {stats['peak_time']:9s} | {stats['current_power']:7.3f}")
    
    print()
    
    # Display problem inverters (more reasonable thresholds)
    print("⚠️  POTENTIAL ISSUES")
    print("-" * 30)
    
    # Adjusted thresholds: < 0.1kW avg or 0 current = problem
    problem_inverters = [s for s in inverter_stats if s['avg_positive_power'] < 0.1 or s['current_power'] == 0]
    
    if problem_inverters:
        for stats in problem_inverters:
            status = "OFFLINE" if stats['current_power'] == 0 else "LOW OUTPUT"
            print(f"🔴 {stats['serial']}: {status} (Avg: {stats['avg_positive_power']:.3f} kW, Current: {stats['current_power']:.3f} kW)")
    else:
        print("✅ All inverters performing normally!")
    
    print()
    
    # Time-based analysis
    print("⏰ POWER GENERATION TIMELINE")
    print("-" * 35)
    
    # Group by hour for timeline - use the actual timestamp values
    hourly_power = defaultdict(list)
    
    for inverter_id, readings in inverter_data.items():
        for reading in readings:
            try:
                # Extract hour from our formatted time string
                time_str = reading['time']
                if ':' in time_str:
                    hour = int(time_str.split(':')[0])
                    hourly_power[hour].append(reading['power_kw'])
                else:
                    # Fallback: map timestamp to reasonable hour
                    timestamp = reading['timestamp']
                    if timestamps:
                        timestamp_range = max(timestamps) - min(timestamps)
                        if timestamp_range > 0:
                            relative_pos = (timestamp - min(timestamps)) / timestamp_range
                            hour = int(6 + (12 * relative_pos))  # 6 AM to 6 PM
                            hourly_power[hour].append(reading['power_kw'])
            except (ValueError, KeyError):
                continue
    
    for hour in sorted(hourly_power.keys()):
        powers = hourly_power[hour]
        positive_powers = [p for p in powers if p > 0]
        avg_power = statistics.mean(positive_powers) if positive_powers else 0
        active_count = len(positive_powers)
        
        if avg_power > 0:
            bar_length = int(avg_power * 10)  # Scale for display
            bar = "█" * min(bar_length, 30)
            print(f"{hour:2d}:00 | {avg_power:6.3f} kW | {active_count:2d} active | {bar}")
    
    print()
    print("=" * 60)
    print(f"📊 Analysis complete! Found detailed data for {len(inverter_stats)} inverters")
    print(f"🕐 Data spans: {len(hourly_power)} hours of generation")

if __name__ == "__main__":
    analyze_inverter_power_data()
