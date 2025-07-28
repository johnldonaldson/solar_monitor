#!/usr/bin/env python3
"""
Inverter Management Utility
Helps manage inverter ID mappings in the Enhanced Chilicon Dashboard
"""

import json
import os
import re
from datetime import datetime


def convert_inverter_id_to_hex(inverter_id):
    """Convert inverter ID to hex serial number format"""
    try:
        inverter_id = int(inverter_id)
        if inverter_id > 0:
            hex_serial = f"{inverter_id:08X}"
        else:
            hex_serial = f"{(inverter_id + 2**32):08X}"
        return hex_serial
    except Exception as e:
        return f"Error: {e}"


def get_current_inverter_mapping():
    """Extract current inverter mapping from enhanced_dashboard.py"""
    try:
        with open('/Users/johndona/Git_Repositories/JesusCalling/enhanced_dashboard.py', 'r') as f:
            content = f.read()
        
        # Find the inverter_id_map section
        pattern = r'inverter_id_map\s*=\s*{([^}]+)}'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            print("❌ Could not find inverter_id_map in enhanced_dashboard.py")
            return {}
        
        mapping_text = match.group(1)
        
        # Parse the mapping (simplified parsing)
        mapping = {}
        for line in mapping_text.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                try:
                    # Extract ID and serial
                    parts = line.split(':')
                    inverter_id = int(parts[0].strip())
                    serial = parts[1].split("'")[1].strip()
                    mapping[inverter_id] = serial
                except:
                    continue
        
        return mapping
        
    except Exception as e:
        print(f"❌ Error reading current mapping: {e}")
        return {}


def add_inverter_to_mapping(inverter_id, serial, description="Manual addition"):
    """Add a new inverter to the mapping in enhanced_dashboard.py"""
    try:
        inverter_id = int(inverter_id)
        
        # Validate serial format
        if not re.match(r'^[0-9A-F]{8}$', serial.upper()):
            print(f"❌ Invalid serial format: {serial}. Must be 8 hex characters.")
            return False
        
        serial = serial.upper()
        
        # Read current file
        file_path = '/Users/johndona/Git_Repositories/JesusCalling/enhanced_dashboard.py'
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Find the end of the current mapping
        pattern = r'(inverter_id_map\s*=\s*{[^}]+)(}\s*)'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            print("❌ Could not find inverter_id_map to update")
            return False
        
        # Calculate hex to verify
        calculated_hex = convert_inverter_id_to_hex(inverter_id)
        
        if calculated_hex != serial:
            print(f"⚠️  Warning: Calculated hex ({calculated_hex}) doesn't match provided serial ({serial})")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                return False
        
        # Add the new mapping
        current_mapping = match.group(1)
        new_line = f"                {inverter_id}: '{serial}',  # {description}\n"
        new_mapping = current_mapping + new_line + "            " + match.group(2)
        
        # Replace in content
        new_content = content.replace(match.group(0), new_mapping)
        
        # Create backup
        backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_path, 'w') as f:
            f.write(content)
        
        # Write updated file
        with open(file_path, 'w') as f:
            f.write(new_content)
        
        print(f"✅ Added inverter mapping: {inverter_id} -> {serial}")
        print(f"📁 Backup created: {backup_path}")
        print(f"🔄 Please restart the dashboard to load the new mapping")
        
        return True
        
    except Exception as e:
        print(f"❌ Error adding inverter: {e}")
        return False


