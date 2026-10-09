"""Offline-Deutschlandkarte mit optionalen lokalen Bundesländergrenzen."""

from collections import defaultdict
from html import escape
import json
from math import cos, isfinite
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu

from .customers import address, contact_lines
from .paths import project_dir

# Diese Beschriftungen sind Kartenorientierung und enthalten keine Kundendaten.
MAJOR_CITIES = (
    ("Hamburg", 53.5511, 9.9937),
    ("Bremen", 53.0793, 8.8017),
    ("Berlin", 52.5200, 13.4050),
    ("Düsseldorf", 51.2277, 6.7735),
    ("Köln", 50.9375, 6.9603),
    ("Leipzig", 51.3397, 12.3731),
    ("Dresden", 51.0504, 13.7373),
    ("Frankfurt", 50.1109, 8.6821),
    ("Stuttgart", 48.7758, 9.1829),
    ("München", 48.1351, 11.5820),
)


def load_state_boundaries(path: Path):
    """Liest nur lokale GeoJSON-Polygone in WGS84 (lon, lat)."""
    if not path.is_file():
        return ()
    try:
        if path.stat().st_size > 8_000_000:
            return ()
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("type") != "FeatureCollection":
            return ()
        features = data.get("features", [])
        if len(features) != 16:
            return ()
        rings = []
        for feature in features:
            geometry = feature["geometry"]
            kind = geometry["type"]
            polygons = ([geometry["coordinates"]] if kind == "Polygon" else
                        geometry["coordinates"] if kind == "MultiPolygon" else [])
            if not polygons:
                return ()
            for polygon in polygons:
                for ring in polygon:
                    points = tuple((float(p[0]), float(p[1])) for p in ring)
                    if len(points) >= 3 and all(5 <= lon <= 16 and 47 <= lat <= 56
                                                for lon, lat in points):
                        rings.append(points)
        return tuple(rings)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return ()


class CustomerMarker(QGraphicsEllipseItem):
    def __init__(self, x: float, y: float, customers: list[dict], callback):
        radius = 10 if len(customers) > 1 else 7
        super().__init__(QRectF(-radius, -radius, 2 * radius, 2 * radius))
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.customers = customers
        self.callback = callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(3)
        if len(customers) == 1:
            customer = customers[0]
            contact = "".join(f"{escape(line)}<br>" for line in contact_lines(customer))
            self.setToolTip(f"<b>{escape(customer['name'])}</b><br>"
                            f"{escape(address(customer))}<br>{contact}"
                            f"{escape(customer['precision'])} – ungefähre Position")
        else:
            self.setToolTip(f"{len(customers)} Kunden an derselben PLZ-Referenz – klicken, um einen auszuwählen")

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if len(self.customers) > 1:
            painter.setPen(QColor("white"))
            font = painter.font()
            font.setBold(True)
            font.setPixelSize(11)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(len(self.customers)))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if self.contains(event.pos()):
            # Erst nach dem Loslassen öffnen: QMenu.exec während mousePressEvent
            # lässt sonst den Marker als Maus-Empfänger für spätere Klicks aktiv.
            if len(self.customers) == 1:
                customer = self.customers[0]
                QTimer.singleShot(0, lambda: self.callback(customer))
            else:
                position = event.screenPos()
                QTimer.singleShot(0, lambda: self._choose_customer(position))
        event.accept()

    def _choose_customer(self, position):
        """Das Sammelmenü nach Abschluss des Mausklicks anzeigen."""
        menu = QMenu()
        for customer in self.customers:
            action = menu.addAction(f"{customer['name']} — {address(customer)}")
            action.setData(customer["row"])
        chosen = menu.exec(position)
        if chosen is not None:
            customer = next(c for c in self.customers if c["row"] == chosen.data())
            self.callback(customer)


