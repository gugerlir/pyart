"""
pyrad.correct.sunlib
====================

Library to deal with sun measurements

.. autosummary::
    :toctree: generated/

    sun_position_pysolar
    sun_position_mfr
    equation_of_time
    hour_angle
    solar_declination
    refraction_correction
    sun_power

"""

import sys
import datetime
import pytz

from numpy import pi, sin, cos, arcsin, arccos, sqrt, floor
import numpy as np
from scipy.special import erf

if (sys.version_info.major == 2):
    try:
        import Pysolar
        _PYSOLAR_AVAILABLE = True
    except:
        _PYSOLAR_AVAILABLE = True
else:
    try:
        import pysolar
        _PYSOLAR_AVAILABLE = True
    except:
        _PYSOLAR_AVAILABLE = True


def sun_position_pysolar(dt, lat, lon, refraction=True):
    """
    obtains the sun position in atenna coordinates using the pysolar
    library.

    Parameters
    ----------
    dt : datetime object
        the time when to look for the sun
    lat, lon : float
        latitude and longitude of the sensor in degrees
    refraction : boolean
        whether to correct for refraction or not

    Returns
    -------
    el, az : float
        elevation and azimuth angles of the sun respect to the sensor in
        degrees

    """
    if (sys.version_info.major == 2):
        el = Pysolar.GetAltitude(lat, lon, dt)
        az = (180 - Pysolar.GetAzimuth(lat, lon, dt)) % 360.
    else:
        el = pysolar.solar.get_altitude(lat, lon, dt, refraction=refraction)
        az = (180 - pysolar.solar.get_azimuth(lat, lon, dt)) % 360.

    return (el, az)


def sun_position_mfr(dt, lat_deg, lon_deg, refraction=True):
    """
    Calculate the sun position for the given time (dt) at the given position
    (lat, lon).

    Parameters
    ----------
    dt : datetime object
        the time when to look for the sun
    lat_deg, lon_deg: floats
        latitude and longitude in degrees
    refraction : boolean
        whether to correct for refraction or not

    Returns
    -------
    elev_sun, azim_sun : floats
        elevation and azimuth angles of the sun respect to the sensor in
        degrees

    """
    lat = lat_deg*pi/180.
    lon = lon_deg*pi/180.

    secs_since_midnight = (
        (dt - dt.replace(
            hour=0, minute=0, second=0, microsecond=0)).total_seconds())
    htime = secs_since_midnight/3600.
    dayjul = (
        (dt - dt.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0)).days +
        1)

    eqt = equation_of_time(dayjul)  # [h]
    hang = hour_angle(htime, lon, eqt)  # [rad]
    sdec = solar_declination(dayjul, htime)  # [rad]

    elev_sun = (arcsin(sin(lat)*sin(sdec) +
                cos(lat)*cos(sdec)*cos(hang))*180./pi)  # [deg]
    azim_sun = (arccos((sin(lat)*cos(sdec)*cos(hang) -
                cos(lat)*sin(sdec))/cos(elev_sun*pi/180.))*180./pi)

    if (hang < 0):
        azim_sun = 180. - azim_sun  # morning
    else:
        azim_sun = 180. + azim_sun  # afternoon

    if refraction:
        elev_sun += refraction_correction(elev_sun)

    return (elev_sun, azim_sun)


def equation_of_time(dayjul):
    """
    Computes the solar hour for a given julian day.

    Parameters
    ----------
    dayjul : double
        julian date

    Returns
    -------
    eqt : float
        hour

    """
    temp_cos = [-0.00720, 0.0528, 0.0012]
    temp_sin = [0.12290, 0.1565, 0.0041]
    omega = 2.*pi/365.2425  # earth mean angular orbital velocity [rad/day]

    eqt = 0.
    for ii in range(3):
        z = dayjul*omega*(ii+1)
        eqt += (temp_cos[ii]*cos(z)+temp_sin[ii]*sin(z))

    return -eqt  # [h]


def hour_angle(htime, lon, eqt):
    """
    Computes the solar angle at a particular time.

    Parameters
    ----------
    htime : double
        time in seconds since midnight
    lon : float
        longitude in degrees
    eqt : float
        solar time

    Returns
    -------
    angle : float
        the solar angle in radiants

    """
    return (htime+12./pi*lon+eqt-12.)*pi/12.  # [rad]


