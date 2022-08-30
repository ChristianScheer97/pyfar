"""
Read and write objects to disk, read and write audio files, read SOFA files.

The functions :py:func:`read` and :py:func:`write` allow to save or load
several pyfar objects and other variables. So, e.g., workspaces in notebooks
can be stored. :py:class:`Signal <pyfar.signal.Signal>` objects can be
imported and exported as WAV files using :py:func:`read_wav` and
:py:func:`write_wav`. :py:func:`read_sofa` provides functionality to read the
data stored in a SOFA file.
"""
import os.path
import pathlib

import warnings
import sofar as sf
import zipfile
import io
import soundfile
import tempfile
import numpy as np
import re

import pyfar
from pyfar import Signal, FrequencyData, Coordinates
from . import _codec as codec
import pyfar.classes.filter as fo


def read_sofa(filename, verify=True):
    """
    Import a SOFA file as pyfar object.

    Parameters
    ----------
    filename : string, Path
        Input SOFA file (cf. [#]_, [#]_).
    verify : bool, optional
        Verify if the data contained in the SOFA file agrees with the AES69
        standard (see references). If the verification fails, the SOFA file
        can be loaded by setting ``verify=False``. The default is ``True``

    Returns
    -------
    audio : pyfar audio object
        The audio object that is returned depends on the DataType of the SOFA
        object:

        - :py:class:`~pyfar.classes.audio.Signal`
            A Signal object is returned is the DataType is ``'FIR'``,
            ``'FIR-E'``, or ``'FIRE'``.
        - :py:class:`~pyfar.classes.audio.FrequencyData`
            A FrequencyData object is returned is the DataType is ``'TF'``,
            ``'TF-E'``, or ``'TFE'``.

        The `cshape` of the object is is ``(M, R)`` with `M` being the number
        of measurements and `R` being the number of receivers from the SOFA
        file.
    source_coordinates : Coordinates
        Coordinates object containing the data stored in
        `SOFA_object.SourcePosition`. The domain, convention and unit are
        automatically matched.
    receiver_coordinates : Coordinates
        Coordinates object containing the data stored in
        `SOFA_object.RecevierPosition`. The domain, convention and unit are
        automatically matched.

    Notes
    -----
    * This function uses the sofar package to read SOFA files [#]_.

    References
    ----------
    .. [#] https://www.sofaconventions.org
    .. [#] “AES69-2020: AES Standard for File Exchange-Spatial Acoustic Data
        File Format.”, 2020.
    .. [#] https://pyfar.org

    """

    sofa = sf.read_sofa(filename, verify)
    return convert_sofa(sofa)


def convert_sofa(sofa):
    """
    Convert SOFA object to pyfar object.

    Parameters
    ----------
    sofa : SOFA object
        A SOFA object read or generated by the sofar package ([#]_).

    Returns
    -------
    audio : pyfar audio object
        The audio object that is returned depends on the DataType of the SOFA
        object:

        - :py:class:`~pyfar.classes.audio.Signal`
            A Signal object is returned is the DataType is ``'FIR'``,
            ``'FIR-E'``, or ``'FIRE'``.
        - :py:class:`~pyfar.classes.audio.FrequencyData`
            A FrequencyData object is returned is the DataType is ``'TF'``,
            ``'TF-E'``, or ``'TFE'``.

        The `cshape` of the object is is ``(M, R)`` with `M` being the number
        of measurements and `R` being the number of receivers from the SOFA
        file.
    source_coordinates : Coordinates
        Coordinates object containing the data stored in
        `SOFA_object.SourcePosition`. The domain, convention and unit are
        automatically matched.
    receiver_coordinates : Coordinates
        Coordinates object containing the data stored in
        `SOFA_object.RecevierPosition`. The domain, convention and unit are
        automatically matched.

    References
    ----------
    .. [#] https://pyfar.org
    """

    # check input
    if not isinstance(sofa, sf.Sofa):
        raise TypeError((
            "Input must be a sofar.Sofa object "
            f"but is of type {str(type(sofa))}"))

    # Check for DataType
    if sofa.GLOBAL_DataType in ['FIR', 'FIR-E', 'FIRE']:
        # make a Signal
        signal = Signal(sofa.Data_IR, sofa.Data_SamplingRate)

    elif sofa.GLOBAL_DataType in ['TF', 'TF-E', 'TFE']:
        # make FrequencyData
        signal = FrequencyData(
            sofa.Data_Real + 1j * sofa.Data_Imag, sofa.N)
    else:
        raise ValueError(
            "DataType {sofa.GLOBAL_DataType} is not supported.")

    # Source
    s_values = sofa.SourcePosition
    s_domain, s_convention, s_unit = _sofa_pos(sofa.SourcePosition_Type)
    source_coordinates = Coordinates(
        s_values[:, 0],
        s_values[:, 1],
        s_values[:, 2],
        domain=s_domain,
        convention=s_convention,
        unit=s_unit)
    # Receiver
    r_values = sofa.ReceiverPosition
    r_domain, r_convention, r_unit = _sofa_pos(sofa.ReceiverPosition_Type)
    receiver_coordinates = Coordinates(
        r_values[:, 0],
        r_values[:, 1],
        r_values[:, 2],
        domain=r_domain,
        convention=r_convention,
        unit=r_unit)

    return signal, source_coordinates, receiver_coordinates


