# Magnetic Declination & Grid Convergence (WGS84) — QGIS Plugin 1.1.3
## PURPOSE

This plugin calculates magnetic declination and geomagnetic field elements using an IGRF/WMM coefficient file (`.COF`), as well as grid convergence for a target CRS. The plugin also provides an illustration of the three north directions: TN (True North), MN (Magnetic North), and GN (Grid North).

## INPUT FIELD GUIDE

### 1. Map Publication Date

Select the date on which the map will be published or printed. This date determines the geomagnetic calculation epoch and must fall within the supported date range of the selected model file.

### 2. Latitude

Enter degrees, minutes, and seconds, then select N for north or S for south.

Example: `4° 18' 17.40" N`

### 3. Longitude

Enter degrees, minutes, and seconds, then select E for east or W for west.

Example: `115° 57' 04.80" E`

### 4. Ellipsoidal Height (m)

Enter the height in metres above the WGS84 ellipsoid. The geomagnetic model uses ellipsoidal height, not orthometric height above mean sea level.

If the available data contains orthometric height (H), convert it to ellipsoidal height using `h = H + N`, where N is the appropriate geoid undulation. The plugin does not apply geoid corrections automatically.

### 5. CRS for Grid Convergence

By default, the plugin automatically selects a UTM CRS based on the input latitude and longitude. Use **Choose another CRS…** to select a different projected CRS. The button can then be used to return to automatic UTM selection.

### 6. Geomagnetic Model / Model File (.COF)

The default `IGRF14.COF` file is included with the plugin. Use **Change file…** to select a local IGRF/WMM file.

The **Check for updates** button only opens the official NOAA/NCEI website. It does not download or replace the model file automatically.

Ensure that the selected file has a valid format and covers the calculation date.

### 7. Calculate Magnetic Field and Grid Convergence

Click this button after checking all input parameters. The numerical results and illustration will be updated.

## REQUIRED DATA

- Calculation date.
- WGS84 geodetic latitude and longitude.
- Ellipsoidal height in metres.
- A geomagnetic coefficient file (`.COF`), such as IGRF or WMM, valid for the selected date.
- A target CRS for grid convergence, or automatic UTM selection.

## CALCULATION METHODS

- **Geomagnetic field:** Uses spherical harmonic coefficients from the selected IGRF/WMM file to calculate magnetic field components for the specified date, position, and height. Declination is derived from the horizontal field components, while inclination and field intensity are calculated from the relevant field components.

- **Grid convergence:** Calculated using QGIS projection factor functions for the target CRS at the specified coordinates. The sign convention follows the QGIS/CRS function. When comparing results with other software, ensure that the definitions and sign conventions are consistent.

- **Illustration:** TN = True North, MN = Magnetic North, and GN = Grid North. D represents the angle between TN and MN (magnetic declination), while γ represents the angle between TN and GN (grid convergence). The illustration is schematic and may exaggerate small angles for visibility. Numerical results should be used as the reference.

## UNDERSTANDING THE RESULTS

- **D — Magnetic declination:** The angle between true north and magnetic north, displayed in DMS and decimal degrees.
- **γ — Grid convergence:** The angle between true north and grid north, displayed in DMS and decimal degrees.
- **I — Magnetic inclination:** The angle of the magnetic field relative to the horizontal plane.
- **H:** Horizontal field intensity (nT).
- **X:** Northward field component (nT).
- **Y:** Eastward field component (nT).
- **Z:** Vertically downward field component (nT).
- **F:** Total magnetic field intensity (nT).
- **dD and dI:** Annual changes in angular values, expressed in arcminutes per year.
- **dH, dX, dY, dZ, and dF:** Annual changes in field intensity, expressed in nT per year.

## EXPECTED RESULTS

After clicking **Calculate Magnetic Field and Grid Convergence**, the results panel displays location and model information, the three main angles (D, γ, and I), the H/X/Y/Z/F field components, and annual changes.

The illustration updates the MN and GN directions. Results depend on the calculation date, coordinates, height, `.COF` model file, and CRS. Differences from other sources may occur when input parameters, models, or sign conventions differ.

## INSTALLATION

1. Close QGIS.
2. Extract the `magnetic_declination_grid_convergence` folder into the `python/plugins` directory of your QGIS profile.

   Example for Windows:

   `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\magnetic_declination_grid_convergence`

3. Open QGIS and enable the plugin under **Plugins > Manage and Install Plugins > Installed**.
4. The plugin icon should appear in the QGIS toolbar. If it is not visible, check **View > Toolbars** and ensure that the Plugins toolbar is enabled. The plugin is also available from the Plugins menu.

## VERSION 1.1.0

- Added
