#!/usr/bin/env python3
import sys
import os
import json
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango

from controller import ThinkPadController

class ThinkControlWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("ThinkControl")
        self.set_default_size(920, 640)

        self._syncing = False
        self._is_busy = False
        self._timer_id = None
        self._is_closing = False
        self._thresh_supported = False
        self._profile_supported = False
        self._kbd_supported = False
        self._lid_supported = False

        self.selected_bat = "BAT0"
        self.available_batteries = ThinkPadController.get_battery_list()
        if self.available_batteries:
            self.selected_bat = self.available_batteries[0]

        # Warranty state
        self._warranty_url = "https://pcsupport.lenovo.com/id/id/warranty-lookup#/"
        self._warranty_data = None

        # Main Split View (Sidebar on left, Content on right)
        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_min_sidebar_width(260)
        self.split_view.set_max_sidebar_width(310)
        self.set_content(self.split_view)

        # 1. Build Left Sidebar
        self._build_sidebar()

        # 2. Build Right Content Area (ViewStack with 4 Tabs)
        self._build_content_area()

        # Initial Data Sync
        self.refresh_data()

        # Initial Warranty Cache (read-only from disk if present, no network, no auth)
        cached_w = ThinkPadController.get_cached_warranty()
        if cached_w:
            self._warranty_data = cached_w
            self._warranty_url = cached_w.get("url") or self._warranty_url

        # Select first tab by default
        first_row = self.nav_list.get_row_at_index(0)
        if first_row:
            self.nav_list.select_row(first_row)

        # Adaptive background polling timer based on window active/focus status
        self.connect("notify::is-active", self._on_window_active_changed)
        self.connect("close-request", self._on_close_request)
        self._start_polling_timer(interval_seconds=3)

    # -------------------------------------------------------------
    # ADAPTIVE POLLING TIMER (POWER SAVING)
    # WINDOW LIFECYCLE & ADAPTIVE POLLING TIMER
    # -------------------------------------------------------------
    def _on_close_request(self, *args):
        self._is_closing = True
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        return False

    def _start_polling_timer(self, interval_seconds=3):
        if self._is_closing:
            return
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add_seconds(interval_seconds, self._auto_refresh_tick)

    def _on_window_active_changed(self, window, pspec):
        if getattr(self, '_is_closing', False):
            return
        is_active = self.is_active()
        if is_active:
            # Window in focus: update immediately and poll every 3 seconds
            self._auto_refresh_tick()
            self._start_polling_timer(3)
        else:
            # Window unfocused or minimized: reduce polling frequency to 15s to save CPU & battery
            self._start_polling_timer(15)

    def show_toast(self, text):
        toast = Adw.Toast.new(text)
        self.toast_overlay.add_toast(toast)

    def set_busy_state(self, busy):
        self._is_busy = busy
        self.apply_btn.set_sensitive(not busy)
        self.conserve_row.set_sensitive(not busy)
        self.profile_row.set_sensitive(not busy)
        self.kbd_row.set_sensitive(not busy)
        self.lid_row.set_sensitive(not busy)
        if busy:
            self.apply_btn.set_sensitive(False)
            self.conserve_row.set_sensitive(False)
            self.start_thresh_row.set_sensitive(False)
            self.stop_thresh_row.set_sensitive(False)
            self.profile_row.set_sensitive(False)
            self.kbd_row.set_sensitive(False)
            self.lid_row.set_sensitive(False)
        else:
            thresh_ok = getattr(self, '_thresh_supported', True)
            self.apply_btn.set_sensitive(thresh_ok)
            self.conserve_row.set_sensitive(thresh_ok)
            self.start_thresh_row.set_sensitive(thresh_ok)
            self.stop_thresh_row.set_sensitive(thresh_ok)
            self.profile_row.set_sensitive(getattr(self, '_profile_supported', True))
            self.kbd_row.set_sensitive(getattr(self, '_kbd_supported', True))
            self.lid_row.set_sensitive(getattr(self, '_lid_supported', True))

        if getattr(self, 'bat_dropdown', None):
            self.bat_dropdown.set_sensitive(not busy)

    def _on_about_clicked(self, btn):
        about = Adw.AboutDialog()
        about_cls = getattr(Adw, "AboutDialog", getattr(Adw, "AboutWindow", None))
        about = about_cls()
        about.set_application_name("ThinkControl")
        about.set_application_icon("com.lenovo.thinkcontrol")
        about.set_version("1.1.0")
        about.set_developer_name("Anggiyawan")
        about.set_copyright("© 2026 Anggiyawan")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/anggiyawan/ThinkControl")
        about.set_issue_url("https://github.com/anggiyawan/ThinkControl/issues")
        about.set_comments("Lenovo Vantage Hardware Control Center for ThinkPad on Linux (Zorin OS / Ubuntu).\nComprehensive control over battery charging thresholds, health diagnostics, dual-battery support, performance profiles, and illumination.")
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

        # Multi-Battery Selector in Sidebar (if > 1 battery detected)
        if len(self.available_batteries) > 1:
            bat_select_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            bat_select_box.set_margin_top(4)
            lbl = Gtk.Label(label="Active:")
            lbl.add_css_class("caption")
            lbl.add_css_class("dim-label")
            bat_select_box.append(lbl)

            self.bat_dropdown = Gtk.DropDown.new_from_strings(self.available_batteries)
            self.bat_dropdown.connect("notify::selected", self._on_battery_selected)
            bat_select_box.append(self.bat_dropdown)
            inner_card.append(bat_select_box)
        else:
            self.bat_dropdown = None

        sidebar_box.append(model_card)

        # Navigation List (5 Tabs)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        sidebar_box.append(scrolled)

        self.nav_list = Gtk.ListBox()
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.connect("row-selected", self._on_nav_row_selected)
        scrolled.set_child(self.nav_list)

        # Define the 5 Navigation Items
        self.nav_items = [
            ("charging", "Battery Charging", "battery-level-80-charging-symbolic", "Thresholds &amp; Conservation"),
            ("health", "Battery Health", "emblem-favorite-symbolic", "Condition, Cycles &amp; Specs"),
            ("performance", "Performance", "speedometer-symbolic", "ACPI Thermal Modes"),
            ("keyboard", "Keyboard &amp; Lighting", "input-keyboard-symbolic", "Backlight &amp; Lid Logo LED"),
            ("warranty", "Warranty &amp; Support", "security-high-symbolic", "Official Lenovo Coverage &amp; Specs")
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

    def _on_battery_selected(self, dropdown, param):
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.available_batteries):
            self.selected_bat = self.available_batteries[idx]
            self.refresh_data()

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

        # Tab 5: Warranty & Support
        self.view_stack.add_titled(self._build_page_warranty(), "warranty", "Warranty & Support")

        self.content_page = Adw.NavigationPage.new(content_box, "Battery Charging")
        self.split_view.set_content(self.content_page)

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

        self.charging_group = Adw.PreferencesGroup()
        self.charging_group.set_title("Battery &amp; Charging Control")
        self.charging_group.set_description("Manage charging thresholds to preserve battery chemistry and longevity")
        box.append(self.charging_group)

        # Charge Level Row
        self.bat_info_row = Adw.ActionRow()
        self.bat_info_row.set_title("Current Charge Level")
        self.bat_info_row.set_subtitle("Loading...")
        self.bat_info_row.set_icon_name("battery-symbolic")

        self.bat_badge = Gtk.Label()
        self.bat_badge.add_css_class("heading")
        self.bat_info_row.add_suffix(self.bat_badge)
        self.charging_group.add(self.bat_info_row)

        # Conservation Mode Switch
        self.conserve_row = Adw.SwitchRow()
        self.conserve_row.set_title("Conservation Mode (80% Limit)")
        self.conserve_row.set_subtitle("Stops charging at 80% to extend battery lifespan")
        self.conserve_row.connect("notify::active", self._on_conserve_toggled)
        self.charging_group.add(self.conserve_row)

        # Start Threshold
        self.start_thresh_row = Adw.SpinRow.new_with_range(20, 95, 5)
        self.start_thresh_row.set_title("Start Charging Threshold (%)")
        self.start_thresh_row.set_subtitle("Battery begins charging when below this percentage")
        self.charging_group.add(self.start_thresh_row)

        # Stop Threshold
        self.stop_thresh_row = Adw.SpinRow.new_with_range(40, 100, 5)
        self.stop_thresh_row.set_title("Stop Charging Threshold (%)")
        self.stop_thresh_row.set_subtitle("Battery stops charging upon reaching this percentage")
        self.charging_group.add(self.stop_thresh_row)

        # Apply Button + Spinner
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_halign(Gtk.Align.END)
        btn_box.set_margin_top(8)

        self.action_spinner = Gtk.Spinner()
        btn_box.append(self.action_spinner)

        self.apply_btn = Gtk.Button(label="Apply Custom Thresholds")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", self._on_apply_thresholds_clicked)
        btn_box.append(self.apply_btn)

        box.append(btn_box)

        # Persistence Status Group
        persist_group = Adw.PreferencesGroup()
        persist_group.set_title("Configuration Persistence")
        self.persist_row = Adw.ActionRow()
        self.persist_row.set_title("Automatic Hardware Restoration")
        self.persist_row.set_subtitle("Configured thresholds are saved and automatically restored on boot and sleep/resume")
        self.persist_row.set_icon_name("emblem-ok-symbolic")
        persist_group.add(self.persist_row)
        box.append(persist_group)

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
    # TAB 5: WARRANTY & SUPPORT
    # -------------------------------------------------------------
    def _build_page_warranty(self):
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

        # 1. Device Hardware Specification Group
        dev_group = Adw.PreferencesGroup()
        dev_group.set_title("ThinkPad Hardware Identity")
        dev_group.set_description("Machine model, serial number, and hardware identification")
        box.append(dev_group)

        details = ThinkPadController.get_model_details()

        self.w_model_row = Adw.ActionRow()
        self.w_model_row.set_title("Product Model")
        self.w_model_row.set_subtitle(details.get("title", "ThinkPad"))
        self.w_model_row.set_icon_name("computer-symbolic")
        dev_group.add(self.w_model_row)

        self.w_mtm_row = Adw.ActionRow()
        self.w_mtm_row.set_title("Machine Type Model (MTM)")
        mtm = ThinkPadController._read_file("/sys/class/dmi/id/product_name", "-")
        self.w_mtm_row.set_subtitle(mtm)
        self.w_mtm_row.set_icon_name("dialog-information-symbolic")
        dev_group.add(self.w_mtm_row)

        self.w_serial_row = Adw.ActionRow()
        self.w_serial_row.set_title("Serial Number (S/N)")
        serial = ThinkPadController.get_device_serial()
        self.w_serial_row.set_subtitle(serial if serial else "Not saved (Click pencil icon)")
        self.w_serial_row.set_icon_name("channel-insecure-symbolic")

        set_sn_btn = Gtk.Button()
        set_sn_btn.set_icon_name("document-edit-symbolic")
        set_sn_btn.set_valign(Gtk.Align.CENTER)
        set_sn_btn.add_css_class("flat")
        set_sn_btn.set_tooltip_text("Set or detect ThinkPad serial number")
        set_sn_btn.connect("clicked", lambda b: self._show_serial_prompt_dialog())
        self.w_serial_row.add_suffix(set_sn_btn)
        dev_group.add(self.w_serial_row)

        # 2. Official Lenovo Warranty Coverage Group
        self.w_status_group = Adw.PreferencesGroup()
        self.w_status_group.set_title("Official Lenovo Warranty Coverage")
        self.w_status_group.set_description("Manufacturer warranty status retrieved directly from Lenovo Support")
        box.append(self.w_status_group)

        # Status row with badge
        self.w_status_row = Adw.ActionRow()
        self.w_status_row.set_title("Coverage Status")
        self.w_status_row.set_subtitle("Not checked (Click 'Check Now' below)")
        self.w_status_row.set_icon_name("security-high-symbolic")

        self.w_status_badge = Gtk.Label(label="Unknown")
        self.w_status_badge.add_css_class("caption")
        self.w_status_badge.add_css_class("pill")
        self.w_status_badge.set_valign(Gtk.Align.CENTER)
        self.w_status_row.add_suffix(self.w_status_badge)
        self.w_status_group.add(self.w_status_row)

        # Package name row
        self.w_pkg_row = Adw.ActionRow()
        self.w_pkg_row.set_title("Warranty Package")
        self.w_pkg_row.set_subtitle("-")
        self.w_pkg_row.set_icon_name("starred-symbolic")
        self.w_status_group.add(self.w_pkg_row)

        # Validity period row
        self.w_period_row = Adw.ActionRow()
        self.w_period_row.set_title("Validity Period")
        self.w_period_row.set_subtitle("-")
        self.w_period_row.set_icon_name("x-office-calendar-symbolic")
        self.w_status_group.add(self.w_period_row)

        # Service delivery type
        self.w_delivery_row = Adw.ActionRow()
        self.w_delivery_row.set_title("Service Delivery Type")
        self.w_delivery_row.set_subtitle("-")
        self.w_delivery_row.set_icon_name("preferences-system-symbolic")
        self.w_status_group.add(self.w_delivery_row)

        # 3. Actions & Portal Links Group
        action_group = Adw.PreferencesGroup()
        action_group.set_title("Actions &amp; Official Portal")
        box.append(action_group)

        # Check warranty button row
        check_row = Adw.ActionRow()
        check_row.set_title("Check Warranty Status")
        check_row.set_subtitle("Retrieve latest warranty status online from Lenovo Support")
        check_row.set_icon_name("view-refresh-symbolic")

        self.check_warranty_btn = Gtk.Button(label="Check Now")
        self.check_warranty_btn.set_valign(Gtk.Align.CENTER)
        self.check_warranty_btn.add_css_class("suggested-action")
        self.check_warranty_btn.connect("clicked", self._on_check_warranty_clicked)
        check_row.add_suffix(self.check_warranty_btn)
        action_group.add(check_row)

        # Open portal button row
        portal_row = Adw.ActionRow()
        portal_row.set_title("View Official Details on Lenovo Support")
        portal_row.set_subtitle("Open official Lenovo portal in web browser for claim details and warranty extensions")
        portal_row.set_icon_name("web-browser-symbolic")

        self.open_portal_btn = Gtk.Button()
        self.open_portal_btn.set_valign(Gtk.Align.CENTER)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.append(Gtk.Label(label="Open Browser"))
        btn_icon = Gtk.Image.new_from_icon_name("external-link-symbolic")
        btn_icon.set_pixel_size(12)
        btn_box.append(btn_icon)
        self.open_portal_btn.set_child(btn_box)
        self.open_portal_btn.connect("clicked", self._on_view_warranty_clicked)
        portal_row.add_suffix(self.open_portal_btn)
        action_group.add(portal_row)

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
                "health": "Battery Health",
                "performance": "Performance",
                "keyboard": "Keyboard & Lighting",
                "warranty": "Warranty & Support"
            }
            title = title_dict.get(tag, "ThinkControl")
            self.content_title_label.set_text(title)
            if hasattr(self, 'content_page'):
                self.content_page.set_title(title)

            if tag == "warranty" and not getattr(self, '_warranty_data', None):
                cached_w = ThinkPadController.get_cached_warranty()
                if cached_w:
                    self._update_warranty_ui(cached_w, None)

    # -------------------------------------------------------------
    # DATA REFRESH & SENSORS
    # -------------------------------------------------------------
    def refresh_data(self):
        if self._is_busy:
            return

        self._syncing = True
        try:
            binfo = ThinkPadController.get_battery_info(self.selected_bat)
            self._thresh_supported = binfo['has_threshold_support']

            bat_label_text = f"{binfo['capacity']}% • {binfo['status']}"
            if len(self.available_batteries) > 1:
                bat_label_text = f"[{self.selected_bat}] {bat_label_text}"

            # Sidebar model badge
            self.sidebar_bat_label.set_text(bat_label_text)
            self.bat_info_row.set_subtitle(GLib.markup_escape_text(f"State: {binfo['status']} ({self.selected_bat})"))
            self.bat_badge.set_text(f"{binfo['capacity']}%")

            # Check threshold hardware support
            if not self._thresh_supported:
                self.conserve_row.set_sensitive(False)
                self.conserve_row.set_subtitle("Charging thresholds not supported by ACPI on this battery")
                self.start_thresh_row.set_sensitive(False)
                self.stop_thresh_row.set_sensitive(False)
                self.apply_btn.set_sensitive(False)
            else:
                self.conserve_row.set_sensitive(True)
                self.conserve_row.set_subtitle("Stops charging at 80% to extend battery lifespan")
                self.start_thresh_row.set_sensitive(True)
                self.stop_thresh_row.set_sensitive(True)
                self.apply_btn.set_sensitive(True)

            # Health details with dynamic status styling
            self.health_badge.set_text(f"{binfo['health']}%")
            self.health_badge.remove_css_class("success")
            self.health_badge.remove_css_class("warning")
            self.health_badge.remove_css_class("error")
            if binfo['health'] >= 80:
                self.health_badge.add_css_class("success")
            elif binfo['health'] >= 50:
                self.health_badge.add_css_class("warning")
            else:
                self.health_badge.add_css_class("error")

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
            spec_text = f"{binfo['manufacturer']} {binfo['technology']} ({binfo['model']})"
            self.spec_row.set_subtitle(GLib.markup_escape_text(spec_text))

            # Update conservation switch
            is_conserv = (binfo['end_threshold'] == 80 and binfo['start_threshold'] >= 70)
            self.conserve_row.set_active(is_conserv)

            if binfo['start_threshold'] >= 20:
                self.start_thresh_row.set_value(binfo['start_threshold'])
            else:
                self.start_thresh_row.set_value(75)

            if binfo['end_threshold'] >= 40:
                self.stop_thresh_row.set_value(binfo['end_threshold'])
            else:
                self.stop_thresh_row.set_value(80)

            # Performance Profile
            pinfo = ThinkPadController.get_platform_profiles()
            self._profile_supported = pinfo['supported']
            if not self._profile_supported:
                self.profile_row.set_sensitive(False)
                self.profile_row.set_subtitle("Platform profile control not supported on this device")
            else:
                self.profile_row.set_sensitive(True)
                cur_prof = pinfo['current']
                if cur_prof in self.profile_keys:
                    idx = self.profile_keys.index(cur_prof)
                    self.profile_row.set_selected(idx)

            # Keyboard Backlight
            kinfo = ThinkPadController.get_kbd_backlight()
            self._kbd_supported = kinfo['supported']
            if not self._kbd_supported:
                self.kbd_row.set_sensitive(False)
                self.kbd_row.set_subtitle("Keyboard backlight not available on this device")
            else:
                self.kbd_row.set_sensitive(True)
                cur_kbd = min(kinfo['current'], 2)
                self.kbd_row.set_selected(cur_kbd)

            # Lid dot
            lid_info = ThinkPadController.get_lid_logo_dot()
            self._lid_supported = lid_info['supported']
            if not self._lid_supported:
                self.lid_row.set_sensitive(False)
                self.lid_row.set_subtitle("Lid logo LED not available on this device")
            else:
                self.lid_row.set_sensitive(True)
                self.lid_row.set_active(lid_info['current'] > 0)

            # CPU Temp
            temp = ThinkPadController.get_cpu_temp()
            self.temp_label.set_text(f"{temp} °C")
        finally:
            self._syncing = False

    def _auto_refresh_tick(self):
        if getattr(self, '_is_closing', False):
            return False
        if self._is_busy:
            return True

        try:
            binfo = ThinkPadController.get_battery_info(self.selected_bat)
            bat_label_text = f"{binfo['capacity']}% • {binfo['status']}"
            if len(self.available_batteries) > 1:
                bat_label_text = f"[{self.selected_bat}] {bat_label_text}"

            self.sidebar_bat_label.set_text(bat_label_text)
            self.bat_badge.set_text(f"{binfo['capacity']}%")
            self.bat_info_row.set_subtitle(GLib.markup_escape_text(f"State: {binfo['status']} ({self.selected_bat})"))

            # Health & Telemetry updates
            self.health_badge.set_text(f"{binfo['health']}%")
            self.health_badge.remove_css_class("success")
            self.health_badge.remove_css_class("warning")
            self.health_badge.remove_css_class("error")
            if binfo['health'] >= 80:
                self.health_badge.add_css_class("success")
            elif binfo['health'] >= 50:
                self.health_badge.add_css_class("warning")
            else:
                self.health_badge.add_css_class("error")

            self.cycle_badge.set_text(f"{binfo['cycle_count']} Cycles")

            watt_text = f"Rate: {binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            if binfo['status'] == "Charging":
                watt_text = f"Charging at +{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            elif binfo['status'] == "Discharging":
                watt_text = f"Discharging at -{binfo['power_w']} W | Voltage: {binfo['voltage_v']} V"
            self.power_row.set_subtitle(watt_text)

            temp = ThinkPadController.get_cpu_temp()
            self.temp_label.set_text(f"{temp} °C")
        except Exception:
            pass
        return True

    # -------------------------------------------------------------
    # ASYNCHRONOUS ACTION HANDLERS (NON-BLOCKING)
    # -------------------------------------------------------------
    def _on_conserve_toggled(self, row, param):
        if getattr(self, '_syncing', False) or self._is_busy:
            return
        active = row.get_active()
        start_val, end_val = (75, 80) if active else (0, 100)

        self.set_busy_state(True)
        self.action_spinner.start()

        def on_done(success, err):
            if getattr(self, '_is_closing', False):
                return
            self.action_spinner.stop()
            self.set_busy_state(False)
            if success:
                self.show_toast(f"Conservation Mode {'Enabled (80%)' if active else 'Disabled (100%)'}")
            else:
                self.show_toast(f"Failed: {err}")
            self.refresh_data()

        ThinkPadController.set_battery_thresholds_async(self.selected_bat, start_val, end_val, on_done)

    def _on_apply_thresholds_clicked(self, btn):
        if self._is_busy:
            return

        start_val = int(self.start_thresh_row.get_value())
        end_val = int(self.stop_thresh_row.get_value())

        if start_val >= end_val:
            self.show_toast("Start threshold must be lower than stop threshold!")
            return

        self.set_busy_state(True)
        self.action_spinner.start()

        def on_done(success, err):
            if getattr(self, '_is_closing', False):
                return
            self.action_spinner.stop()
            self.set_busy_state(False)
            if success:
                self.show_toast(f"Battery thresholds set to: {start_val}% - {end_val}%")
            else:
                self.show_toast(f"Failed: {err}")
            self.refresh_data()

        ThinkPadController.set_battery_thresholds_async(self.selected_bat, start_val, end_val, on_done)

    def _on_profile_selected(self, row, param):
        if getattr(self, '_syncing', False) or self._is_busy:
            return
        idx = row.get_selected()
        if 0 <= idx < len(self.profile_keys):
            target_profile = self.profile_keys[idx]
            self.set_busy_state(True)

            def on_done(success, err):
                if getattr(self, '_is_closing', False):
                    return
                self.set_busy_state(False)
                if success:
                    self.show_toast(f"Platform profile switched to {self.profile_map[target_profile]}")
                    prof_title = self.profile_map.get(target_profile, target_profile)
                    self.show_toast(f"Platform profile switched to {prof_title}")
                else:
                    self.show_toast(f"Failed: {err}")
                self.refresh_data()

            ThinkPadController.set_platform_profile_async(target_profile, on_done)

    def _on_kbd_selected(self, row, param):
        if getattr(self, '_syncing', False) or self._is_busy:
            return
        level = row.get_selected()
        self.set_busy_state(True)

        def on_done(success, err):
            if getattr(self, '_is_closing', False):
                return
            self.set_busy_state(False)
            if success:
                names = ["Off", "Low", "High"]
                self.show_toast(f"Keyboard backlight set to {names[level] if level < len(names) else level}")
            else:
                self.show_toast(f"Failed: {err}")
            self.refresh_data()

        ThinkPadController.set_kbd_backlight_async(level, on_done)

    def _on_lid_dot_toggled(self, row, param):
        if getattr(self, '_syncing', False) or self._is_busy:
            return
        val = 255 if row.get_active() else 0
        self.set_busy_state(True)

        def on_done(success, err):
            if getattr(self, '_is_closing', False):
                return
            self.set_busy_state(False)
            if success:
                self.show_toast(f"ThinkPad Lid LED {'Enabled' if val > 0 else 'Disabled'}")
            else:
                self.show_toast(f"Failed: {err}")
            self.refresh_data()

        ThinkPadController.set_lid_logo_dot_async(val, on_done)

    # -------------------------------------------------------------
    # WARRANTY HANDLERS & DIALOGS (TAB 5)
    # -------------------------------------------------------------
    def _update_warranty_ui(self, data, err):
        if getattr(self, '_is_closing', False):
            return
        self._warranty_data = data
        if not hasattr(self, 'w_status_row'):
            return

        if not data:
            self.w_status_row.set_subtitle("Not checked or data unavailable")
            self.w_status_badge.set_text("Unknown")
            self.w_status_badge.remove_css_class("success")
            self.w_status_badge.remove_css_class("warning")
            self._warranty_url = "https://pcsupport.lenovo.com/id/id/warranty-lookup#/"
            return

        url = data.get("url") or "https://pcsupport.lenovo.com/id/id/warranty-lookup#/"
        self._warranty_url = url
        is_active = data.get("is_active", False)
        rem = data.get("remaining_days", -1)
        start_date = data.get("start_date", "-")
        end_date = data.get("end_date", "-")
        pkg = data.get("package_name", "Lenovo Warranty")
        delivery = data.get("delivery_type", "Standard")
        serial = data.get("serial", "")

        if serial and hasattr(self, 'w_serial_row'):
            self.w_serial_row.set_subtitle(serial)

        self.w_status_badge.remove_css_class("success")
        self.w_status_badge.remove_css_class("warning")
        self.w_status_badge.remove_css_class("error")

        if is_active:
            self.w_status_badge.set_text("Active")
            self.w_status_badge.add_css_class("success")
            self.w_status_row.set_subtitle(f"Official Warranty Active ({rem} days remaining)")
            self.w_status_row.set_icon_name("security-high-symbolic")
        elif rem == 0 or data.get("status") == "Expired":
            self.w_status_badge.set_text("Expired")
            self.w_status_badge.add_css_class("warning")
            self.w_status_row.set_subtitle(f"Warranty period expired on {end_date}")
            self.w_status_row.set_icon_name("security-medium-symbolic")
        else:
            self.w_status_badge.set_text("Online")
            self.w_status_row.set_subtitle("Click 'Check Now' to query online")
            self.w_status_row.set_icon_name("help-about-symbolic")

        self.w_pkg_row.set_subtitle(pkg)
        if start_date != "-" or end_date != "-":
            self.w_period_row.set_subtitle(f"{start_date} to {end_date}")
        else:
            self.w_period_row.set_subtitle("-")
        self.w_delivery_row.set_subtitle(delivery)

    def _on_check_warranty_clicked(self, btn):
        serial = ThinkPadController.get_device_serial()
        if not serial:
            self._show_serial_prompt_dialog()
            return

        self.check_warranty_btn.set_sensitive(False)
        self.w_status_row.set_subtitle("Contacting Lenovo Support servers...")
        self.show_toast("Checking warranty status...")

        def on_done(data, err):
            self.check_warranty_btn.set_sensitive(True)
            if getattr(self, '_is_closing', False):
                return
            if data and data.get("status") in ("In Warranty", "Expired"):
                self.show_toast("Warranty details successfully updated!")
            elif err:
                self.show_toast(f"Lookup failed: {err}")
            self._update_warranty_ui(data, err)

        ThinkPadController.fetch_warranty_async(on_done, force=True)

    def _on_view_warranty_clicked(self, btn):
        data = getattr(self, '_warranty_data', None)
        serial = data.get("serial", "") if data else ThinkPadController.get_device_serial()
        url = getattr(self, '_warranty_url', None) or "https://pcsupport.lenovo.com/id/id/warranty-lookup#/"

        if not serial:
            self._show_serial_prompt_dialog()
            return

        try:
            Gtk.show_uri(self, url, 0)
            self.show_toast("Opening warranty details in browser...")
        except Exception:
            try:
                Gio.AppInfo.launch_default_for_uri(url, None)
                self.show_toast("Opening warranty details in browser...")
            except Exception as e:
                self.show_toast(f"Failed to open link: {e}")

    def _show_serial_prompt_dialog(self):
        dialog = Adw.MessageDialog.new(self, "ThinkPad Serial Number", "")
        dialog.set_body(
            "A ThinkPad serial number is required to query official warranty details.\n"
            "You can enter the serial number (printed on bottom cover or in BIOS), "
            "or detect it automatically (requires administrator authorization)."
        )

        entry = Gtk.Entry()
        entry.set_placeholder_text("Example: PF123456")
        entry.set_margin_top(8)
        entry.set_margin_bottom(8)
        entry.set_alignment(0.5)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(entry)
        dialog.set_extra_child(box)

        dialog.add_response("cancel", "Cancel")
        dialog.add_response("portal", "Open Web Portal")
        dialog.add_response("detect", "Auto-Detect")
        dialog.add_response("save", "Save & Check")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response_id):
            if response_id == "portal":
                portal_url = "https://pcsupport.lenovo.com/id/id/warranty-lookup#/"
                try:
                    Gtk.show_uri(self, portal_url, 0)
                except Exception:
                    Gio.AppInfo.launch_default_for_uri(portal_url, None)
            elif response_id == "detect":
                self.show_toast("Detecting serial number...")
                def on_detect(s, err):
                    if s:
                        self.show_toast("Serial number detected!")
                        if hasattr(self, 'w_serial_row'):
                            self.w_serial_row.set_subtitle(s)
                        cache_dir = os.path.expanduser("~/.cache/thinkcontrol")
                        os.makedirs(cache_dir, exist_ok=True)
                        try:
                            with open(os.path.join(cache_dir, "warranty.json"), "w") as f:
                                json.dump({"serial": s}, f)
                        except Exception:
                            pass
                        ThinkPadController.fetch_warranty_async(self._update_warranty_ui, force=True)
                    else:
                        self.show_toast(f"Detection failed: {err or 'Permission cancelled'}")
                ThinkPadController.detect_serial_privileged_async(on_detect)
            elif response_id == "save":
                s = entry.get_text().strip().upper()
                if s:
                    if hasattr(self, 'w_serial_row'):
                        self.w_serial_row.set_subtitle(s)
                    cache_dir = os.path.expanduser("~/.cache/thinkcontrol")
                    os.makedirs(cache_dir, exist_ok=True)
                    try:
                        with open(os.path.join(cache_dir, "warranty.json"), "w") as f:
                            json.dump({"serial": s}, f)
                    except Exception:
                        pass
                    ThinkPadController.fetch_warranty_async(self._update_warranty_ui, force=True)
                else:
                    self.show_toast("Serial number cannot be empty")

        dialog.connect("response", on_response)
        dialog.present()

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