def list_current_inverters():
    """List all current inverter mappings"""
    print("🔧 CURRENT INVERTER MAPPINGS")
    print("=" * 50)
    
    mapping = get_current_inverter_mapping()
    
    if not mapping:
        print("❌ No mappings found")
        return
    
    # Categorize inverters
    original_inverters = []
    replacement_inverters = []
    
    for inverter_id, serial in mapping.items():
        calculated_hex = convert_inverter_id_to_hex(inverter_id)
        
        if inverter_id in [1902118887, 1902121595]:
            inverter_type = "New Replacement"
        elif inverter_id in [-1053817559, 1093666578]:
            inverter_type = "Previous Replacement"
        else:
            inverter_type = "Original"
        
        entry = {
            'id': inverter_id,
            'serial': serial,
            'type': inverter_type,
            'calculated_hex': calculated_hex,
            'matches_calc': serial == calculated_hex
        }
        
        if inverter_type == "Original":
            original_inverters.append(entry)
        else:
            replacement_inverters.append(entry)
    
    # Display original inverters
    print(f"\n📦 ORIGINAL INVERTERS ({len(original_inverters)}):")
    print("-" * 40)
    for inv in sorted(original_inverters, key=lambda x: x['serial']):
        status = "✅" if inv['matches_calc'] else "⚠️"
        print(f"{status} {inv['id']:>12} -> {inv['serial']} (calc: {inv['calculated_hex']})")
    
    # Display replacement inverters
    if replacement_inverters:
        print(f"\n🔄 REPLACEMENT INVERTERS ({len(replacement_inverters)}):")
        print("-" * 40)
        for inv in sorted(replacement_inverters, key=lambda x: x['id']):
            status = "✅" if inv['matches_calc'] else "⚠️"
            print(f"{status} {inv['id']:>12} -> {inv['serial']} ({inv['type']}) (calc: {inv['calculated_hex']})")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Total inverters: {len(mapping)}")
    print(f"   Original: {len(original_inverters)}")
    print(f"   Replacements: {len(replacement_inverters)}")


def interactive_add_inverter():
    """Interactive prompt to add a new inverter"""
    print("\n➕ ADD NEW INVERTER MAPPING")
    print("=" * 30)
    
    try:
        # Get inverter ID
        inverter_id_str = input("Enter Inverter ID: ").strip()
        if not inverter_id_str:
            print("❌ Inverter ID is required")
            return
        
        inverter_id = int(inverter_id_str)
        
        # Calculate hex
        calculated_hex = convert_inverter_id_to_hex(inverter_id)
        print(f"🔢 Calculated hex serial: {calculated_hex}")
        
        # Get serial (with default)
        serial_input = input(f"Enter Serial Number [{calculated_hex}]: ").strip().upper()
        serial = serial_input if serial_input else calculated_hex
        
        # Get description
        description = input("Enter description [Replacement inverter]: ").strip()
        if not description:
            description = "Replacement inverter"
        
        # Confirm
        print(f"\n📋 CONFIRMATION:")
        print(f"   Inverter ID: {inverter_id}")
        print(f"   Serial: {serial}")
        print(f"   Description: {description}")
        print(f"   Calculated Hex: {calculated_hex}")
        
        if serial != calculated_hex:
            print(f"   ⚠️  WARNING: Serial differs from calculated hex!")
        
        confirm = input("\nAdd this mapping? (y/n): ").lower()
        if confirm == 'y':
            add_inverter_to_mapping(inverter_id, serial, description)
        else:
            print("❌ Cancelled")
            
    except ValueError:
        print("❌ Invalid inverter ID. Must be an integer.")
    except KeyboardInterrupt:
        print("\n❌ Cancelled")
    except Exception as e:
        print(f"❌ Error: {e}")


