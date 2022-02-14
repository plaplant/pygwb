import logging
import os

import bilby.gw.detector
import numpy as np
from bilby.gw.detector.psd import PowerSpectralDensity

from .pre_processing import (
    preprocessing_data_channel_name,
    preprocessing_data_gwpy_timeseries,
    preprocessing_data_timeseries_array,
)
from .spectral import before_after_average, power_spectral_density


class Interferometer(bilby.gw.detector.Interferometer):

    """Subclass of bilby's Interferometer class"""

    def __init__(self, *args, **kwargs):
        """Instantiate an Interferometer class

        Parameters
        ==========
        *args : arguments passed to the (parent) bilby's Interferometer class.
        **kwargs : keyword arguments passed to the (parent) bilby's Inteferometer class.

        Nominally, the bilby's Interferometer class takes the following arguments.
        name: str
            Interferometer name, e.g. H1.
        power_spectral_density: bilby.gw.detector.PowerSpectralDensity
            Power spectral density determining the sensitivity of the detector.
        minimum_frequency: float
            Minimum frequency to analyse for detector.
        maximum_frequency: float
            Maximum frequency to analyse for detector.
        length: float
            Length of the interferometer in km.
        latitude: float
            Latitude North in degrees (South is negative).
        longitude: float
            Longitude East in degrees (West is negative).
        elevation: float
            Height above surface in metres.
        xarm_azimuth: float
            Orientation of the x arm in degrees North of East.
        yarm_azimuth: float
            Orientation of the y arm in degrees North of East.
        xarm_tilt: float, optional
            Tilt of the x arm in radians above the horizontal defined by
            ellipsoid earth model in LIGO-T980044-08.
        yarm_tilt: float, optional
            Tilt of the y arm in radians above the horizontal.
        calibration_model: Recalibration
            Calibration model, this applies the calibration correction to the
            template, the default model applies no correction.

        See https://lscsoft.docs.ligo.org/bilby/api/bilby.gw.detector.interferometer.Interferometer.html#bilby.gw.detector.interferometer.Interferometer
        for the detailed docs of the parent class.

        Additional attributes
        timeseries : gwpy timeseries
            timeseries object with resampling/high-pass filter applied.
        psd_spectrogram : gwpy spectrogram
            gwpy spectrogram of power spectral density

        """
        super(Interferometer, self).__init__(*args, **kwargs)

    @classmethod
    def get_empty_interferometer(cls, name):
        """
        A classmethod to get an Interferometer class from a given ifo name

        Parameters
        ==========
        name : str
            Interferometer name, e.g. H1.

        Returns
        =======
        interferometer: Interferometer
            Interferometer instance

        """
        filename = os.path.join(
            os.path.dirname(bilby.gw.detector.__file__),
            "detectors",
            f"{name}.interferometer",
        )
        try:
            parameters = dict()
            with open(filename, "r") as parameter_file:
                lines = parameter_file.readlines()
                for line in lines:
                    if line[0] == "#" or line[0] == "\n":
                        continue
                    split_line = line.split("=")
                    key = split_line[0].strip()
                    value = eval("=".join(split_line[1:]))
                    parameters[key] = value
            if "shape" not in parameters.keys():
                logging.debug("Assuming L shape for name")
            elif parameters["shape"].lower() in ["l", "ligo"]:
                parameters.pop("shape")
            elif parameters["shape"].lower() in ["triangular", "triangle"]:
                raise ValueError("Triangular detectros are not implemented yet.")
            else:
                raise IOError(
                    f"{filename} could not be loaded. Invalid parameter 'shape'."
                )
            ifo_cls = cls(**parameters)
            ifo_cls._check_ifo_name(name)
            return ifo_cls
        except OSError:
            raise ValueError(f"Interferometer {name} not implemented")

    @classmethod
    def from_parameters(cls, name, parameters):
        """
        A classmethod to get an Interferometer class from a given argparser object

        Parameters
        ==========
        name : str
            Interferometer name, e.g. H1.
        parameters : argparser object
            This contains attributes defined for command line options

        Returns
        =======
        interferometer: Interferometer
            Interferometer instance

        """
        ifo = cls.get_empty_interferometer(name)
        channel = str(ifo.name + ":" + parameters.channel)
        ifo.set_timeseries_from_channel_name(
            channel,
            t0=parameters.t0,
            tf=parameters.tf,
            data_type=parameters.data_type,
            new_sample_rate=parameters.new_sample_rate,
            cutoff_frequency=parameters.cutoff_frequency,
            segment_duration=parameters.segment_duration,
            number_cropped_seconds=parameters.number_cropped_seconds,
            window_downsampling=parameters.window_downsampling,
            ftype=parameters.ftype,
        )
        return ifo

    def set_timeseries_from_channel_name(self, channel, **kwargs):
        """
        Set a timeseries attribute from a given channel name

        Parameters
        ==========
        channel: str
            Name of the channel (e.g.: "L1:GWOSC-4KHZ_R1_STRAIN") from which to load the data.

        **kwargs : keyword arguments passed to preprocess module.

        """

        t0 = kwargs.pop("t0")
        tf = kwargs.pop("tf")
        data_type = kwargs.pop("data_type")
        new_sample_rate = kwargs.pop("new_sample_rate")
        cutoff_frequency = kwargs.pop("cutoff_frequency")
        segment_duration = kwargs.pop("segment_duration")
        self.duration=segment_duration
        self.timeseries = preprocessing_data_channel_name(
            IFO=self.name,
            channel=channel,
            t0=t0,
            tf=tf,
            data_type=data_type,
            new_sample_rate=new_sample_rate,
            cutoff_frequency=cutoff_frequency,
            segment_duration=segment_duration,
            **kwargs
        )
        # self._check_timeseries_channel_name(channel)

    def set_timeseries_from_timeseries_array(self, timeseries_array, **kwargs):
        """
        Set a timeseries attribute from a given numpy array

        Parameters
        ==========
        timeseries_array: numpy array
            timeseries strain data as numpy array object

        **kwargs : keyword arguments passed to preprocess module.

        """

        t0 = kwargs.pop("t0")
        tf = kwargs.pop("tf")
        data_type = kwargs.pop("data_type")
        new_sample_rate = kwargs.pop("new_sample_rate")
        cutoff_frequency = kwargs.pop("cutoff_frequency")
        segment_duration = kwargs.pop("segment_duration")
        self.duration=segment_duration
        self.timeseries = preprocessing_data_timeseries_array(
            IFO=self.name,
            array=timeseries_array,
            t0=t0,
            tf=tf,
            data_type=data_type,
            new_sample_rate=new_sample_rate,
            cutoff_frequency=cutoff_frequency,
            segment_duration=segment_duration,
            **kwargs
        )
        # self._check_timeseries_sample_rate(new_sample_rate)

    def set_timeseries_from_gwpy_timeseries(self, gwpy_timeseries, **kwargs):
        """
        Set a timeseries attribute from a given gwpy timeseries object

        Parameters
        ==========
        gwpy_timeseries: gwpy.timeseries
            timeseries strain data as gwpy.timeseries object

        **kwargs : keyword arguments passed to preprocess module.

        """

        new_sample_rate = kwargs.pop("new_sample_rate")
        cutoff_frequency = kwargs.pop("cutoff_frequency")
        self.duration=segment_duration
        self.timeseries = preprocessing_data_gwpy_timeseries(
            IFO=self.name,
            gwpy_timeseries=gwpy_timeseries,
            new_sample_rate=new_sample_rate,
            cutoff_frequency=cutoff_frequency,
            **kwargs
        )
        # self._check_timeseries_sample_rate(new_sample_rate)

    def set_psd_spectrogram(
        self,
        frequency_resolution,
        overlap_factor=0.5,
        overlap_factor_welch_psd=0,
        window_fftgram="hann",
    ):
        """
        Set psd_spectrogram attribute from a given spectrum-related information.

        Parameters
        ==========
        frequency_resolution: float
            Frequency resolution of the final PSDs; This sets the time duration
            over which FFTs are calculated in the pwelch method
        overlap_factor: float, optional
            Amount of overlap between adjacent segments (range between 0 and 1)
            This factor should be same as the one used for cross_spectral_density
            (default 0, no overlap)
        overlap_factor_welch_psd: float, optional
            Amount of overlap between data blocks used in pwelch method (range between 0 and 1)
            (default 0, no overlap)
        window_fftgram: str, optional
            Type of window to use for FFT (default no window)

        """

        # psd_array = spectral.psd(self.timeseries, frequencies)
        self.psd_spectrogram = power_spectral_density(
            self.timeseries,
            self.duration,
            frequency_resolution,
            overlap_factor=overlap_factor,
            window_fftgram=window_fftgram,
            overlap_factor_welch_psd=overlap_factor_welch_psd,
        )
        self._check_spectrogram_sample_rate(self.timeseries.sample_rate)
        self._check_spectrogram_channel_name(self.timeseries.channel)
        self._check_spectrogram_frequency_resolution(frequency_resolution)

    def set_average_psd(self, N_average_segments_welch_psd):
        """
        Set average_psd attribute from the existing raw psd

        Parameters
        ==========
        N_average_segments_welch_psd : int
            Number of segments used for PSD averaging (from both sides of the segment of interest)
            N_avg_segs should be even and >= 2

        """
        try:
            self.average_psd = before_after_average(
                self.psd_spectrogram, self.duration, N_average_segments_welch_psd
            )
        except AttributeError:
            print(
                "PSDs have not been calculated yet! Need to set_psd_spectrogram first."
            )

    def _check_ifo_name(self, name):
        if not self.name == name:
            raise AssertionError("The ifo name in Interferomaeter class does not match given name!")

    def _check_timeseries_channel_name(self, channel_name):
        if not self.timeseries.channel == channel_name:
            raise AssertionError("Channel name in timeseries does not match given channel!")

    def _check_timeseries_sample_rate(self, sample_rate):
        if not self.timeseries.sample_rate == sample_rate:
            raise AssertionError("Sampling rate in timeseries does not match given sampleing rate!")

    def _check_spectrogram_sample_rate(self, sample_rate):
        if not self.psd_spectrogram.sample_rate == sample_rate:
            raise AssertionError("Sampling rate in psd_spectrogram does not match given sampleing rate!")

    def _check_spectrogram_channel_name(self, channel_name):
        if not self.psd_spectrogram.channel == channel_name:
            raise AssertionError("Channel name in psd_spectrogram does not match given channel!")

    def _check_spectrogram_frequency_resolution(self, frequency_resolution):
        if not self.psd_spectrogram.df.value == frequency_resolution:
            raise AssertionError("Frequency resolution in psd_spectrogram does not match given frequency resolution!")
