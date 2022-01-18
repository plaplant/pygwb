import json
import os
import sys
from pathlib import Path

import bilby
import matplotlib.pyplot as plt
import numpy as np
from gwpy import timeseries

import pygwb.argument_parser
from pygwb import network, orfs, pre_processing, spectral
from pygwb.baseline import Baseline
from pygwb.constants import H0, speed_of_light
from pygwb.delta_sigma_cut import run_dsc
from pygwb.detector import Interferometer
from pygwb.notch import StochNotch, StochNotchList
from pygwb.parameters import Parameters
from pygwb.postprocessing import postprocess_Y_sigma
from pygwb.util import calc_bias, calc_Y_sigma_from_Yf_varf, window_factors


def calculate_Yf_varf_params(freqs, csd, avg_psd_1, avg_psd_2, orf, params):
    S_alpha = (
        3
        * H0 ** 2
        / (10 * np.pi ** 2)
        / freqs ** 3
        * (freqs / params.fref) ** params.alpha
    )
    Y_fs = np.real(csd) / (orf * S_alpha)
    var_fs = (
        1
        / (2 * params.segment_duration * (freqs[1] - freqs[0]))
        * avg_psd_1
        * avg_psd_2
        / (orf ** 2 * S_alpha ** 2)
    )

    w1w2bar, w1w2squaredbar, _, _ = window_factors(
        params.new_sample_rate * params.segment_duration
    )

    var_fs = var_fs * w1w2squaredbar / w1w2bar ** 2
    return Y_fs, var_fs


