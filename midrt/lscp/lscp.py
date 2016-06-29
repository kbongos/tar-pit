# -*-  coding: utf-8 -*-
"""LinuxSampler Control Protocol (LSCP) client library."""

from __future__ import absolute_import, print_function, unicode_literals

__all__ = [
    'CaseInsensitiveKeyDict',
    'LSCPClient',
    'LSCPError',
    'LSCPWarning'
]

import collections
import csv
import logging
import re
import socket

from .release import version as __version__  # noqa

try:
    basestring
except NameError:
    basestring = str
    unichr = chr
    unicode = None

_RX_OK = re.compile(r'(?P<type>OK)(\[(?P<index>\d+)\])?$')
_RX_ERR = re.compile(
    r'(?P<type>ERR|WRN)(\[(?P<index>\d+)\])?:(?P<code>.*?):(?P<msg>.*)$')
_RX_OCT_CODE = re.compile(r'\\(\d{3})')
_RX_HEX_CODE = re.compile(r'\\x([\dA-Fa-f]{2})')
_ESCAPE_CHARS = (
    ('\n', '\\n'),
    ('\r', '\\r'),
    ('\f', '\\f'),
    ('\t', '\\t'),
    ('\v', '\\v'),
    ("'", "\\'"),
    ('"', '\\"')
)
log = logging.getLogger(__name__)


class CaseInsensitiveKeyDict(collections.MutableMapping):
    """A ``dict``-like object with case-insensitive string keys.

    Derived from: https://github.com/kennethreitz/requests

    Implements all methods and operations of ``collections.MutableMapping``
    as well as dict's ``copy``.

    All keys are expected to be strings. ``iter(instance)``, ``keys()``,
    ``items()``, ``iterkeys()``, and ``iteritems()`` will yield lowercase
    keys. Also, querying and contains testing is case insensitive::

        cid = CaseInsensitiveKeyDict()
        cid['Accept'] = 'application/json'
        cid['aCCEPT'] == 'application/json'  # True
        list(cid) == ['accept']  # True

    """
    def __init__(self, data=None, **kwargs):
        self._store = dict()
        if data is None:
            data = {}
        self.update(data, **kwargs)

    def __setitem__(self, key, value):
        self._store[key.lower()] = value

    def __getitem__(self, key):
        return self._store[key.lower()]

    def __delitem__(self, key):
        del self._store[key.lower()]

    def __iter__(self):
        return iter(self._store)

    def __len__(self):
        return len(self._store)

    def __eq__(self, other):
        if isinstance(other, collections.Mapping):
            other = CaseInsensitiveKeyDict(other)
        else:
            return NotImplemented
        # Compare insensitively
        return self._store == other._store

    # Copy is required
    def copy(self):
        return CaseInsensitiveKeyDict(self._store.items())

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, dict(self.items()))


class LSCPError(Exception):
    """Base LSCP communication error."""
    def __init__(self, msg, code=None):
        super(LSCPError, self).__init__(msg)
        self.code = code


class LSCPWarning(LSCPError):
    pass


def _convert_param(value, type):
    if type == 'BOOL':
        return True if value == 'true' else False
    elif type == 'INT':
        return int(value)
    elif type == 'FLOAT':
        return float(value)
    elif type == 'STRING':
        return value.strip("'")
    else:
        raise ValueError("Unknown parameter type '%s'." % type)

def _escape(s, encoding='ascii'):
    """Replace non-ASCII chars and double/single quotes with escape sequences.

    Expects and returns a unicode string.

    """
    s = s.replace('\\', '\\\\')
    for substr, repl in _ESCAPE_CHARS:
        s = s.replace(substr, repl)
    return s.encode(encoding, 'backslashreplace').decode(encoding)

def _make_keyvalue_list(d):
    return ''.join(
        (" %s=%s" % (k.upper(), "'%s'" % v if isinstance(v, basestring) else v)
        for k, v in d.items()))