def remove_inverter_from_mapping(inverter_id, reason="Removed from system"):
    """Remove an inverter from the mapping in enhanced_dashboard.py"""
    try:
        inverter_id = int(inverter_id)
        
        # Read current file
        file_path = '/Users/johndona/Git_Repositories/JesusCalling/enhanced_dashboard.py'
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the specific line to remove
        pattern = rf'\s*{inverter_id}:\s*\'[^\']+\',\s*#[^\n]*\n'
        match = re.search(pattern, content)
        
        if not match:
            print(f"❌ Inverter ID {inverter_id} not found in mapping")
            return False
        
        # Show what will be removed
        line_to_remove = match.group(0).strip()
        print(f"📋 Found mapping to remove:")
        print(f"   {line_to_remove}")
        
        # Confirm removal
        response = input(f"\n🗑️ Remove this mapping? (y/n): ").lower()
        if response != 'y':
            print("❌ Cancelled")
            return False
        
        # Create backup
        backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Remove the line
        new_content = re.sub(pattern, '', content)
        
        # Write updated file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✅ Removed inverter mapping: {inverter_id}")
        print(f"📁 Backup created: {backup_path}")
        print(f"🔄 Please restart the dashboard to load the updated mapping")
        
        # Log the removal
        log_entry = f"{datetime.now().isoformat()}: Removed inverter {inverter_id} - {reason}\n"
        with open('/Users/johndona/Git_Repositories/JesusCalling/inverter_removal_log.txt', 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        return True
        
    except Exception as e:
        print(f"❌ Error removing inverter: {e}")
        return False


def interactive_remove_inverter():
    """Interactive prompt to remove an inverter"""
    print("\n🗑️ REMOVE INVERTER MAPPING")
    print("=" * 30)
    
    try:
        # Show current mapping first
        print("📋 Current inverter mappings:")
        mapping = get_current_inverter_mapping()
        
        if not mapping:
            print("❌ No mappings found")
            return
        
        # Display with numbering for easy selection
        inverter_list = list(mapping.items())
        print("\nIdx | Inverter ID  | Serial   | Type")
        print("-" * 40)
        
        for i, (inv_id, serial) in enumerate(inverter_list, 1):
            inv_type = "Replacement" if inv_id in [1902118887, 1902121595, -1053817559, 1093666578] else "Original"
            print(f"{i:3d} | {inv_id:12d} | {serial:8s} | {inv_type}")
        
        print(f"\n📊 Total: {len(inverter_list)} inverters")
        
        # Get user selection
        selection = input(f"\nSelect inverter to remove (1-{len(inverter_list)}) or enter Inverter ID directly: ").strip()
        
        if not selection:
            print("❌ No selection made")
            return
        
        # Parse selection
        try:
            if selection.isdigit() and 1 <= int(selection) <= len(inverter_list):
                # Selection by index
                idx = int(selection) - 1
                inverter_id = inverter_list[idx][0]
                serial = inverter_list[idx][1]
            else:
                # Direct ID entry
                inverter_id = int(selection)
                if inverter_id not in mapping:
                    print(f"❌ Inverter ID {inverter_id} not found in mapping")
                    return
                serial = mapping[inverter_id]
        except ValueError:
            print("❌ Invalid selection")
            return
        
        # Get removal reason
        print(f"\n📋 Selected: {inverter_id} ({serial})")
        reason = input("Enter reason for removal [Inverter offline/replaced]: ").strip()
        if not reason:
            reason = "Inverter offline/replaced"
        
        # Final confirmation
        print(f"\n⚠️ CONFIRMATION:")
        print(f"   Remove: {inverter_id} ({serial})")
        print(f"   Reason: {reason}")
        print(f"   This will reduce total inverters from {len(mapping)} to {len(mapping)-1}")
        
        confirm = input("\nProceed with removal? (y/n): ").lower()
        if confirm == 'y':
            remove_inverter_from_mapping(inverter_id, reason)
        else:
            print("❌ Cancelled")
    
    except KeyboardInterrupt:
        print("\n❌ Cancelled")
    except Exception as e:
        print(f"❌ Error: {e}")
def main():
    """Main menu"""
    while True:
        print("\n🔧 INVERTER MANAGEMENT UTILITY")
        print("=" * 35)
        print("1. List current inverters")
        print("2. Add new inverter")
        print("3. Remove inverter")
        print("4. Convert ID to hex")
        print("5. Exit")
        
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            list_current_inverters()
        elif choice == '2':
            interactive_add_inverter()
        elif choice == '3':
            interactive_remove_inverter()
        elif choice == '4':
            try:
                inverter_id = input("Enter Inverter ID: ").strip()
                if inverter_id:
                    hex_serial = convert_inverter_id_to_hex(inverter_id)
                    print(f"🔢 {inverter_id} -> {hex_serial}")
            except Exception as e:
                print(f"❌ Error: {e}")
        elif choice == '5':
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice")


if __name__ == "__main__":
    main()
