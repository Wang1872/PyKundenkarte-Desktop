"""PyKundenkarte Desktop: lokal, offline, ohne Webserver."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from kundenkarte.csv_io import CSVError, read_csv
from kundenkarte.customer_csv import CustomerFile, SaveError
from kundenkarte.customers import FIELDS, address, contact_lines, filter_customers, locate, prepare, suggest
from kundenkarte.map_view import MapView
from kundenkarte.paths import project_dir
from kundenkarte.postcodes import load_postcodes
from kundenkarte.session import COLORS, SessionStore, customer_key


def warning(parent, message: str):
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("PyKundenkarte")
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(message)
    dialog.exec()


def light_palette():
    """Explizite Kontraste, auch wenn Windows Qt im Dunkelmodus startet."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f3f6fa",
        QPalette.ColorRole.WindowText: "#1e293b",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f5f8fc",
        QPalette.ColorRole.Text: "#1e293b",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#1e293b",
        QPalette.ColorRole.Highlight: "#dbeafe",
        QPalette.ColorRole.HighlightedText: "#0f172a",
        QPalette.ColorRole.PlaceholderText: "#64748b",
        QPalette.ColorRole.ToolTipBase: "#ffffff",
        QPalette.ColorRole.ToolTipText: "#1e293b",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#64748b"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#64748b"))
    return palette


