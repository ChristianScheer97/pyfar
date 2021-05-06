import numpy as np
import numpy.testing as npt
import pytest
import pyfar

from pyfar import dsp


def test_phase_rad(sine_plus_impulse):
    """Test the function returning the phase of a signal in radians."""
    phase = dsp.phase(sine_plus_impulse, deg=False, unwrap=False)
    truth = np.angle(sine_plus_impulse.freq)
    npt.assert_allclose(phase, truth, rtol=1e-10)


def test_phase_deg(sine_plus_impulse):
    """Test the function returning the phase of a signal in degrees."""
    phase = dsp.phase(sine_plus_impulse, deg=True, unwrap=False)
    truth = np.degrees(np.angle(sine_plus_impulse.freq))
    npt.assert_allclose(phase, truth, rtol=1e-10)


def test_phase_unwrap(sine_plus_impulse):
    """Test the function returning the unwrapped phase of a signal."""
    phase = dsp.phase(sine_plus_impulse, deg=False, unwrap=True)
    truth = np.unwrap(np.angle(sine_plus_impulse.freq))
    npt.assert_allclose(phase, truth, rtol=1e-10)


def test_phase_deg_unwrap(sine_plus_impulse):
    """Test the function returning the unwrapped phase of a signal in deg."""
    phase = dsp.phase(sine_plus_impulse, deg=True, unwrap=True)
    truth = np.degrees(np.unwrap(np.angle(sine_plus_impulse.freq)))
    npt.assert_allclose(phase, truth, rtol=1e-10)


def test_group_delay_single_channel(impulse_group_delay):
    """Test the function returning the group delay of a signal,
    single channel."""
    signal = impulse_group_delay[0]

    with pytest.raises(ValueError, match="Invalid method"):
        dsp.group_delay(signal, method='invalid')

    with pytest.raises(ValueError, match="not supported"):
        dsp.group_delay(signal, method='fft', frequencies=[1, 2, 3])

    grp = dsp.group_delay(signal, method='scipy')
    assert grp.shape == (signal.n_bins, )
    npt.assert_allclose(grp, impulse_group_delay[1].flatten(), rtol=1e-10)

    grp = dsp.group_delay(signal, method='fft')
    assert grp.shape == (signal.n_bins, )
    npt.assert_allclose(grp, impulse_group_delay[1].flatten(), rtol=1e-10)

    grp = dsp.group_delay(
        signal, method='fft')
    assert grp.shape == (signal.n_bins, )
    npt.assert_allclose(grp, impulse_group_delay[1].flatten(), rtol=1e-10)


def test_group_delay_two_channel(impulse_group_delay_two_channel):
    """Test the function returning the group delay of a signal,
    two channels."""
    signal = impulse_group_delay_two_channel[0]
    grp = dsp.group_delay(signal, method='scipy')
    assert grp.shape == (signal.cshape + (signal.n_bins,))
    npt.assert_allclose(grp, impulse_group_delay_two_channel[1], rtol=1e-10)

    grp = dsp.group_delay(signal, method='fft')
    assert grp.shape == (signal.cshape + (signal.n_bins,))
    npt.assert_allclose(grp, impulse_group_delay_two_channel[1], rtol=1e-10)


def test_group_delay_two_by_two_channel(
        impulse_group_delay_two_by_two_channel):
    """Test the function returning the group delay of a signal,
    2-by-2 channels."""
    signal = impulse_group_delay_two_by_two_channel[0]
    grp = dsp.group_delay(signal)
    assert grp.shape == (signal.cshape + (signal.n_bins,))
    npt.assert_allclose(
        grp, impulse_group_delay_two_by_two_channel[1], rtol=1e-10)


def test_group_delay_custom_frequencies(impulse_group_delay):
    """Test the function returning the group delay of a signal,
    called for specific frequencies."""
    signal = impulse_group_delay[0]
    # Single frequency, of type int
    frequency = 1000
    frequency_idx = np.abs(signal.frequencies-frequency).argmin()
    grp = dsp.group_delay(signal, frequency, method='scipy')
    assert grp.shape == ()
    npt.assert_allclose(grp, impulse_group_delay[1][0, frequency_idx])

    # Multiple frequencies
    frequency = np.array([1000, 2000])
    frequency_idx = np.abs(
        signal.frequencies-frequency[..., np.newaxis]).argmin(axis=-1)
    grp = dsp.group_delay(signal, frequency, method='scipy')
    assert grp.shape == (2,)
    npt.assert_allclose(grp, impulse_group_delay[1][0, frequency_idx])


def test_xfade(impulse):
    first = np.ones(5001)
    idx_1 = 500
    second = np.ones(5001)*2
    idx_2 = 1000

    res = dsp.dsp._cross_fade(first, second, [idx_1, idx_2])
    np.testing.assert_array_almost_equal(first[:idx_1], res[:idx_1])
    np.testing.assert_array_almost_equal(second[idx_2:], res[idx_2:])

    idx_1 = 501
    idx_2 = 1000
    res = dsp.dsp._cross_fade(first, second, [idx_1, idx_2])
    np.testing.assert_array_almost_equal(first[:idx_1], res[:idx_1])
    np.testing.assert_array_almost_equal(second[idx_2:], res[idx_2:])