def _parse_params(response):
    """Parse a list of response lines into a dictionary of parameters.

    Returns a :class:`CaseInsensitiveKeyDict` instance, where keys are
    parameter names and values are parameter values converted into appropriate
    Python types.

    """
    params = CaseInsensitiveKeyDict()
    for line in response:
        k, v = line.split(': ', 1)

        if v in ('true', 'yes'):
            v = True
        elif v in ('false', 'no'):
            v = False

        params[k] = v

    # some conversions depend on the value of another parameter, which may
    # occur later in the response, so loop over the complete dict items again
    for k, v in params.items():
        if k == 'depends':
            v = tuple(v.split(','))
        elif k == 'parameters':
            v = tuple(v.split(','))
        elif k in ('default', 'possibilities'):
            if k == 'possibilities' or params.get('multiplicity'):
                v = tuple(_convert_param(v, params['type'])
                    for v in next(csv.reader([v], quotechar="'")))
            else:
                v = _convert_param(v, params['type'])
        elif k in ('range_min', 'range_max'):
            v = _convert_param(v, params['type'])

        params[k] = v

    return params

def _unescape(s):
    """Replace escape sequences in string with the characters they stand for.

    Expects and returns a unicode string.

    """
    for substr, repl in _ESCAPE_CHARS:
        s = s.replace(repl, substr)
    s = _RX_OCT_CODE.sub(lambda m: unichr(int(m.group(1), 8)), s)
    s = _RX_HEX_CODE.sub(lambda m: unichr(int(m.group(1), 16)), s)
    return s.replace('\\\\', '\\')


