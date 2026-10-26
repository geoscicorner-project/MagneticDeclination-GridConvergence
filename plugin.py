# -*- coding: utf-8 -*-
"""IGRF Magnetic Field QGIS plugin."""
import os
import math
from qgis.PyQt.QtCore import QDate, QUrl, Qt, QPoint, QRectF
from qgis.PyQt.QtGui import QAction, QDesktopServices, QPainter, QPen, QBrush, QColor, QFont, QPolygon, QIcon
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QDateEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QLabel, QMessageBox, QComboBox,
    QGroupBox, QPlainTextEdit, QTextEdit, QTextBrowser, QFileDialog, QWidget, QFrame, QSizePolicy, QSpinBox, QFormLayout, QHBoxLayout, QLineEdit
)
from qgis.core import QgsCoordinateReferenceSystem, QgsPoint
from qgis.gui import QgsProjectionSelectionDialog
from .geomag import calculate, model_info

IGRF_URL = 'https://www.ncei.noaa.gov/products/international-geomagnetic-reference-field'


def dms_to_decimal(deg, minute, second, hemisphere):
    value = abs(float(deg)) + float(minute) / 60.0 + float(second) / 3600.0
    if hemisphere in ('S', 'W'):
        value = -value
    return value


def angle_dms(value):
    sign = '-' if value < 0 else ''
    a = abs(value)
    deg = int(a)
    minutes_float = (a - deg) * 60.0
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60.0
    return u'%s%d° %02d′ %04.1f″' % (sign, deg, minutes, seconds)


