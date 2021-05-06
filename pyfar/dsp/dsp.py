import numpy as np
from scipy import signal as sgn
import pyfar
from pyfar.dsp import fft


def phase(signal, deg=False, unwrap=False):
    """Returns the phase for a given signal object.

    Parameters
    ----------
    signal : Signal, FrequencyData
        pyfar Signal or FrequencyData object.
    deg : Boolean
        Specifies, whether the phase is returned in degrees or radians.
    unwrap : Boolean
        Specifies, whether the phase is unwrapped or not.
        If set to "360", the phase is wrapped to 2 pi.

    Returns
    -------
    phase : np.array()
        Phase.
    """

    if not isinstance(signal, pyfar.Signal) and \
            not isinstance(signal, pyfar.FrequencyData):
        raise TypeError(
            'Input data has to be of type: Signal or FrequencyData.')

    phase = np.angle(signal.freq)

    if np.isnan(phase).any() or np.isinf(phase).any():
        raise ValueError('Your signal has a point with NaN or Inf phase.')

    if unwrap is True:
        phase = np.unwrap(phase)
    elif unwrap == '360':
        phase = wrap_to_2pi(np.unwrap(phase))

    if deg:
        phase = np.degrees(phase)
    return phase


def group_delay(signal, frequencies=None, method='fft'):
    """Returns the group delay of a signal in samples.

    Parameters
    ----------
    signal : Signal object
        An audio signal object from the pyfar signal class
    frequencies : number array like
        Frequency or frequencies in Hz at which the group delay is calculated.
        The default is None, in which case signal.frequencies is used.
    method : 'scipy', 'fft', optional
        Method to calculate the group delay of a Signal. Both methods calculate
        the group delay using the method presented in [#]_ avoiding issues
        due to discontinuities in the unwrapped phase. Note that the scipy
        version additionally allows to specify frequencies for which the
        group delay is evaluated. The default is 'fft', which is faster.

    Returns
    -------
    group_delay : numpy array
        Frequency dependent group delay in samples. The array is flattened if
        a single channel signal was passed to the function.

    References
    ----------
    .. [#]  https://www.dsprelated.com/showarticle/69.php
    """

    # check input and default values
    if not isinstance(signal, pyfar.Signal):
        raise TypeError('Input data has to be of type: Signal.')

    if frequencies is not None and method == 'fft':
        raise ValueError(
            "Specifying frequencies is not supported for the 'fft' method.")

    frequencies = signal.frequencies if frequencies is None \
        else np.asarray(frequencies, dtype=float)

    if method == 'scipy':
        # get time signal and reshape for easy looping
        time = signal.time
        time = time.reshape((-1, signal.n_samples))

        # initialize group delay
        group_delay = np.zeros((np.prod(signal.cshape), frequencies.size))

        # calculate the group delay
        for cc in range(time.shape[0]):
            group_delay[cc] = sgn.group_delay(
                (time[cc], 1), frequencies, fs=signal.sampling_rate)[1]

        # reshape to match signal
        group_delay = group_delay.reshape(signal.cshape + (-1, ))

    elif method == 'fft':
        freq_k = fft.rfft(signal.time * np.arange(signal.n_samples),
                          signal.n_samples, signal.sampling_rate,
                          fft_norm='none')

        freq = fft.normalization(
            signal.freq, signal.n_samples, signal.sampling_rate,
            signal.fft_norm, inverse=True)

        group_delay = np.real(freq_k / freq)

        # catch zeros in the denominator
        group_delay[np.abs(freq) < 1e-15] = 0

    else:
        raise ValueError(
            "Invalid method, needs to be either 'scipy' or 'fft'.")

    # flatten in numpy fashion if a single channel is returned
    if signal.cshape == (1, ):
        group_delay = np.squeeze(group_delay)

    return group_delay


def wrap_to_2pi(x):
    """Wraps phase to 2 pi.

    Parameters
    ----------
    x : double
        Input phase to be wrapped to 2 pi.

    Returns
    -------
    x : double
        Phase wrapped to 2 pi.
    """
    positive_input = (x > 0)
    zero_check = np.logical_and(positive_input, (x == 0))
    x = np.mod(x, 2*np.pi)
    x[zero_check] = 2*np.pi
    return x


def nextpow2(x):
    """Returns the exponent of next higher power of 2.

    Parameters
    ----------
    x : double
        Input variable to determine the exponent of next higher power of 2.

    Returns
    -------
    nextpow2 : double
        Exponent of next higher power of 2.
    """
    return np.ceil(np.log2(x))