class MapView(QGraphicsView):
    drawingsChanged = Signal()
    viewChanged = Signal()
    WIDTH = 960
    HEIGHT = 740
    LEFT = 60
    TOP = 55
    RIGHT = 900
    BOTTOM = 675

    def __init__(self, on_customer_click, parent=None):
        super().__init__(parent)
        self.on_customer_click = on_customer_click
        self.map_scene = QGraphicsScene(self)
        self.setScene(self.map_scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#f7fafc"))
        self.markers = {}
        self.draw_mode = "move"
        self.drawings = []
        self.stroke_items = []
        self._current_points = None
        self._current_item = None
        self.state_boundaries = load_state_boundaries(
            project_dir() / "data" / "bundeslaender.geojson")
        self.zoom_level = 1.0
        self.set_customers([])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom_level == 1.0:
            self.reset_zoom()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom(1.2 ** (delta / 120), under_mouse=True)
        event.accept()

    def set_draw_mode(self, mode: str):
        """Zwischen Verschieben, Zeichnen und Radieren wechseln."""
        if mode not in ("move", "draw", "erase"):
            return
        self.draw_mode = mode
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == "move"
                         else QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if mode != "move"
                                  else Qt.CursorShape.ArrowCursor)

    def _map_point(self, position):
        point = self.mapToScene(position)
        area = QRectF(self.LEFT, self.TOP, self.RIGHT - self.LEFT, self.BOTTOM - self.TOP)
        return point if area.contains(point) else None

    def _draw_item(self, points):
        path = QPainterPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        if len(points) == 1:
            path.lineTo(points[0][0] + 0.1, points[0][1])
        pen = QPen(QColor("#b94f61"), 3, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        pen.setCosmetic(True)
        item = self.map_scene.addPath(path, pen)
        item.setZValue(8)
        return item

    def set_drawings(self, strokes):
        """Gespeicherte Linien nach jedem Neuzeichnen der Karte wiederherstellen."""
        for item in self.stroke_items:
            self.map_scene.removeItem(item)
        self.stroke_items = []
        self.drawings = []
        if not isinstance(strokes, list):
            return
        for stroke in strokes[:250]:
            if not isinstance(stroke, list) or not 1 <= len(stroke) <= 1200:
                continue
            if not all(isinstance(p, (list, tuple)) and len(p) == 2
                       and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                               and isfinite(v) for v in p)
                       and 0 <= p[0] <= self.WIDTH and 0 <= p[1] <= self.HEIGHT
                       for p in stroke):
                continue
            points = [[float(x), float(y)] for x, y in stroke]
            self.drawings.append(points)
            self.stroke_items.append(self._draw_item(points))

    def remove_last_drawing(self):
        if self.drawings:
            self.drawings.pop()
            self.map_scene.removeItem(self.stroke_items.pop())
            self.drawingsChanged.emit()

    def clear_drawings(self):
        if self.drawings:
            self.set_drawings([])
            self.drawingsChanged.emit()

    def mousePressEvent(self, event):
        if self.draw_mode == "move" or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self.draw_mode == "erase":
            item = next((item for item in self.items(event.pos()) if item in self.stroke_items), None)
            if item is not None:
                index = self.stroke_items.index(item)
                self.map_scene.removeItem(self.stroke_items.pop(index))
                self.drawings.pop(index)
                self.drawingsChanged.emit()
        else:
            point = self._map_point(event.pos())
            if point is not None and len(self.drawings) < 250:
                self._current_points = [[point.x(), point.y()]]
                self._current_item = self._draw_item(self._current_points)
        event.accept()

    def mouseMoveEvent(self, event):
        if self._current_item is None:
            super().mouseMoveEvent(event)
            return
        point = self._map_point(event.pos())
        if point is not None and len(self._current_points) < 1200:
            previous = self._current_points[-1]
            if abs(point.x() - previous[0]) + abs(point.y() - previous[1]) >= 1:
                self._current_points.append([point.x(), point.y()])
                path = self._current_item.path()
                path.lineTo(point)
                self._current_item.setPath(path)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._current_item is not None and event.button() == Qt.MouseButton.LeftButton:
            self.drawings.append(self._current_points)
            self.stroke_items.append(self._current_item)
            self._current_points = None
            self._current_item = None
            self.drawingsChanged.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self.draw_mode == "move" and event.button() == Qt.MouseButton.LeftButton:
            self.viewChanged.emit()

    def zoom(self, factor: float, under_mouse=False):
        new_level = max(1.0, min(8.0, self.zoom_level * factor))
        if new_level == self.zoom_level:
            return
        if new_level == 1.0:
            self.reset_zoom()
        else:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if under_mouse
                                         else QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.scale(new_level / self.zoom_level, new_level / self.zoom_level)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.zoom_level = new_level
            self.viewChanged.emit()

    def reset_zoom(self):
        self.resetTransform()
        self.fitInView(self.map_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.map_scene.sceneRect().center())
        self.zoom_level = 1.0
        self.viewChanged.emit()

    def _label(self, label, x, y, offset, color="#334155", size=9):
        item = self.map_scene.addText(label, QFont("Segoe UI", size))
        item.setDefaultTextColor(QColor(color))
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        item.setTransform(QTransform.fromTranslate(*offset))
        item.setPos(x, y)

    def set_customers(self, customers: list[dict], color_for=None):
        """Zeigt Kunden mit einer lokalen, ungefähren PLZ-Referenzposition."""
        strokes = self.drawings
        self.map_scene.clear()
        self.markers = {}
        self.stroke_items = []
        self._current_item = None
        self._current_points = None
        self.map_scene.setSceneRect(0, 0, self.WIDTH, self.HEIGHT)
        valid = [c for c in customers if c["lat"] is not None and c["lon"] is not None and not c["issue"]]

        lon_min, lon_max, lat_min, lat_max = 5.5, 15.5, 46.9, 55.4
        latitude_scale = cos(51 * 3.141592653589793 / 180)
        x_span = (lon_max - lon_min) * latitude_scale
        y_span = lat_max - lat_min
        scale = min((self.RIGHT - self.LEFT) / x_span,
                    (self.BOTTOM - self.TOP) / y_span)
        x_start = (self.WIDTH - x_span * scale) / 2
        y_start = (self.HEIGHT - y_span * scale) / 2

        def xy(lon, lat):
            return (x_start + (lon - lon_min) * latitude_scale * scale,
                    y_start + (lat_max - lat) * scale)

        background = self.map_scene.addRect(
            QRectF(self.LEFT, self.TOP, self.RIGHT - self.LEFT, self.BOTTOM - self.TOP),
            QPen(QColor("#d7e3e8")), QBrush(QColor("#edf5f7")))
        background.setZValue(-3)
        if self.state_boundaries:
            states = QPainterPath()
            states.setFillRule(Qt.FillRule.OddEvenFill)
            for ring in self.state_boundaries:
                states.moveTo(*xy(*ring[0]))
                for point in ring[1:]:
                    states.lineTo(*xy(*point))
                states.closeSubpath()
            state_lines = self.map_scene.addPath(
                states, QPen(QColor("#839878"), 0.85), QBrush(QColor("#e8eedb")))
            state_lines.setZValue(-2)

        for city, lat, lon in MAJOR_CITIES:
            x, y = xy(lon, lat)
            dot = self.map_scene.addEllipse(
                -2.5, -2.5, 5, 5, QPen(QColor("#718a76")), QBrush(QColor("#718a76")))
            dot.setPos(x, y)
            dot.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            dot.setZValue(-1)
            offsets = {"Bremen": (-62, -12), "Düsseldorf": (-85, -22),
                       "Köln": (-44, 3), "Leipzig": (8, -25),
                       "Dresden": (10, 2), "Frankfurt": (-78, 0)}
            self._label(city, x, y, offsets.get(city, (8, -24)), "#405d50")

        positions = defaultdict(list)
        for customer in valid:
            positions[(customer["lat"], customer["lon"])].append(customer)
        for (lat, lon), customers_here in positions.items():
            x, y = xy(lon, lat)
            marker = CustomerMarker(x, y, customers_here, self.on_customer_click)
            colors = {color_for(c) for c in customers_here} if color_for else {"#2563eb"}
            marker.base_color = colors.pop() if len(colors) == 1 else "#64748b"
            marker.setBrush(QBrush(QColor(marker.base_color)))
            marker.setPen(QPen(QColor("white"), 2))
            self.map_scene.addItem(marker)
            for customer in customers_here:
                self.markers[customer["row"]] = marker
        self.set_drawings(strokes)

    def highlight(self, csv_row: int, focus: bool = False):
        """Markiert den Kunden sichtbar und führt die Karte bei Bedarf dorthin."""
        target = self.markers.get(csv_row)
        for marker in set(self.markers.values()):
            selected = marker is target
            marker.setPen(QPen(QColor("#111827" if selected else "white"), 3 if selected else 2))
            marker.setBrush(QBrush(QColor(marker.base_color)))
            marker.setScale(1.35 if selected else 1.0)
            marker.setZValue(5 if selected else 3)
        if focus and target is not None:
            if self.zoom_level < 2.0:
                self.zoom(2.0 / self.zoom_level)
            self.centerOn(target)
