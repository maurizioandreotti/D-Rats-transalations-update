#!/usr/bin/python
'''Main Window'''
#
# Copyright 2009 Dan Smith <dsmith@danplanet.com>
# review 2015 Maurizio Andreotti
# Copyright 2021-2022 John. E. Malmberg - Python3 Conversion
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import absolute_import
from __future__ import print_function

import logging
import sys
import os
import time
import subprocess

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import GLib

if not '_' in locals():
    import gettext
    _ = gettext.gettext

from d_rats.ui.main_messages import MessagesTab
from d_rats.ui.main_chat import ChatTab
from d_rats.ui.event_tab import EventTab
from d_rats.ui.main_files import FilesTab
from d_rats.ui.main_stations import StationsList
from d_rats.ui.main_common import MainWindowElement
from d_rats.ui.main_common import prompt_for_station
from d_rats.ui.main_common import ask_for_confirmation

from d_rats.menu_helpers import add_menu_theme_image
from d_rats.menu_helpers import add_menu_accel_file_image
from d_rats.menu_helpers import add_menu_accel_theme_image

from d_rats.version import \
    DRATS_VERSION, \
    DRATS_NAME, \
    DRATS_DESCRIPTION, \
    AUTHORS, \
    COPYRIGHT, \
    TRANSLATIONS, \
    WEBSITE

from d_rats import formbuilder
from d_rats import signals