def _sofa_pos(pos_type):
    if pos_type == 'spherical':
        domain = 'sph'
        convention = 'top_elev'
        unit = 'deg'
    elif pos_type == 'cartesian':
        domain = 'cart'
        convention = 'right'
        unit = 'met'
    else:
        raise ValueError("Position:Type {pos_type} is not supported.")
    return domain, convention, unit


def read(filename):
    """
    Read any compatible pyfar object or numpy array (.far file) from disk.

    Parameters
    ----------
    filename : string, Path
        Input file. If no extension is provided, .far-suffix is added.

    Returns
    -------
    collection: dict
        Contains pyfar objects like
        ``{ 'name1': 'obj1', 'name2': 'obj2' ... }``.

    Examples
    --------
    Read signal and orientations objects stored in a .far file.

    >>> collection = pyfar.read('my_objs.far')
    >>> my_signal = collection['my_signal']
    >>> my_orientations = collection['my_orientations']
    """
    # Check for .far file extension
    filename = pathlib.Path(filename).with_suffix('.far')

    collection = {}
    with open(filename, 'rb') as f:
        zip_buffer = io.BytesIO()
        zip_buffer.write(f.read())
        with zipfile.ZipFile(zip_buffer) as zip_file:
            zip_paths = zip_file.namelist()
            obj_names_hints = [
                path.split('/')[:2] for path in zip_paths if '/$' in path]
            for name, hint in obj_names_hints:
                if codec._is_pyfar_type(hint[1:]):
                    obj = codec._decode_object_json_aided(name, hint, zip_file)
                elif hint == '$ndarray':
                    obj = codec._decode_ndarray(f'{name}/{hint}', zip_file)
                else:
                    raise TypeError(
                        '.far-file contains unknown types.'
                        'This might occur when writing and reading files with'
                        'different versions of Pyfar.')
                collection[name] = obj

        if 'builtin_wrapper' in collection:
            for key, value in collection['builtin_wrapper'].items():
                collection[key] = value
            collection.pop('builtin_wrapper')

    return collection


