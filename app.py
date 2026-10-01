"""PyKundenkarte Desktop: lokal, offline, ohne Webserver."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from kundenkarte.csv_io import CSVError, read_csv
from kundenkarte.customer_csv import CustomerFile, SaveError
from kundenkarte.customers import FIELDS, address, contact_lines, filter_customers, locate, prepare, suggest
from kundenkarte.map_view import MapView
from kundenkarte.postcodes import load_postcodes


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


class MainWindow(QMainWindow):
    """Hauptfenster: CSV-Daten, lokale PLZ-Referenzen, Karte und Filter."""

    HEADERS = ["CSV-Zeile", "Kundenname", "Straße", "Hausnummer", "PLZ", "Ort", "Bundesland", "Land", "E-Mail", "Telefon", "Position / Hinweis"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyKundenkarte")
        self.resize(1180, 740)
        self.customers = []
        self.customer_file = None
        self.lookup = {}
        self.row_index = {}
        self.lookup_text = "Keine lokale Ortsdatei geladen"
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
        self._load_default_lookup()
        self.refresh()
        self.setStyleSheet("""
            QWidget#root { background: #f3f6fa; color: #1e293b; }
            QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 6px;
                          color: #1e293b; padding: 7px 12px; min-height: 23px; }
            QPushButton:hover { background: #e8f1fb; border-color: #93c5fd; }
            QPushButton:disabled { color: #94a3b8; background: #f8fafc; }
            QPushButton#primary { background: #1d4ed8; color: white; border-color: #1d4ed8; }
            QPushButton#primary:hover { background: #1e40af; }
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
        for column, width in enumerate((72, 190, 180, 96, 70, 145, 145, 80, 220, 140, 230)):
            table.setColumnWidth(column, width)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    def _load_default_lookup(self):
        """GeoNames-DE-Datei aus dem Projektordner beim Start offline einlesen."""
        path = Path(__file__).resolve().parent / "data" / "DE.txt"
        try:
            lookup, invalid, ambiguous = load_postcodes(path.read_bytes())
        except FileNotFoundError:
            self.lookup_text = "Ortsdatei fehlt: data/DE.txt."
        except (OSError, CSVError):
            self.lookup_text = "Ortsdatei data/DE.txt konnte nicht gelesen werden."
        else:
            self.lookup = lookup
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
        try:
            raw = Path(path).read_bytes()
            try:
                header, rows, encoding, delimiter = read_csv(raw)
            except CSVError:
                options = ImportOptions(self)
                if options.exec() != QDialog.DialogCode.Accepted:
                    return
                header, rows, encoding, delimiter = read_csv(raw, options.encoding.currentText(), options.separator.currentData())
        except OSError:
            warning(self, "Die ausgewählte CSV-Datei konnte lokal nicht gelesen werden.")
            return
        except CSVError as exc:
            warning(self, str(exc))
            return
        dialog = ColumnMapping(self, header)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mapping = dialog.mapping()
        self.customer_file = CustomerFile(path, raw, header, mapping, encoding, delimiter)
        self.customers = prepare(rows, mapping)
        self.add_button.setEnabled(True)
        self.statusBar().showMessage("CSV geladen.", 4000)
        self.refresh()

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
        """Die PLZ-Referenzen für diese Sitzung aus einer lokalen Datei ersetzen."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Lokale GeoNames-Ortsdatei öffnen", "", "GeoNames-Dateien (DE.txt DE.zip *.txt *.zip);;Alle Dateien (*)")
        if not path:
            return
        try:
            raw = Path(path).read_bytes()
            lookup, invalid, ambiguous = load_postcodes(raw)
        except OSError:
            warning(self, "Die Ortsdatei konnte lokal nicht gelesen werden.")
            return
        except CSVError as exc:
            warning(self, str(exc))
            return
        self.lookup = lookup
        self.lookup_text = self._lookup_summary(lookup, invalid, ambiguous)
        self.lookup_label.setText("")
        self.lookup_label.hide()
        self.refresh()

    def _populate(self, table, customers):
        table.setUpdatesEnabled(False)
        table.setRowCount(len(customers))
        for row, customer in enumerate(customers):
            values = [str(customer["row"]), customer["name"], customer["street"], customer["number"],
                      customer["postcode"], customer["city"], customer["state"], customer["country"],
                      customer["email"], customer["phone"],
                      customer["issue"] or customer["precision"]]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, customer["row"])
                table.setItem(row, col, cell)
        table.setUpdatesEnabled(True)

    def refresh(self):
        """Suche und PLZ-Filter gemeinsam auf Tabelle, Karte und Trefferzahl anwenden."""
        located = locate(self.customers, self.lookup)
        filtered = filter_customers(located, self.search.text(), self.postcode_filter.text())
        mapped = [c for c in filtered if not c["issue"] and c["lat"] is not None]
        issues = [c for c in filtered if c["issue"] or c["lat"] is None]
        self._populate(self.table, filtered)
        self._populate(self.issues, issues)
        self.row_index = {c["row"]: row for row, c in enumerate(filtered)}
        self.map.set_customers(mapped)
        self.count_label.setText(f"{len(filtered)} Kunden gefunden  ·  {len(mapped)} auf der Karte  ·  {len(issues)} ohne Position")
        self.tabs.setTabText(1, f"Ohne verlässliche Position ({len(issues)})")
        if not self.customers:
            self.statusBar().showMessage("Bitte eine Kunden-CSV öffnen.")
        elif not filtered:
            self.statusBar().showMessage("Keine passenden Kunden.")
        else:
            self.statusBar().clearMessage()

    def select_table_row(self, row, _column):
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
