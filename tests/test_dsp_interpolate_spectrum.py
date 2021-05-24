import pytest
from pytest import raises
import numpy as np
import numpy.testing as npt
import matplotlib.pyplot as plt
import pyfar as pf
from pyfar.dsp import interpolate_spectrum

# TODO: Finish `test_interpolation()` for 'magnitude_minimum'


def test_init():
    """Test return objects"""
    fd = pf.FrequencyData([1, .5], [100, 200])

    # interpolation object
    interpolator = interpolate_spectrum(
        fd, "complex", ("linear", "linear", "linear"))
    assert isinstance(interpolator, interpolate_spectrum)

    # interpolation result
    signal = interpolator(8, 44100)
    assert isinstance(signal, pf.Signal)


def test_init_assertions():
    """Test if init raises assertions correctly"""
    fd = pf.FrequencyData([1, .5], [100, 200])

    # data (invalid type)
    with raises(TypeError, match="data must be"):
        interpolate_spectrum(1, "complex", ("linear", "linear", "linear"))
    # data (invalid FFT normalization)
    with raises(ValueError, match="data.fft_norm is 'rms'"):
        fd_rms = pf.FrequencyData([1, .5], [100, 200], 'rms')
        interpolate_spectrum(
            fd_rms, "complex", ("linear", "linear", "linear"))
    # data (not enough bins)
    with raises(ValueError, match="data.n_bins must be at least 2"):
        fd_short = pf.FrequencyData(1, 100)
        interpolate_spectrum(
            fd_short, "complex", ("linear", "linear", "linear"))

    # test invalid method
    with raises(ValueError, match="method is 'invalid'"):
        interpolate_spectrum(fd, "invalid", ("linear", "linear", "linear"))

    # test kind (invald type)
    with raises(ValueError, match="kind must be a tuple of length 3"):
        interpolate_spectrum(fd, "complex", "linear")
    # test kind (invalid length)
    with raises(ValueError, match="kind must be a tuple of length 3"):
        interpolate_spectrum(fd, "complex", ("linear", "linear"))
    # test kind (wrong entry)
    with raises(ValueError, match="kind contains 'wrong'"):
        interpolate_spectrum(fd, "complex", ("linear", "linear", "wrong"))

    # test fscale
    with raises(ValueError, match="fscale is 'nice'"):
        interpolate_spectrum(
            fd, "complex", ("linear", "linear", "linear"), fscale="nice")

    # test clip (wrong value of bool)
    with raises(ValueError, match="clip must be a tuple of length 2"):
        interpolate_spectrum(
            fd, "complex", ("linear", "linear", "linear"), clip=True)
    # test clip (invalid type)
    with raises(ValueError, match="clip must be a tuple of length 2"):
        interpolate_spectrum(
            fd, "complex", ("linear", "linear", "linear"), clip=1)
    # test clip (invalid length)
    with raises(ValueError, match="clip must be a tuple of length 2"):
        interpolate_spectrum(
            fd, "complex", ("linear", "linear", "linear"), clip=(1, 2, 3))

    # test not providing group_delay for method="magnitude_linear"
    with raises(ValueError, match="The group delay must be specified"):
        interpolate_spectrum(
            fd, "magnitude_linear", ("linear", "linear", "linear"))


@pytest.mark.parametrize(
    "method, freq_in, frequencies, n_samples, sampling_rate, freq_out",
    [
     ("complex", [1+2j, 2+1j], [1, 2], 12, 6,
      [0+3j, 0.5+2.5j, 1+2j, 1.5+1.5j, 2+1j, 2.5+0.5j, 3+0j]),

     ("magnitude_unwrap",
      # magnitude increases with 1 per Hz, phase with pi per Hz
      [np.linspace(1, 2, 3) * np.exp(-1j * np.linspace(np.pi, np.pi*2, 3))],
      [1, 1.5, 2], 24, 6,
      # freq_out be means of magnitude and unwrapped phase response
      [np.linspace(0, 3, 13), np.linspace(0, 3*np.pi, 13)]),

     ("magnitude_linear", [1, 2], [1, 2], 12, 6,
      # freq_out by means of magnitude and group delay)
      [[0, .5, 1, 1.5, 2, 2.5, 3], [0, 6, 6, 6, 6, 6, 6]]),

     ("magnitude_minimum", [1, 2], [1, 2], 12, 6,
      # freq_out by means of magnitude only. Minimum phase test signal is
      # generated from this inside the test
      [0, .5, 1, 1.5, 2, 2.5, 3]),
     ("magnitude", [1, 2], [1, 2], 12, 6,
      [0, .5, 1, 1.5, 2, 2.5, 3])
    ])
