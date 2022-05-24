import copy
import os
import shutil

import gwpy
import h5py
import numpy as np
from scipy.interpolate import interp1d
from scipy.signal import get_window

from pygwb.constants import H0


def window_factors(N, window_fftgram_dict={"window_fftgram": "hann"}):
    """
    Calculate window factors. By default, for a hann window.
    """
    window_tuple = get_window_tuple(window_fftgram_dict)
    w = get_window(window_tuple, N, fftbins=False)
    w1w2bar = np.mean(w ** 2)
    w1w2squaredbar = np.mean(w ** 4)

    w1 = w[int(N / 2) : N]
    w2 = w[0 : int(N / 2)]
    w1w2squaredovlbar = 1 / (N / 2.0) * np.sum(w1 ** 2 * w2 ** 2)

    w1w2ovlbar = 1 / (N / 2.0) * np.sum(w1 * w2)

    return w1w2bar, w1w2squaredbar, w1w2ovlbar, w1w2squaredovlbar


def get_window_tuple(window_fftgram_dict={"window_fftgram": "hann"}):
    window_dict = copy.deepcopy(window_fftgram_dict)
    out = tuple([window_dict["window_fftgram"]])
    window_dict.pop("window_fftgram")
    for name in window_dict:
        if name != "sym":
            out += tuple([window_dict[name]])
    if "sym" in window_fftgram_dict:
        out += tuple([window_dict["sym"]])
    return out


def calc_rho1(N, window_fftgram_dict={"window_fftgram": "hann"}):
    """
    Calculate the combined window factor rho.

    Parameters
    ==========
    N: int
        Length of the window.
    """
    w1w2bar, _, w1w2ovlbar, _ = window_factors(N, window_fftgram_dict)
    rho1 = (0.5 * w1w2ovlbar / w1w2bar) ** 2
    return rho1


def calc_bias(
    segmentDuration,
    deltaF,
    deltaT,
    N_avg_segs=2,
    window_fftgram_dict={"window_fftgram": "hann"},
):
    """
    Calculate the bias factor introduced by welch averaging.

    Parameters
    ==========
    segmentDuration: float
        Duration in seconds of welched segment.
    deltaF: float
        Frequency resolution of welched segment.
    deltaT: float
        Time sampling of welched segment.
    N_avg_segs: int, optional
        Number of segments over which the average is performed.
    """
    N = int(segmentDuration / deltaT)
    rho1 = calc_rho1(N, window_fftgram_dict)
    Nsegs = 2 * segmentDuration * deltaF - 1
    wfactor = (1 + 2 * rho1) ** (-1)
    Neff = N_avg_segs * wfactor * Nsegs
    bias = Neff / (Neff - 1)
    return bias


def omega_to_power(omega_GWB, frequencies):
    """
    Compute the GW power spectrum starting from the omega_GWB
    spectrum.

    Parameters
    ==========

    Returns
    =======
    power: gwpy.frequencyseries.FrequencySeries
        A gwpy FrequencySeries containing the GW power spectrum
    """
    H_theor = (3 * H0 ** 2) / (10 * np.pi ** 2)

    power = H_theor * omega_GWB * frequencies ** (-3)
    power = gwpy.frequencyseries.FrequencySeries(power, frequencies=frequencies)

    return power


def interpolate_frequency_series(fSeries, new_frequencies):
    """
    Interpolate a frequency series, given a new set of frequencies.

    Parameters
    ==========
    fSeries: FrequencySeries object
    new_frequencies: array_like
    """
    spectrum = fSeries.value
    frequencies = fSeries.frequencies.value

    spectrum_func = interp1d(
        frequencies, spectrum, kind="cubic", fill_value="extrapolate"
    )

    return gwpy.frequencyseries.FrequencySeries(
        spectrum_func(new_frequencies), frequencies=new_frequencies
    )


def StatKS(DKS):
    """
    Compute the KS test.
    """
    jmax = 500
    pvalue = 0.0
    for jj in np.arange(1, jmax + 1):
        pvalue += 2.0 * (-1) ** (jj + 1) * np.exp(-2.0 * jj ** 2 * DKS ** 2)
    return pvalue