def write(filename, compress=False, **objs):
    """
    Write any compatible pyfar object or numpy array and often used builtin
    types as .far file to disk.

    Parameters
    ----------
    filename : string
        Full path or filename. If now extension is provided, .far-suffix
        will be add to filename.
    compress : bool
        Default is ``False`` (uncompressed).
        Compressed files take less disk space but need more time for writing
        and reading.
    **objs:
        Objects to be saved as key-value arguments, e.g.,
        ``name1=object1, name2=object2``.

    Examples
    --------

    Save Signal object, Orientations objects and numpy array to disk.

    >>> s = pyfar.Signal([1, 2, 3], 44100)
    >>> o = pyfar.Orientations.from_view_up([1, 0, 0], [0, 1, 0])
    >>> a = np.array([1,2,3])
    >>> pyfar.io.write('my_objs.far', signal=s, orientations=o, array=a)

    Notes
    -----
    * Supported builtin types are:
      bool, bytes, complex, float, frozenset, int, list, set, str and tuple
    """
    # Check for .far file extension
    filename = pathlib.Path(filename).with_suffix('.far')
    compression = zipfile.ZIP_STORED if compress else zipfile.ZIP_DEFLATED
    zip_buffer = io.BytesIO()
    builtin_wrapper = codec.BuiltinsWrapper()
    with zipfile.ZipFile(zip_buffer, "a", compression) as zip_file:
        for name, obj in objs.items():
            if codec._is_pyfar_type(obj):
                codec._encode_object_json_aided(obj, name, zip_file)
            elif codec._is_numpy_type(obj):
                codec._encode({f'${type(obj).__name__}': obj}, name, zip_file)
            elif type(obj) in codec._supported_builtin_types():
                builtin_wrapper[name] = obj
            else:
                error = (
                    f'Objects of type {type(obj)} cannot be written to disk.')
                if isinstance(obj, fo.Filter):
                    error = f'{error}. Consider casting to {fo.Filter}'
                raise TypeError(error)

        if len(builtin_wrapper) > 0:
            codec._encode_object_json_aided(
                builtin_wrapper, 'builtin_wrapper', zip_file)

    with open(filename, 'wb') as f:
        f.write(zip_buffer.getvalue())


def read_audio(filename, dtype='float64', **kwargs):
    """
    Import an audio file as :py:class:`~pyfar.classes.audio.Signal` object.

    Reads 'wav', 'aiff', 'ogg', and 'flac' files among others. For a complete
    list see :py:func:`audio_formats`.

    Parameters
    ----------
    filename : string, Path
        Input file.
    dtype : {'float64', 'float32', 'int32', 'int16'}, optional
        Data type of the returned signal, by default ``'float64'``.
        Floating point audio data is typically in the range from
        ``-1.0`` to ``1.0``.  Note that ``'int16'`` and ``'int32'`` should only
        be used if the data was written in the same format. Integer data is in
        the range from ``-2**15`` to ``2**15-1`` for ``'int16'`` and from
        ``-2**31`` to ``2**31-1`` for ``'int32'``.
    **kwargs
        Other keyword arguments to be passed to :py:func:`soundfile.read`. This
        is needed, e.g, to read RAW audio files.

    Returns
    -------
    signal : Signal
        :py:class:`~pyfar.classes.audio.Signal` object containing the audio
        data.

    Notes
    -----
    * This function is based on :py:func:`soundfile.read`.
    * Reading int values from a float file will *not* scale the data to
      [-1.0, 1.0). If the file contains ``np.array([42.6], dtype='float32')``,
      you will read ``np.array([43], dtype='int32')`` for ``dtype='int32'``.
    """
    data, sampling_rate = soundfile.read(
        file=filename, dtype=dtype, always_2d=True, **kwargs)
    signal = Signal(data.T, sampling_rate, domain='time', dtype=dtype)
    return signal


def write_audio(signal, filename, subtype=None, overwrite=True, **kwargs):
    """
    Write a :py:class:`~pyfar.classes.audio.Signal` object as a audio file to
    disk.

    Writes 'wav', 'aiff', 'ogg', and 'flac' files among others. For a complete
    list see :py:func:`audio_formats`.

    Parameters
    ----------
    signal : Signal
        Object to be written.
    filename : string, Path
        Output file. The format is determined from the file extension.
        See :py:func:`audio_formats` for all possible formats.
    subtype : str, optional
        The subtype of the sound file, the default value depends on the
        selected `format` (see :py:func:`default_audio_subtype`).
        See :py:func:`audio_subtypes` for all possible subtypes for
        a given ``format``.
    overwrite : bool
        Select wether to overwrite the audio file, if it already exists.
        The default is ``True``.
    **kwargs
        Other keyword arguments to be passed to :py:func:`soundfile.write`.

    Notes
    -----
    * Signals are flattened before writing to disk (e.g. a signal with
      ``cshape = (3, 2)`` will be written to disk as a six channel audio file).
    * This function is based on :py:func:`soundfile.write`.
    * Except for the subtypes ``'FLOAT'``, ``'DOUBLE'`` and ``'VORBIS'`` ´
      amplitudes larger than +/- 1 are clipped.

    """
    sampling_rate = signal.sampling_rate
    data = signal.time

    # Reshape to 2D
    data = data.reshape(-1, data.shape[-1])
    if len(signal.cshape) != 1:
        warnings.warn(f"Signal flattened to {data.shape[0]} channels.")

    # Check if file exists and for overwrite
    if overwrite is False and os.path.isfile(filename):
        raise FileExistsError(
            "File already exists,"
            "use overwrite option to disable error.")
    else:
        # Only the subtypes FLOAT, DOUBLE, VORBIS are not clipped,
        # see _clipped_audio_subtypes()
        format = pathlib.Path(filename).suffix[1:]
        if subtype is None:
            subtype = default_audio_subtype(format)
        if (np.any(data > 1.) and
                subtype.upper() not in ['FLOAT', 'DOUBLE', 'VORBIS']):
            warnings.warn(
                f'{format}-files of subtype {subtype} are clipped to +/- 1.')
        soundfile.write(
            file=filename, data=data.T, samplerate=sampling_rate,
            subtype=subtype, **kwargs)