def test_regu_inversion(impulse):

    with pytest.raises(
            ValueError, match='needs to be of type pyfar.Signal'):
        dsp.regularized_spectrum_inversion('error', (1, 2))

    with pytest.raises(
            ValueError, match='lower and upper limits'):
        dsp.regularized_spectrum_inversion(impulse, (2))

    res = dsp.regularized_spectrum_inversion(impulse * 2, [200, 10e3])

    ind = impulse.find_nearest_frequency([200, 10e3])
    npt.assert_allclose(
        res.freq[:, ind[0]:ind[1]],
        np.ones((1, ind[1]-ind[0]), dtype=complex)*0.5)

    npt.assert_allclose(res.freq[:, 0], [0.25])
    npt.assert_allclose(res.freq[:, -1], [0.25])


def test_windowing_default():
    "Test windowing function with default values."
    pass


def test_windowing_input():
    sig = pyfar.Signal(np.ones(5), 2)
    with pytest.raises(TypeError, match='signal'):
        dsp.windowing([1., 2.])
    with pytest.raises(ValueError, match='shape'):
        dsp.windowing(sig, shape='top')
    with pytest.raises(TypeError, match='truncate'):
        dsp.windowing(sig, truncate='t')
    with pytest.raises(ValueError, match='unit'):
        dsp.windowing(sig, length=[0, 1], unit='kg')
    with pytest.raises(TypeError, match='length'):
        dsp.windowing(sig, length=1)


def test_windowing_length_order_error():
    sig = pyfar.Signal(np.ones(10), 2)
    with pytest.raises(ValueError, match='ascending'):
        dsp.windowing(sig, length=[2, 1])
    with pytest.raises(ValueError, match='ascending'):
        dsp.windowing(sig, length=[1, 2, 3, 0])


def test_windowing_length_unit_error():
    sig = pyfar.Signal(np.ones(10), 2)
    with pytest.raises(ValueError, match='than signal'):
        dsp.windowing(sig, length=[0, 11], unit='samples')
    with pytest.raises(ValueError, match='than signal'):
        dsp.windowing(sig, length=[0, 6], unit='s')
    with pytest.raises(ValueError, match='than signal'):
        dsp.windowing(sig, length=[0, 6e3], unit='ms')


def test_windowing_truncate():
    sig = pyfar.Signal(np.ones(10), 2)
    sig_win = dsp.windowing(sig, length=[1, 3], truncate=False)
    assert sig_win.n_samples == 10
    sig_win = dsp.windowing(
        sig, length=[1, 3], shape='symmetric', unit='samples', truncate=True)
    assert sig_win.n_samples == 3
    sig_win = dsp.windowing(
        sig, length=[0.5, 1.5], shape='symmetric', unit='s', truncate=True)
    assert sig_win.n_samples == 3
    sig_win = dsp.windowing(
        sig, length=[500, 1500], shape='symmetric', unit='ms', truncate=True)
    assert sig_win.n_samples == 3
    sig_win = dsp.windowing(sig, length=[1, 3], shape='left', truncate=True)
    assert sig_win.n_samples == 9
    sig_win = dsp.windowing(sig, length=[1, 3], shape='right', truncate=True)
    assert sig_win.n_samples == 4


def test_windowing_single_sided():
    sig = pyfar.Signal(np.ones(7), 1)
    # Fade in, odd number of samples
    sig_win = dsp.windowing(
        sig, window='triang', length=[2, 4], shape='left', truncate=False)
    time_win = np.array([[0, 0, 0.25, 0.75, 1, 1, 1]])
    npt.assert_allclose(sig_win.time, time_win)
    # Fade in, even number of samples
    sig_win = dsp.windowing(
        sig, window='triang', length=[2, 5], shape='left', truncate=False)
    time_win = np.array([[0, 0, 1/6, 3/6, 5/6, 1, 1]])
    npt.assert_allclose(sig_win.time, time_win)
    # Fade out, odd number of samples
    sig_win = dsp.windowing(
        sig, window='triang', length=[2, 4], shape='right', truncate=False)
    time_win = np.array([[1, 1, 1, 0.75, 0.25, 0, 0]])
    npt.assert_allclose(sig_win.time, time_win)
    # Fade out, even number of samples
    sig_win = dsp.windowing(
        sig, window='triang', length=[2, 5], shape='right', truncate=False)
    time_win = np.array([[1, 1, 1, 5/6, 3/6, 1/6, 0]])
    npt.assert_allclose(sig_win.time, time_win)


def test_windowing_length_4():
    sig = pyfar.Signal(np.ones(9), 1)
    sig_win = dsp.windowing(
        sig, window='triang', length=[1, 3, 6, 7], unit='samples',
        truncate=False)
    time_win = np.array([[0, 0.25, 0.75, 1, 1, 1, 1, 0.5, 0]])
    npt.assert_allclose(sig_win.time, time_win)
    sig = pyfar.Signal(np.ones(10), 1)
    sig_win = dsp.windowing(
        sig, window='triang', length=[1, 3, 6, 7], unit='samples',
        truncate=False)
    time_win = np.array([[0, 0.25, 0.75, 1, 1, 1, 1, 0.5, 0, 0]])
    npt.assert_allclose(sig_win.time, time_win)


def test_windowing_multichannel():
    time = np.array(
        [[[1, 1, 1, 1], [2, 2, 2, 2]], [[3, 3, 3, 3], [4, 4, 4, 4]]])
    sig = pyfar.Signal(time, 1)
    sig_win = dsp.windowing(sig, window='triang', length=[1, 2], truncate=True)
    time_win = np.array(
        [[[1, 1], [2, 2]], [[3, 3], [4, 4]]])
    npt.assert_allclose(sig_win.time, time_win)