class MainWindow(MainWindowElement):
    '''
    MainWindow.

    :param application: MainApp application
    :type: application: :class:`MainApp`
    '''

    __gsignals__ = {
        "config-changed" : signals.CONFIG_CHANGED,
        "show-map-station" : signals.SHOW_MAP_STATION,
        "ping-station" : signals.PING_STATION,
        "get-station-list" : signals.GET_STATION_LIST,
        "user-send-chat" : signals.USER_SEND_CHAT,
        "get-chat-port" : signals.GET_CHAT_PORT,
        }
    _signals = __gsignals__

    logger = logging.getLogger("MainWindow")

    def __init__(self, application):
        config = application.config
        wtree = Gtk.Builder()
        file_name = os.path.join(config.ship_obj_fn("ui/mainwindow.glade"))
        wtree.add_from_file(file_name)
        MainWindowElement.__init__(self, wtree, config)
        self._application = application
        self._window = self._wtree.get_object("mainwindow")
        self._window.set_application(application)
        self._tabs = self._wtree.get_object("main_tabs")
        self._tabs.connect("switch-page", self._tab_switched)
        self.tabs = {}
        self.__last_status = 0
        self.tabs["chat"] = ChatTab(wtree, config)
        self.tabs["messages"] = MessagesTab(wtree, config, self._window)
        self.tabs["event"] = EventTab(wtree, config, self._window)
        self.tabs["files"] = FilesTab(wtree, config)
        self.tabs["stations"] = StationsList(wtree, config, self._window)
        for label, tab in self.tabs.items():
            tab.connect("notice", self._maybe_blink, label)
        self._current_tab = "messages"
        in_color = "incomingcolor"

        self.tabs["chat"].display_info("D-RATS v%s" % DRATS_VERSION, in_color)
        self.tabs["chat"].display_info(COPYRIGHT, in_color)
        self.tabs["chat"].display_info("")

        self._window.connect("destroy", self._destroy)
        self._window.connect("delete_event", self._delete)
        self._window.connect("focus-in-event", self._got_focus)

        self._connect_menu_items()

        height = self._config.getint("state", "main_size_x")
        width = self._config.getint("state", "main_size_y")
        if self._config.getboolean("state", "main_maximized"):
            self._window.maximize()
            self._window.set_default_size(height, width)
        else:
            self._window.resize(height, width)

        try:
            # Pylance can not detect this import on a linux system.
            import gtkmacintegration # type: ignore
            mbar = self._wtree.get_object("menubar1")
            mbar.hide()
            gtkmacintegration.gtk_mac_menu_set_menu_bar(mbar)
            gtkmacintegration.gtk_mac_menu_set_global_key_handler_enabled(False)
            self.logger.info("Enabled OSX menubar integration")
        except ImportError:
            pass

        self._window.show()

        GLib.timeout_add(3000, self.__update_status)

    def _delete(self, window, event):
        '''
        Delete Event Handler.

        :param window: window
        :type window: :class:`Gtk.Window`
        :param event: Event widget, not used
        :type event: :class:`Gtk.Event`
        :returns: False if program should actually exit
        :rtype: bool
        '''
        self.logger.info("_delete handler invoked %s", type(event) )
        if self._config.getboolean("prefs", "confirm_exit"):
            if not ask_for_confirmation("Really exit D-RATS?", window):
                return True

        window.set_default_size(*window.get_size())
        self._application.quit()
        return True

    def _destroy(self, _window):
        '''
        Destroy Handler.

        The Destroy Handler is invoked by requesting an exit of the program.
        Or by the Delete Handler returning False from a deletion event.

        At this point many of the internal objects may have already been
        destroyed, so this is may be a chance to let background threads,
        etcetera to be notified to cleanup.

        :param _window: Window object, Unused
        :type _window: :class:`Gtk.Window`
        '''
        self.logger.info("_destroy handler called.")
        print("mainwindow: _destroy handler")

    def _activate_save_and_quit(self, _button):
        '''
        Activate Save and Quit handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        width, height = self._window.get_size()
        self._window.set_default_size(width, height)
        # Use delete handler to start the shutdown.
        self._delete(self._window, None)

    def _activate_about(self, _button):
        '''
        Activate About handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        # show the "about window"
        dialog = Gtk.AboutDialog()
        dialog.set_transient_for(self._window)

        verinfo = "Python %s\nGTK %s.%s.%s\n" % (
            sys.version.split()[0],
            Gtk.MAJOR_VERSION,
            Gtk.MINOR_VERSION,
            Gtk.MICRO_VERSION)

        dialog.set_name(DRATS_NAME)
        dialog.set_version(DRATS_VERSION)
        dialog.set_copyright(COPYRIGHT)
        dialog.set_website(WEBSITE)
        dialog.set_authors((AUTHORS,))
        dialog.set_comments(DRATS_DESCRIPTION)
        dialog.set_translator_credits(TRANSLATIONS)
        dialog.set_comments(verinfo)

        dialog.run()
        dialog.destroy()

    def _activate_debug(self, _button):
        '''
        Activate About handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        path = self._config.platform.config_file("debug.log")
        if os.path.exists(path):
            self._config.platform.open_text_file(path)
        else:
            dialog = Gtk.MessageDialog(buttons=Gtk.ButtonsType.OK,
                                       parent=self._window)
            dialog.set_property("text", "Debug log not available")
            dialog.run()
            dialog.destroy()

    def _activate_prefs(self, _button):
        '''
        Activate Prefs handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        saved = self._config.show(parent=self._window)
        if saved:
            self.emit("config-changed")
            for tabs in self.tabs.values():
                tabs.reconfigure()

    def _activate_map(self, _button):
        '''
        Activate Map Display handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        # shows the map window passing our username and callsign
        # as defined in the preferences
        call = self._config.get("user", "callsign")
        self.emit("show-map-station", call)

    def _activate_message_templates(self, _button):
        '''
        Activate Message Templates handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        formbuilder.FormManagerGUI(self._application,
                                   self._config.form_source_dir(),
                                   config=self._config)

    def _activate_ping(self, _button):
        '''
        Activate Ping handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        station_list = self.emit("get-station-list")
        stations = []
        for portlist in station_list.values():
            stations += [str(x) for x in portlist]
        station, port = prompt_for_station(stations, self._config)
        if station:
            self.emit("ping-station", station, port)

    def _activate_conninet(self, button):
        '''
        Activate Connect to the Internet activate handler.

        :param button: Internet Connection Checkbox
        :type button: :class:`Gtk.CheckMenuItem`
        '''
        active = button.get_active()
        self._config.set("state", "connected_inet", str(active))
        self.logger.info("activate_conninet: change on connection status to %s",
                         active)

    def _activate_station_pane(self, button, pane):
        '''
        Activate station pane activate handler.

        :param button: Show Station Pane Button
        :type button: :class:`Gtk.CheckMenuItem'
        :param pane: Station display pane
        :type pane: :class:`Gtk.Box`
        '''
        active = button.get_active()
        self._config.set("state", "sidepane_visible", str(active))
        if active:
            pane.show()
        else:
            pane.hide()

    def _activate_dq(self, _button):
        '''
        Activate dquery handler.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        cfg = self._config

        wtree = Gtk.Builder()
        wtree.add_from_file(cfg.ship_obj_fn("ui/mainwindow.glade"))
        wtree.set_translation_domain("D-RATS")
        dlg = wtree.get_object("dquery_dialog")
        cmd = wtree.get_object("dq_cmd")
        dlg.set_modal(True)
        dlg.set_transient_for(self._window)
        run_status = dlg.run()
        d_text = cmd.get_text()
        dlg.destroy()
        if run_status == Gtk.ResponseType.OK:
            port = self.emit("get-chat-port")

            # original d-rats string
            self.emit("user-send-chat", "CQCQCQ", port, "?D*%s?" % d_text, True)
            # sample rs-ms1a string CQCQCQ: \
            # $$Msg,IZ2LXI,,0011DCtest transmission
            # self.emit("user-send-chat", "CQCQCQ", port,
            #           "$$Msg,IZ000,,0011D,%s" % d, True)

    def _activate_proxy(self, _button):
        '''
        Activate Proxy handler.

        Attempts to start a local D-rats repeater.

        :param _button: Signaled Widget, unused
        :type _button: :class:`Gtk.ImageMenuItem`
        '''
        # WB8TYW: This probably needs some better documentation
        # in the gui or somewhere of what it is trying to do.
        # The location of the d-rats_repeater can also be probably
        # looked up from the location of this module.
        if sys.platform != "darwin":
            args = []
        else:
            args = [sys.executable]
        if os.path.exists("./d-rats_repeater"):
            args.append("./d-rats_repeater")
        else:
            args.append("d-rats_repeater")
        self.logger.info("activate_proxy: Running proxy: %s", str(args))
        subprocess.Popen(args)

    def _connect_menu_items(self):

        menu_quit = self._wtree.get_object("main_menu_quit")
        add_menu_accel_theme_image(menu_quit, "application-exit", _("Quit"))
        menu_quit.connect("activate", self._activate_save_and_quit)

        about = self._wtree.get_object("main_menu_about")
        add_menu_theme_image(about, "help-about", _("About"))
        about.connect("activate", self._activate_about)

        debug = self._wtree.get_object("main_menu_debuglog")
        debug.connect("activate", self._activate_debug)

        menu_prefs = self._wtree.get_object("main_menu_prefs")
        add_menu_accel_theme_image(menu_prefs, "preferences-system",
                                   _("Preferences"))
        menu_prefs.connect("activate", self._activate_prefs)

        menu_map = self._wtree.get_object("main_menu_map")
        add_menu_accel_file_image(menu_map, "images/map.png", _("Map"))
        menu_map.connect("activate", self._activate_map)

        menu_templates = self._wtree.get_object("main_menu_msgtemplates")
        menu_templates.connect("activate", self._activate_message_templates)

        ping = self._wtree.get_object("main_menu_ping")
        add_menu_accel_file_image(ping, "images/event_ping.png",
                                  ("Ping Station"))
        ping.connect("activate", self._activate_ping)

        conn = self._wtree.get_object("main_menu_conninet")
        conn.set_active(self._config.getboolean("state", "connected_inet"))
        self._config.platform.set_connected(conn.get_active())
        conn.connect("activate", self._activate_conninet)

        sspw = self._wtree.get_object("main_menu_showpane")
        pane = self._wtree.get_object("main_stations_frame")
        sspw.set_active(self._config.getboolean("state", "sidepane_visible"))
        if not sspw.get_active():
            pane.hide()
        sspw.connect("activate", self._activate_station_pane, pane)

        menu_dq = self._wtree.get_object("main_menu_dq")
        add_menu_theme_image(menu_dq, "dialog-question", _("Send D*Query"))
        menu_dq.connect("activate", self._activate_dq)

        proxy = self._wtree.get_object("main_menu_proxy")
        add_menu_theme_image(proxy, "network-workgroup", _("Network Proxy"))
        proxy.connect("activate", self._activate_proxy)

    def _page_name(self, index=None):
        if index is None:
            index = self._tabs.get_current_page()

        cur_page = self._tabs.get_nth_page(index)
        _page_ml = self._tabs.get_menu_label_text(cur_page)

        tab_labels = ["messages", "chat", "files", "event"]
        return tab_labels[index]

    def _tab_switched(self, _tabs, _page, page_num):
        '''
        Tab switched switch-page handler.

        :param _tabs: Widget that is signaled, unused
        :type _tabs: :class:`Gtk.Notebook`
        :param _page: Widget for current page, unused
        :type _page: :class:`MainWindowTab`
        :param page_num: The index for the page
        :type page_num: int
        '''
        tab = self._page_name(page_num)
        self.tabs[self._current_tab].deselected()
        self._current_tab = tab
        self.tabs[self._current_tab].selected()

    def _maybe_blink(self, _tab, key):
        '''
        Maybe Blink handler.

        :param _tab: Widget signaled
        :type _tab: :class:`MainWindowTab`
        :param key: key for the window tab
        :type key: str
        '''
        blink = self._config.getboolean("prefs", "blink_%s" % key)
        if blink and not self._window.is_active():
            self._window.set_urgency_hint(True)

        if key == "event":
            sounde = False
        else:
            sounde = self._config.getboolean("sounds", "%s_enabled" % key)
            soundf = self._config.get("sounds", key)
        if sounde:
            self._config.platform.play_sound(soundf)

    def _got_focus(self, _window, _event):
        '''
        Got Focus focus-in-event handler.

        :param _window: Widget signaled
        :type _window: :class:`Gtk.Window`
        '''
        self._window.set_urgency_hint(False)

    def __update_status(self):
        '''
        Update Status Handler.

        :returns: True
        :rtype: bool
        '''
        if (time.time() - self.__last_status) > 30:
            status_bar = self._wtree.get_object("statusbar")
            ident = status_bar.get_context_id("default")
            status_bar.pop(ident)

        return True

    def set_status(self, msg):
        '''
        Set status.

        :param msg: Status message
        :type msg: str
        '''
        status_bar = self._wtree.get_object("statusbar")
        call_bar = self._wtree.get_object("callbar")

        self.__last_status = time.time()

        ident = status_bar.get_context_id("default")
        status_bar.pop(ident)
        status_bar.push(ident, msg)

        call = self._config.get("user", "callsign")
        self._window.set_title("D-RATS: %s" % call)
        call_bar.pop(0)
        call_bar.push(0, call)


class TestMainWindow(Gtk.Application):
    '''
    Test MainWindow application.
    '''

    def __init__(self):
        from gi.repository import Gio
        Gtk.Application.__init__(self,
                                 application_id='localhost.d-rats.test_mw',
                                 flags=Gio.ApplicationFlags.NON_UNIQUE)

        from . import config
        self.config = config.DratsConfig(None)

    # pylint can not detect this for GTK classes.
    # pylint: disable=arguments-differ
    def do_activate(self):
        '''
        Do Activation.

        Emits a :class:`Gio.Application` signal to the application.
        '''
        _main_window = MainWindow(self)
        Gtk.Application.do_activate(self)


def main():
    '''UI Message Model Menu Unit test.'''

    logging.basicConfig(format="%(asctime)s:%(levelname)s:%(name)s:%(message)s",
                        datefmt="%m/%d/%Y %H:%M:%S",
                        level=logging.INFO)

    test_main_window_gui = TestMainWindow()
    test_main_window_gui.run(None)

if __name__ == "__main__":
    main()