def audio_formats():
    """Return a dictionary of available audio formats.

    Notes
    -----
    This function is a wrapper of :py:func:`soundfile.available_formats()`.

    Examples
    --------
    >>> import pyfar as pf
    >>> pf.io.audio_formats()
    {'FLAC': 'FLAC (FLAC Lossless Audio Codec)',
     'OGG': 'OGG (OGG Container format)',
     'WAV': 'WAV (Microsoft)',
     'AIFF': 'AIFF (Apple/SGI)',
     ...
     'WAVEX': 'WAVEX (Microsoft)',
     'RAW': 'RAW (header-less)',
     'MAT5': 'MAT5 (GNU Octave 2.1 / Matlab 5.0)'}

    """
    return soundfile.available_formats()


def audio_subtypes(format=None):
    """Return a dictionary of available audio subtypes.

    Parameters
    ----------
    format : str
        If given, only compatible subtypes are returned.

    Notes
    -----
    This function is a wrapper of :py:func:`soundfile.available_subtypes()`.

    Examples
    --------
    >>> import pyfar as pf
    >>> pf.io.audio_subtypes('FLAC')
    {'PCM_24': 'Signed 24 bit PCM',
     'PCM_16': 'Signed 16 bit PCM',
     'PCM_S8': 'Signed 8 bit PCM'}

    """
    return soundfile.available_subtypes(format=format)


def default_audio_subtype(format):
    """Return the default subtype for a given format.

    Notes
    -----
    This function is a wrapper of :py:func:`soundfile.default_audio_subtype()`.

    Examples
    --------
    >>> import pyfar as pf
    >>> pf.io.default_audio_subtype('WAV')
    'PCM_16'
    >>> pf.io.default_audio_subtype('MAT5')
    'DOUBLE'

    """
    return soundfile.default_subtype(format)


