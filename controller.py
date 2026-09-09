import os
import subprocess
import glob

class ThinkPadController:
    BAT_PATH = "/sys/class/power_supply/BAT0"
    PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"
    PLATFORM_PROFILE_CHOICES = "/sys/firmware/acpi/platform_profile_choices"
    KBD_BACKLIGHT = "/sys/class/leds/tpacpi::kbd_backlight/brightness"
    KBD_BACKLIGHT_MAX = "/sys/class/leds/tpacpi::kbd_backlight/max_brightness"
    LID_LOGO_DOT = "/sys/class/leds/tpacpi::lid_logo_dot/brightness"

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
    def get_battery_info(cls):
        """Read comprehensive battery telemetry: capacity, cycle count, health, wattage, and specs"""
        cap = cls._read_file(f"{cls.BAT_PATH}/capacity", "0")
        status = cls._read_file(f"{cls.BAT_PATH}/status", "Unknown")
        cycle = cls._read_file(f"{cls.BAT_PATH}/cycle_count", "0")
        
        start_thresh = cls._read_file(f"{cls.BAT_PATH}/charge_control_start_threshold")
        if not start_thresh:
            start_thresh = cls._read_file(f"{cls.BAT_PATH}/charge_start_threshold", "0")
            
        end_thresh = cls._read_file(f"{cls.BAT_PATH}/charge_control_end_threshold")
        if not end_thresh:
            end_thresh = cls._read_file(f"{cls.BAT_PATH}/charge_stop_threshold", "100")

        energy_full_raw = cls._read_file(f"{cls.BAT_PATH}/energy_full") or cls._read_file(f"{cls.BAT_PATH}/charge_full")
        energy_design_raw = cls._read_file(f"{cls.BAT_PATH}/energy_full_design") or cls._read_file(f"{cls.BAT_PATH}/charge_full_design")
        power_raw = cls._read_file(f"{cls.BAT_PATH}/power_now", "0")
        voltage_raw = cls._read_file(f"{cls.BAT_PATH}/voltage_now", "0")
        
        mfg = cls._read_file(f"{cls.BAT_PATH}/manufacturer", "Lenovo")
        model = cls._read_file(f"{cls.BAT_PATH}/model_name", "Integrated Battery").replace("\x00", "").strip()
        tech = cls._read_file(f"{cls.BAT_PATH}/technology", "Li-poly")

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

        return {
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
            "technology": tech
        }

    @classmethod
    def get_platform_profiles(cls):
        choices = cls._read_file(cls.PLATFORM_PROFILE_CHOICES, "low-power balanced performance").split()
        current = cls._read_file(cls.PLATFORM_PROFILE, "balanced")
        return {
            "choices": choices,
            "current": current
        }

    @classmethod
    def get_kbd_backlight(cls):
        cur = cls._read_file(cls.KBD_BACKLIGHT, "0")
        max_b = cls._read_file(cls.KBD_BACKLIGHT_MAX, "2")
        return {
            "current": int(cur) if cur.isdigit() else 0,
            "max": int(max_b) if max_b.isdigit() else 2
        }

    @classmethod
    def get_lid_logo_dot(cls):
        cur = cls._read_file(cls.LID_LOGO_DOT, "0")
        return int(cur) if cur.isdigit() else 0

    @classmethod
    def get_cpu_temp(cls):
        thermal_zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")
        temps = []
        for tz in thermal_zones:
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

    @classmethod
    def get_system_model(cls):
        product = cls._read_file("/sys/class/dmi/id/product_name", "Lenovo ThinkPad")
        family = cls._read_file("/sys/class/dmi/id/product_family", "")
        vendor = cls._read_file("/sys/class/dmi/id/sys_vendor", "Lenovo")
        return f"{vendor} {product} {family}".strip()

    @classmethod
    def set_battery_thresholds(cls, start_val, end_val):
        """Configure battery start and stop charging thresholds"""
        script = f"""
if [ -f {cls.BAT_PATH}/charge_control_start_threshold ]; then
    echo {start_val} > {cls.BAT_PATH}/charge_control_start_threshold
fi
if [ -f {cls.BAT_PATH}/charge_start_threshold ]; then
    echo {start_val} > {cls.BAT_PATH}/charge_start_threshold
fi
if [ -f {cls.BAT_PATH}/charge_control_end_threshold ]; then
    echo {end_val} > {cls.BAT_PATH}/charge_control_end_threshold
fi
if [ -f {cls.BAT_PATH}/charge_stop_threshold ]; then
    echo {end_val} > {cls.BAT_PATH}/charge_stop_threshold
fi
"""
        return cls._run_privileged_sh(script)

    @classmethod
    def set_platform_profile(cls, profile_name):
        script = f"echo {profile_name} > {cls.PLATFORM_PROFILE}"
        return cls._run_privileged_sh(script)

    @classmethod
    def set_kbd_backlight(cls, val):
        script = f"echo {val} > {cls.KBD_BACKLIGHT}"
        return cls._run_privileged_sh(script)

    @classmethod
    def set_lid_logo_dot(cls, val):
        script = f"echo {val} > {cls.LID_LOGO_DOT}"
        return cls._run_privileged_sh(script)

    @classmethod
    def _run_privileged_sh(cls, script_content):
        cmd = ["pkexec", "sh", "-c", script_content]
        try:
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return True, ""
        except subprocess.CalledProcessError as e:
            return False, e.stderr or "Permission denied or cancelled by user."
        except Exception as e:
            return False, str(e)
