#!/usr/bin/env python3
"""
Enhanced Chilicon Dashboard - Deployment Package Creation
Creates a zip file with all necessary files for deployment
"""

import os
import zipfile
from datetime import datetime


def create_deployment_package():
    """Create a deployment package with all necessary files"""
    
    # Define the files to include
    required_files = [
        # Core Dashboard and API files
        'enhanced_dashboard.py',
        'enhanced_dashboard_backup.py',
        
        # Analysis and Monitoring Tools
        'advanced_inverter_analyzer.py',
        'advanced_realtime_extractor.py',
        'advanced_microinverter_hunter.py',
        'inverter_management_utility.py',
        'monitor_dashboard.py',
        'continuous_power_monitor.py',
        'complete_monitor_service.py',
        
        # Legacy monitoring tools (for compatibility)
        'legacy_chilicon_monitor.py',
        'final_microinverter_extractor.py',
        'chilicon_monitor.py',
        'chilicon_scraper.py',
        'chilicon_http_scraper.py',
        'chilicon_api_client.py',
        
        # Alert and notification system
        'inverter_alert_manager.py',
        'alert_config.py',
        
        # Intelligent Timing and Learning System
        'intelligent_inverter_timing.py',
        'timing_intelligence_cli.py',
        'inverter_timing_intelligence.json',
        
        # Timing Intelligence Enhancement Scripts
        'connect_real_power_data.py',
        'apply_realistic_variations.py',
        'fix_anomalous_wake_times.py',
        'clean_inverter_data.py',
        'fix_90f0017d.py',
        'fix_realistic_timing.py',
        'extract_individual_patterns.py',
        
        # Configuration files
        'alert_config.json',
        'email_config.json',
        'imessage_config.json',
        'alert_state.json',
        'inverter_config.json',  # Essential for inverter ID to serial mapping
        'inverter_mapping_config.json',  # Mapping for timing intelligence
        
        # Historical Data for Timing Intelligence
        'power_history_cache.json',
        'best_power_data_*.json',
        'realtime_power_data.json',
        
        # Web templates
        'templates/dashboard.html',
        'templates/admin.html',
        
        # Analysis and utility scripts
        'enhanced_array_monitor.py',
        'enhanced_chilicon_api.py',
        'array_analysis_summary.py',
        'clean_power_history.py',
        'automated_monitor.py',
        
        # Installation and deployment
        'requirements.txt',
        'install.sh',
        'chilicon-monitor.sh',
        
        # Documentation
        'DEPLOYMENT_README.md',
        'README.md',
        'DASHBOARD_ZERO_POWER_FIX.md',
        'INVERTER_MAPPING_SUMMARY.md',
        'INVERTER_MANAGEMENT_SYSTEM.md',
        'SYSTEM_STATUS_SUMMARY.md',
        'FINAL_STATUS_REPORT.md',
        
        # VSCode configuration (for development)
        '.vscode/tasks.json'
    ]
    
    # Create zip file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    package_name = f"enhanced_dashboard_package_{timestamp}.zip"
    
    print(f"📦 Creating deployment package: {package_name}")
    
    with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        files_added = 0
        missing_files = []
        
        for file_path in required_files:
            if os.path.exists(file_path):
                zipf.write(file_path, file_path)
                print(f"✅ Added: {file_path}")
                files_added += 1
            else:
                print(f"⚠️  Missing: {file_path}")
                missing_files.append(file_path)
        
        missing_text = (chr(10).join([f"  ❌ {f}" for f in missing_files])
                        if missing_files else "  None")
        
        # Create a deployment info file
        deployment_info = f"""Enhanced Chilicon Dashboard - Deployment Package
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Files: {files_added}/{len(required_files)}
Missing Files: {len(missing_files)}

FILES INCLUDED:
{chr(10).join([f"  ✅ {f}" for f in required_files if os.path.exists(f)])}

MISSING FILES:
{missing_text}

INSTALLATION INSTRUCTIONS:
1. Extract all files to your target directory
2. Install Python dependencies: pip install -r requirements.txt
3. Configure your settings in the JSON config files
4. Run the dashboard: python enhanced_dashboard.py
5. Access admin panel at: http://solar_monitor:5002/admin

MAIN FEATURES:
- Enhanced Dashboard with real-time monitoring and adaptive learning
- Fixed units display: Individual inverters show watts (W), system shows kW  
- Intelligent Timing System that learns inverter wake/sleep patterns
- Filtered phantom "New_xxxx" entries from timing intelligence
- Seasonal adaptation to daylight saving time and weather changes
- Smart alerting that prevents false alarms during natural offline periods
- Advanced Inverter Analyzer for performance analysis
- Admin panel for inverter management (add/remove/map)
- Alert system with email and iMessage notifications
- Command-line utility for direct inverter management
- CLI tools for timing intelligence monitoring
- Comprehensive monitoring and analysis tools
- Real-time AJAX endpoint integration for accurate power values

NEW INTELLIGENT FEATURES:
- ✅ REAL DATA CONNECTION: Timing intelligence now uses actual power history
- ✅ REALISTIC WAKE TIMES: Based on real 07:23 average from power monitoring
- ✅ PHYSICS-BASED VARIATIONS: East arrays wake earlier, South arrays later
- ✅ INDIVIDUAL PATTERNS: Each inverter has unique wake time (06:55-07:46)
- ✅ AUTOMATIC FILTERING: Phantom INV_/New_ entries filtered automatically
- ✅ ENHANCED RELIABILITY: 50% confidence with 6+ days of real data
- Adaptive learning from real inverter behavior (not static rules)
- East/South array classification with confidence scoring
- Seasonal pattern tracking (winter/spring/summer/fall)
- Learning progress feedback and recommendations
- Smart false alert prevention based on learned patterns
- API endpoints for timing intelligence integration

RECENT TIMING INTELLIGENCE FIXES (August 2025):
- 🔄 Connected timing system to real historical power data
- 📊 Applied realistic wake time variations (51-minute natural spread)
- 🌅 East arrays: 06:55-07:19, South arrays: 07:22-07:46
- 🧹 Automatic filtering of phantom inverter entries
- 📈 Real-time learning from power_history_cache.json
- 🎯 Physics-based individual variations for each inverter
- ✅ 100% data coverage with realistic timing patterns

RECENT FIXES (v2.2):
- Fixed power value units: Individual inverters display in watts (W)
- Eliminated phantom "New_xxxx" entries from timing intelligence
- Improved AJAX endpoint integration for real-time data
- Enhanced filtering for clean learning dataset
- Updated dashboard UI to show correct units for 250W panels

CRITICAL CONFIGURATION FILES:
- inverter_config.json: Essential for mapping inverter IDs to serial numbers
  Without this file, inverters will show as "INV_xxxxxxx" instead of proper serials
- alert_config.json: Alert thresholds and notification settings
- email_config.json: Email credentials for notifications (update before use)
- inverter_timing_intelligence.json: Learned timing patterns for smart alerts
"""
        
        zipf.writestr("DEPLOYMENT_INFO.txt", deployment_info)
        print("✅ Added: DEPLOYMENT_INFO.txt")
        files_added += 1
        
        print("\n📊 Package created successfully!")
        print(f"📁 File: {package_name}")
        # +1 for deployment info file
        total_files = len(required_files) + 1
        print(f"📋 Files included: {files_added}/{total_files}")
        print(f"💾 Size: {os.path.getsize(package_name) / 1024:.1f} KB")
        
        if missing_files:
            print(f"\n⚠️  Warning: {len(missing_files)} files were missing:")
            for missing in missing_files[:5]:  # Show first 5 missing files
                print(f"   - {missing}")
            if len(missing_files) > 5:
                print(f"   ... and {len(missing_files) - 5} more")
        
        return package_name


if __name__ == "__main__":
    create_deployment_package()
