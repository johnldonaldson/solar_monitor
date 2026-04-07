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
        self.station_url = 'https://www.wunderground.com/dashboard/pws/KCAHUNTI63'
        self.cache_file = Path('simple_weather_cache.json')
        self.cache_duration = 300          # seconds (5 minutes)
        self.rain_rate_threshold = 0.01    # in/hr
        self.high_humidity_threshold = 98  # %

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_weather_status(self):
        """Get weather status with rain detection"""
        cached = self._load_cache()
        if cached and self._is_cache_valid(cached):
            return cached

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.station_url, headers=headers, timeout=15)
            response.raise_for_status()
            html = response.text

            obs = self._parse_latest_observation(html)
            if obs:
                temp         = obs.get('temp')
                humidity     = obs.get('humidity')
                precip_rate  = obs.get('precip_rate')
                precip_total = obs.get('precip_total')
                obs_time     = obs.get('observation_time')
            else:
                temp         = self._extract_temp(html)
                humidity     = self._extract_humidity(html)
                precip_rate  = self._extract_precip_rate(html)
                precip_total = self._extract_precip_total(html)
                obs_time     = datetime.now().isoformat()

            solar = self._extract_solar_radiation(html)

            data = {
                'temp':             temp,
                'humidity':         humidity,
                'precip_rate':      precip_rate,
                'precip_total':     precip_total,
                'solar_radiation':  solar,
                'observation_time': obs_time,
                'timestamp':        datetime.now().isoformat(),
            }
            data.update(self._process_weather_data(data))
            self._save_cache(data)
            return data

        except requests.RequestException as e:
            print(f"⚠️ Weather fetch error: {e}")
            return self._unavailable_status()
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"⚠️ Weather parse error: {e}")
            return self._unavailable_status()

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_temp(self, html):
        """Extract temperature"""
        return self._extract_float(html, (
            r'"imperial":\s*\{[^\}]*"temp":([0-9.]+)',
            r'CURRENT\s+(\d+\.?\d*)\s*°',
            r'(\d+\.?\d*)\s*°F',
            r'"tempHigh":([0-9.]+)',
        ))

    def _extract_humidity(self, html):
        """Extract humidity"""
        return self._extract_int(html, (
            r'"relativeHumidity":(\d+)',
            r'HUMIDITY\s+(\d+)\s*%',
            r'"humidityHigh":(\d+)',
        ))

    def _extract_precip_rate(self, html):
        """Extract precipitation rate"""
        return self._extract_float_max(html, (
            r'"precipRate":([0-9.]+)',
            r'PRECIP RATE\s+([0-9.]+)\s*in/hr',
        ))

    def _extract_precip_total(self, html):
        """Extract total precipitation"""
        return self._extract_float_max(html, (
            r'"precipTotal":([0-9.]+)',
            r'PRECIP\s+(?:TOTAL|ACCUM)\s+([0-9.]+)\s*in',
        ))

    def _extract_solar_radiation(self, html):
        """Extract solar radiation (W/m^2)"""
        return self._extract_float_max(html, (
            r'"solarRadiation":([0-9.]+)',
            r'"solarRadiationHigh":([0-9.]+)',
            r'SOLAR\s+RADIATION\s+([0-9.]+)\s*w/m²',
            r'SOLAR\s+RADIATION\s+([0-9.]+)\s*w/m2',
        ))

    def _extract_float(self, html, patterns):
        """Extract first float value using multiple patterns"""
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, IndexError):
                    continue
        return 0.0

    def _extract_float_max(self, html, patterns):
        """Extract the maximum float value across all pattern matches"""
        values = []
        for pattern in patterns:
            if isinstance(pattern, tuple):
                pattern = pattern[0]
            for match in re.findall(pattern, html, re.IGNORECASE):
                try:
                    values.append(float(match))
                except (ValueError, IndexError):
                    continue
        return max(values) if values else 0.0

    def _extract_int(self, html, patterns):
        """Extract integer value using multiple patterns"""
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    continue
        return 0

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process_weather_data(self, data):
        """Process weather data and determine rain status"""
        precip_rate  = data.get('precip_rate') or 0
        precip_total = data.get('precip_total') or 0
        humidity     = data.get('humidity') or 0

        reasons = []
        is_raining = False

        if precip_rate >= self.rain_rate_threshold:
            is_raining = True
            reasons.append(f"Active precipitation: {precip_rate} in/hr")

        if humidity >= self.high_humidity_threshold:
            reasons.append(f"Very high humidity: {humidity}%")

        should_suspend = is_raining

        return {
            'is_raining':           is_raining,
            'should_suspend_alerts': should_suspend,
            'summary':              ', '.join(reasons) if reasons else 'No rain detected',
            'condition_detail':     ', '.join(reasons) if reasons else 'Clear conditions',
        }

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _load_cache(self):
        """Load cached weather data"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _save_cache(self, payload):
        """Save weather data to cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            print(f"⚠️ Cache save error: {e}")

    def _is_cache_valid(self, cached_data):
        """Check if cached data is still valid"""
        try:
            ts = cached_data['timestamp']
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            return age < self.cache_duration
        except (KeyError, ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_latest_observation(self, html):
        """Parse latest observation block when available"""
        m = re.search(r'"observations":\[(.*?)\]\}', html, re.DOTALL)
        if not m:
            return None
        try:
            # Take the last complete observation object
            raw = '[' + m.group(1) + ']'
            observations = json.loads(raw)
            if not observations:
                return None
            obs = observations[-1]
            imperial = obs.get('imperial', {})
            return {
                'temp':             imperial.get('tempAvg') or imperial.get('temp'),
                'humidity':         obs.get('humidityAvg') or obs.get('humidity'),
                'precip_rate':      imperial.get('precipRate'),
                'precip_total':     imperial.get('precipTotal'),
                'observation_time': obs.get('obsTimeLocal'),
            }
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _unavailable_status():
        return {
            'is_raining':            False,
            'should_suspend_alerts': False,
            'summary':               'Weather monitoring unavailable',
            'condition_detail':      'Weather monitoring unavailable',
            'temp':                  None,
            'humidity':              None,
            'precip_rate':           None,
            'precip_total':          None,
            'solar_radiation':       None,
            'observation_time':      None,
            'timestamp':             datetime.now().isoformat(),
        }


if __name__ == '__main__':
    print('🌤️  Testing Simple Weather Monitor')
    print('=' * 40)
    monitor = SimpleWeatherMonitor()
    status = monitor.get_weather_status()
    suspend_flag = status.get('should_suspend_alerts')
    details      = status.get('summary')
    print(f"🌧️  Raining: {'Yes' if status.get('is_raining') else 'No'}")
    print(f"🚨 Suspend Alerts: {'Yes' if suspend_flag else 'No'}")
    print(f"📝 Summary: {details}")
    weather_data = status
    print('\n📊 Weather Details:')
    print(f"  🌡️  Temperature: {weather_data.get('temp', 'N/A')}°F")
