#!/usr/bin/env python3
"""
Simple Weather Monitor for Alert Suspension
Uses Weather Underground API data to detect rain
"""

import json
import re
from datetime import datetime
from pathlib import Path

import requests


class SimpleWeatherMonitor:
    def __init__(self):
        self.station_url = (
            "https://www.wunderground.com/dashboard/pws/KCAHUNTI63"
        )
        self.cache_file = Path('simple_weather_cache.json')
        self.cache_duration = 300  # 5 minutes
        
        # Rain detection thresholds
        self.rain_rate_threshold = 0.01  # Any measurable precipitation
        self.high_humidity_threshold = 98  # Very high humidity
        
    def get_weather_status(self):
        """Get weather status with rain detection"""
        try:
            # Check cache first
            cached = self._load_cache()
            if cached and self._is_cache_valid(cached):
                return self._process_weather_data(cached)
            
            # Fetch fresh data
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36'
                )
            }

            response = requests.get(
                self.station_url,
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            
            html = response.text

            latest = self._parse_latest_observation(html)

            if latest:
                weather_data = {
                    'timestamp': datetime.now().isoformat(),
                    'temp': latest.get('temp', self._extract_temp(html)),
                    'humidity': latest.get(
                        'humidity',
                        self._extract_humidity(html),
                    ),
                    'precip_rate': latest.get('precip_rate'),
                    'precip_total': latest.get('precip_total'),
                    'observation_time': latest.get('observation_time'),
                    'solar_radiation': latest.get(
                        'solar_radiation',
                        latest.get('solarRadiation')
                    ),
                    'source': 'observations_json',
                }
            else:
                # Regex fallback when embedded JSON moves
                weather_data = {
                    'timestamp': datetime.now().isoformat(),
                    'temp': self._extract_temp(html),
                    'humidity': self._extract_humidity(html),
                    'precip_rate': self._extract_precip_rate(html),
                    'precip_total': self._extract_precip_total(html),
                    'observation_time': None,
                    'solar_radiation': self._extract_solar_radiation(html),
                    'source': 'regex_fallback',
                }
            
            # Save to cache
            self._save_cache(weather_data)
            
            return self._process_weather_data(weather_data)
            
        except (
            requests.RequestException,
            json.JSONDecodeError,
            ValueError,
            KeyError,
        ) as exc:
            print(f"⚠️ Weather fetch error: {exc}")
            # Return safe fallback (no rain detected)
            return {
                'is_raining': False,
                'should_suspend_alerts': False,
                'summary': 'Weather data unavailable - assuming no rain',
                'error': str(exc)
            }
    
    def _extract_temp(self, html):
        """Extract temperature"""
        patterns = [
            r'"imperial":\s*\{[^\}]*"temp":([0-9.]+)',
            r'CURRENT\s+(\d+\.?\d*)\s*°',
            r'(\d+\.?\d*)\s*°F',
            r'"tempHigh":([0-9.]+)'
        ]
        return self._extract_float(html, patterns)
    
    def _extract_humidity(self, html):
        """Extract humidity"""
        patterns = [
            r'"relativeHumidity":(\d+)',
            r'HUMIDITY\s+(\d+)\s*%',
            r'"humidityHigh":(\d+)'
        ]
        return self._extract_int(html, patterns)
    
    def _extract_precip_rate(self, html):
        """Extract precipitation rate"""
        patterns = [
            r'"precipRate":([0-9.]+)',
            r'PRECIP RATE\s+([0-9.]+)\s*in/hr'
        ]
        return self._extract_float_max(html, patterns)
    
    def _extract_precip_total(self, html):
        """Extract total precipitation"""
        patterns = [
            r'"precipTotal":([0-9.]+)',
            r'PRECIP\s+(?:TOTAL|ACCUM)\s+([0-9.]+)\s*in'
        ]
        return self._extract_float_max(html, patterns)

    def _extract_solar_radiation(self, html):
        """Extract solar radiation (W/m^2)"""
        patterns = [
            r'"solarRadiation":([0-9.]+)',
            r'"solarRadiationHigh":([0-9.]+)',
            r'SOLAR\s+RADIATION\s+([0-9.]+)\s*w/m²',
            r'SOLAR\s+RADIATION\s+([0-9.]+)\s*w/m2'
        ]
        return self._extract_float_max(html, patterns)
    
    def _extract_float(self, html, patterns):
        """Extract first float value using multiple patterns"""
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue
        return 0.0

    def _extract_float_max(self, html, patterns):
        """Extract the maximum float value across all pattern matches"""
        values = []
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                try:
                    if isinstance(match, tuple):
                        match = match[0]
                    values.append(float(match))
                except (ValueError, IndexError):
                    continue
        return max(values) if values else 0.0
    
    def _extract_int(self, html, patterns):
        """Extract integer value using multiple patterns"""
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        return 0
    
    def _process_weather_data(self, data):
        """Process weather data and determine rain status"""
        temp = data.get('temp', 0)
        humidity = data.get('humidity', 0)
        precip_rate = data.get('precip_rate', 0)
        precip_total = data.get('precip_total', 0)
        solar_radiation = data.get('solar_radiation')
        
        # Determine if it's raining
        is_raining = False
        reasons = []
        
        if precip_rate > self.rain_rate_threshold:
            is_raining = True
            reasons.append(f"Active precipitation: {precip_rate} in/hr")
        
        if precip_total > 0.1:  # Significant accumulation today
            is_raining = True
            reasons.append(f"Daily accumulation: {precip_total} in")
        
        if humidity >= self.high_humidity_threshold:
            is_raining = True
            reasons.append(f"Very high humidity: {humidity}%")
        
        # Create summary
        if is_raining:
            summary = f"Rain detected: {', '.join(reasons)}"
        else:
            summary = (
                "No rain - Temp: "
                f"{temp}°F, Humidity: {humidity}%, Precip: {precip_rate} in/hr"
            )
        
        return {
            'is_raining': is_raining,
            'should_suspend_alerts': is_raining,
            'summary': summary,
            'weather_data': data,
            'reasons': reasons,
            'solar_radiation': solar_radiation
        }
    
    def _load_cache(self):
        """Load cached weather data"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return None
    
    def _save_cache(self, payload):
        """Save weather data to cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except OSError as exc:
            print(f"⚠️ Cache save error: {exc}")
    
    def _is_cache_valid(self, cached_data):
        """Check if cached data is still valid"""
        try:
            cache_time = datetime.fromisoformat(cached_data['timestamp'])
            age = datetime.now() - cache_time
            return age.total_seconds() < self.cache_duration
        except (KeyError, ValueError, TypeError):
            return False

    def _parse_latest_observation(self, html):
        """Parse latest observation block when available"""
        match = re.search(r'"observations":\[(.*?)\]\}', html, re.DOTALL)
        if not match:
            return None

        observations_text = '[' + match.group(1) + ']'

        try:
            observations = json.loads(observations_text)
        except json.JSONDecodeError:
            return None

        if not observations:
            return None

        latest = observations[-1]
        imperial = latest.get('imperial', {})

        return {
            'temp': imperial.get('temp', imperial.get('tempAvg')),
            'humidity': latest.get('humidity', latest.get('humidityAvg')),
            'precip_rate': imperial.get('precipRate', 0.0),
            'precip_total': imperial.get('precipTotal', 0.0),
            'observation_time': latest.get('obsTimeLocal'),
            'solar_radiation': latest.get(
                'solarRadiation',
                latest.get('solarRadiationHigh')
            ),
        }


# Test the simple weather monitor
if __name__ == "__main__":
    print("🌤️  Testing Simple Weather Monitor")
    print("=" * 40)
    
    monitor = SimpleWeatherMonitor()
    status = monitor.get_weather_status()
    
    print(f"🌧️  Raining: {'Yes' if status['is_raining'] else 'No'}")
    suspend_flag = 'Yes' if status['should_suspend_alerts'] else 'No'
    print(f"🚨 Suspend Alerts: {suspend_flag}")
    print(f"📝 Summary: {status['summary']}")
    
    if 'weather_data' in status:
        details = status['weather_data']
        print("\n📊 Weather Details:")
        print(f"  🌡️  Temperature: {details.get('temp', 'N/A')}°F")
        print(f"  💧 Humidity: {details.get('humidity', 'N/A')}%")
        print(f"  🌧️  Precip Rate: {details.get('precip_rate', 0)} in/hr")
        print(f"  📈 Precip Total: {details.get('precip_total', 0)} in")
        print(
            "  ☀️  Solar Radiation: "
            f"{details.get('solar_radiation', 'N/A')} W/m^2"
        )
    
    if status.get('error'):
        print(f"\n❌ Error: {status['error']}")