class LSCPClient(object):
    """Client for the LinuxSampler Control Protocol (LSCP).

    """
    RECV_BUFLEN = 4096

    def __init__(self, host='127.0.0.1', port=8888, timeout=5):
        """Set up instance and open socket connection to LinuxSampler server.

        ``host`` address defauts to ``'127.0.0.1'`` and ``port`` to ``8888``.

        If no initial connection to the server should be established, pass
        ``None`` as the server host name and call the ``connect`` method later
        and pass a host name or address to it.

        Sets the socket timeout to ``timeout`` (default ``5``), so that opening
        the socket and all socket operations time out after as many seconds.

        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket = None
        self.encoding = "ascii"
        self.raise_warnings = False
        self.sock = None

        if host:
            self.connect(host, port)

    def connect(self, host=None, port=None):
        """Create socket connection to LinuxSampler server."""
        if host:
            self.host = host
        if port:
            self.port = port
        if not self.host:
            raise ValueError("'host' attribute must be not-None to connect.")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))

    def close(self):
        """Close socket connection to LinuxSampler server."""
        if self.sock:
            self.sock.close()

        self.sock = None

    def _check_response(self, response):
        for rx in (_RX_ERR, _RX_OK):
            m = rx.match(response)
            if m:
                type = m.group('type')
                index = m.group('index')
                if index:
                    index = int(index)

                if type == 'OK':
                    code = msg = None
                else:
                    code = int(m.group('code'))
                    msg = m.group('msg')

                if type == 'ERR':
                    raise LSCPError(msg, code)
                elif type == 'WRN' and self.raise_warnings:
                    raise LSCPWarning(msg, code)
                else:
                    if type == 'WRN':
                        log.warning("LSCP warning: %i:%s", code, msg)
                    return dict(type=type, index=index, code=code, msg=msg)

        return response

    def send(self, msg):
        """Send a message to the LinuxSampler server.

        The message must be a byte string and should end with CRLR.

        Returns the number of bytes written to the socket.

        """
        totalsent = 0
        while totalsent < len(msg):
            sent = self.sock.send(msg[totalsent:])
            if sent == 0:
                raise IOError("socket connection broken")
            totalsent = totalsent + sent

        return totalsent

    def receive(self, delimiter=b'\r\n'):
        """Receive a message from the LinuxSampler server.

        Reads from the connected socket until the end of the message - normally
        indicated by CRLF - is received, or the socket times out, or the
        connection is broken (socket returns 0 bytes).

        Returns the received message as a bytes object.

        """
        msg = b''

        while not msg.endswith(delimiter):
            chunk = self.sock.recv(self.RECV_BUFLEN)
            if chunk == b'':
                raise IOError("socket connection broken")
            msg = msg + chunk

        return msg

    def receive_multiline(self):
        """Receive a multi-line message from the LinuxSampler server.

        Returns response message lines as a single byte string with embedded
        CRLF line-breaks and the last line consisting of a single ``'.'``.

        """
        return self.receive(delimiter=b'.\r\n')

    def query(self, qry, multiline=False):
        """Send a query/command to the LinuxSampler server and return reply.
        """
        if self.sock is None:
            self.connect()

        if unicode and isinstance(qry, unicode):
            qry = qry.encode(self.encoding)

        if not isinstance(qry, bytes):
            qry = bytes(qry, self.encoding)

        qry = qry.rstrip(b'\r\n') + b'\r\n'

        log.debug("SEND: %r", qry)
        self.send(qry)

        if multiline:
            response = self.receive_multiline()
        else:
            response = self.receive()

        log.debug("RECV: %r", response)
        response = response.decode(self.encoding).rstrip('.\r\n')
        response = self._check_response(response)

        if isinstance(response, basestring) and multiline:
            return response.splitlines()

        return response

    def get_server_info(self):
        return _parse_params(self.query('GET SERVER INFO', True))

    def get_available_audio_output_drivers(self):
        """Return number of available audio output drivers.

        :return: integer number of audio output drivers

        """
        return int(self.query('GET AVAILABLE_AUDIO_OUTPUT_DRIVERS'))

    def list_available_audio_output_drivers(self):
        """Get list of names of available audio output drivers.

        :return: list of names of available audio output drivers

        """
        return tuple(
            self.query('LIST AVAILABLE_AUDIO_OUTPUT_DRIVERS').split(','))

    def get_audio_output_driver_info(self, driver):
        """Get detailed information about given audio output driver.

        :param str driver: name of the audio output driver (from the list
            returned by :meth:`.list_available_audio_output_drivers`)
        :return: dictionary with information about the driver. For
            documentation about members and the meaning of their values, refer
            to the LSCP specification, section 6.2.3.
        :rtype: :class:`~lscp.CaseInsensitiveKeyDict` instance

        """
        return _parse_params(self.query(
            'GET AUDIO_OUTPUT_DRIVER INFO %s' % driver, True))

    def get_audio_output_driver_param_info(self, driver, param, **deps):
        """Get detailed information about given audio output driver parameter.

        :param str driver: name of the audio output driver (from the list
            returned by :meth:`.list_available_audio_output_drivers`)
        :param str param: parameter name (from the list of parameter names in
            the information returned by :meth:`.get_audio_output_driver_info`
            for the given audio output driver)
        :return: dictionary with information about the parameter. For
            documentation about members and the meaning of their values, refer
            to the LSCP specification, section 6.2.4.
        :rtype: :class:`~lscp.CaseInsensitiveKeyDict` instance

        """
        deps = _make_keyvalue_list(deps)
        query = 'GET AUDIO_OUTPUT_DRIVER_PARAMETER INFO %s %s%s' % (
            driver, param.upper(), deps)
        return _parse_params(self.query(query, True))

    def create_audio_output_device(self, driver, **params):
        params = _make_keyvalue_list(params)
        query = 'CREATE AUDIO_OUTPUT_DEVICE %s%s' % (driver, params)
        return self.query(query)['index']

    def destroy_audio_output_device(self, index):
        return self.query('DESTROY AUDIO_OUTPUT_DEVICE %i' % index)

    def get_audio_output_devices(self):
        return int(self.query('GET AUDIO_OUTPUT_DEVICES'))

    def list_audio_output_devices(self):
        return tuple(int(device)
            for device in self.query('LIST AUDIO_OUTPUT_DEVICES').split(',')
            if device)

    def get_audio_output_device_info(self, index):
        return _parse_params(
            self.query('GET AUDIO_OUTPUT_DEVICE INFO %i' % index, True))

    def set_audio_output_device_param(self, index, param, value):
        return self.query('SET AUDIO_OUTPUT_DEVICE_PARAMETER %i %s=%s' % (
            index, param.upper(),
            "'%s'" % value if isinstance(value, str) else value))

    def get_audio_output_channel_info(self, index, channel):
        return _parse_params(
            self.query('GET AUDIO_OUTPUT_CHANNEL INFO %i %i' %
            (index, channel), True))

    def get_audio_output_channel_param_info(self, index, channel, param):
        return _parse_params(
            self.query('GET AUDIO_OUTPUT_CHANNEL_PARAMETER INFO %i %i %s' %
                (index, channel, param.upper()), True))

    def set_audio_output_channel_param(self, index, channel, param, value):
        return self.query('SET AUDIO_OUTPUT_CHANNEL_PARAMETER %i %i %s=%s' % (
            index, channel, param.upper(),
            "'%s'" % value if isinstance(value, str) else value))

    def get_available_midi_input_drivers(self):
        return int(self.query('GET AVAILABLE_MIDI_INPUT_DRIVERS'))

    def list_available_midi_input_drivers(self):
        return tuple(
            self.query('LIST AVAILABLE_MIDI_INPUT_DRIVERS').split(','))

    def get_midi_input_driver_info(self, driver):
        return _parse_params(self.query(
            'GET MIDI_INPUT_DRIVER INFO %s' % driver, True))

    def get_midi_input_driver_param_info(self, driver, param, **deps):
        deps = _make_keyvalue_list(deps)
        query = 'GET MIDI_INPUT_DRIVER_PARAMETER INFO %s %s%s' % (
            driver, param.upper(), deps)
        return _parse_params(self.query(query, True))

    def create_midi_input_device(self, driver, **params):
        params = _make_keyvalue_list(params)
        query = 'CREATE MIDI_INPUT_DEVICE %s%s' % (driver, params)
        return self.query(query)['index']

    def destroy_midi_input_device(self, index):
        return self.query('DESTROY MIDI_INPUT_DEVICE %i' % index)

    def get_midi_input_devices(self):
        return int(self.query('GET MIDI_INPUT_DEVICES'))

    def list_midi_input_devices(self):
        return tuple(int(dev)
            for dev in self.query('LIST MIDI_INPUT_DEVICES').split(',') if dev)

    def get_midi_input_device_info(self, index):
        return _parse_params(
            self.query('GET MIDI_INPUT_DEVICE INFO %i' % index, True))

    def set_midi_input_device_param(self, index, param, value):
        return self.query('SET MIDI_INPUT_DEVICE_PARAMETER %i %s=%s' % (
            index, param.upper(),
            "'%s'" % value if isinstance(value, str) else value))

    def get_midi_input_port_info(self, index, port):
        return _parse_params(
            self.query('GET MIDI_INPUT_PORT INFO %i %i' % index, True))

    def set_midi_input_port_param(self, index, port, param, value):
        return self.query('SET MIDI_INPUT_PORT_PARAMETER %i %i %s=%s' % (
            index, port, param.upper(),
            "'%s'" % value if isinstance(value, str) else value))

    def load_engine(self, engine, channel):
        return self.query("LOAD ENGINE %s %i" % (engine, channel))

    def load_instrument(self, filename, index, channel, non_modal=False):
        return self.query("LOAD INSTRUMENT%s '%s' %i %i" % (
            ' NON_MODAL' if non_modal else '',
            _escape(filename), index, channel))

    def get_channels(self):
        return int(self.query('GET CHANNELS'))

    def list_channels(self):
        return tuple(int(ch)
            for ch in self.query('LIST CHANNELS').split(',') if ch)

    def add_channel(self):
        return self.query('ADD CHANNEL')['index']

    def remove_channel(self, channel):
        return self.query('REMOVE CHANNEL %i' % channel)

    def get_available_engines(self):
        return int(self.query('GET AVAILABLE_ENGINES'))

    def list_available_engines(self):
        return tuple(engine.strip("'")
            for engine in self.query('LIST AVAILABLE_ENGINES').split(',')
            if engine)

    def get_engine_info(self, engine):
        return _parse_params(self.query('GET ENGINE INFO %s' % engine, True))

    def reset(self):
        return self.query('RESET')


def shell(args=None):
    import argparse
    import sys
    from IPython import embed

    argparser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argparser.add_argument('-t', '--timeout', default=5, type=int,
        help="Socket timeout (default: %(default)s).")
    argparser.add_argument('-d', '--debug', action="store_true",
        help="Enable debug logging.")
    argparser.add_argument('host', nargs='?', default='localhost',
        help="LSCP server hostname (default: %(default)s).")
    argparser.add_argument('port', nargs='?', default=8888, type=int,
        help="LSCP server port (default: %(default)s).")

    args = argparser.parse_args(args if args is not None else sys.argv[1:])
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    lscpc = LSCPClient(args.host, args.port)  # noqa
    embed()


if __name__ == '__main__':
    shell()