if __name__ == "__main__":
    parser = pygwb.argument_parser.parser
    parser.add_argument(
        "-out",
        help="Location at which to save data (optional)",
        action="store",
        default="None",
    )
    args = parser.parse_args()
    params = Parameters.from_file(args.param_file)
    params.t0 = args.t0
    params.tf = args.tf
    params.alphas = json.loads(params.alphas_delta_sigma_cut)
    print("successfully imported parameters from paramfile.")
    # params.save_new_paramfile()
    outfile_path = Path(args.param_file)
    outfile_path = outfile_path.with_name(
        f"{outfile_path.stem}_final{outfile_path.suffix}"
    )
    params.save_paramfile(str(outfile_path))
    print(f"saved final param file at {outfile_path}.")

    # Parameters.from_file("param.ini")

    # Boolean_CSD = True #if False, it will only compute the CSDs and PSDs, if True, it will compute until the point estimates

    ifo_H = Interferometer.from_parameters("H1", params)
    ifo_L = Interferometer.from_parameters("L1", params)
    print(f"loaded up interferometers with selected parameters.")

    base_HL = Baseline.from_parameters(ifo_H, ifo_L, params)
    print(f"baseline with interferometers {ifo_H.name}, {ifo_L.name} initialised.")

    print(f"setting PSD and CSD of the baseline...")
    base_HL.set_cross_and_power_spectral_density(params.frequency_resolution)
    base_HL.set_average_power_spectral_densities()
    base_HL.set_average_cross_spectral_density()

    print(f"... done.")
    segment_starttime = base_HL.csd.times.value - (
        params.segment_duration / 2
    )  # for later use

    freqs = base_HL.interferometer_1.average_psd.yindex.value
    base_HL.set_frequencies(freqs)

    deltaF = freqs[1] - freqs[0]
    try:
        assert (
            abs(deltaF - params.frequency_resolution) < 1e-6
        )  # within machine (floating point) precision
    except ValueError:
        print("Frequency resolution in PSD/CSD is different than requested.")

    naive_psd_1 = base_HL.interferometer_1.psd_spectrogram
    naive_psd_2 = base_HL.interferometer_2.psd_spectrogram

    freq_band_cut = (freqs >= params.flow) & (freqs <= params.fhigh)
    naive_psd_1 = naive_psd_1.crop_frequencies(
        params.flow, params.fhigh + deltaF
    )
    naive_psd_2 = naive_psd_2.crop_frequencies(
        params.flow, params.fhigh + deltaF
    )
    avg_psd_1 = base_HL.interferometer_1.average_psd.crop_frequencies(
        params.flow, params.fhigh + deltaF
    )
    avg_psd_2 = base_HL.interferometer_2.average_psd.crop_frequencies(
        params.flow, params.fhigh + deltaF
    )
    csd = base_HL.average_csd.crop_frequencies(params.flow, params.fhigh + deltaF)

    stride = params.segment_duration * (1 - params.overlap_factor)
    csd_segment_offset = int(np.ceil(params.segment_duration / stride))
    naive_psd_1 = naive_psd_1[
        csd_segment_offset : -(csd_segment_offset + 1) + 1
    ]
    naive_psd_2 = naive_psd_2[
        csd_segment_offset : -(csd_segment_offset + 1) + 1
    ]


    kamiel_path = "/home/kamiel.janssens/Development_pyGWB/myOwn_Fork/pygwb/tutorials/"

    lines_stochnotch = StochNotchList.load_from_file(
        "{0}Official_O3_HL_notchlist.txt".format(kamiel_path)
    )

    lines_2 = np.zeros((len(lines_stochnotch), 2))

    for index, notch in enumerate(lines_stochnotch):
        lines_2[index, 0] = lines_stochnotch[index].minimum_frequency
        lines_2[index, 1] = lines_stochnotch[index].maximum_frequency

    badGPStimes = run_dsc(
        params.delta_sigma_cut,
        naive_psd_1,
        naive_psd_2,
        avg_psd_1,
        avg_psd_2,
        params.alphas,
        lines_2,
        #params.new_sample_rate,
        #params.segment_duration,
    )

    print(badGPStimes)

    sys.exit()

    freqs = freqs[freq_band_cut]
    indices_notches, inv_indices = lines_stochnotch.get_idxs(freqs)

    if params.Boolean_CSD:
        orf = base_HL.overlap_reduction_function[freq_band_cut]
        Y_fs, var_fs = calculate_Yf_varf_params(
            freqs, csd.value, avg_psd_1.value, avg_psd_2.value, orf, params
        )

        # notch_freq = np.real(stochastic_mat['ptEst_ff']==0)
        Y_fs[:, indices_notches] = 0
        var_fs[:, indices_notches] = np.Inf

        # from pygwb import postprocessing_pat
        # iso_job = postprocessing_pat.IsotropicJob(Y_fs, (var_fs)**0.5, segment_starttime, segment_duration, sample_rate, frequencies=freqs)
        # Y_f = iso_job.combined_Y_spectrum
        # var_f = iso_job.combined_sigma_spectrum**2
        # Y_pyGWB, sigma_pyGWB = iso_job.calculate_broadband_statistics(0) # alpha = 0
        # Y_f[boolean_notch] = 0
        # var_f[boolean_notch] = np.inf

        Y_f_new, var_f_new = postprocess_Y_sigma(
            Y_fs,
            var_fs,
            params.segment_duration,
            deltaF,
            params.new_sample_rate,
            indices_notches,
        )

        Y_pyGWB_new, sigma_pyGWB_new = calc_Y_sigma_from_Yf_varf(
            Y_f_new, var_f_new, freqs, params.alpha, params.fref
        )

        print("\tpyGWB: %e" % (Y_pyGWB_new))
        print("\tpyGWB: %e" % (sigma_pyGWB_new))

        data_file_name = args.out + "_{0}".format(str(int(args.t0)))

        base_HL.save_data(
            params.save_data_type,
            data_file_name,
            freqs,
            Y_f_new,
            var_f_new,
            Y_pyGWB_new,
            sigma_pyGWB_new,
        )

    else:
        print("csd")

        data_file_name = args.out + "_{0}".format(str(int(args.t0)))

        base_HL.save_data_csd(
            params.save_data_type, data_file_name, freqs, csd, avg_psd_1, avg_psd_2
        )
