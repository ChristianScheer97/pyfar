import numpy as np
from scipy import signal as sgn
from pyfar import Signal
import pyfar.fft as fft


def phase(signal, deg=False, unwrap=False):
    """Returns the phase for a given signal object.

    Parameters
    ----------
    signal : Signal object
        An audio signal object from the pyfar signal class
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

    if not isinstance(signal, Signal):
        raise TypeError('Input data has to be of type: Signal.')

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


def group_delay(signal, frequencies=None):
    """Returns the group delay of a signal in samples.

    Parameters
    ----------
    signal : Signal object
        An audio signal object from the pyfar signal class
    frequencies : number array like
        Frequency or frequencies in Hz at which the group delay is calculated.
        The default is None, in which case signal.frequencies is used.

    Returns
    -------
    group_delay : numpy array
        Frequency dependent group delay in samples. The array is flattened if
        a single channel signal was passed to the function.
    """

    # check input and default values
    if not isinstance(signal, Signal):
        raise TypeError('Input data has to be of type: Signal.')

    frequencies = signal.frequencies if frequencies is None \
        else np.asarray(frequencies)

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
        Falg to plot the logarithmic magnitude specturm. The default is True.
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
    if not isinstance(signal, Signal):
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


def windows(signal, window_function='hann', times=None,
            window_shape='symmetric', unit='samples', **kwargs):
    """Returns a windowed pyfar signal with selected window_function.

    Parameters
    ----------
    signal : Signal object
        An audio signal object from the pyfar signal class

    window_function: string
        select window type from 'rect', 'hann', 'hamming', 'blackman',
        'bartlett', 'kaiser', 'kaiserBessel' , 'flattop' or 'dolphChebychev'

    times: int
        sets window length in unit('samples') of selected window

    window_shape: string
        'symmetric' (default), 'left', 'right'

    Returns
    -------
    out : pyfar
        window coefficients
    """

    # check input and default values
    if not isinstance(signal, Signal):
        raise TypeError('Input data has to be of type: Signal.')

    if not isinstance(times, int):
        raise TypeError('times has to be of type int.')

    window_shape_list = ['symmteric', 'left', 'right']
    if window_shape not in window_shape_list:
        raise ValueError(f"window_shape is {window_shape} but has to be"
                         f" one of the following:"
                         f" {', '.join(list(window_shape_list))}.")

    if not isinstance(unit, str):
        raise TypeError('''window_shape has to be a sting of the following:
                        'samples', 's','ms','mus'.''')
    # copy signal object
    signal_copy = signal.copy()

    if times is None:
        times_left = 0
        times_right = signal_copy.n_samples
    elif len(times) = 2:
        times_left = times(1)
        times_right = times(2)

    # copy signal object
    signal_copy = signal.copy()
    # create selected window with simulated switch case
    switcher_window = {
        'rect': sgn.windows.boxcar,
        'hann': sgn.windows.hann,
        'hamming': sgn.windows.hamming,
        'blackman': sgn.windows.blackman,
        'bartlett': sgn.windows.bartlett,
        'kaiser': sgn.windows.kaiser,
        'flattop': sgn.windows.flattop,
        'chebwin': sgn.windows.chebwin,
    }
    if window_function in switcher_window:
        win = switcher_window[window_function](times, **kwargs)
    else:
        raise ValueError(f"window_function is {window_function} but has to be"
                         f" one of the following:"
                         f" {', '.join(list(switcher_window))}.")

    # apply windowing to time domain copy of signal
    # if times > np.size(signal_copy.time[..., :]):
    #     ValueError('>>>>>>> window is longer than signal!')

    # create zeropadded window with shape of signal
    windowShape = np.zeros(np.size(signalCopyFlat.time[0]))

    # check if window is not being set within signal bounds
    if windowStartIndex+np.size(win) <= np.size(windowShape):
        windowShape[windowStartIndex:windowStartIndex+np.size(win)] = win
    elif windowStartIndex+np.size(win)-np.size(windowShape) >= np.size(win)-1:
        # return not windowed signal with warning
        signalCopy = signalCopyFlat.reshape(signal.cshape)
        print('>>>>>>> No windowing applied!')
        return signalCopy
    else:
        # apply window only partially if windowStartIndex set, so that the
        # window doesn't fit at the end
        win = win[:-(windowStartIndex+np.size(win)-np.size(windowShape))]
        windowShape[windowStartIndex:windowStartIndex+np.size(win)] = win

    # apply window
    signalCopyFlat.time = signalCopyFlat.time * windowShape
    signalCopy = signalCopyFlat.reshape(signal.cshape)

    return signalCopy
