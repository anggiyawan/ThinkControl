#!/usr/bin/env python3
import sys
import os
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

from controller import ThinkPadController

class ThinkControlWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("ThinkControl")
        self.set_default_size(900, 620)

        # Main Split View (Sidebar on left, Content on right)
        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_min_sidebar_width(260)
        self.split_view.set_max_sidebar_width(300)
        self.set_content(self.split_view)

        # 1. Build Left Sidebar
        self._build_sidebar()

        # 2. Build Right Content Area (ViewStack with 4 Tabs)
        self._build_content_area()

        # Initial Data Sync
        self.refresh_data()

        # Select first tab by default
        first_row = self.nav_list.get_row_at_index(0)
        if first_row:
            self.nav_list.select_row(first_row)

        # Background polling timer for live temperature & telemetry (every 3 seconds)
        GLib.timeout_add_seconds(3, self._auto_refresh_tick)

    def show_toast(self, text):
        toast = Adw.Toast.new(text)
        self.toast_overlay.add_toast(toast)

    def _on_about_clicked(self, btn):
        about = Adw.AboutDialog()
        about.set_application_name("ThinkControl")
        about.set_application_icon("com.lenovo.thinkcontrol")
        about.set_version("1.0.0")
        about.set_developer_name("Anggiyawan")
        about.set_copyright("© 2026 Anggiyawan")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/anggiyawan/ThinkControl")
        about.set_issue_url("https://github.com/anggiyawan/ThinkControl/issues")
        about.set_comments("Lenovo Vantage Hardware Control Center for ThinkPad on Linux (Zorin OS / Ubuntu).\nComprehensive control over battery charging thresholds, health diagnostics, performance profiles, and illumination.")
        about.present(self)

    # -------------------------------------------------------------
    # SIDEBAR BUILDER
    # -------------------------------------------------------------
    def _build_sidebar(self):
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Sidebar Header Bar
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)

        # Title widget for sidebar header
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_icon = Gtk.Image.new_from_icon_name("com.lenovo.thinkcontrol")
        title_icon.set_pixel_size(20)
        title_label = Gtk.Label(label="ThinkControl")
        title_label.add_css_class("heading")
        title_box.append(title_icon)
        title_box.append(title_label)
        sidebar_header.set_title_widget(title_box)

        # Refresh button in sidebar
        reload_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        reload_btn.set_tooltip_text("Refresh Hardware Status")
        reload_btn.connect("clicked", lambda x: self.refresh_data())
        sidebar_header.pack_start(reload_btn)

        # About button in sidebar
        about_btn = Gtk.Button(icon_name="help-about-symbolic")
        about_btn.set_tooltip_text("About ThinkControl")
        about_btn.connect("clicked", self._on_about_clicked)
        sidebar_header.pack_end(about_btn)

        sidebar_box.append(sidebar_header)

        # System Model Banner (Polished & Padded Card)
        model_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        model_card.add_css_class("card")
        model_card.set_margin_top(12)
        model_card.set_margin_bottom(12)
        model_card.set_margin_start(12)
        model_card.set_margin_end(12)

        inner_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner_card.set_margin_top(14)
        inner_card.set_margin_bottom(14)
        inner_card.set_margin_start(14)
        inner_card.set_margin_end(14)
        model_card.append(inner_card)

        # Header with clean title and subtitle
        details = ThinkPadController.get_model_details()
        self.model_title = Gtk.Label()
        self.model_title.set_halign(Gtk.Align.START)
        self.model_title.add_css_class("heading")
        self.model_title.set_text(details["title"])
        inner_card.append(self.model_title)

        self.model_sub = Gtk.Label()
        self.model_sub.set_halign(Gtk.Align.START)
        self.model_sub.add_css_class("caption")
        self.model_sub.add_css_class("dim-label")
        self.model_sub.set_text(details["subtitle"])
        inner_card.append(self.model_sub)

        # Separator inside card
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        sep.set_margin_top(2)
        sep.set_margin_bottom(2)
        inner_card.append(sep)

        # Live Battery Status Pill
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.sidebar_bat_icon = Gtk.Image.new_from_icon_name("battery-symbolic")
        self.sidebar_bat_icon.set_pixel_size(16)
        self.sidebar_bat_label = Gtk.Label(label="--%")
        self.sidebar_bat_label.add_css_class("caption")
        status_box.append(self.sidebar_bat_icon)
        status_box.append(self.sidebar_bat_label)
        inner_card.append(status_box)

        sidebar_box.append(model_card)

        # Navigation List (4 Tabs)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        sidebar_box.append(scrolled)

        self.nav_list = Gtk.ListBox()
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.connect("row-selected", self._on_nav_row_selected)
        scrolled.set_child(self.nav_list)

        # Define the 4 Navigation Items
        self.nav_items = [
            ("charging", "Battery Charging", "battery-level-80-charging-symbolic", "Thresholds &amp; Conservation"),
            ("health", "Battery Health", "emblem-favorite-symbolic", "Condition, Cycles &amp; Specs"),
            ("performance", "Performance", "speedometer-symbolic", "ACPI Thermal Modes"),
            ("keyboard", "Keyboard &amp; Lighting", "input-keyboard-symbolic", "Backlight &amp; Lid Logo LED")
        ]

        self.row_to_tag = {}
        for tag, title, icon_name, desc in self.nav_items:
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(desc)
            row.set_icon_name(icon_name)
            self.nav_list.append(row)
            self.row_to_tag[row] = tag

        sidebar_page = Adw.NavigationPage.new(sidebar_box, "ThinkControl")
        self.split_view.set_sidebar(sidebar_page)

    # -------------------------------------------------------------
    # CONTENT AREA BUILDER (VIEWSTACK)
    # -------------------------------------------------------------
    def _build_content_area(self):
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Content Header Bar
        self.content_header = Adw.HeaderBar()
        self.content_title_label = Gtk.Label(label="Battery Charging")
        self.content_title_label.add_css_class("heading")
        self.content_header.set_title_widget(self.content_title_label)
        content_box.append(self.content_header)

        # Toast Overlay
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_vexpand(True)
        content_box.append(self.toast_overlay)

        # ViewStack for Tab Pages
        self.view_stack = Adw.ViewStack()
        self.toast_overlay.set_child(self.view_stack)

        # Tab 1: Battery Charging
        self.view_stack.add_titled(self._build_page_charging(), "charging", "Battery Charging")

        # Tab 2: Battery Health
        self.view_stack.add_titled(self._build_page_health(), "health", "Battery Health")

        # Tab 3: Performance
        self.view_stack.add_titled(self._build_page_performance(), "performance", "Performance")

        # Tab 4: Keyboard & Peripherals
        self.view_stack.add_titled(self._build_page_keyboard(), "keyboard", "Keyboard & Lighting")

        content_page = Adw.NavigationPage.new(content_box, "Details")
        self.split_view.set_content(content_page)

    # -------------------------------------------------------------
    # TAB 1: BATTERY CHARGING
    # -------------------------------------------------------------
    def _build_page_charging(self):
        scrolled = Gtk.ScrolledWindow()
        clamp = Adw.Clamp()
        clamp.set_maximum_size(680)
        scrolled.set_child(clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        group = Adw.PreferencesGroup()
        group.set_title("Battery &amp; Charging Control")
        group.set_description("Manage charging thresholds to preserve battery chemistry and longevity")
        box.append(group)

        # Charge Level Row
        self.bat_info_row = Adw.ActionRow()
        self.bat_info_row.set_title("Current Charge Level")
        self.bat_info_row.set_subtitle("Loading...")
        self.bat_info_row.set_icon_name("battery-symbolic")

        self.bat_badge = Gtk.Label()
        self.bat_badge.add_css_class("heading")
        self.bat_info_row.add_suffix(self.bat_badge)
        group.add(self.bat_info_row)

        # Conservation Mode Switch
        self.conserve_row = Adw.SwitchRow()
        self.conserve_row.set_title("Conservation Mode (80% Limit)")
        self.conserve_row.set_subtitle("Stops charging at 80% to dramatically extend battery lifespan")
        self.conserve_row.connect("notify::active", self._on_conserve_toggled)
        group.add(self.conserve_row)

        # Start Threshold
        self.start_thresh_row = Adw.SpinRow.new_with_range(20, 95, 5)
        self.start_thresh_row.set_title("Start Charging Threshold (%)")
        self.start_thresh_row.set_subtitle("Battery begins charging when below this percentage")
        group.add(self.start_thresh_row)

        # Stop Threshold
        self.stop_thresh_row = Adw.SpinRow.new_with_range(40, 100, 5)
        self.stop_thresh_row.set_title("Stop Charging Threshold (%)")
        self.stop_thresh_row.set_subtitle("Battery stops charging upon reaching this percentage")
        group.add(self.stop_thresh_row)

        # Apply Button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        apply_btn = Gtk.Button(label="Apply Custom Thresholds")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self._on_apply_thresholds_clicked)
        btn_box.append(apply_btn)

        box.append(btn_box)
        return scrolled

    # -------------------------------------------------------------
    # TAB 2: BATTERY HEALTH
    # -------------------------------------------------------------
    def _build_page_health(self):
        scrolled = Gtk.ScrolledWindow()
        clamp = Adw.Clamp()
        clamp.set_maximum_size(680)
        scrolled.set_child(clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        group = Adw.PreferencesGroup()
        group.set_title("Battery Health &amp; Diagnostics")
        group.set_description("Hardware health ratio, cycle counter, and live power flow telemetry")
        box.append(group)

        # Health Condition
        self.health_row = Adw.ActionRow()
        self.health_row.set_title("Battery Health Condition")
        self.health_row.set_subtitle("Calculating health ratio...")
        self.health_row.set_icon_name("emblem-favorite-symbolic")

        self.health_badge = Gtk.Label()
        self.health_badge.add_css_class("title-3")
        self.health_badge.add_css_class("success")
        self.health_row.add_suffix(self.health_badge)
        group.add(self.health_row)

        # Cycle Count
        self.cycle_row = Adw.ActionRow()
        self.cycle_row.set_title("Battery Cycle Count")
        self.cycle_row.set_subtitle("Total complete charging cycles recorded by battery firmware")
        self.cycle_row.set_icon_name("view-refresh-symbolic")

        self.cycle_badge = Gtk.Label()
        self.cycle_badge.add_css_class("heading")
        self.cycle_row.add_suffix(self.cycle_badge)
        group.add(self.cycle_row)

        # Power Flow
        self.power_row = Adw.ActionRow()
        self.power_row.set_title("Power Flow &amp; Voltage")
        self.power_row.set_subtitle("Monitoring active wattage rate and voltage")
        self.power_row.set_icon_name("power-profile-balanced-symbolic")
        group.add(self.power_row)

        # Hardware Spec
        self.spec_row = Adw.ActionRow()
        self.spec_row.set_title("Battery Hardware Specification")
        self.spec_row.set_subtitle("Loading hardware metadata...")
        self.spec_row.set_icon_name("dialog-information-symbolic")
        group.add(self.spec_row)

        return scrolled

    # -------------------------------------------------------------
    # TAB 3: PERFORMANCE
    # -------------------------------------------------------------
    def _build_page_performance(self):
        scrolled = Gtk.ScrolledWindow()
        clamp = Adw.Clamp()
        clamp.set_maximum_size(680)
        scrolled.set_child(clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        group = Adw.PreferencesGroup()
        group.set_title("Performance &amp; Thermal Profiles")
        group.set_description("ACPI power modes and cooling profiles configured directly in Lenovo firmware")
        box.append(group)

        # CPU Temp
        self.temp_row = Adw.ActionRow()
        self.temp_row.set_title("Processor Temperature (CPU)")
        self.temp_row.set_subtitle("Live monitoring of ThinkPad thermal sensors")
        self.temp_row.set_icon_name("sensors-temperature-symbolic")

        self.temp_label = Gtk.Label()
        self.temp_label.add_css_class("title-3")
        self.temp_row.add_suffix(self.temp_label)
        group.add(self.temp_row)

        # Operation Mode
        self.profile_row = Adw.ComboRow()
        self.profile_row.set_title("Operation Mode")
        self.profile_row.set_subtitle("Select built-in Lenovo ACPI platform profile")
        self.profile_row.set_icon_name("speedometer-symbolic")

        self.profiles_list = Gtk.StringList()
        self.profile_map = {
            "low-power": "Quiet / Power Saver",
            "balanced": "Balanced",
            "performance": "Extreme Performance"
        }
        self.profile_keys = ["low-power", "balanced", "performance"]
        for k in self.profile_keys:
            self.profiles_list.append(self.profile_map[k])

        self.profile_row.set_model(self.profiles_list)
        self.profile_row.connect("notify::selected", self._on_profile_selected)
        group.add(self.profile_row)

        return scrolled

    # -------------------------------------------------------------
    # TAB 4: KEYBOARD & LIGHTING
    # -------------------------------------------------------------
    def _build_page_keyboard(self):
        scrolled = Gtk.ScrolledWindow()
        clamp = Adw.Clamp()
        clamp.set_maximum_size(680)
        scrolled.set_child(clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(16)
        box.set_margin_end(16)
        clamp.set_child(box)

        group = Adw.PreferencesGroup()
        group.set_title("Keyboard &amp; Illumination")
        group.set_description("Control keyboard backlight brightness and iconic ThinkPad indicator LEDs")
        box.append(group)

        # Keyboard Backlight
        self.kbd_row = Adw.ComboRow()
        self.kbd_row.set_title("Keyboard Backlight")
        self.kbd_row.set_subtitle("Adjust keyboard illumination brightness level")
        self.kbd_row.set_icon_name("input-keyboard-symbolic")

        kbd_model = Gtk.StringList()
        kbd_model.append("Off")
        kbd_model.append("Low")
        kbd_model.append("High")
        self.kbd_row.set_model(kbd_model)
        self.kbd_row.connect("notify::selected", self._on_kbd_selected)
        group.add(self.kbd_row)

        # Lid Logo Dot LED Switch
        self.lid_row = Adw.SwitchRow()
        self.lid_row.set_title("ThinkPad Lid Logo LED")
        self.lid_row.set_subtitle("Toggle the iconic illuminated red dot on display cover")
        self.lid_row.connect("notify::active", self._on_lid_dot_toggled)
        group.add(self.lid_row)

        return scrolled

    # -------------------------------------------------------------
    # NAVIGATION HANDLER
    # -------------------------------------------------------------
    def _on_nav_row_selected(self, list_box, row):
        if row and row in self.row_to_tag:
            tag = self.row_to_tag[row]
            self.view_stack.set_visible_child_name(tag)
            title_dict = {
                "charging": "Battery Charging",
                "health": "Battery Health & Diagnostics",
                "performance": "Performance & Thermal Profiles",
                "keyboard": "Keyboard & Illumination"
            }
            self.content_title_label.set_text(title_dict.get(tag, "ThinkControl"))

    # -------------------------------------------------------------
    # DATA REFRESH & SENSORS
    # -------------------------------------------------------------
    def refresh_data(self):
        self._syncing = True
        try:
            binfo = ThinkPadController.get_battery_info()

            # Sidebar model badge
            self.sidebar_bat_label.set_text(f"{binfo['capacity']}% • {binfo['status']}")
            self.bat_info_row.set_subtitle(f"State: {binfo['status']}")
            self.bat_badge.set_text(f"{binfo['capacity']}%")

            # Health details
            self.health_badge.set_text(f"{binfo['health']}%")
            self.health_row.set_subtitle(
                f"{binfo['energy_full_wh']} Wh available / {binfo['energy_design_wh']} Wh design capacity"
            )

            # Cycle count
            self.cycle_badge.set_text(f"{binfo['cycle_count']} Cycles")

            # Power flow & voltage
            watt_text = f"Rate: {binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            if binfo['status'] == "Charging":
                watt_text = f"Charging at +{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            elif binfo['status'] == "Discharging":
                watt_text = f"Discharging at -{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            self.power_row.set_subtitle(watt_text)

            # Hardware spec
            self.spec_row.set_subtitle(
                f"{binfo['manufacturer']} {binfo['technology']} ({binfo['model']})"
            )

            # Update conservation switch
            is_conserv = (binfo['end_threshold'] == 80 and binfo['start_threshold'] >= 70)
            self.conserve_row.set_active(is_conserv)

            self.start_thresh_row.set_value(binfo['start_threshold'] or 75)
            self.stop_thresh_row.set_value(binfo['end_threshold'] or 80)

            # Performance Profile
            pinfo = ThinkPadController.get_platform_profiles()
            cur_prof = pinfo['current']
            if cur_prof in self.profile_keys:
                idx = self.profile_keys.index(cur_prof)
                self.profile_row.set_selected(idx)

            # Keyboard Backlight
            kinfo = ThinkPadController.get_kbd_backlight()
            cur_kbd = min(kinfo['current'], 2)
            self.kbd_row.set_selected(cur_kbd)

            # Lid dot
            lid_val = ThinkPadController.get_lid_logo_dot()
            self.lid_row.set_active(lid_val > 0)

            # CPU Temp
            temp = ThinkPadController.get_cpu_temp()
            self.temp_label.set_text(f"{temp} °C")
        finally:
            self._syncing = False

    def _auto_refresh_tick(self):
        binfo = ThinkPadController.get_battery_info()
        self.sidebar_bat_label.set_text(f"{binfo['capacity']}% • {binfo['status']}")
        self.bat_badge.set_text(f"{binfo['capacity']}%")
        self.bat_info_row.set_subtitle(f"State: {binfo['status']}")

        # Health & Telemetry updates
        self.health_badge.set_text(f"{binfo['health']}%")
        self.cycle_badge.set_text(f"{binfo['cycle_count']} Cycles")

        watt_text = f"Rate: {binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
        if binfo['status'] == "Charging":
            watt_text = f"Charging at +{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
        elif binfo['status'] == "Discharging":
            watt_text = f"Discharging at -{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
        self.power_row.set_subtitle(watt_text)

        temp = ThinkPadController.get_cpu_temp()
        self.temp_label.set_text(f"{temp} °C")
        return True

    def _on_conserve_toggled(self, row, param):
        if getattr(self, '_syncing', False):
            return
        active = row.get_active()
        if active:
            start_val, end_val = 75, 80
        else:
            start_val, end_val = 0, 100

        success, err = ThinkPadController.set_battery_thresholds(start_val, end_val)
        if success:
            self.show_toast(f"Conservation Mode {'Enabled (80%)' if active else 'Disabled (100%)'}")
            self.refresh_data()
        else:
            self.show_toast(f"Failed: {err}")
            self.refresh_data()

    def _on_apply_thresholds_clicked(self, btn):
        start_val = int(self.start_thresh_row.get_value())
        end_val = int(self.stop_thresh_row.get_value())

        if start_val >= end_val:
            self.show_toast("Start threshold must be lower than stop threshold!")
            return

        success, err = ThinkPadController.set_battery_thresholds(start_val, end_val)
        if success:
            self.show_toast(f"Battery thresholds set to: {start_val}% - {end_val}%")
            self.refresh_data()
        else:
            self.show_toast(f"Failed: {err}")
            self.refresh_data()

    def _on_profile_selected(self, row, param):
        if getattr(self, '_syncing', False):
            return
        idx = row.get_selected()
        if 0 <= idx < len(self.profile_keys):
            target_profile = self.profile_keys[idx]
            success, err = ThinkPadController.set_platform_profile(target_profile)
            if success:
                self.show_toast(f"Platform profile switched to {self.profile_map[target_profile]}")
            else:
                self.show_toast(f"Failed: {err}")
                self.refresh_data()

    def _on_kbd_selected(self, row, param):
        if getattr(self, '_syncing', False):
            return
        level = row.get_selected()
        success, err = ThinkPadController.set_kbd_backlight(level)
        if success:
            names = ["Off", "Low", "High"]
            self.show_toast(f"Keyboard backlight set to {names[level] if level < len(names) else level}")
        else:
            self.show_toast(f"Failed: {err}")
            self.refresh_data()

    def _on_lid_dot_toggled(self, row, param):
        if getattr(self, '_syncing', False):
            return
        val = 255 if row.get_active() else 0
        success, err = ThinkPadController.set_lid_logo_dot(val)
        if success:
            self.show_toast(f"ThinkPad Lid LED {'Enabled' if val > 0 else 'Disabled'}")
        else:
            self.show_toast(f"Failed: {err}")
            self.refresh_data()

class ThinkControlApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.lenovo.thinkcontrol",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = ThinkControlWindow(application=self)
        win.present()

if __name__ == "__main__":
    app = ThinkControlApp()
    app.run(sys.argv)
