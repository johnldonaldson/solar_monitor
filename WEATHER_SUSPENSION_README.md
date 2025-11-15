# Weather-Based Alert Suspension System

## Overview
Added rain detection to automatically suspend solar panel alerts during rainy weather, preventing false alarms when panels naturally produce less power due to weather conditions.

## Components Added

### 1. Simple Weather Monitor (`simple_weather_monitor.py`)
- Fetches real-time weather data from Weather Underground station KCAHUNTI63
- Detects rain using multiple indicators:
  - Active precipitation rate > 0.01 in/hr
  - Daily precipitation accumulation > 0.1 inches
  - Very high humidity ≥ 98% (indicates rain/storm conditions)
- Caches data for 5 minutes to reduce API calls
- Returns clear status with rain detection reasoning

### 2. Enhanced Alert Manager (`inverter_alert_manager.py`)
- Integrated weather checking into main alert flow
- Automatically suspends ALL solar alerts when rain is detected
- Sends one-time weather suspension notification (rate-limited to prevent spam)
- Resumes normal alerting when weather clears

## How It Works

1. **Before Processing Alerts**: System checks current weather conditions
2. **Rain Detection**: If any rain indicators are present, alerts are suspended
3. **Suspension Notice**: Sends informational alert about suspension (once every 4 hours max)
4. **Clear Weather**: Normal alert processing resumes automatically

## Current Weather Detection
Based on station KCAHUNTI63 (your local area):
- **Temperature**: 62.6°F  
- **Humidity**: 99% (indicating rain conditions)
- **Status**: ✅ Currently detecting rain - alerts suspended

## Benefits

- **No False Alarms**: Prevents alerts during legitimate low-power conditions (rain/clouds)
- **Automatic Operation**: No manual intervention needed
- **Intelligent Recovery**: Resumes normal monitoring when weather clears
- **User Awareness**: Sends notification when suspension begins
- **Rate Limited**: Won't spam with repeated weather alerts

## Configuration

Weather suspension is automatically enabled when the system starts. No additional configuration needed.

The system will continue monitoring weather every 5 minutes and adjust alert behavior accordingly.

## Testing

The system has been tested with both rainy and clear weather conditions:
- ✅ Rain detected: Alerts properly suspended
- ✅ Clear weather: Normal alert processing continues
- ✅ Suspension notifications: Sent appropriately with rate limiting

## Usage

Simply restart your solar monitoring system to enable weather-based alert suspension:

```bash
# If you have the dashboard running, stop it (Ctrl+C) and restart
python enhanced_dashboard.py
```

The system will automatically start monitoring weather and suspending alerts during rain.