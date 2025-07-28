#!/usr/bin/env python3
"""
Inverter ID to Hex Serial Number Converter
Converts negative inverter IDs to hex serial numbers
"""

def convert_inverter_id_to_hex(inverter_id):
    """Convert a negative inverter ID to hex serial number format"""
    try:
        # Handle negative numbers by converting to unsigned 32-bit
        if inverter_id < 0:
            # Convert to unsigned 32-bit
            unsigned_id = inverter_id + 2**32
        else:
            unsigned_id = inverter_id
        
        # Convert to hex and format as 8-character uppercase string
        hex_serial = f"{unsigned_id:08X}"
        
        return hex_serial
    except Exception as e:
        return f"Error: {e}"

def analyze_current_inverter_mapping():
    """Analyze current inverter mapping and identify any missing conversions"""
    
    # Current mapping from enhanced_dashboard.py
    current_mapping = {
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
        # Converted inverter IDs
        -1053817559: 'C1300529',  # Position 5 (hex conversion)
        1093666578: '41300712',   # Position 20 (hex conversion)
    }
    
    print("🔍 INVERTER ID TO HEX CONVERSION ANALYSIS")
    print("=" * 50)
    
    print("\n📋 CURRENT MAPPING VERIFICATION:")
    for inverter_id, expected_serial in current_mapping.items():
        calculated_hex = convert_inverter_id_to_hex(inverter_id)
        match_status = "✅" if calculated_hex == expected_serial else "❌"
        print(f"{match_status} ID: {inverter_id:>12} -> {expected_serial} (calc: {calculated_hex})")
    
    # Inverter IDs from debug file that we should check
    all_inverter_ids = [
        -1863319175, -1863319184, -1863319181, -1863319160, -1863319204,
        -1053817559, -1863319143, -1863319173, -1863319188, -1863319193,
        -1863319119, -1863319163, -1863319114, -1863319168, -1863319174,
        -1863319169, -1863319121, -1863319161, -1863319170, -1863319179,
        1093666578, -1863319123, -1863319078, -1863319180, -1863319171
    ]
    
    print(f"\n🔍 ANALYZING {len(all_inverter_ids)} INVERTER IDs FROM DEBUG DATA:")
    
    missing_mappings = []
    for inverter_id in all_inverter_ids:
        if inverter_id not in current_mapping:
            hex_serial = convert_inverter_id_to_hex(inverter_id)
            missing_mappings.append((inverter_id, hex_serial))
            print(f"❓ MISSING: {inverter_id:>12} -> {hex_serial}")
    
    if missing_mappings:
        print(f"\n⚠️  FOUND {len(missing_mappings)} UNMAPPED INVERTER IDs")
        print("\n📝 ADD THESE TO YOUR INVERTER_ID_MAP:")
        for inverter_id, hex_serial in missing_mappings:
            print(f"    {inverter_id}: '{hex_serial}',  # Convert from hex")
    else:
        print("\n✅ ALL INVERTER IDs ARE PROPERLY MAPPED!")
    
    print(f"\n🔢 SUMMARY:")
    print(f"   Total inverters in debug file: {len(all_inverter_ids)}")
    print(f"   Currently mapped: {len(current_mapping)}")
    print(f"   Missing mappings: {len(missing_mappings)}")
    
    return missing_mappings

if __name__ == "__main__":
    print("🔧 Starting Inverter ID Analysis...")
    missing = analyze_current_inverter_mapping()
    
    if missing:
        print(f"\n🚨 ACTION REQUIRED: Add {len(missing)} missing inverter mappings to enhanced_dashboard.py")
    else:
        print(f"\n🎉 All inverter IDs are properly converted and mapped!")