def test_interpolation(
        method, freq_in, frequencies, freq_out, n_samples, sampling_rate):
    """
    Test the if the interpolated spectrum matches the reference across methods.
    """

    # create test data
    data = pf.FrequencyData(freq_in, frequencies)
    interpolator = interpolate_spectrum(
        data, method, ("linear", "linear", "linear"), group_delay=6)
    signal = interpolator(n_samples, sampling_rate)

    # check output depending on method
    if method == "magnitude_unwrap":
        # test magnitude and unwrapped phase response
        npt.assert_allclose(np.abs(signal.freq), np.atleast_2d(freq_out[0]))
        npt.assert_allclose(pf.dsp.phase(signal, unwrap=True),
                            np.atleast_2d(freq_out[1]))
    elif method == "magnitude_linear":
        # test magnitude and group delay
        npt.assert_allclose(np.abs(signal.freq), np.atleast_2d(freq_out[0]))
        npt.assert_allclose(pf.dsp.group_delay(signal), freq_out[1])
    elif method == "magnitude_minimum":
        # test magnitude and minimum phase response
        npt.assert_allclose(np.abs(signal.freq), np.atleast_2d(freq_out))
        # generate reference minimum phase signal
        # signal_min = pf.Signal(freq_out, sampling_rate, n_samples, "freq")
        # signal_min = pf.dsp.minimum_phase(signal_min)
        # npt.assert_allclose(signal.freq, signal_min.freq)

    else:
        # test complex spectrum
        npt.assert_allclose(signal.freq, np.atleast_2d(freq_out))


def test_clip():
    """Test if clipping the magnitude data works."""

    data = pf.FrequencyData([1, 2], [1, 2])
    # interpolate with and without clipping
    interpolator = interpolate_spectrum(
        data, "magnitude", ("linear", "linear", "linear"))
    signal_no_clip = interpolator(6, 6)

    interpolator = interpolate_spectrum(
        data, "magnitude", ("linear", "linear", "linear"), clip=(1, 2))
    signal_clip = interpolator(6, 6)

    assert np.any(np.abs(signal_no_clip.freq) < 1) and \
           np.any(np.abs(signal_no_clip.freq) > 2)
    assert np.all(np.abs(signal_clip.freq) >= 1) and \
           np.all(np.abs(signal_clip.freq) <= 2)


def test_fscale():
    """
    Test frequency vectors for linear and logarithmic frequency interpolation.
    """

    # test parametres and data
    f_in_lin = [0, 10, 20]
    f_in_log = np.log([10, 10, 20])
    n_samples = 10
    sampling_rate = 40
    f_query_lin = pf.dsp.fft.rfftfreq(n_samples, sampling_rate)
    f_query_log = f_query_lin.copy()
    f_query_log[0] = f_query_log[1]
    f_query_log = np.log(f_query_log)
    data = pf.FrequencyData([1, 1, 1], f_in_lin)

    # generate interpolator with linear frequency
    interpolator_lin = interpolate_spectrum(
        data, "magnitude", ("linear", "linear", "linear"), fscale="linear")
    _ = interpolator_lin(n_samples, sampling_rate)
    # generate interpolator with logarithmic frequency
    interpolator_log = interpolate_spectrum(
        data, "magnitude", ("linear", "linear", "linear"), fscale="log")
    _ = interpolator_log(n_samples, sampling_rate)

    # test frequency vectors
    npt.assert_allclose(interpolator_lin._f_in, f_in_lin)
    npt.assert_allclose(interpolator_lin._f_query, f_query_lin)

    npt.assert_allclose(interpolator_log._f_in, f_in_log)
    npt.assert_allclose(interpolator_log._f_query, f_query_log)


def test_show():
    """Test plotting the results.

    This only tests if the code finishes without errors. Because the plot is
    an informal plot for inspection, we don't test specifics of the figure and
    axes for speed up the testing."""

    data = pf.FrequencyData([1, 2], [1, 2])
    interpolator = interpolate_spectrum(
        data, "magnitude", ("linear", "linear", "linear"))
    _ = interpolator(10, 10, show=True)

    plt.close()