class ImportOptions(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("CSV-Importoptionen")
        layout = QFormLayout(self)
        self.encoding = QComboBox()
        self.encoding.addItems(["Automatisch", "utf-8-sig", "utf-8", "cp1252", "iso-8859-1"])
        self.separator = QComboBox()
        for label, value in [("Automatisch", "Automatisch"), ("Semikolon ;", ";"),
                             ("Komma ,", ","), ("Tabulator", "\t"), ("Pipe |", "|")]:
            self.separator.addItem(label, value)
        layout.addRow("Kodierung", self.encoding)
        layout.addRow("Trennzeichen", self.separator)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class ColumnMapping(QDialog):
    def __init__(self, parent, headers):
        super().__init__(parent)
        self.setWindowTitle("CSV-Spalten zuordnen")
        layout = QFormLayout(self)
        self.boxes = {}
        for field, (title, required, _) in FIELDS.items():
            box = QComboBox()
            box.addItems(["—", *headers])
            box.setCurrentText(suggest(field, headers))
            layout.addRow(title + (" *" if required else " (optional)"), box)
            self.boxes[field] = box
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def mapping(self):
        return {field: box.currentText() for field, box in self.boxes.items()}

    def _validate(self):
        chosen = self.mapping()
        missing = [FIELDS[field][0] for field in FIELDS if FIELDS[field][1] and chosen[field] == "—"]
        nonempty = [column for column in chosen.values() if column != "—"]
        if missing:
            warning(self, "Pflichtspalten fehlen: " + ", ".join(missing))
        elif len(nonempty) != len(set(nonempty)):
            warning(self, "Eine CSV-Spalte darf nicht mehreren Feldern zugeordnet werden.")
        else:
            self.accept()


class AddCustomer(QDialog):
    """Hausnummer wird für neue Einträge bewusst nicht abgefragt."""

    def __init__(self, parent, mapping):
        super().__init__(parent)
        self.setWindowTitle("Kunde hinzufügen")
        self.setMinimumWidth(380)
        layout = QFormLayout(self)
        self.inputs = {}
        for field, label in (("name", "Kundenname"), ("street", "Straße"),
                             ("postcode", "PLZ"), ("city", "Ort")):
            edit = QLineEdit()
            layout.addRow(label + " *", edit)
            self.inputs[field] = edit
        for field, label in (("email", "E-Mail"), ("phone", "Telefon")):
            if mapping.get(field, "—") != "—":
                edit = QLineEdit()
                layout.addRow(label + " (optional)", edit)
                self.inputs[field] = edit
        self.inputs["name"].setFocus()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("In CSV speichern")
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return {field: edit.text().strip() for field, edit in self.inputs.items()}

    def _validate(self):
        if any(not self.inputs[field].text().strip() for field in ("name", "street", "postcode", "city")):
            warning(self, "Bitte alle vier Felder ausfüllen.")
        else:
            self.accept()


class MarkerColorDialog(QDialog):
    def __init__(self, parent, current):
        super().__init__(parent)
        self.setWindowTitle("Markerfarbe")
        self.choice = current
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Farbe für diesen Kunden"))
        for name, code in COLORS.items():
            button = QPushButton(f"●  {name}")
            button.setStyleSheet(f"QPushButton {{ color: {code}; font-size: 16px; text-align: left; }}")
            button.clicked.connect(lambda _checked=False, color=name: self._choose(color))
            layout.addWidget(button)
        cancel = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        cancel.rejected.connect(self.reject)
        layout.addWidget(cancel)

    def _choose(self, name):
        self.choice = name
        self.accept()


class MainWindow(QMainWindow):
    """Hauptfenster: CSV-Daten, lokale PLZ-Referenzen, Karte und Filter."""

    HEADERS = ["CSV-Zeile", "Farbe", "Kundenname", "Straße", "Hausnummer", "PLZ", "Ort", "Bundesland", "Land", "E-Mail", "Telefon", "Position / Hinweis"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyKundenkarte")
        self.resize(1180, 740)
        self.customers = []
        self.customer_file = None
        self.lookup = {}
        self.lookup_file = None
        self.row_index = {}
        self.lookup_text = "Keine lokale Ortsdatei geladen"
        self.session = SessionStore()
        self.active_file_path = None
        self.marker_colors = {}
        self._session_ready = False
        self._updating_table = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_session)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        csv_button = QPushButton("CSV öffnen …")
        csv_button.setObjectName("primary")
        csv_button.clicked.connect(self.open_customers)
        self.add_button = QPushButton("+ Kunde hinzufügen")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.add_customer)
        plz_button = QPushButton("Ortsdatei ändern …")
        plz_button.clicked.connect(self.open_postcodes)
        toolbar.addWidget(csv_button)
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(plz_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.lookup_label = QLabel("")
        self.lookup_label.setWordWrap(True)
        self.lookup_label.setObjectName("hint")
        layout.addWidget(self.lookup_label)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Name, Straße, PLZ, Ort oder Bundesland")
        self.search.setToolTip("Mehrere Suchbegriffe mit && als ODER verbinden, z. B. Hessen && Baden-Württemberg.")
        self.postcode_filter = QLineEdit()
        self.postcode_filter.setPlaceholderText("z. B. 60 -- 69 oder 01 && 09")
        self.postcode_filter.setToolTip("PLZ-Anfang oder Bereich: 01 -- 09. Beide Grenzen gleich lang; && verbindet mit ODER.")
        filters.addWidget(QLabel("Suche:"))
        filters.addWidget(self.search, 3)
        filters.addWidget(QLabel("PLZ beginnt mit:"))
        filters.addWidget(self.postcode_filter, 1)
        layout.addLayout(filters)
        self.count_label = QLabel("0 Kunden gefunden")
        self.count_label.setObjectName("count")
        layout.addWidget(self.count_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        self.map = MapView(self.select_customer)
        map_panel = QWidget()
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(6)
        map_controls = QHBoxLayout()
        map_controls.addWidget(QLabel("Karte:"))
        self.mode_buttons = QButtonGroup(self)
        self.mode_buttons.setExclusive(True)
        for name, mode in (("Bewegen", "move"), ("Zeichnen", "draw"), ("Radieren", "erase")):
            button = QPushButton(name)
            button.setObjectName("mode")
            button.setCheckable(True)
            button.setChecked(mode == "move")
            button.clicked.connect(lambda _checked=False, selected=mode: self.map.set_draw_mode(selected))
            self.mode_buttons.addButton(button)
            map_controls.addWidget(button)
        self.undo_button = QPushButton("Linie zurück")
        self.undo_button.clicked.connect(self.map.remove_last_drawing)
        map_controls.addWidget(self.undo_button)
        self.clear_button = QPushButton("Zeichnungen löschen")
        self.clear_button.clicked.connect(self.map.clear_drawings)
        map_controls.addWidget(self.clear_button)
        map_controls.addStretch()
        for title, action in (("−", lambda: self.map.zoom(1 / 1.3)),
                              ("+", lambda: self.map.zoom(1.3)),
                              ("Übersicht", self.map.reset_zoom)):
            button = QPushButton(title)
            button.clicked.connect(action)
            map_controls.addWidget(button)
        map_layout.addLayout(map_controls)
        map_layout.addWidget(self.map)
        map_panel.setMinimumHeight(240)
        splitter.addWidget(map_panel)
        self.tabs = QTabWidget()
        self.table = self._table()
        self.issues = self._table()
        self.tabs.addTab(self.table, "Kundenliste")
        self.tabs.addTab(self.issues, "Ohne verlässliche Position")
        self.tabs.setMinimumHeight(150)
        splitter.addWidget(self.tabs)
        splitter.setSizes([510, 290])
        layout.addWidget(splitter)
        self.search.textChanged.connect(self.refresh)
        self.postcode_filter.textChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(
            lambda: self.select_table_row(self.table.currentRow(), 0))
        self.table.cellClicked.connect(self.choose_marker_color)
        self.map.drawingsChanged.connect(self._drawings_changed)
        self.map.viewChanged.connect(self._schedule_session_save)
        self.tabs.currentChanged.connect(self._schedule_session_save)
        self._load_default_lookup()
        self.refresh()
        QTimer.singleShot(0, self._restore_previous_session)
        self.setStyleSheet("""
            QWidget#root { background: #f3f6fa; color: #1e293b; }
            QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 6px;
                          color: #1e293b; padding: 7px 12px; min-height: 23px; }
            QPushButton:hover { background: #e8f1fb; border-color: #93c5fd; }
            QPushButton:disabled { color: #94a3b8; background: #f8fafc; }
            QPushButton#primary { background: #1d4ed8; color: white; border-color: #1d4ed8; }
            QPushButton#primary:hover { background: #1e40af; }
            QPushButton#mode:checked { background: #e8f1eb; color: #285b46;
                                       border-color: #83af96; }
            QLineEdit { background: white; border: 1px solid #cbd5e1; border-radius: 6px;
                        color: #1e293b; padding: 6px 9px; min-height: 24px; }
            QLineEdit:focus { border-color: #2563eb; }
            QLabel { color: #1e293b; }
            QLabel#count { color: #1e293b; font-size: 15px; font-weight: 600; }
            QLabel#hint { color: #a33a2b; }
            QGraphicsView, QTableWidget { background: white; border: 1px solid #d7e1ea;
                                          color: #1e293b; border-radius: 6px; }
            QTabWidget::pane { border: 1px solid #d7e1ea; }
            QTabBar::tab { background: #e8eef6; border: 1px solid #cbd5e1;
                           color: #1e293b; padding: 6px 12px; }
            QTabBar::tab:selected { background: white; border-bottom-color: white; }
            QHeaderView::section { background: #e8eef6; color: #1e293b;
                                   border: 1px solid #d7e1ea; padding: 4px; }
            QStatusBar { background: #f3f6fa; color: #1e293b; }
        """)

    def _table(self):
        table = QTableWidget(0, len(self.HEADERS))
        table.setHorizontalHeaderLabels(self.HEADERS)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        for column, width in enumerate((72, 58, 190, 180, 96, 70, 145, 145, 80, 220, 140, 230)):
            table.setColumnWidth(column, width)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _load_default_lookup(self):
        """GeoNames-DE-Datei aus dem Projektordner beim Start offline einlesen."""
        path = project_dir() / "data" / "DE.txt"
        try:
            lookup, invalid, ambiguous = load_postcodes(path.read_bytes())
        except FileNotFoundError:
            self.lookup_text = "Ortsdatei fehlt: data/DE.txt."
        except (OSError, CSVError):
            self.lookup_text = "Ortsdatei data/DE.txt konnte nicht gelesen werden."
        else:
            self.lookup = lookup
            self.lookup_file = str(path)
            self.lookup_text = self._lookup_summary(lookup, invalid, ambiguous)
        loaded = bool(getattr(self.lookup, "by_city", None))
        self.lookup_label.setText("" if loaded else self.lookup_text)
        self.lookup_label.setVisible(not loaded)

    @staticmethod
    def _lookup_summary(lookup, invalid, ambiguous):
        """Nur statistische Angaben anzeigen, niemals Orts- oder Kundendaten protokollieren."""
        count = len(lookup.by_city)
        return (f"Lokale Ortsdatei geladen: {count} PLZ; "
                f"{invalid} ungültige Zeilen, {ambiguous} PLZ mit mehreren Ortsnamen. "
                "Marker bezeichnen keine genauen Kundenadressen.")

    def open_customers(self):
        """CSV lokal lesen und den Zuordnungsdialog für abweichende Spalten zeigen."""
        path, _ = QFileDialog.getOpenFileName(self, "Kunden-CSV öffnen", "", "CSV-Dateien (*.csv *.txt);;Alle Dateien (*)")
        if not path:
            return
        self._load_customer_file(path)

    def _load_customer_file(self, path, restore=False):
        """Datei explizit importieren oder die letzte Sitzung ohne Dialog wiederherstellen."""
        state = self.session.for_file(path)
        try:
            raw = Path(path).read_bytes()
            try:
                header, rows, encoding, delimiter = read_csv(
                    raw, state.get("encoding", "Automatisch") if restore else "Automatisch",
                    state.get("delimiter", "Automatisch") if restore else "Automatisch")
            except CSVError:
                if restore:
                    raise
                options = ImportOptions(self)
                if options.exec() != QDialog.DialogCode.Accepted:
                    return False
                header, rows, encoding, delimiter = read_csv(raw, options.encoding.currentText(), options.separator.currentData())
        except OSError:
            if not restore:
                warning(self, "Die ausgewählte CSV-Datei konnte lokal nicht gelesen werden.")
            return False
        except CSVError as exc:
            if not restore:
                warning(self, str(exc))
            return False
        mapping = state.get("mapping") if restore else None
        if not self._valid_mapping(mapping, header):
            if restore:
                return False
            dialog = ColumnMapping(self, header)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            mapping = dialog.mapping()
        if self.active_file_path:
            self._save_session()
        self._session_ready = False
        self.customer_file = CustomerFile(path, raw, header, mapping, encoding, delimiter)
        self.customers = prepare(rows, mapping)
        self.active_file_path = str(Path(path).resolve())
        saved_colors = state.get("colors", {})
        self.marker_colors = {key: color for key, color in (saved_colors if isinstance(saved_colors, dict) else {}).items()
                              if isinstance(key, str) and len(key) == 64 and color in COLORS}
        self.search.setText(state.get("search", "") if isinstance(state.get("search"), str) else "")
        self.postcode_filter.setText(state.get("postcode", "") if isinstance(state.get("postcode"), str) else "")
        self.map.set_drawings(state.get("drawings", []))
        lookup_path = state.get("lookup_file")
        if restore and isinstance(lookup_path, str) and lookup_path != self.lookup_file:
            self._read_lookup(Path(lookup_path), quiet=True)
        self.add_button.setEnabled(True)
        self.statusBar().showMessage("CSV geladen.", 4000)
        self.refresh()
        self.tabs.setCurrentIndex(state.get("tab", 0) if state.get("tab") in (0, 1) else 0)
        self._session_ready = True
        QTimer.singleShot(0, lambda view=state.get("view", {}): self._restore_map_view(view))
        self._schedule_session_save()
        return True

    @staticmethod
    def _valid_mapping(mapping, headers):
        if not isinstance(mapping, dict):
            return False
        chosen = [mapping.get(field) for field in FIELDS]
        return (all(isinstance(value, str) and (value == "—" or value in headers) for value in chosen)
                and all(mapping[field] != "—" for field, (_, required, _) in FIELDS.items() if required)
                and len([value for value in chosen if value != "—"])
                == len(set(value for value in chosen if value != "—")))

    def _restore_previous_session(self):
        path = self.session.last_csv()
        if path and not self._load_customer_file(path, restore=True):
            self.statusBar().showMessage("Letzte CSV konnte nicht geöffnet werden. Bitte CSV erneut wählen.", 9000)

    def _restore_map_view(self, view):
        self.map.reset_zoom()
        if isinstance(view, dict):
            zoom = view.get("zoom", 1)
            if isinstance(zoom, (int, float)) and 1 <= zoom <= 8:
                self.map.zoom(zoom)
            center = view.get("center")
            if isinstance(center, list) and len(center) == 2 and all(
                    isinstance(n, (int, float)) and 0 <= n <= 1700 for n in center):
                self.map.centerOn(*center)
        self._schedule_session_save()

    def _schedule_session_save(self, *_args):
        if self._session_ready and self.active_file_path:
            self._save_timer.start(350)

    def _save_session(self):
        if not self.active_file_path or self.customer_file is None:
            return
        center = self.map.mapToScene(self.map.viewport().rect().center())
        state = {
            "mapping": self.customer_file.mapping,
            "encoding": self.customer_file.encoding,
            "delimiter": self.customer_file.delimiter,
            "search": self.search.text(),
            "postcode": self.postcode_filter.text(),
            "tab": self.tabs.currentIndex(),
            "view": {"zoom": self.map.zoom_level, "center": [center.x(), center.y()]},
            "colors": self.marker_colors,
            "drawings": self.map.drawings,
            "lookup_file": self.lookup_file,
        }
        if not self.session.save_file(self.active_file_path, state):
            self.statusBar().showMessage("Sitzung konnte lokal nicht gespeichert werden.", 6000)

    def closeEvent(self, event):
        self._save_timer.stop()
        self._save_session()
        super().closeEvent(event)

    def add_customer(self):
        """Einen neuen Eintrag in die gerade geöffnete CSV schreiben."""
        if self.customer_file is None:
            warning(self, "Bitte zuerst eine Kunden-CSV öffnen.")
            return
        dialog = AddCustomer(self, self.customer_file.mapping)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            rows = self.customer_file.append(dialog.values())
        except SaveError as exc:
            warning(self, str(exc))
            return
        self.customers = prepare(rows, self.customer_file.mapping)
        self.search.clear()
        self.postcode_filter.clear()
        self.refresh()
        self.statusBar().showMessage("Kunde in CSV gespeichert.", 5000)

    def open_postcodes(self):
        """Die PLZ-Referenzen aus einer lokalen Datei ersetzen."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Lokale GeoNames-Ortsdatei öffnen", "", "GeoNames-Dateien (DE.txt DE.zip *.txt *.zip);;Alle Dateien (*)")
        if not path:
            return
        self._read_lookup(Path(path))

    def _read_lookup(self, path, quiet=False):
        try:
            raw = Path(path).read_bytes()
            lookup, invalid, ambiguous = load_postcodes(raw)
        except OSError:
            if not quiet:
                warning(self, "Die Ortsdatei konnte lokal nicht gelesen werden.")
            return False
        except CSVError as exc:
            if not quiet:
                warning(self, str(exc))
            return False
        self.lookup = lookup
        self.lookup_file = str(path)
        self.lookup_text = self._lookup_summary(lookup, invalid, ambiguous)
        self.lookup_label.setText("")
        self.lookup_label.hide()
        self.refresh()
        return True

    def _color_for(self, customer):
        return COLORS[self.marker_colors.get(customer_key(customer), "Blau")]

    def choose_marker_color(self, row, column):
        if column != 1:
            return
        cell = self.table.item(row, 0)
        if cell is None:
            return
        csv_row = cell.data(Qt.ItemDataRole.UserRole)
        customer = next((c for c in self.customers if c["row"] == csv_row), None)
        if customer is None:
            return
        key = customer_key(customer)
        dialog = MarkerColorDialog(self, self.marker_colors.get(key, "Blau"))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.choice == "Blau":
                self.marker_colors.pop(key, None)
            else:
                self.marker_colors[key] = dialog.choice
            self.refresh()

    def _drawings_changed(self):
        self._update_draw_buttons()
        self._schedule_session_save()

    def _update_draw_buttons(self):
        has_drawings = bool(self.map.drawings)
        self.undo_button.setEnabled(has_drawings)
        self.clear_button.setEnabled(has_drawings)

    def _populate(self, table, customers):
        self._updating_table = True
        table.setUpdatesEnabled(False)
        table.setRowCount(len(customers))
        for row, customer in enumerate(customers):
            values = [str(customer["row"]), "●", customer["name"], customer["street"], customer["number"],
                      customer["postcode"], customer["city"], customer["state"], customer["country"],
                      customer["email"], customer["phone"],
                      customer["issue"] or customer["precision"]]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, customer["row"])
                if col == 1:
                    cell.setForeground(QBrush(QColor(self._color_for(customer))))
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    cell.setToolTip("Klicken, um eine von drei Markerfarben zu wählen" if table is self.table
                                    else "Markerfarbe (Position derzeit nicht verfügbar)")
                table.setItem(row, col, cell)
        table.setUpdatesEnabled(True)
        self._updating_table = False

    def refresh(self):
        """Suche und PLZ-Filter gemeinsam auf Tabelle, Karte und Trefferzahl anwenden."""
        located = locate(self.customers, self.lookup)
        filtered = filter_customers(located, self.search.text(), self.postcode_filter.text())
        mapped = [c for c in filtered if not c["issue"] and c["lat"] is not None]
        issues = [c for c in filtered if c["issue"] or c["lat"] is None]
        self._populate(self.table, filtered)
        self._populate(self.issues, issues)
        self.row_index = {c["row"]: row for row, c in enumerate(filtered)}
        self.map.set_customers(mapped, self._color_for)
        self._update_draw_buttons()
        self.count_label.setText(f"{len(filtered)} Kunden gefunden  ·  {len(mapped)} auf der Karte  ·  {len(issues)} ohne Position")
        self.tabs.setTabText(1, f"Ohne verlässliche Position ({len(issues)})")
        if not self.customers:
            self.statusBar().showMessage("Bitte eine Kunden-CSV öffnen.")
        elif not filtered:
            self.statusBar().showMessage("Keine passenden Kunden.")
        else:
            self.statusBar().clearMessage()
        self._schedule_session_save()

    def select_table_row(self, row, _column):
        if self._updating_table:
            return
        cell = self.table.item(row, 0)
        if cell is not None:
            self.map.highlight(cell.data(Qt.ItemDataRole.UserRole), focus=True)

    def select_customer(self, customer):
        row = self.row_index.get(customer["row"])
        if row is not None:
            self.tabs.setCurrentWidget(self.table)
            self.table.selectRow(row)
            self.table.scrollToItem(self.table.item(row, 0))
            self.map.highlight(customer["row"])
        detail = QMessageBox(self)
        detail.setWindowTitle("Kunde")
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setText("\n".join([customer["name"], address(customer),
                                  *contact_lines(customer), "",
                                  f"{customer['precision']} – ungefähre PLZ-Position"]))
        detail.exec()


def main():
    """Qt ohne Webserver starten; Fehlerdialoge enthalten keine Kundenadressen."""
    app = QApplication(sys.argv)
    app.setApplicationName("PyKundenkarte")
    app.setStyle("Fusion")
    app.setPalette(light_palette())

    def show_unexpected(_kind, _error, _traceback):
        warning(None, "Ein unerwarteter Fehler ist aufgetreten. Es wurden keine Kundendaten protokolliert.")

    sys.excepthook = show_unexpected
    window = MainWindow()
    screen = app.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        window.resize(min(window.width(), available.width()),
                      min(window.height(), available.height()))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
