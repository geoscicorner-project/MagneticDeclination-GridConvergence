# -*- coding: utf-8 -*-
"""Python port of the core geomagnetic calculation in NOAA/NCEI Geomag 7.0.

The coefficient-file layout and spherical-harmonic recurrence follow the supplied
geomag70.c source. Units: altitude input to calculate() is metres above the
WGS84 ellipsoid; field components are nT; angles are degrees.
"""
import math
import os

EARTH_RADIUS = 6371.2
A2 = 40680631.59  # WGS84 semi-major axis squared, km^2
B2 = 40408299.98  # WGS84 semi-minor axis squared, km^2


def _decimal_year(year, month, day):
    import datetime
    d = datetime.date(year, month, day)
    start = datetime.date(year, 1, 1)
    end = datetime.date(year + 1, 1, 1)
    return year + (d - start).days / float((end - start).days)


def _read_models(path):
    """Read model headers and coefficient rows from IGRF/WMM .COF files."""
    with open(path, 'r', encoding='ascii', errors='replace') as f:
        lines = f.readlines()
    models = []
    current = None
    for line in lines:
        p = line.split()
        if not p:
            continue
        if p[0].upper().startswith(('IGRF', 'DGRF', 'WMM')) and len(p) >= 4:
            try:
                epoch = float(p[1]); nmax = int(p[2]); nsv = int(p[3])
            except (ValueError, IndexError):
                continue
            current = {'name': p[0], 'epoch': epoch, 'nmax': nmax,
                       'nsv': nsv, 'main': [], 'sv': []}
            models.append(current)
            continue
        if current is None or len(p) < 6:
            continue
        try:
            n, m = int(p[0]), int(p[1])
            vals = [float(p[i]) for i in range(2, 6)]
        except (ValueError, IndexError):
            continue
        if 1 <= n <= 13 and 0 <= m <= n:
            current['main'].append((n, m, vals[0], vals[1]))
            current['sv'].append((n, m, vals[2], vals[3]))
    # Keep complete blocks only; coefficient rows are ordered as in Geomag 7.0.
    valid = []
    for model in models:
        expected = model['nmax'] * (model['nmax'] + 3) // 2
        if len(model['main']) >= expected:
            model['main'] = model['main'][:expected]
            model['sv'] = model['sv'][:expected]
            valid.append(model)
    if not valid:
        raise ValueError('Tidak dapat membaca blok koefisien dari file COF.')
    return valid


def model_info(path):
    """Return model name and supported calculation date bounds.

    The upper bound reserves one year for the plugin's annual-change output.
    """
    models = _read_models(path)
    first = models[0]
    last = models[-1]
    # The model is extrapolated with secular variation for up to five years.
    end_year = last['epoch'] + (5.0 if last['nsv'] > 0 else 0.0)
    # calculate() also evaluates year + 1 to calculate annual differences.
    calc_end_year = end_year - 1.0
    return {
        'name': last['name'],
        'first_epoch': first['epoch'],
        'last_epoch': last['epoch'],
        'start_year': int(math.floor(first['epoch'])),
        'end_year': int(math.floor(calc_end_year)),
        'raw_end_year': end_year,
    }


def _coeff_vector(rows, max_degree=13):
    # Geomag's 1-based storage order: g(n,0), g(n,1), h(n,1), ...
    out = [0.0] * (max_degree * (max_degree + 2) + 1)
    idx = 1
    for n, m, g, h in rows:
        out[idx] = g; idx += 1
        if m != 0:
            out[idx] = h; idx += 1
    return out


def _model_coefficients(models, year):
    if year < models[0]['epoch']:
        raise ValueError('Tanggal lebih awal daripada model IGRF yang tersedia.')
    for i in range(len(models) - 1):
        a, b = models[i], models[i + 1]
        if a['epoch'] <= year <= b['epoch']:
            f = (year - a['epoch']) / (b['epoch'] - a['epoch'])
            nmax = max(a['nmax'], b['nmax'])
            ca = _coeff_vector(a['main']); cb = _coeff_vector(b['main'])
            count = nmax * (nmax + 2)
            return [0.0] + [ca[j] + f * (cb[j] - ca[j]) for j in range(1, count + 1)], nmax
    last = models[-1]
    if last['nsv'] <= 0 or year > last['epoch'] + 5.0 + 1e-8:
        raise ValueError('Tanggal berada di luar rentang prediksi model IGRF yang tersedia.')
    main = _coeff_vector(last['main'])
    sv = _coeff_vector(last['sv'])
    count = last['nmax'] * (last['nmax'] + 2)
    return [0.0] + [main[j] + (year - last['epoch']) * sv[j] for j in range(1, count + 1)], last['nmax']


