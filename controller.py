import os
import subprocess
import glob
import threading
import json
import re
import time
import urllib.request
import urllib.error
from gi.repository import GLib

class ThinkPadController:
    SYS_POWER = "/sys/class/power_supply"
    PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"
    PLATFORM_PROFILE_CHOICES = "/sys/firmware/acpi/platform_profile_choices"
    KBD_BACKLIGHT = "/sys/class/leds/tpacpi::kbd_backlight/brightness"
    KBD_BACKLIGHT_MAX = "/sys/class/leds/tpacpi::kbd_backlight/max_brightness"
    LID_LOGO_DOT = "/sys/class/leds/tpacpi::lid_logo_dot/brightness"

    # Cached thermal sensor paths to avoid repeated globbing
    _cached_thermal_zones = None

    @staticmethod
    def _read_file(path, default=""):
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return default

    @classmethod
    def get_battery_list(cls):
        """Returns sorted list of detected battery names (e.g. ['BAT0', 'BAT1'])"""
        bats = []
        for path in glob.glob(f"{cls.SYS_POWER}/BAT*"):
            name = os.path.basename(path)
            # Ensure it's a battery by checking 'type' if present
            b_type = cls._read_file(f"{path}/type", "Battery")
            if b_type.lower() == "battery":
                bats.append(name)
        bats.sort()
        return bats if bats else ["BAT0"]

    @classmethod
    def get_battery_info(cls, bat_name="BAT0"):
        """Read comprehensive battery telemetry for a specific battery"""
        bat_dir = f"{cls.SYS_POWER}/{bat_name}"
        if not os.path.exists(bat_dir):
            # Fallback to first available battery if requested not found
            available = cls.get_battery_list()
            if available:
                bat_dir = f"{cls.SYS_POWER}/{available[0]}"
                bat_name = available[0]

        cap = cls._read_file(f"{bat_dir}/capacity", "0")
        status = cls._read_file(f"{bat_dir}/status", "Unknown")
        cycle = cls._read_file(f"{bat_dir}/cycle_count", "0")
        
        start_thresh = cls._read_file(f"{bat_dir}/charge_control_start_threshold")
        if not start_thresh:
            start_thresh = cls._read_file(f"{bat_dir}/charge_start_threshold", "0")
            
        end_thresh = cls._read_file(f"{bat_dir}/charge_control_end_threshold")
        if not end_thresh:
            end_thresh = cls._read_file(f"{bat_dir}/charge_stop_threshold", "100")

        energy_full_raw = cls._read_file(f"{bat_dir}/energy_full") or cls._read_file(f"{bat_dir}/charge_full")
        energy_design_raw = cls._read_file(f"{bat_dir}/energy_full_design") or cls._read_file(f"{bat_dir}/charge_full_design")
        power_raw = cls._read_file(f"{bat_dir}/power_now", "0")
        voltage_raw = cls._read_file(f"{bat_dir}/voltage_now", "0")
        
        mfg = cls._read_file(f"{bat_dir}/manufacturer", "Lenovo")
        model = cls._read_file(f"{bat_dir}/model_name", "Integrated Battery").replace("\x00", "").strip()
        tech = cls._read_file(f"{bat_dir}/technology", "Li-poly")

        # Convert to human-friendly Wh and W
        energy_full_wh = round(int(energy_full_raw) / 1000000.0, 2) if energy_full_raw.isdigit() else 0.0
        energy_design_wh = round(int(energy_design_raw) / 1000000.0, 2) if energy_design_raw.isdigit() else 0.0
        power_w = round(int(power_raw) / 1000000.0, 1) if power_raw.isdigit() else 0.0
        voltage_v = round(int(voltage_raw) / 1000000.0, 2) if voltage_raw.isdigit() else 0.0

        health = 100.0
        try:
            if energy_full_wh > 0 and energy_design_wh > 0:
                health = round((energy_full_wh / energy_design_wh) * 100.0, 1)
        except Exception:
            pass

        # Check threshold support
        has_thresh = any(os.path.exists(f"{bat_dir}/{n}") for n in [
            "charge_control_end_threshold", "charge_stop_threshold"
        ])

        return {
            "name": bat_name,
            "capacity": int(cap) if cap.isdigit() else 0,
            "status": status,
            "cycle_count": int(cycle) if cycle.isdigit() else 0,
            "start_threshold": int(start_thresh) if start_thresh.isdigit() else 0,
            "end_threshold": int(end_thresh) if end_thresh.isdigit() else 100,
            "health": min(health, 100.0),
            "energy_full_wh": energy_full_wh,
            "energy_design_wh": energy_design_wh,
            "power_w": power_w,
            "voltage_v": voltage_v,
            "manufacturer": mfg,
            "model": model,
            "technology": tech,
            "has_threshold_support": has_thresh
        }

    @classmethod
    def get_platform_profiles(cls):
        supported = os.path.exists(cls.PLATFORM_PROFILE_CHOICES)
        choices = cls._read_file(cls.PLATFORM_PROFILE_CHOICES, "low-power balanced performance").split()
        current = cls._read_file(cls.PLATFORM_PROFILE, "balanced")
        return {
            "supported": supported,
            "choices": choices,
            "current": current
        }

    @classmethod
    def get_kbd_backlight(cls):
        supported = os.path.exists(cls.KBD_BACKLIGHT)
        cur = cls._read_file(cls.KBD_BACKLIGHT, "0")
        max_b = cls._read_file(cls.KBD_BACKLIGHT_MAX, "2")
        return {
            "supported": supported,
            "current": int(cur) if cur.isdigit() else 0,
            "max": int(max_b) if max_b.isdigit() else 2
        }

    @classmethod
    def get_lid_logo_dot(cls):
        supported = os.path.exists(cls.LID_LOGO_DOT)
        cur = cls._read_file(cls.LID_LOGO_DOT, "0")
        return {
            "supported": supported,
            "current": int(cur) if cur.isdigit() else 0
        }

    @classmethod
    def get_cpu_temp(cls):
        if cls._cached_thermal_zones is None:
            cls._cached_thermal_zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")

        temps = []
        for tz in cls._cached_thermal_zones:
            try:
                val = cls._read_file(tz)
                if val.isdigit():
                    t = int(val) / 1000.0
                    if 20 <= t <= 110:
                        temps.append(t)
            except Exception:
                pass
        return round(max(temps), 1) if temps else 0.0

    @classmethod
    def get_model_details(cls):
        product = cls._read_file("/sys/class/dmi/id/product_name", "ThinkPad")
        family = cls._read_file("/sys/class/dmi/id/product_family", "")
        vendor = cls._read_file("/sys/class/dmi/id/sys_vendor", "Lenovo")

        v_cap = "Lenovo" if vendor.upper() == "LENOVO" else vendor
        if "thinkpad" in family.lower():
            title = family
            sub = f"{v_cap} • Model {product}"
        elif "thinkpad" in product.lower():
            title = product
            sub = f"{v_cap} • {family}".strip(" •")
        else:
            title = f"{v_cap} {family or product}".strip()
            sub = f"Model {product}"
        return {"title": title, "subtitle": sub, "raw": f"{vendor} {product} {family}".strip()}

    # --- DEVICE IDENTITY & WARRANTY TELEMETRY ---

    @classmethod
    def get_device_serial(cls):
        """Resolves device serial number via /etc/thinkcontrol.json, cache, or DMI"""
        # 1. Check system config (cached by service/helper)
        cfg_path = "/etc/thinkcontrol.json"
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    data = json.load(f)
                    s = data.get("serial_number", "").strip()
                    if s:
                        return s
            except Exception:
                pass

        # 2. Check user warranty cache
        cache_path = os.path.expanduser("~/.cache/thinkcontrol/warranty.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    s = data.get("serial", "").strip()
                    if s:
                        return s
            except Exception:
                pass

        # 3. Direct DMI sysfs (if readable)
        s = cls._read_file("/sys/class/dmi/id/product_serial")
        if s:
            return s

        return ""

    @classmethod
    def detect_serial_privileged_async(cls, callback):
        """Explicit user-triggered privileged serial detection via helper"""
        def worker():
            helper = cls._find_helper_path()
            if not helper:
                GLib.idle_add(callback, "", "Helper not found")
                return
            try:
                res = subprocess.run(["pkexec", helper, "get-serial"], capture_output=True, text=True, check=True)
                s = res.stdout.strip()
                GLib.idle_add(callback, s, "")
            except Exception as e:
                GLib.idle_add(callback, "", str(e))
        threading.Thread(target=worker, daemon=True).start()

    @classmethod
    def get_cached_warranty(cls):
        """Returns cached warranty dictionary if exists and fresh (< 7 days)"""
        cache_path = os.path.expanduser("~/.cache/thinkcontrol/warranty.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    age = time.time() - data.get("timestamp", 0)
                    data["is_stale"] = age > (7 * 86400)
                    return data
            except Exception:
                pass
        return None

    @classmethod
    def fetch_warranty_async(cls, callback, force=False):
        """
        Fetches official Lenovo warranty information asynchronously without blocking GUI.
        Calls callback(data, error_message) on GTK main loop via GLib.idle_add.
        """
        def worker():
            cached = cls.get_cached_warranty()
            if cached and not cached.get("is_stale") and not force:
                GLib.idle_add(callback, cached, None)
                return

            serial = cls.get_device_serial()
            if not serial:
                if cached:
                    GLib.idle_add(callback, cached, "Using cached warranty (Serial inaccessible)")
                else:
                    fallback_info = {
                        "serial": "",
                        "is_active": False,
                        "status": "Lookup Required",
                        "status_label": "Check Warranty Online",
                        "remaining_days": 0,
                        "package_name": "Lenovo Warranty Portal",
                        "url": "https://pcsupport.lenovo.com/id/id/warranty-lookup#/",
                        "description": "Serial number not detected. Click to open official Lenovo warranty portal.",
                        "start_date": "-",
                        "end_date": "-"
                    }
                    GLib.idle_add(callback, fallback_info, "Serial number not found")
                return

            try:
                headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
                # Step 1: Query getproducts API to resolve serial to canonical ProductId
                api_url = f"https://pcsupport.lenovo.com/us/en/api/v4/mse/getproducts?productId={serial}"
                req1 = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req1, timeout=8) as resp1:
                    prods = json.loads(resp1.read().decode("utf-8"))

                prod_id = prods[0].get("Id") if prods and isinstance(prods, list) else None
                prod_name = prods[0].get("Name") if prods and isinstance(prods, list) else ""

                if not prod_id:
                    raise ValueError(f"Product not found on Lenovo support for serial {serial}")

                # Step 2: Fetch warranty page and parse embedded ds_warranties JSON
                w_url = f"https://pcsupport.lenovo.com/us/en/products/{prod_id}/warranty"
                req2 = urllib.request.Request(w_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    html = resp2.read().decode("utf-8", errors="ignore")

                m = re.search(r"ds_warranties\s*=\s*window\.ds_warranties\s*\|\|\s*(\{.*?\});\s*(?:var|</script>)", html, re.DOTALL)
                if not m:
                    raise ValueError("Warranty data structure not found in portal response")

                w_data = json.loads(m.group(1))
                rem_days = w_data.get("RemainingDays", 0)
                is_active = (rem_days > 0)

                base_w = w_data.get("BaseWarranties", [])
                first_w = base_w[0] if base_w else {}

                pkg_name = first_w.get("Name") or ("Active Warranty" if is_active else "Standard Warranty")
                start_date = first_w.get("Start") or "-"
                end_date = first_w.get("End") or first_w.get("EndDate") or "-"
                desc = first_w.get("Description") or ""
                delivery = first_w.get("DeliveryType") or "Standard"

                official_url = f"https://pcsupport.lenovo.com/id/id/products/{prod_id}/warranty"

                result = {
                    "serial": serial,
                    "product_name": prod_name or w_data.get("ProductName", ""),
                    "machine_type": w_data.get("MachineType", ""),
                    "is_active": is_active,
                    "status": "In Warranty" if is_active else "Expired",
                    "status_label": f"Active ({rem_days} days remaining)" if is_active else "Warranty Expired",
                    "remaining_days": rem_days,
                    "package_name": pkg_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "delivery_type": delivery.capitalize(),
                    "description": desc,
                    "url": official_url,
                    "timestamp": time.time()
                }

                # Cache to user home
                cache_dir = os.path.expanduser("~/.cache/thinkcontrol")
                os.makedirs(cache_dir, exist_ok=True)
                with open(os.path.join(cache_dir, "warranty.json"), "w") as f:
                    json.dump(result, f, indent=2)

                GLib.idle_add(callback, result, None)

            except Exception as e:
                if cached:
                    GLib.idle_add(callback, cached, f"Offline - cached: {e}")
                else:
                    fallback_info = {
                        "serial": serial,
                        "is_active": False,
                        "status": "Check Online",
                        "status_label": "Check Warranty Online",
                        "remaining_days": -1,
                        "package_name": "Lenovo Warranty Portal",
                        "url": f"https://pcsupport.lenovo.com/id/id/warranty-lookup#/",
                        "description": "Unable to retrieve warranty details automatically. Click to open official portal.",
                        "start_date": "-",
                        "end_date": "-"
                    }
                    GLib.idle_add(callback, fallback_info, str(e))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    # --- PRIVILEGED OPERATIONS (NON-BLOCKING ASYNC WITH FALLBACK) ---

    @classmethod
    def _find_helper_path(cls):
        """Locate thinkcontrol-helper binary"""
        candidates = [
            "/usr/libexec/thinkcontrol-helper",
            "/opt/thinkcontrol/thinkcontrol-helper",
            "/usr/local/bin/thinkcontrol-helper",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "thinkcontrol-helper")
        ]
        for c in candidates:
            if os.path.exists(c) and os.access(c, os.X_OK):
                return c
        return None

    @classmethod
    def _execute_privileged_async(cls, helper_args, fallback_sh_script, callback):
        """
        Executes privileged command in a background thread to prevent GUI freeze.
        Calls callback(success, error_message) on the GTK main loop via GLib.idle_add.
        """
        def worker():
            helper = cls._find_helper_path()
            if helper:
                cmd = ["pkexec", helper] + [str(a) for a in helper_args]
            else:
                cmd = ["pkexec", "sh", "-c", fallback_sh_script]

            try:
                res = subprocess.run(cmd, check=True, capture_output=True, text=True)
                ok = True
                err = ""
            except subprocess.CalledProcessError as e:
                ok = False
                err = (e.stderr or e.stdout or "Authentication cancelled or permission denied.").strip()
                if "cancelled" in err.lower() or "dismissed" in err.lower() or e.returncode in (126, 127):
                    err = "Authentication cancelled or permission denied."
            except Exception as e:
                ok = False
                err = str(e)

            def dispatch():
                try:
                    callback(ok, err)
                except Exception as ex:
                    print(f"Callback error: {ex}", file=sys.stderr)
                return False

            GLib.idle_add(dispatch)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @classmethod
    def set_battery_thresholds_async(cls, bat_name, start_val, end_val, callback):
        """Async setting of battery thresholds without GUI blocking"""
        bat_dir = f"{cls.SYS_POWER}/{bat_name}"
        # Write end then start then end to ensure start < end invariant is preserved in shell fallback
        fallback_sh = f"""
if [ -f {bat_dir}/charge_control_start_threshold ]; then
    echo {start_val} > {bat_dir}/charge_control_start_threshold
fi
if [ -f {bat_dir}/charge_start_threshold ]; then
    echo {start_val} > {bat_dir}/charge_start_threshold
fi
if [ -f {bat_dir}/charge_control_end_threshold ]; then
    echo {end_val} > {bat_dir}/charge_control_end_threshold
fi
if [ -f {bat_dir}/charge_stop_threshold ]; then
    echo {end_val} > {bat_dir}/charge_stop_threshold
fi
echo {end_val} > {bat_dir}/charge_control_end_threshold 2>/dev/null || true
echo {end_val} > {bat_dir}/charge_stop_threshold 2>/dev/null || true
echo {start_val} > {bat_dir}/charge_control_start_threshold 2>/dev/null || true
echo {start_val} > {bat_dir}/charge_start_threshold 2>/dev/null || true
echo {end_val} > {bat_dir}/charge_control_end_threshold 2>/dev/null || true
echo {end_val} > {bat_dir}/charge_stop_threshold 2>/dev/null || true
"""
        cls._execute_privileged_async(
            ["set-battery-thresholds", bat_name, start_val, end_val],
            fallback_sh,
            callback
        )

    @classmethod
    def set_platform_profile_async(cls, profile_name, callback):
        fallback_sh = f"echo {profile_name} > {cls.PLATFORM_PROFILE}"
        cls._execute_privileged_async(
            ["set-platform-profile", profile_name],
            fallback_sh,
            callback
        )

    @classmethod
    def set_kbd_backlight_async(cls, val, callback):
        fallback_sh = f"echo {val} > {cls.KBD_BACKLIGHT}"
        cls._execute_privileged_async(
            ["set-kbd-backlight", val],
            fallback_sh,
            callback
        )

    @classmethod
    def set_lid_logo_dot_async(cls, val, callback):
        fallback_sh = f"echo {val} > {cls.LID_LOGO_DOT}"
        cls._execute_privileged_async(
            ["set-lid-logo-dot", val],
            fallback_sh,
            callback
        )