def spectrogram(signal, dB=True, log_prefix=20, log_reference=1,
                window='hann', window_length=1024, window_overlap_fct=0.5):
    """Compute the magnitude spectrum versus time.

    This is a wrapper for scipy.signal.spectogram with two differences. First,
    the returned times refer to the start of the FFT blocks, i.e., the first
    time is always 0 whereas it is window_length/2 in scipy. Second, the
    returned spectrogram is normalized accroding to `signal.signal_type` and
    `signal.fft_norm`.

    Parameters
    ----------
    signal : Signal
        pyfar Signal object.
    db : Boolean
        False to plot the logarithmic magnitude spectrum. The default is True.
    log_prefix : integer, float
        Prefix for calculating the logarithmic time data. The default is 20.
    log_reference : integer
        Reference for calculating the logarithmic time data. The default is 1.
    window : str
        Specifies the window (See scipy.signal.get_window). The default is
        'hann'.
    window_length : integer
        Specifies the window length in samples. The default ist 1024.
    window_overlap_fct : double
        Ratio of points to overlap between fft segments [0...1]. The default is
        0.5

    Returns
    -------
    frequencies : numpy array
        Frequencies in Hz at which the magnitude spectrum was computed
    times : numpy array
        Times in seconds at which the magnitude spectrum was computed
    spectrogram : numpy array
    """

    # check input
    if not isinstance(signal, pyfar.Signal):
        raise TypeError('Input data has to be of type: Signal.')

    if window_length > signal.n_samples:
        raise ValueError("window_length exceeds signal length")

    # get spectrogram from scipy.signal
    window_overlap = int(window_length * window_overlap_fct)
    window = sgn.get_window(window, window_length)

    frequencies, times, spectrogram = sgn.spectrogram(
        x=signal.time.squeeze(), fs=signal.sampling_rate, window=window,
        noverlap=window_overlap, mode='magnitude', scaling='spectrum')

    # remove normalization from scipy.signal.spectrogram
    spectrogram /= np.sqrt(1 / window.sum()**2)

    # apply normalization from signal
    spectrogram = fft.normalization(
        spectrogram, window_length, signal.sampling_rate,
        signal.fft_norm, window=window)

    # scipy.signal takes the center of the DFT blocks as time stamp we take the
    # beginning (looks nicer in plots, both conventions are used)
    times -= times[0]

    return frequencies, times, spectrogram