def read_comsol(filename, expressions, data_format='spreadsheet'):
    """
    Read data from COMSOL exported files into a Dictonary.

    Parameters
    ----------
    filename : string, Path
        Input file. .txt, .csv and .dat is supported and need to be given.
    data_format : string
        'spreadsheet' or 'sectionwise'

    Returns
    -------
    collection: dict
        Contains comsol data like
        ``{ 'data': 'obj1', 'coordinates': 'obj2' ... }``.

    Examples
    --------
    Read data from COMSOL export file.

    >>> collection = pyfar.io.read_comsol('my_data.csv')
    >>> my_data = collection['data']
    >>> my_coordinates = collection['coordinates']
    """
    # Check Datatype
    suffix = pathlib.Path(filename).suffix
    if not suffix.endswith(('.txt', '.dat', '.csv')):
        raise SyntaxError((
            "Input path must be a .txt, .csv or .dat file"
            f"but is of type {str(suffix)}"))

    # get orginal expressions 
    expressions_original = _read_comsol_expressions(filename)

    # get required metadata
    is_freq = 'freq=' in expressions[-1]
    num_dimension = 1
    if (expressions[1] == 'Y') or (expressions[1] == 'y'):
        num_dimension = 2
    if (expressions[2] == 'Z') or (expressions[2] == 'z'):
        num_dimension = 3
    num_data = len(expressions) - num_dimension

    # read body
    data_type = np.complex_ if is_freq else np.float_
    txt = np.loadtxt(
        filename,
        dtype=data_type,
        comments='%',
        converters=lambda s: s.replace('i', 'j'),
        encoding=None,
        delimiter=',')
    # txt.shape = (coordinates, Dimension+Expression)
    if len(txt.shape) == 1:
        txt = np.reshape(
            txt,
            (1, num_data + num_dimension))

    # read coordinates
    coords_data = txt[:, 0:num_dimension].astype(np.float)
    x = coords_data[:, 0]
    y = coords_data[:, 1] if coords_data.shape[1] > 1 else np.zeros(
        coords_data[:, 0].shape)
    z = coords_data[:, 2] if coords_data.shape[1] > 2 else np.zeros(
        coords_data[:, 0].shape)
    coordinates = Coordinates(x, y, z)

    # read data
    domain_str = 'freq' if 'freq=' in expressions_original[-1] else 't'
    domain_array = np.unique([float(x) for x in re.findall(
        domain_str + r'=([0-9.]+)',
        ','.join(expressions_original))])
    additional_expressions = np.unique(
        [x.replace(';', '').replace('=', '_') for x in re.findall(
            domain_str + r'=[0-9.]+([;a-zA-Z0-9=]+),',
            ','.join(expressions_original
                     ).replace('Hz', '').replace('s', '') + ',')])

    additional_expressions = dict()
    additional_expression_names = np.unique(
        re.findall(
            r';([a-zA-Z0-9]+)=[0-9]+[a-zA-Z]+,',
            ','.join(expressions_original
                     ).replace('Hz', '').replace('s', '') + ','))
    for exp in additional_expression_names:
        exp_values = np.unique(
            [float(x) for x in re.findall(
                exp + r'=([0-9]+)[a-zA-Z]+',
                ','.join(expressions_original
                         ).replace('Hz', '').replace('s', '') + ',')])
        exp_units = np.unique(
            re.findall(
                exp + r'=[0-9]+([a-zA-Z]+)',
                ','.join(expressions_original
                         ).replace('Hz', '').replace('s', '') + ','))
        additional_expressions[exp + "_" + exp_units[0]] = exp_values

    all_solutions = np.unique(re.findall(
        r',([;a-zA-Z0-9.\(\_)]+)\([;a-zA-Z0-9.\(\_)]+\)@',
        ','.join(expressions_original)))
    all_units = np.unique(re.findall(
        r',[;a-zA-Z0-9.\(\_)]+\(([;a-zA-Z0-9.\(\_)]+)\)@',
        ','.join(expressions_original)))

    if 'dB' in all_units:
        raise Warning("dB Values neglect information, it is strongly "
                      "recommended not to use dB data.")

    dim_domain = len(domain_array)
    len_solution = len(all_solutions) if len(all_solutions) > 0 else 1
    len_additional_expressions = len(additional_expressions) \
        if len(additional_expressions) > 0 else 1
    dim_remaining = len_solution * len_additional_expressions
    if dim_remaining * dim_domain != txt[:, num_dimension:].shape[1]:
        raise SyntaxError((
            "Data Dimension is wrong, "))

    # apply datashape data.shape = (coordinates, Expressions, Domain bins)
    domain_data = np.reshape(txt[:, num_dimension:],
                             (txt.shape[0], dim_remaining, dim_domain))
    is_freq = 'freq=' in expressions_original[-1]

    if is_freq:
        data_out = FrequencyData(
            domain_data, domain_array, dtype=data_type,
            comment="data_set + in  + unit")
    else:
        fs = 1 / np.mean(np.diff(domain_array))
        if len(domain_array) < 2:
            raise ValueError(
                "More than one time sample need to be available to "
                "calculate the samplerate.")
        diff_domain_data = np.diff(domain_array) - \
                           np.diff(domain_array)[0]
        if np.any(diff_domain_data > 1e-8):
            raise ValueError(
                "Time vector does not have the same distance.")
        data_out = Signal(
            domain_data, fs, comment="data_set + in  + unit")

    return data_out, coordinates