def solar_declination(dayjul, htime):
    """
    Computes the solar declination.

    Parameters
    ----------
    dayjul : double
        julian date
    htime : double
        time in seconds since midnight

    Returns
    -------
    angle : float
        the solar declination in radiants

    """
    omega = 2.*pi/365.2425  # earth mean angular orbital velocity [rad/day]
    correction = [0., 3., 6., 9., 12., 13., 12., 10., 10., 8., 6., 3., 1.,
                  -2., -3., -4., -5., -5., -3., -3., -1., -1., 0., 0., 1., 3.,
                  6.]

    z = dayjul * omega
    x = 0.33281 - 22.984 * cos(z) - 0.3499 * cos(2.*z) - 0.1398 * cos(3. * z)
    y = 3.7872 * sin(z) + 0.03205 * sin(2. * z) + 0.07187 * sin(3. * z)

    fortnight = int(floor(dayjul/15)) + 1
    day_fortnight = dayjul-(fortnight-1)*15
    corr1 = ((correction[fortnight] +
              day_fortnight/15.*(correction[fortnight+1] -
              correction[fortnight]))/60.)
    delta1 = x + y + corr1

    z = (dayjul+1) * omega
    x = 0.33281 - 22.984 * cos(z) - 0.3499 * cos(2.*z) - 0.1398 * cos(3. * z)
    y = 3.7872 * sin(z) + 0.03205 * sin(2. * z) + 0.07187 * sin(3. * z)

    fortnight = int(floor(dayjul+1)/15) + 1
    day_fortnight = (dayjul+1)-(fortnight-1)*15
    corr2 = ((correction[fortnight] +
              day_fortnight/15.*(correction[fortnight+1] -
              correction[fortnight]))/60.)
    delta2 = x + y + corr2

    return (delta1+(delta2-delta1)*htime/24.)*pi/180.  # [rad]


def refraction_correction(es_deg):
    """
    Computes the correction that has to be applied to the sun elevation angle
    to account for refraction

    Parameters
    ----------
    es_deg : float
        sun elevation in degrees

    Returns
    -------
    refr : float
        the correction due to refraction in degrees

    References
    ----------
    Holleman & Huuskonen, 2013: analytical formulas for refraction of
    radiowaves from exoatmospheric sources, radio science, vol. 48, 226-231

    """
    if (es_deg < -0.77):
        return 0.0
    es_rad = es_deg*pi/180.
    k = 5./4.  # effective earth radius factor (typically 4/3)
    n = 313.   # surface refractivity
    no = n*1e-6 + 1.
    refr = (
        ((k-1.)/(2.*k-1.)*cos(es_rad) *
         (sqrt((sin(es_rad))**2.+(4.*k-2.)/(k-1.)*(no-1.)) -
         sin(es_rad)))*180./pi)

    return refr


def gas_att_sun(es_deg, attg):
    """
    Computes the attenuation suffered by the sun signal through the atmosphere

    Parameters
    ----------
    es_deg : float
        sun elevation in degrees
    attg : float
        1-way gas attenuation in dB/km

    Returns
    -------
    gas_att_sun : float
        the sun attenuation in dB

    """
    r43 = 4./3.*6371  # effective earth radius [km]
    z0 = 8.4          # equivalent height of the atmosphere [km]
    return attg*(r43*sqrt((sin(es_deg*pi/180.))**2.+2.*z0/r43+(z0/r43)**2) -
                 r43*sin(es_deg*pi/180.))


def gauss_fit(az_data, az_ref, el_data, el_ref, sunhits, npar, degree=True,
              do_elcorr=True):
    """
    estimates a gaussian fit of sun hits data

    Parameters
    ----------
    az_data, el_data : float array
        azimuth and elevation radar data
    az_ref, el_ref : float array
        azimuth and elevation sun data
    sunhits : float array
        sun hits data
    npar : int
        number of parameters of the fit
    degree : boolean
        boolean indicating whether the data is in degree or radians
    do_elcorr : boolean
        indicates whether azimuth data is corrected so that azimuth
        differences are invalid with elevation

    Returns
    -------
    par : 1D float array
        the fit parameters
    alpha: 2D float array
        the matrix used in the fit
    beta: 1D float array
        the vector used in the fit

    """
    nhits = len(az_data)

    el_corr = 1.
    if do_elcorr:
        if degree:
            el_corr = np.ma.cos(el_data*np.pi/180.)
        else:
            el_corr = np.ma.cos(el_data)

    basis = np.ma.zeros((npar, nhits))
    basis[0, :] = 1.
    basis[1, :] = (az_data-az_ref)*el_corr
    basis[2, :] = el_data-el_ref

    if npar == 5:
        basis[3, :] = basis[1, :]*basis[1, :]
        basis[4, :] = basis[2, :]*basis[2, :]

    alpha = np.ma.zeros((npar, npar))
    beta = np.ma.zeros(npar)
    for hit in range(nhits):
        for ipar in range(npar):
            for jpar in range(npar):
                alpha[jpar, ipar] += basis[jpar, hit] * basis[ipar, hit]
            beta[ipar] += sunhits[hit] * basis[ipar, hit]

    try:
        alphainv = np.linalg.inv(alpha)
        par = np.ma.dot(alphainv, beta)

        return par, alpha, beta

    except LinAlgError:
        warn('Unable to perform Guassian fit of sun hits data')
        return None, None, None