def windowing(signal, window='hann', length=None, shape='symmetric',
              unit='samples', truncate=True):
    """Apply time window to signal.

    This function uses the windows implemented in ``scipy.signal.windows``.

    Parameters
    ----------
    signal : Signal
        pyfar Signal object to be windowed
    window: string, float, or tuple
        The type of window to create. See below for more details.
        The default is ``hann``.
    length: list of int or None
        If length has two entries, these specify the beginning and the end of
        the window or the fade-in / fade-out (see parameter `shape`).
        If length has four entries, a symmetric window with fade-in between
        the first two entries and a fade-out between the last two is created,
        while it is constant in between.
        If ``None``, a symmetric window is applied to the overall length of
        the signal and `shape` and `unit` are ignored.
        The unit of `length` is specified by the parameter `unit`.
    shape: string
        ``symmetric``, ``left`` or ``right``.
        Specifies, if the window is applied single sided or symmetrically.
        If ``left`` or ``right``, the beginning and the end of the fade is
        defined by the two values in `length`. The default is ``symmetric``.
    unit: string
        Unit of the parameter `length`. Can be set to ``s`` (seconds), ``ms``
        (milliseconds) or ``samples``. If ``samples``, the values in length
        denote the first and last sample being included. Time values are
        rounded to the nearest sample. The default is ``samples``.
    truncate: bool
        If ``True``, the signal is truncated to the length of the window.
        The default is ``False``.

    Returns
    -------
    signal_windowed : Signal
        Windowed signal object

    Notes
    -----
    This function calls `~scipy.signal.windows.get_window` to create the
    window.
    Window types:
    - ``scipy.signal.windows.boxcar``
    - ``scipy.signal.windows.triang``
    - ``scipy.signal.windows.blackman``
    - ``scipy.signal.windows.hamming``
    - ``scipy.signal.windows.hann``
    - ``scipy.signal.windows.bartlett``
    - ``scipy.signal.windows.flattop``
    - ``scipy.signal.windows.parzen``
    - ``scipy.signal.windows.bohman``
    - ``scipy.signal.windows.blackmanharris``
    - ``scipy.signal.windows.nuttall``
    - ``scipy.signal.windows.barthann``
    - ``scipy.signal.windows.kaiser`` (needs beta)
    - ``scipy.signal.windows.gaussian`` (needs standard deviation)
    - ``scipy.signal.windows.general_gaussian`` (needs power, width)
    - ``scipy.signal.windows.dpss`` (needs normalized half-bandwidth)
    - ``scipy.signal.windows.chebwin`` (needs attenuation)
    - ``scipy.signal.windows.exponential`` (needs center, decay scale)
    - ``scipy.signal.windows.tukey`` (needs taper fraction)
    - ``scipy.signal.windows.taylor`` (needs number of constant sidelobes,
      sidelobe level)
    If the window requires no parameters, then `window` can be a string.
    If the window requires parameters, then `window` must be a tuple
    with the first argument the string name of the window, and the next
    arguments the needed parameters.
    If `window` is a floating point number, it is interpreted as the beta
    parameter of the `~scipy.signal.windows.kaiser` window.
    """
    # Check input
    if not isinstance(signal, pyfar.Signal):
        raise TypeError("The parameter signal has to be of type: Signal.")
    if shape not in ('symmetric', 'left', 'right'):
        raise ValueError(
            "The parameter shape has to be 'symmetric', 'left' or 'right'.")
    if not isinstance(truncate, bool):
        raise TypeError("The parameter truncate has to be of type: bool.")
    if not isinstance(length, (list, type(None))):
        raise TypeError(
            "The parameter length has to be of type list or None.")

    if length is None:
        length = [0, signal.n_samples]
        unit = 'samples'
    if length != sorted(length):
        raise ValueError("Values in length need to be in ascending order.")

    # Convert length to samples
    if unit == 's':
        length = [round(li*signal.sampling_rate) for li in length]
    elif unit == 'ms':
        length = [round(li*signal.sampling_rate/1e3) for li in length]
    elif unit != 'samples':
        raise ValueError(f"unit is {unit} but has to be"
                         f" 'samples', 's' or 'ms'.")
    # Check window size
    if length[-1] > signal.n_samples:
        raise ValueError(
            "Values in length require window to be longer than signal.")

    # Create window
    if length is None:
        win_samples = signal.n_samples
        win = sgn.windows.get_window(window, win_samples, fftbins=False)
        win_start = 0
        win_stop = signal.n_samples-1
    elif len(length) == 2:
        if shape == 'symmetric':
            win_samples = length[1]-length[0]+1
            win = sgn.windows.get_window(window, win_samples, fftbins=False)
            win_start = length[0]
            win_stop = length[1]
        else:
            fade_samples = int(2*(length[1]-length[0]))
            fade = sgn.windows.get_window(window, fade_samples, fftbins=False)
            if shape == 'left':
                win = np.ones(signal.n_samples-length[0])
                win[0:length[1]-length[0]] = fade[:int(fade_samples/2)]
                win_start = length[0]
                win_stop = signal.n_samples-1
            if shape == 'right':
                win = np.ones(length[1]+1)
                win[length[0]+1:] = fade[int(fade_samples/2):]
                win_start = 0
                win_stop = length[1]
    elif len(length) == 4:
        fade_in_samples = int(2*(length[1]-length[0]))
        fade_in = sgn.windows.get_window(
            window, fade_in_samples, fftbins=False)
        fade_in = fade_in[:int(fade_in_samples/2)]
        fade_out_samples = int(2*(length[3]-length[2]))
        fade_out = sgn.windows.get_window(
            window, fade_out_samples, fftbins=False)
        fade_out = fade_out[int(fade_out_samples/2):]
        win = np.ones(length[-1]-length[0]+1)
        win[0:length[1]-length[0]] = fade_in
        win[length[2]-length[0]+1:length[3]-length[0]+1] = fade_out
        win_start = length[0]
        win_stop = length[3]

    # Apply window
    signal_win = signal.copy()
    if truncate:
        signal_win.time = signal_win[..., win_start:win_stop+1].time*win
    else:
        # create zeropadded window with shape of signal
        window_zeropadded = np.zeros(signal.n_samples)
        window_zeropadded[win_start:win_stop+1] = win
        signal_win.time = signal_win.time*window_zeropadded

    return signal_win


