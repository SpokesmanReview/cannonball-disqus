# Some fun utilities to serialize python data into compressed strings.
# Need this because a) memcached has a 1MB datasize limit and b) memcached
# requires plain, ASCII-only strings.

try:
    from cPickle import dumps, loads
except ImportError:
    from pickle import dumps, loads

import bz2
import zlib
from base64 import b64encode, b64decode

def encode_value(data, compression_level=1):
    serialized = dumps(data, -1)
    if compression_level:
        compressed = zlib.compress(serialized, compression_level)
    else:
        compressed = serialized
    coded = b64encode(compressed)
    return str(coded)

def decode_value(data):
    coded = str(data)
    compressed = b64decode(coded)

    # Most likely case: gzip'd
    try:
        return loads(zlib.decompress(compressed))
    except:
        pass

    # Second likely: not compressed
    try:
        return loads(compressed)
    except:
        pass

    # Legacy: bz2 compressed
    # Don't try/except here, so we can bubble up that this is bad data
    return loads(bz2.decompress(compressed))