def _field(lat, lon, altitude_km, coeff, nmax):
    """Evaluate X north, Y east, Z down using Geomag 7.0's recurrence."""
    dtr = 0.01745329
    slat = math.sin(lat * dtr)
    aa_lat = lat
    if 90.0 - lat < 0.001: aa_lat = 89.999
    elif 90.0 + lat < 0.001: aa_lat = -89.999
    clat = math.cos(aa_lat * dtr)
    sl = [0.0] * 14; cl = [0.0] * 14
    sl[1] = math.sin(lon * dtr); cl[1] = math.cos(lon * dtr)
    x = y = z = 0.0
    cd = 1.0; sd = 0.0
    elev = altitude_km
    aa = A2 * clat * clat
    bb = B2 * slat * slat
    cc = aa + bb
    dd = math.sqrt(cc)
    arg = elev * (elev + 2.0 * dd) + (A2 * aa + B2 * bb) / cc
    r = math.sqrt(arg)
    cd = (elev + dd) / r
    sd = (A2 - B2) / dd * slat * clat / r
    old_slat = slat
    slat = slat * cd - clat * sd
    clat = clat * cd + old_slat * sd
    ratio = EARTH_RADIUS / r
    p = [0.0] * 120; q = [0.0] * 120
    p[1] = 2.0 * slat; p[2] = 2.0 * clat
    p[3] = 4.5 * slat * slat - 1.5
    p[4] = 3.0 * math.sqrt(3.0) * clat * slat
    q[1] = -clat; q[2] = slat
    q[3] = -3.0 * clat * slat
    q[4] = math.sqrt(3.0) * (slat * slat - clat * clat)
    n = 0; m = 1; coeff_idx = 1
    for k in range(1, nmax * (nmax + 3) // 2 + 1):
        if n < m:
            m = 0; n += 1
            rr = ratio ** (n + 2); fn = float(n)
        fm = float(m)
        if k >= 5:
            if m == n:
                aa = math.sqrt(1.0 - 0.5 / fm)
                j = k - n - 1
                p[k] = (1.0 + 1.0 / fm) * aa * clat * p[j]
                q[k] = aa * (clat * q[j] + slat / fm * p[j])
                sl[m] = sl[m-1] * cl[1] + cl[m-1] * sl[1]
                cl[m] = cl[m-1] * cl[1] - sl[m-1] * sl[1]
            else:
                aa = math.sqrt(fn * fn - fm * fm)
                bb = math.sqrt((fn - 1.0) * (fn - 1.0) - fm * fm) / aa
                cc = (2.0 * fn - 1.0) / aa
                ii = k - n; j = k - 2 * n + 1
                p[k] = (fn + 1.0) * (cc * slat / fn * p[ii] - bb / (fn - 1.0) * p[j])
                q[k] = cc * (slat * q[ii] - clat / fn * p[ii]) - bb * q[j]
        a = rr * coeff[coeff_idx]
        if m == 0:
            x += a * q[k]; z -= a * p[k]; coeff_idx += 1
        else:
            b = rr * coeff[coeff_idx + 1]
            c = a * cl[m] + b * sl[m]
            x += c * q[k]; z -= c * p[k]
            if clat > 0.0:
                y += (a * sl[m] - b * cl[m]) * fm * p[k] / ((fn + 1.0) * clat)
            else:
                y += (a * sl[m] - b * cl[m]) * q[k] * slat
            coeff_idx += 2
        m += 1
    old_x = x
    x = x * cd + z * sd
    z = z * cd - old_x * sd
    return x, y, z


def calculate(date, latitude, longitude, altitude_m, cof_path):
    """Return field elements and one-year differences for a decimal year/date.

    date can be a decimal year (float) or (year, month, day) tuple.
    Coordinates are geodetic WGS84 degrees; altitude is metres.
    """
    if isinstance(date, (tuple, list)):
        year = _decimal_year(int(date[0]), int(date[1]), int(date[2]))
    else:
        year = float(date)
    if not -90 <= latitude <= 90: raise ValueError('Lintang harus antara -90 dan 90 derajat.')
    if not -180 <= longitude <= 180: raise ValueError('Bujur harus antara -180 dan 180 derajat.')
    models = _read_models(cof_path)
    c1, n1 = _model_coefficients(models, year)
    c2, n2 = _model_coefficients(models, year + 1.0)
    n = min(n1, n2)
    x, y, z = _field(latitude, longitude, altitude_m / 1000.0, c1, n)
    x2, y2, z2 = _field(latitude, longitude, altitude_m / 1000.0, c2, n)
    h = math.hypot(x, y); f = math.sqrt(h*h + z*z)
    d = math.degrees(math.atan2(y, x))
    inc = math.degrees(math.atan2(z, h))
    h2 = math.hypot(x2, y2); f2 = math.sqrt(h2*h2 + z2*z2)
    d2 = math.degrees(math.atan2(y2, x2)); i2 = math.degrees(math.atan2(z2, h2))
    dd = ((d2 - d + 180.0) % 360.0 - 180.0) * 60.0
    return {'date': year, 'D_deg': d, 'I_deg': inc, 'H_nT': h, 'X_nT': x,
            'Y_nT': y, 'Z_nT': z, 'F_nT': f, 'dD_min': dd,
            'dI_min': (i2-inc)*60.0, 'dH_nT': h2-h, 'dX_nT': x2-x,
            'dY_nT': y2-y, 'dZ_nT': z2-z, 'dF_nT': f2-f}