def regularized_spectrum_inversion(
        signal, freq_range,
        regu_outside=1., regu_inside=10**(-200/20), regu_final=None):
    r"""Invert the spectrum of a signal applying frequency dependent
    regularization. Regularization can either be specified within a given
    frequency range using two different regularization factors, or for each
    frequency individually using the parameter `regu_final`. In the first case
    the regularization factors for the frequency regions are cross-faded using
    a raised cosine window function with a width of `math:f*\sqrt(2)` above and
    below the given frequency range. Note that the resulting regularization
    function is adjusted to the quadratic maximum of the given signal.
    In case the `regu_final` parameter is used, all remaining options are
    ignored and an array matching the number of frequency bins of the signal
    needs to be given. In this case, no normalization of the regularization
    function is applied. Finally, the inverse spectrum is calculated as
    [#]_, [#]_,

    .. math::

        S^{-1}(f) = \frac{S^*(f)}{S^*(f)S(f) + \epsilon(f)}


    Parameters
    ----------
    signal : pyfar.Signal
        The signals which spectra are to be inverted.
    freq_range : tuple, array_like, double
        The upper and lower frequency limits outside of which the
        regularization factor is to be applied.
    regu_outside : float, optional
        The normalized regularization factor outside the frequency range.
        The default is 1.
    regu_inside : float, optional
        The normalized regularization factor inside the frequency range.
        The default is 10**(-200/20).
    regu_final : float, array_like, optional
        The final regularization factor for each frequency, by default None.
        If this parameter is set, the remaining regularization factors are
        ignored.

    Returns
    -------
    pyfar.Signal
        The resulting signal after inversion.

    References
    ----------
    .. [#]  O. Kirkeby and P. A. Nelson, “Digital Filter Designfor Inversion
            Problems in Sound Reproduction,” J. Audio Eng. Soc., vol. 47,
            no. 7, p. 13, 1999.

    .. [#]  P. C. Hansen, Rank-deficient and discrete ill-posed problems:
            numerical aspects of linear inversion. Philadelphia: SIAM, 1998.

    """
    if not isinstance(signal, pyfar.Signal):
        raise ValueError("The input signal needs to be of type pyfar.Signal.")

    data = signal.freq
    freq_range = np.asarray(freq_range)

    if freq_range.size < 2:
        raise ValueError(
            "The frequency range needs to specify lower and upper limits.")

    if regu_final is None:
        regu_inside = np.ones(signal.n_bins, dtype=np.double) * regu_inside
        regu_outside = np.ones(signal.n_bins, dtype=np.double) * regu_outside

        idx_xfade_lower = signal.find_nearest_frequency(
            [freq_range[0]/np.sqrt(2), freq_range[0]])

        regu_final = _cross_fade(regu_outside, regu_inside, idx_xfade_lower)

        if freq_range[1] < signal.sampling_rate/2:
            idx_xfade_upper = signal.find_nearest_frequency([
                freq_range[1],
                np.min([freq_range[1]*np.sqrt(2), signal.sampling_rate/2])])

            regu_final = _cross_fade(regu_final, regu_outside, idx_xfade_upper)

        regu_final *= np.max(np.abs(data)**2)

    inverse = signal.copy()
    inverse.freq = np.conj(data) / (np.conj(data)*data + regu_final)

    return inverse


def _cross_fade(first, second, indices):
    """Cross-fade two numpy arrays by multiplication with a raised cosine
    window inside the range specified by the indices. Outside the range, the
    result will be the respective first or second array, without distortions.

    Parameters
    ----------
    first : array, double
        The first array.
    second : array, double
        The second array.
    indices : array-like, tuple, int
        The lower and upper cross-fade indices.

    Returns
    -------
    result : array, double
        The resulting array after cross-fading.
    """
    indices = np.asarray(indices)
    if np.shape(first)[-1] != np.shape(second)[-1]:
        raise ValueError("Both arrays need to be of same length.")
    len_arrays = np.shape(first)[-1]
    if np.any(indices > np.shape(first)[-1]):
        raise IndexError("Index is out of range.")

    len_xfade = np.squeeze(np.abs(np.diff(indices)))
    window = sgn.windows.windows.hann(len_xfade*2 + 1, sym=True)
    window_rising = window[:len_xfade]
    window_falling = window[len_xfade+1:]

    window_first = np.concatenate(
        (np.ones(indices[0]), window_falling, np.zeros(len_arrays-indices[1])))
    window_second = np.concatenate(
        (np.zeros(indices[0]), window_rising, np.ones(len_arrays-indices[1])))

    result = first * window_first + second * window_second

    return result