def read_comsol_header(filename):
    # Check Datatype
    suffix = pathlib.Path(filename).suffix
    if not suffix.endswith(('.txt', '.dat', '.csv')):
        raise SyntaxError((
            "Input path must be a .txt, .csv or .dat file"
            f"but is of type {str(suffix)}"))

    # read header
    metadata = _read_comsol_metadata(filename)
    expressions = _read_comsol_expressions(filename)
    return expressions, metadata


def _read_comsol_expressions(filename):
    header_data = []
    with open(filename) as f:
        for idx, line in enumerate(f):
            if idx == 8:
                header_data = line
                break
    header_data = header_data.replace('\n', '')
    expressions = header_data[2:].replace(', ', '; ').replace(
        ' ', '').split(',')
    return expressions


def _read_comsol_metadata(filename):
    suffix = pathlib.Path(filename).suffix
    metadata = dict()
    seperator_header = ','
    with open(filename) as f:
        while True:
            line = f.readline()
            if line[0] != '%' or line[2] == 'X' or line[2] == 'x':
                break
            elif len(line) > 0:
                number_names = ['dimension', 'nodes', 'expressions']
                if suffix.endswith('.csv'):
                    line = line[2:-1].replace('"', '').split(
                        seperator_header)
                elif suffix.endswith('.dat') or suffix.endswith('.txt'):
                    line = " ".join(line[2:-1].replace(',', ';')
                                    .replace(':', ',').split()).split(
                        seperator_header)
                if any(number_name == line[0].lower() for number_name in
                       number_names):
                    metadata[line[0]] = int(line[-1])
                else:
                    if suffix.endswith('.csv'):
                        metadata[line[0]] = ",".join(line[1:])
                    elif suffix.endswith('.dat') or suffix.endswith('.txt'):
                        line[1] = line[1][1:]
                        metadata[line[0]] = ":".join(
                            line[1:]).replace(';', ',')
    return metadata


def _clipped_audio_subtypes():
    """Creates a dictionary of format/subtype combinations which are clipped by
    :py:func:´write_audio`.

    This function is not called directly due to the need of writing all files
    to disk. It needs to be called manually:
    pyfar.io.io._clipped_audio_subtypes().
    """
    collection = {}
    signal = pyfar.Signal([-1.5, -1, -.5, 0, .5, 1, 1.5] * 100, 44100)
    with tempfile.TemporaryDirectory() as tmpdir:
        formats = pyfar.io.audio_formats()
        for format in formats:
            filename = os.path.join(tmpdir, 'test_file.' + format)
            for subtype in pyfar.io.audio_subtypes(format):
                write_valid = not _soundfile_write_errors(format, subtype)
                read_valid = not _soundfile_read_errors(format, subtype)
                format_valid = soundfile.check_format(format, subtype)
                if write_valid and read_valid and format_valid:
                    if format == 'RAW':
                        write_audio(signal, filename, subtype=subtype)
                        signal_read = read_audio(
                            filename, samplerate=44100, channels=1,
                            subtype=subtype)
                    else:
                        write_audio(signal, filename, subtype=subtype)
                        signal_read = read_audio(filename)
                    if (np.any(signal_read.time > 1.1) and
                            np.any(signal_read.time < -1.1)):
                        behavior = 'not clipping (' + format + ')'
                    elif (np.any(signal_read.time > .1) and
                          np.any(signal_read.time < -.1)):
                        behavior = 'clipping to +/- 1 (' + format + ')'
                    else:
                        raise ValueError(f"{format}/{subtype}")

                    if subtype not in collection:
                        collection[subtype] = [behavior]
                    else:
                        collection[subtype] = collection[subtype] + [behavior]

    return collection


def _soundfile_write_errors(format, subtype):
    """Checks if a write error due to soundfile/libsnfile can be expected.

    Written according to test_write_audio_read_audio.
    """
    if format == 'AIFF' and subtype == 'DWVW_12':
        error_expected = True
    else:
        error_expected = False
    return error_expected


def _soundfile_read_errors(format, subtype):
    """Checks if a read error due to soundfile/libsnfile can be expected.

    Written according to test_write_audio_read_audio.
    """
    if 'DWVW' in subtype and (format == 'AIFF' or format == 'RAW'):
        error_expected = True
    else:
        error_expected = False
    return error_expected