class NorthIllustration(QWidget):
    """Combined schematic of true north (TN), magnetic north (MN), and grid north (GN)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.declination = None
        self.convergence = None
        self.setMinimumSize(280, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_angles(self, declination, convergence):
        self.declination = float(declination)
        self.convergence = float(convergence)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(12, 12, -12, -12)
        cx = rect.center().x()
        cy = rect.center().y() + 28
        radius = min(rect.width() * 0.27, rect.height() * 0.25)
        radius = max(48, radius)
        length = min(radius * 1.48, max(95, rect.height() * 0.36))

        p.setPen(QPen(QColor('#c6cbd1'), 1.4)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(cx-radius*0.65), int(cy-radius*0.65), int(radius*1.3), int(radius*1.3))
        p.setFont(QFont('Sans Serif', 9, QFont.Bold)); p.setPen(QColor('#6b7280'))
        p.drawText(int(cx-6), int(cy-radius*0.72), 'N')
        p.drawText(int(cx+radius*0.72), int(cy+5), 'E')
        p.drawText(int(cx-5), int(cy+radius*0.80), 'S')
        p.drawText(int(cx-radius*0.82), int(cy+5), 'W')

        # Schematic angle scaling: preserve sign and relative magnitude.
        # Fixed, different minimum angles made gamma appear larger than D.
        def signed_visual(value):
            value = float(value or 0.0)
            if abs(value) < 1e-12:
                return 0.0
            magnitude = min(28.0, 2.0 + abs(value) * 30.0)
            return math.copysign(magnitude, value)

        dvis = signed_visual(self.declination) if self.declination is not None else None
        gvis = signed_visual(self.convergence) if self.convergence is not None else None

        def endpoint(deg):
            a = math.radians(deg)
            return cx + math.sin(a)*length, cy - math.cos(a)*length

        def arrow(tip, color, width=2.5):
            x1, y1 = tip
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(int(cx), int(cy), int(x1), int(y1))
            dx, dy = x1-cx, y1-cy
            norm = math.hypot(dx, dy) or 1.0
            ux, uy = dx/norm, dy/norm
            size = 10
            px, py = -uy*size*.48, ux*size*.48
            poly = QPolygon([QPoint(int(x1),int(y1)),
                             QPoint(int(x1-ux*size+px),int(y1-uy*size+py)),
                             QPoint(int(x1-ux*size-px),int(y1-uy*size-py))])
            p.setBrush(color); p.drawPolygon(poly)

        us = (cx, cy-length)
        arrow(us, QColor('#17324d'), 3)
        p.setFont(QFont('Sans Serif', 11, QFont.Bold)); p.setPen(QColor('#17324d'))
        p.drawText(int(cx+8), int(us[1]-14), 'TN')

        um = endpoint(dvis) if dvis is not None else None
        ug = endpoint(gvis) if gvis is not None else None
        if um is not None:
            arrow(um, QColor('#e53935'), 2.7)
        if ug is not None:
            arrow(ug, QColor('#1570ef'), 2.7)

        # Place each label just outside its own ray; adjust horizontally to avoid overlap.
        p.setFont(QFont('Sans Serif', 10, QFont.Bold))
        if um is not None:
            p.setPen(QColor('#e53935'))
            ux = um[0] + (8 if dvis >= 0 else -30)
            p.drawText(int(max(rect.left(), min(rect.right()-34, ux))), int(um[1]+15), 'MN')
        if ug is not None:
            p.setPen(QColor('#1570ef'))
            gx = ug[0] + (8 if gvis >= 0 else -30)
            p.drawText(int(max(rect.left(), min(rect.right()-34, gx))), int(ug[1]-4), 'GN')

        # D is the angle US–UM; gamma is the angle US–UG.
        arc_radius = radius * 0.38
        if dvis is not None:
            p.setPen(QPen(QColor('#e53935'), 1.6))
            p.drawArc(int(cx-arc_radius), int(cy-arc_radius), int(2*arc_radius), int(2*arc_radius),
                      90*16, int(-dvis*16))
            p.setPen(QColor('#e53935')); p.setFont(QFont('Sans Serif', 10, QFont.Bold))
            da = math.radians(dvis * 0.55)
            p.drawText(int(cx + math.sin(da)*(arc_radius+8)), int(cy - math.cos(da)*(arc_radius+8)), 'D')
        if gvis is not None:
            gr = radius * 0.57
            p.setPen(QPen(QColor('#1570ef'), 1.6))
            p.drawArc(int(cx-gr), int(cy-gr), int(2*gr), int(2*gr), 90*16, int(-gvis*16))
            p.setPen(QColor('#1570ef')); p.setFont(QFont('Sans Serif', 10, QFont.Bold))
            ga = math.radians(gvis * 0.55)
            p.drawText(int(cx + math.sin(ga)*(gr+7)), int(cy - math.cos(ga)*(gr+7)), u'γ')

        p.setPen(self.palette().text().color()); p.setFont(QFont('Sans Serif', 8))
        note = 'Illustration angles are schematic; numerical values are the calculated results.'
        p.drawText(QRectF(8, self.height()-24, self.width()-16, 18), Qt.AlignCenter, note)
        p.end()


class IGRFDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Magnetic Declination & Grid Convergence')
        self.resize(1120, 740)
        self.setMinimumSize(960, 640)
        self.cof_path = os.path.join(os.path.dirname(__file__), 'IGRF14.COF')
        self._last_declination = 0.0
        self.target_crs = None

        outer = QVBoxLayout(self)
        main = QHBoxLayout()
        outer.addLayout(main, 1)
        left = QVBoxLayout(); right = QVBoxLayout()
        main.addLayout(left, 9)
        main.addLayout(right, 10)

        # Date label requested by user
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel('Map publication date'))
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat('yyyy-MM-dd')
        date_row.addWidget(self.date, 1)
        self.help_button = QPushButton('Guide')
        self.help_button.setToolTip('Input instructions, required data, calculation methods, and result interpretation')
        self.help_button.clicked.connect(self.show_help)
        date_row.addWidget(self.help_button)
        left.addLayout(date_row)

        coord_box = QGroupBox('Coordinates (Geodetic, WGS84)')
        cg = QGridLayout(coord_box)
        cg.setHorizontalSpacing(6)
        cg.setVerticalSpacing(8)
        cg.addWidget(QLabel('Latitude'), 0, 0)
        self.lat_deg = self._int_combo(0, 90, 4)
        self.lat_min = self._int_combo(0, 59, 18)
        self.lat_sec = self._sec_spin(17.40)
        self.lat_hemi = self._combo(['N', 'S'], 'N')
        cg.addWidget(self.lat_deg, 0, 1); cg.addWidget(QLabel('°'), 0, 2)
        cg.addWidget(self.lat_min, 0, 3); cg.addWidget(QLabel('′'), 0, 4)
        cg.addWidget(self.lat_sec, 0, 5); cg.addWidget(QLabel('″'), 0, 6)
        cg.addWidget(self.lat_hemi, 0, 7)
        cg.addWidget(QLabel('Longitude'), 1, 0)
        self.lon_deg = self._int_combo(0, 180, 115)
        self.lon_min = self._int_combo(0, 59, 57)
        self.lon_sec = self._sec_spin(4.80)
        self.lon_hemi = self._combo(['E', 'W'], 'E')
        cg.addWidget(self.lon_deg, 1, 1); cg.addWidget(QLabel('°'), 1, 2)
        cg.addWidget(self.lon_min, 1, 3); cg.addWidget(QLabel('′'), 1, 4)
        cg.addWidget(self.lon_sec, 1, 5); cg.addWidget(QLabel('″'), 1, 6)
        cg.addWidget(self.lon_hemi, 1, 7)
        cg.setColumnStretch(5, 1)
        self.alt = QDoubleSpinBox(); self.alt.setRange(-12000, 100000); self.alt.setDecimals(3); self.alt.setValue(1080.0)
        self.alt.setSingleStep(1.0)
        cg.addWidget(QLabel('Ellipsoidal height (m)'), 2, 0, 1, 3)
        cg.addWidget(self.alt, 2, 3, 1, 5)
        left.addWidget(coord_box)

        crs_box = QGroupBox('CRS for grid convergence')
        crs_layout = QHBoxLayout(crs_box)
        self.crs_label = QLabel()
        self.crs_label.setWordWrap(True)
        self.crs_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.choose_crs_button = QPushButton('Choose another CRS…')
        self.choose_crs_button.setMaximumWidth(150)
        self.choose_crs_button.clicked.connect(self.choose_crs)
        crs_layout.addWidget(self.crs_label, 1)
        crs_layout.addWidget(self.choose_crs_button)
        left.addWidget(crs_box)
        for w in (self.lat_deg, self.lat_min, self.lat_sec, self.lat_hemi,
                  self.lon_deg, self.lon_min, self.lon_sec, self.lon_hemi):
            if hasattr(w, 'currentIndexChanged'):
                w.currentIndexChanged.connect(self._update_crs_label)
            if hasattr(w, 'valueChanged'):
                w.valueChanged.connect(self._update_crs_label)
        self._update_crs_label()

        model_heading = QLabel('Geomagnetic Model')
        model_heading.setStyleSheet('font-weight: bold;')
        left.addWidget(model_heading)
        file_box = QHBoxLayout()
        file_box.addWidget(QLabel('Model file (.COF)'))
        self.file_label = QLabel(os.path.basename(self.cof_path))
        self.file_label.setMinimumWidth(80)
        self.file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_label.setToolTip(self.cof_path)
        file_box.addWidget(self.file_label, 1)
        self.browse_button = QPushButton('Change file…')
        self.browse_button.clicked.connect(self.choose_model)
        file_box.addWidget(self.browse_button)
        self.update_button = QPushButton('Check for updates')
        self.update_button.clicked.connect(self.open_igrf_updates)
        self.update_button.setToolTip('Open the official NOAA/NCEI website to obtain IGRF files')
        file_box.addWidget(self.update_button)
        left.addLayout(file_box)
        self.model_label = QLabel('Model: loading…')
        self.model_label.setStyleSheet('font-weight: bold;')
        self.range_label = QLabel('Calculation date range: loading…')
        self.range_label.setWordWrap(True)
        left.addWidget(self.model_label)
        left.addWidget(self.range_label)

        self.run_button = QPushButton('Calculate Magnetic Field and Grid Convergence')
        self.run_button.setMinimumHeight(38)
        self.run_button.clicked.connect(self.run_calculation)
        left.addWidget(self.run_button)
        results_box = QGroupBox('Calculation Results')
        rb = QVBoxLayout(results_box)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(250)
        self.output.setStyleSheet('QTextEdit { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; padding: 5px; }')
        rb.addWidget(self.output)
        left.addWidget(results_box, 1)

        illustration_box = QGroupBox('North Direction Illustration')
        il = QVBoxLayout(illustration_box)
        self.compass = NorthIllustration()
        il.addWidget(self.compass, 1)
        note = QLabel(
            '<b>Illustration legend</b><br>'
            '<table cellspacing="4" cellpadding="1" width="100%">'
            '<tr><td width="28"><b>US</b></td><td>True North</td></tr>'
            '<tr><td><b>UM</b></td><td>Magnetic North</td></tr>'
            '<tr><td><b>UG</b></td><td>Grid North</td></tr>'
            '</table><hr>'
            '<span style="color:#e53935"><b>D = Magnetic declination</b></span><br>'
            'Angle from TN to MN.<br>'
            '<span style="color:#1570ef"><b>γ = Grid convergence</b></span><br>'
            'Angle from TN to GN.'
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.RichText)
        note.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        note.setStyleSheet('background:#eef6ff; border:1px solid #b8d9ff; border-radius:6px; padding:8px;')
        il.addWidget(note)
        right.addWidget(illustration_box, 1)

        foot = QLabel('Enter elevation as height above the WGS84 ellipsoid (metres).')
        foot.setWordWrap(True)
        foot.setStyleSheet('color:#6b5b2a; font-size:9pt;')
        left.addWidget(foot)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        outer.addWidget(close)
        self.update_model_info()

    @staticmethod
    def _int_combo(minimum, maximum, value):
        c = QComboBox()
        for v in range(minimum, maximum + 1):
            c.addItem(str(v), v)
        c.setCurrentIndex(value - minimum)
        c.setMinimumWidth(65)
        return c

    @staticmethod
    def _combo(values, current):
        c = QComboBox(); c.addItems(values); c.setCurrentText(current)
        return c

    @staticmethod
    def _sec_spin(value):
        # QLineEdit is used instead of QDoubleSpinBox because pasted decimal
        # coordinates can be rejected by QDoubleSpinBox locale/input handling.
        s = QLineEdit(str(value))
        s.setMinimumWidth(85)
        s.setPlaceholderText('seconds')
        # Deliberately avoid a spin-box/strict validator here: some Qt locales
        # reject pasted decimal strings. Validate and normalize on edit finish
        # and again before calculation instead.
        s.editingFinished.connect(lambda w=s: IGRFDialog._normalize_seconds_edit(w))
        return s

    @staticmethod
    def _seconds_value(widget):
        text = widget.text().strip().replace(',', '.')
        if not text:
            raise ValueError('The seconds field cannot be empty.')
        try:
            value = float(text)
        except ValueError:
            raise ValueError('Seconds must be numeric, for example 17.40.')
        if value < 0 or value >= 60:
            raise ValueError('Seconds must be at least 0 and less than 60.')
        return value

    @staticmethod
    def _normalize_seconds_edit(widget):
        # Accept either decimal comma or decimal point, and preserve all
        # supplied fractional digits instead of rounding to a fixed precision.
        text = widget.text().strip()
        if not text:
            return
        normalized = text.replace(',', '.')
        try:
            value = float(normalized)
            if 0 <= value < 60:
                widget.setText(normalized)
        except (TypeError, ValueError):
            # Leave invalid input visible; calculation reports a clear error.
            return

    def _coordinates(self):
        lat = dms_to_decimal(self.lat_deg.currentData(), self.lat_min.currentData(), self._seconds_value(self.lat_sec), self.lat_hemi.currentText())
        lon = dms_to_decimal(self.lon_deg.currentData(), self.lon_min.currentData(), self._seconds_value(self.lon_sec), self.lon_hemi.currentText())
        if self.lat_deg.currentData() == 90 and (self.lat_min.currentData() != 0 or self._seconds_value(self.lat_sec) != 0):
            raise ValueError('At latitude 90°, minutes and seconds must be zero.')
        if self.lon_deg.currentData() == 180 and (self.lon_min.currentData() != 0 or self._seconds_value(self.lon_sec) != 0):
            raise ValueError('At longitude 180°, minutes and seconds must be zero.')
        return lat, lon

    def show_help(self):
        help_html = '''
        <h2>User Guide</h2>
        <h3>1. Cara mengisi setiap field</h3>
        <ul>
          <li><b>Map publication date</b> — select the date for which the map will be published or printed. This date is used to calculate the geomagnetic field for the corresponding epoch and must fall within the model file's supported date range.</li>
          <li><b>Latitude</b> — enter degrees, minutes, and seconds, then select <b>N</b> for north or <b>S</b> for south.</li>
          <li><b>Longitude</b> — enter degrees, minutes, and seconds, then select <b>E</b> for east or <b>W</b> for west.</li>
          <li><b>Ellipsoidal height (m)</b> — height in metres above the WGS84 ellipsoid, not orthometric height or height above mean sea level. If only orthometric height is available, convert it using geoid undulation (h = H + N) from an appropriate geoid source.</li>
          <li><b>CRS for grid convergence</b> — by default, the UTM zone and hemisphere are determined from the coordinates. Click <b>Choose another CRS…</b> to calculate convergence for a different projected CRS. Click the button, which changes to <b>Automatic UTM</b>, to return to automatic selection.</li>
          <li><b>Model file (.COF)</b> — use a suitable IGRF or WMM coefficient file. <b>Change file…</b> lets you select a local file. <b>Check for updates</b> opens the official NOAA/NCEI website; the file is not downloaded or replaced automatically.</li>
        </ul>
        <h3>2. Data yang diperlukan</h3>
        <ul>
          <li>Calculation date, latitude, longitude, and ellipsoidal height.</li>
          <li>A valid geomagnetic coefficient <code>.COF</code> file that covers the selected date.</li>
          <li>A target CRS for grid convergence; if none is selected, the plugin uses automatic UTM.</li>
        </ul>
        <h3>3. Calculation methods</h3>
        <ul>
          <li><b>Geomagnetic field</b> is calculated from the spherical harmonic coefficients in the IGRF/WMM file using the date, geodetic coordinates, and ellipsoidal height. Declination is calculated from the horizontal field components; inclination and intensity are derived from the other field components.</li>
          <li><b>Grid convergence (γ)</b> is calculated by the QGIS projection library for the target CRS at the input location. It is the angle between true north and grid north according to the sign convention used by QGIS and the CRS.</li>
          <li><b>The TN/MN/GN illustration</b> is schematic and shows the directional relationships: TN = true north, MN = magnetic north, and GN = grid north. Angle D is TN–MN; γ is TN–GN. Small angles may be exaggerated for visibility, so use the numerical results as the reference.</li>
        </ul>
        <h3>4. Understanding the results</h3>
        <ul>
          <li><b>Magnetic declination (D)</b> — the angle between true north and magnetic north, displayed in DMS and decimal degrees.</li>
          <li><b>Grid convergence (γ)</b> — the angle between true north and grid north, displayed in DMS and decimal degrees.</li>
          <li><b>Magnetic inclination (I)</b> — the angle of the magnetic field relative to the horizontal plane.</li>
          <li><b>H</b> — horizontal intensity; <b>X</b> — north component; <b>Y</b> — east component; <b>Z</b> — vertically downward component; <b>F</b> — total intensity. Intensity is measured in nanotesla (nT).</li>
          <li><b>dD, dI, dH, dX, dY, dZ, dF</b> — estimated annual changes from the model, expressed in arcminutes per year for angles and nT per year for intensity.</li>
        </ul>
        <h3>5. Expected results and validation</h3>
        <p>After clicking <b>Calculate Magnetic Field and Grid Convergence</b>, the results panel displays the location and model, D, γ, I, field components, and annual changes; the illustration updates the MN and GN directions. Results depend on the date, coordinates, height, model file, and CRS. To validate the results, ensure the date falls within the model's range, the height is ellipsoidal, and the target CRS is appropriate. Results may differ from other applications if the model, epoch, height, CRS, or sign convention differs.</p>
        <p><b>Note:</b> the <i>Check for updates</i> button only opens the official NOAA/NCEI website. Check the file's licence, version, and date range before changing the model.</p>
        '''
        # Use a resizable dialog with a scrollable HTML viewer. QMessageBox.about()
        # is not suitable for long manuals because it may become excessively tall.
        dlg = QDialog(self)
        dlg.setWindowTitle('Guide — Magnetic Declination & Grid Convergence')
        dlg.resize(1080, 820)
        dlg.setMinimumSize(760, 560)
        layout = QVBoxLayout(dlg)
        viewer = QTextBrowser(dlg)
        viewer.setOpenExternalLinks(True)
        viewer.setHtml(help_html)
        viewer.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(viewer, 1)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton('Close', dlg)
        close_button.clicked.connect(dlg.accept)
        close_button.setDefault(True)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
        dlg.exec_()

    def open_igrf_updates(self):
        QDesktopServices.openUrl(QUrl(IGRF_URL))

    def _input_lat_lon(self):
        lat = dms_to_decimal(self.lat_deg.currentData(), self.lat_min.currentData(), self._seconds_value(self.lat_sec), self.lat_hemi.currentText())
        lon = dms_to_decimal(self.lon_deg.currentData(), self.lon_min.currentData(), self._seconds_value(self.lon_sec), self.lon_hemi.currentText())
        if self.lat_deg.currentData() == 90 and (self.lat_min.currentData() != 0 or self._seconds_value(self.lat_sec) != 0):
            raise ValueError('At latitude 90°, minutes and seconds must be zero.')
        if self.lon_deg.currentData() == 180 and (self.lon_min.currentData() != 0 or self._seconds_value(self.lon_sec) != 0):
            raise ValueError('At longitude 180°, minutes and seconds must be zero.')
        return lat, lon

    @staticmethod
    def _automatic_utm(lat, lon):
        if lat < -80 or lat > 84:
            raise ValueError('Coordinates are outside the standard UTM latitude range; choose another CRS.')
        zone = min(60, max(1, int((lon + 180) // 6) + 1))
        epsg = (32600 if lat >= 0 else 32700) + zone
        crs = QgsCoordinateReferenceSystem('EPSG:{}'.format(epsg))
        if not crs.isValid():
            raise ValueError('The automatically selected UTM CRS is invalid.')
        return crs

    def _update_crs_label(self, *args):
        try:
            lat, lon = self._input_lat_lon()
            crs = self.target_crs if self.target_crs is not None else self._automatic_utm(lat, lon)
            suffix = 'user-selected' if self.target_crs is not None else 'automatically from coordinates'
            self.crs_label.setText('{} — {} ({})'.format(crs.authid() or 'Custom CRS', crs.description(), suffix))
        except Exception as exc:
            self.crs_label.setText('Automatic UTM: {}'.format(exc))

    def choose_crs(self):
        dialog = QgsProjectionSelectionDialog(self)
        if self.target_crs is not None:
            dialog.setCrs(self.target_crs)
        else:
            try:
                lat, lon = self._input_lat_lon()
                dialog.setCrs(self._automatic_utm(lat, lon))
            except Exception:
                dialog.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        if dialog.exec_():
            selected = dialog.crs()
            if selected.isValid():
                self.target_crs = selected
                self.choose_crs_button.setText('Automatic UTM')
                try: self.choose_crs_button.clicked.disconnect()
                except TypeError: pass
                self.choose_crs_button.clicked.connect(self.use_automatic_utm)
                self._update_crs_label()

    def use_automatic_utm(self):
        self.target_crs = None
        self.choose_crs_button.setText('Choose another CRS…')
        try: self.choose_crs_button.clicked.disconnect()
        except TypeError: pass
        self.choose_crs_button.clicked.connect(self.choose_crs)
        self._update_crs_label()

    def choose_model(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select a geomagnetic coefficient file', '', 'IGRF/WMM model files (*.COF *.cof);;All files (*.*)')
        if not path:
            return
        try:
            info = model_info(path)
            self.cof_path = path
            self.file_label.setText(os.path.basename(path))
            self.file_label.setToolTip(path)
            self._apply_model_info(info)
            self.output.clear()
            self.compass.set_angles(0.0, 0.0)
        except Exception as e:
            QMessageBox.critical(self, 'Invalid model file', str(e))

    def _apply_model_info(self, info):
        start = QDate(info['start_year'], 1, 1)
        end = QDate(info['end_year'], 1, 1)
        self.date.setMinimumDate(start)
        self.date.setMaximumDate(end)
        if self.date.date() < start: self.date.setDate(start)
        elif self.date.date() > end: self.date.setDate(end)
        self.model_label.setText('Model: %s' % info['name'])
        self.range_label.setText('Calculation date range: %s – %s' % (start.toString('yyyy-MM-dd'), end.toString('yyyy-MM-dd')))

    def update_model_info(self):
        try:
            self._apply_model_info(model_info(self.cof_path))
        except Exception as e:
            self.model_label.setText('Model: unknown')
            self.range_label.setText('Unable to read model file: %s' % e)

    def run_calculation(self):
        try:
            d = self.date.date()
            lat, lon = self._input_lat_lon()
            # The input is ellipsoidal height, as required by the geomagnetic model.
            r = calculate((d.year(), d.month(), d.day()), lat, lon, self.alt.value(), self.cof_path)
            self._last_declination = r['D_deg']
            crs = self.target_crs if self.target_crs is not None else self._automatic_utm(lat, lon)
            if not crs.isValid():
                raise ValueError('The target CRS for grid convergence is invalid.')
            factors = crs.factors(QgsPoint(lon, lat))
            if not factors.isValid():
                raise ValueError('Projection factors are invalid at these coordinates.')
            gamma = factors.meridianConvergence()
            self.compass.set_angles(r['D_deg'], gamma)
            from html import escape
            date_text = d.toString('yyyy-MM-dd')
            lat_dms = angle_dms(lat)
            lon_dms = angle_dms(lon)
            crs_text = '%s — %s' % (crs.authid() or 'Custom CRS', crs.description())
            model_text = model_info(self.cof_path).get('name', os.path.basename(self.cof_path))
            def row(label, value, label_width=190):
                # Three compact columns: label, aligned colon, value.
                return ('<tr><td style="width:%dpx;padding:3px 2px 3px 7px;vertical-align:top;text-align:left;">%s</td>'
                        '<td style="width:10px;padding:3px 2px;vertical-align:top;text-align:center;">:</td>'
                        '<td style="padding:3px 7px 3px 2px;vertical-align:top;text-align:left;">%s</td></tr>') % (label_width, label, value)
            def section(title, colspan=3):
                return '<tr><td colspan="%d" style="background:#e5f1ff;padding:6px;font-weight:bold;border:1px solid #bfdbfe;">%s</td></tr>' % (colspan, title)
            def compact_row(label, value):
                return row(label, value, 36)
            parts = [
                '<html><body style="font-family:Arial,sans-serif;font-size:10pt;color:#172033;">',
                '<table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:auto;">',
                section('Location and model information'),
                row('Map publication date', escape(date_text)),
                row('Latitude', escape('%s (%+.6f°)' % (lat_dms, lat))),
                row('Longitude', escape('%s (%+.6f°)' % (lon_dms, lon))),
                row('Ellipsoidal height', '%.3f m' % self.alt.value()),
                row('Grid CRS', escape(crs_text)),
                row('Geomagnetic model', escape('%s (%s)' % (model_text, os.path.basename(self.cof_path)))),
                section('Key angles'),
                row('<b>Magnetic declination (D)</b>', '<span style="color:#e53935;">%s &nbsp; (%+.6f°)</span>' % (angle_dms(r['D_deg']), r['D_deg'])),
                row('Grid convergence (γ)', '<span style="color:#1570ef;">%s &nbsp; (%+.6f°)</span>' % (angle_dms(gamma), gamma)),
                row('Magnetic inclination (I)', '%s &nbsp; (%+.6f°)' % (angle_dms(r['I_deg']), r['I_deg'])),
                '</table><br>',
                '<table width="100%" cellspacing="0" cellpadding="0"><tr>',
                '<td valign="top" style="width:50%;padding-right:5px;"><table width="100%" cellspacing="0" cellpadding="3" style="border:1px solid #bfdbfe;border-collapse:collapse;">',
                '<tr><td colspan="3" style="background:#e5f1ff;font-weight:bold;">Magnetic field components (nT)</td></tr>',
                compact_row('H', '%.1f' % r['H_nT']), compact_row('X', '%.1f' % r['X_nT']),
                compact_row('Y', '%.1f' % r['Y_nT']), compact_row('Z', '%.1f' % r['Z_nT']), compact_row('F', '%.1f' % r['F_nT']),
                '</table></td><td valign="top" style="width:50%;padding-left:5px;"><table width="100%" cellspacing="0" cellpadding="3" style="border:1px solid #bfdbfe;border-collapse:collapse;">',
                '<tr><td colspan="3" style="background:#e5f1ff;font-weight:bold;">Annual change</td></tr>',
                compact_row('dD', '%.2f arcmin/year' % r['dD_min']),
                compact_row('dI', '%.2f arcmin/year' % r['dI_min']),
                compact_row('dH', '%.2f nT/year' % r['dH_nT']), compact_row('dX', '%.2f nT/year' % r['dX_nT']),
                compact_row('dY', '%.2f nT/year' % r['dY_nT']), compact_row('dZ', '%.2f nT/year' % r['dZ_nT']),
                compact_row('dF', '%.2f nT/year' % r['dF_nT']),
                '</table></td></tr></table>',
                '<p style="color:#64748b;font-size:9pt;">Angles in the illustration may be exaggerated for visibility; numerical values are the calculated results. Height is measured above the WGS84 ellipsoid.</p>',
                '<h2>Author and Collaboration</h2><p>Developed and maintained by <b>Suryanto</b>.</p><p>For questions, bug reports, suggestions, or collaboration opportunities, please contact <a href=&quot;mailto:suryanto.bakos@gmail.com&quot;>suryanto.bakos@gmail.com</a>.</p><p>Contributions from the geospatial community are welcome. If you are interested in testing, improving, or extending this plugin, please get in touch. Feedback is appreciated to help improve its accuracy, usability, and functionality.</p></body></html>'
            ]
            html = ''.join(parts)
            self.output.setHtml(html)
        except Exception as e:
            QMessageBox.critical(self, 'Calculation failed', str(e))


class IGRFMagneticFieldPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.svg')
        self.action = QAction(QIcon(icon_path), 'Magnetic Declination & Grid Convergence', self.iface.mainWindow())
        self.action.setToolTip('Calculate magnetic declination and grid convergence')
        self.action.setWhatsThis('Calculates geomagnetic field elements from an IGRF/WMM file and grid convergence in the target CRS.')
        self.action.triggered.connect(self.show_dialog)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu('&Magnetic Declination & Grid Convergence', self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu('&Magnetic Declination & Grid Convergence', self.action)

    def show_dialog(self):
        if self.dialog is None:
            self.dialog = IGRFDialog(self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