def retrieval_result(sunhits, alpha, beta, par, npar):
    """
    computes the physical parameters of the sun retrieval from the results of
    a Gaussian fit.

    Parameters
    ----------
    sunhits : float array
        sun hits data
    alpha: 2D float array
        the matrix used in the fit
    beta: 1D float array
        the vector used in the fit
    par : 1D float array
        the fit parameters
    npar : int
        number of parameters of the fit

    Returns
    -------
    val, val_std : float
        retrieved value and its standard deviation
    az_bias, el_bias : float
        retrieved azimuth and elevation antenna bias respect to the sun
        position
    az_width, el_width : float
        retrieved azimuth and elevation antenna widths

    """
    nhits = len(sunhits)

    val = (
        par[0]-0.25*np.ma.power(par[1], 2.)/par[3] -
        0.25*np.ma.power(par[2], 2.)/par[4])

    az_bias = -0.5*par[1]/par[3]
    el_bias = -0.5*par[2]/par[4]

    coeff = -40.*np.ma.log10(2.)
    az_width = np.ma.sqrt(coeff/par[3])
    el_width = np.ma.sqrt(coeff/par[4])

    val_std = np.ma.sum(np.ma.power(sunhits, 2.))-2.*np.ma.sum(par*beta)
    for ipar in range(npar):
        for jpar in range(npar):
            val_std += par[ipar]*par[jpar]*alpha[ipar, jpar]
    val_std = np.ma.sqrt(val_std/(nhits-npar))

    return val, val_std, az_bias, el_bias, az_width, el_width


def sun_power(solar_flux, pulse_width, wavelen, antenna_gain, angle_step,
              beamwidth):
    """
    computes the theoretical sun power detected at the antenna [dBm] as it
    would be without atmospheric attenuation (sun power at top of the
    atmosphere

    Parameters
    ----------
    solar_flux : float array
        the solar fluxes measured at 10.7 cm wavelength [10e-22 W/(m2 Hz)]
    pulse_width : float
        pulse width [s]
    wavelen : float
        radar wavelength [m]
    antenna_gain : float
        the antenna gain [dB]
    angle_step : float
        integration angle [deg]
    beamwidth : float
        3 dB-beamwidth [deg]

    Returns
    -------
    pwr_det : float array
        the detected power

    """
    delta_s = 0.57  # apparent diameter of radio sun [deg]

    # minimum flux
    mfu = [1980., 495., 255., 170., 126., 102., 88., 76., 72., 68., 64., 61.,
           58., 55., 54., 53., 52., 51., 50., 49., 48., 48., 47., 47., 47.,
           46., 46., 45., 45., 45.]

    # scale factor
    sfa = [0.67, 0.68, 0.69, 0.70, 0.71, 0.73, 0.78, 0.84, 0.96, 1.00, 1.00,
           0.98, 0.94, 0.90, 0.85, 0.80, 0.78, 0.77, 0.76, 0.75, 0.74, 0.73,
           0.72, 0.71, 0.70, 0.69, 0.68, 0.67, 0.66, 0.65]

    g = np.power(10., 0.1*antenna_gain)
    b = 1./pulse_width  # receiver bandwidth [Hz]

    ind_w = int(wavelen*100.)-1  # table index
    s0 = sfa[ind_w]*(solar_flux-64.)+mfu[ind_w]  # solar flux at wavelen

    aeff = g*wavelen**2./(4.*np.pi)  # effective are of the antenna [m2]
    ptoa = 10.*np.log10(0.5*b*aeff*s0*1e-19)  # sun power at TOA [dBm]

    # losses due to scanning and antenna beamwidth
    l0 = 1./np.log(2.)*beamwidth**2./delta_s**2.*(
        1.-np.exp(-np.log(2.)*delta_s**2./beamwidth**2))
    la = 10.*np.log10(
        l0*np.sqrt(np.pi/(4.*np.log(2.)))*beamwidth/angle_step *
        erf(np.sqrt(np.log(2.))*angle_step/beamwidth))

    return ptoa+la
