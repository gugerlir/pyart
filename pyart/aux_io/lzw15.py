"""
Stream friendly, simple compression library, built around
iterators. See L{compress} and L{decompress} for the easiest way to
get started.

Basically implemented after the TIFF implementation of LZW, as described here:
U{http://www.fileformat.info/format/tiff/corion-lzw.htm}
But we included adjustments for more control codes and larger code sizes.

In an even-nuttier-shell, lzw compresses input bytes with integer
codes. Starting with codes 0-255 that code to themselves, and three
control codes, we work our way through a stream of bytes. When we
encounter a pair of codes c1,c2 we add another entry to our code table
with the lowest available code and the value value(c1) + value(c2)[0]

Of course, there are details :)

The Details
===========

    Our control codes are
        - END_OF_INFO_CODE (codepoint 256). This code is reserved for
          encoder/decoders over the integer codepoint stream (like the
          mechanical bit that unpacks bits into codepoints)
        - BUMB_CODE (codepoint 257). When this code is encountered we
          increase the bit size of the codepoints by 1.
        - CLEAR_CODE (codepoint 258). When this code is encountered, we flush
          the codebook and start over.

    When dealing with bytes, codes are emitted as variable
    length bit strings packed into the stream of bytes.

    codepoints are written with varying length
        - initially 9 bits
        - at 512   entries 10 bits
        - at 1024  entries 11 bits
        - at 2048  entries 12 bits
        - at 4096  entries 13 bits
        - at 8192  entries 14 bits
        - at 16384 entries 15 bits
        - with max 32768 entries in a table (including EOI, CLEAR and BUMP codes)

    code points are stored with their MSB in the most significant bit
    available in the output character.

>>> import lzw15
>>>
>>> mybytes = lzw15.readbytes("README.txt")
>>> lessbytes = lzw15.compress(mybytes)
>>> newbytes = b"".join(lzw15.decompress(lessbytes))
>>> oldbytes = b"".join(lzw15.readbytes("README.txt"))
>>> oldbytes == newbytes
True


"""

import operator
import struct

END_OF_INFO_CODE = 256
BUMP_CODE = 257
NEXT_BUMP_CODE = 511
CLEAR_CODE = 258

DEFAULT_MIN_BITS = 9
DEFAULT_MAX_BITS = 15

MAX_CODE = 2**DEFAULT_MAX_BITS

FIRST_CODE = 259


def compress(plaintext_bytes):
    """
    Given an iterable of bytes, returns a (hopefully shorter) iterable
    of bytes that you can store in a file or pass over the network or
    what-have-you, and later use to get back your original bytes with
    L{decompress}. This is the best place to start using this module.
    """
    encoder = ByteEncoder()
    return encoder.encodetobytes(plaintext_bytes)


def decompress(compressed_bytes):
    """
    Given an iterable of bytes that were the result of a call to
    L{compress}, returns an iterator over the uncompressed bytes.
    """
    decoder = ByteDecoder()
    return decoder.decodefrombytes(compressed_bytes)


class ByteEncoder:
    """
    Takes a stream of uncompressed bytes and produces a stream of
    compressed bytes, usable by L{ByteDecoder}. Combines an L{Encoder}
    with a L{BitPacker}.


    >>> import lzw15
    >>>
    >>> enc = lzw15.ByteEncoder(12)
    >>> bigstr = b"gabba gabba yo gabba gabba gabba yo gabba gabba gabba yo
    >>> gabba gabba gabba yo"
    >>> encoding = enc.encodetobytes(bigstr)
    >>> encoded = b"".join( b for b in encoding )
    >>> encoded == b'3\\x98LF#\\x08\\x82\\x05\\x04\\x83\\x1eM\\xf0x\\x1c
    >>>            \\x16\\x1b\\t\\x88C\\xe1q(4"\\x1f\\x17\\x85C#1X\\xec.\\x00'
    True
    >>>
    >>> dec = lzw15.ByteDecoder()
    >>> decoding = dec.decodefrombytes(encoded)
    >>> decoded = b"".join(decoding)
    >>> decoded == bigstr
    True

    """

    def __init__(self, max_width=DEFAULT_MAX_BITS):
        """
        max_width is the maximum width in bits we want to see in the
        output stream of codepoints.
        """
        self._encoder = Encoder(max_code_size=2**max_width)
        self._packer = BitPacker(initial_code_size=self._encoder.code_size())

    def encodetobytes(self, bytesource):
        """
        Returns an iterator of bytes, adjusting our packed width
        between minwidth and maxwidth when it detects an overflow is
        about to occur. Dual of L{ByteDecoder.decodefrombytes}.
        """
        codepoints = self._encoder.encode(bytesource)
        codebytes = self._packer.pack(codepoints)

        return codebytes


class ByteDecoder:
    """
    Decodes, combines bit-unpacking and interpreting a codepoint
    stream, suitable for use with bytes generated by
    L{ByteEncoder}.

    See L{ByteDecoder} for a usage example.
    """

    def __init__(self):
        """
        """

        self._decoder = Decoder()
        self._unpacker = BitUnpacker(
            initial_code_size=self._decoder.code_size())

    def decodefrombytes(self, bytesource):
        """
        Given an iterator over BitPacked, Encoded bytes, Returns an
        iterator over the uncompressed bytes. Dual of
        L{ByteEncoder.encodetobytes}. See L{ByteEncoder} for an
        example of use.
        """
        codepoints = self._unpacker.unpack(bytesource)
        clearbytes = self._decoder.decode(codepoints)

        return clearbytes


class BitPacker:
    """
    Translates a stream of lzw codepoints into a variable width packed
    stream of bytes, for use by L{BitUnpacker}.  One of a (potential)
    set of encoders for a stream of LZW codepoints, intended to behave
    as closely to the TIFF variable-width encoding as possible.

    The inbound stream of integer lzw codepoints are packed into
    variable width bit fields, starting at the smallest number of bits
    it can and then increasing the bit width as it anticipates the LZW
    code size growing to overflow.

    This class knows all kinds of intimate things about how it's
    upstream codepoint processors work; it knows the control codes
    CLEAR_CODE and END_OF_INFO_CODE, and (more intimately still), it
    makes assumptions about the rate of growth of it's consumer's
    codebook. This is ok, as long as the underlying encoder/decoders
    don't know any intimate details about their BitPackers/Unpackers
    """

    def __init__(self, initial_code_size):
        """
        Takes an initial code book size (that is, the count of known
        codes at the beginning of encoding, or after a clear)
        """
        self._initial_code_size = initial_code_size

    def pack(self, codepoints):
        """
        Given an iterator of integer codepoints, returns an iterator
        over bytes containing the codepoints packed into varying
        lengths, with bit width growing to accomodate an input code
        that it assumes will grow by one entry per codepoint seen.

        Widths will be reset to the given initial_code_size when the
        LZW CLEAR_CODE or END_OF_INFO_CODE code appears in the input,
        and bytes following END_OF_INFO_CODE will be aligned to the
        next byte boundary.

        >>> import lzw, six
        >>> pkr = lzw.BitPacker(258)
        >>> [ b for b in pkr.pack([ 1, 257]) ] == [ struct.Struct(">B").pack(0),
        >>>  struct.Struct(">B").pack(0xC0), struct.Struct(">B").pack(0x40) ]
        True
        """

        tailbits = []
        codesize = self._initial_code_size

        minwidth = DEFAULT_MIN_BITS

        nextwidth = minwidth

        for pt in codepoints:

            newbits = inttobits(pt, nextwidth)

            tailbits = tailbits + newbits  # Last bits in the list.

            # PAY ATTENTION. This calculation should be driven by the
            # size of the upstream codebook, right now we're just trusting
            # that everybody intends to follow the TIFF spec.

            codesize = codesize + 1

            if pt == END_OF_INFO_CODE:
                while len(tailbits) % 8:
                    tailbits.append(0)

            if pt == BUMP_CODE:
                nextwidth = nextwidth + 1

            elif codesize >= MAX_CODE:
                print("Attention: codesize >= MAX_CODE. Check the python lzw code!")

            while len(tailbits) > 8:
                nextbits = tailbits[:8]
                nextbytes = bitstobytes(nextbits)

                for bt in nextbytes:
                    yield struct.pack("B", bt)

                tailbits = tailbits[8:]

        if tailbits:
            tail = bitstobytes(tailbits)
            # print("TAIL:", tailbits)
            for bt in tail:
                yield struct.pack("B", bt)


class BitUnpacker:
    """
    An adaptive-width bit unpacker, intended to decode streams written
    by L{BitPacker} into integer codepoints. Like L{BitPacker}, knows
    about code size changes and control codes.
    """

    def __init__(self, initial_code_size):
        """
        initial_code_size is the starting size of the codebook
        associated with the to-be-unpacked stream.
        """
        self._initial_code_size = initial_code_size

    def unpack(self, bytesource):
        """
        Given an iterator of bytes, returns an iterator of integer
        code points. Auto-magically adjusts point width when it sees
        an almost-overflow in the input stream, or an LZW CLEAR_CODE
        or END_OF_INFO_CODE

        Trailing bits at the end of the given iterator, after the last
        codepoint, will be dropped on the floor.

        At the end of the iteration, or when an END_OF_INFO_CODE seen
        the unpacker will ignore the bits after the code until it
        reaches the next aligned byte. END_OF_INFO_CODE will *not*
        stop the generator, just reset the alignment and the width

        >>> import lzw, six
        >>> unpk = lzw.BitUnpacker(initial_code_size=258)
        >>> [ i for i in unpk.unpack([ struct.Struct(">B").pack(0),
        >>>  struct.Struct(">B").pack(0xC0), struct.Struct(">B").pack(0x40) ]) ]
        [1, 257]
        """
        bits = []
        offset = 0
        ignore = 0

        codesize = self._initial_code_size

        # Uncommented
        # minwidth = 8
        # while (1 << minwidth) < codesize:
        #    minwidth = minwidth + 1

        minwidth = DEFAULT_MIN_BITS
        pointwidth = minwidth

        for nextbit in bytestobits(bytesource):

            offset = (offset + 1) % 8

            if ignore > 0:
                ignore = ignore - 1
                continue

            bits.append(nextbit)

            if len(bits) == pointwidth:
                codepoint = intfrombits(bits)
                bits = []
                yield codepoint
                codesize = codesize + 1

                if codepoint == BUMP_CODE:
                    pointwidth = pointwidth + 1

                if codepoint == END_OF_INFO_CODE:
                    ignore = (8 - offset) % 8


class Decoder:
    """
    Uncompresses a stream of lzw code points, as created by
    L{Encoder}. Given a list of integer code points, with all
    unpacking foolishness complete, turns that list of codepoints into
    a list of uncompressed bytes. See L{BitUnpacker} for what this
    doesn't do.
    """

    def __init__(self):
        """
        Creates a new Decoder. Decoders should not be reused for
        different streams.
        """
        self._clear_codes()
        self.remainder = []
        self._count = 0

    def code_size(self):
        """
        Returns the current size of the Decoder's code book, that is,
        it's mapping of codepoints to byte strings. The return value of
        this method will change as the decode encounters more encoded
        input, or control codes.
        """
        return len(self._codepoints)

    def decode(self, codepoints):
        """
        Given an iterable of integer codepoints, yields the
        corresponding bytes, one at a time, as byte strings of length
        E{1}. Retains the state of the codebook from call to call, so
        if you have another stream, you'll likely need another
        decoder!

        Decoders will NOT handle END_OF_INFO_CODE (rather, they will
        handle the code by throwing an exception); END_OF_INFO should
        be handled by the upstream codepoint generator (see
        L{BitUnpacker}, for example)

        >>> import lzw
        >>> dec = lzw.Decoder()
        >>> result = b''.join(dec.decode([103, 97, 98, 98, 97, 32, 258, 260,
        >>>          262, 121, 111, 263, 259, 261, 256]))
        >>> result == b'gabba gabba yo gabba'
        True

        """
        codepoints = [cp for cp in codepoints]

        for cp in codepoints:
            if cp == BUMP_CODE:
                # print("BUMB_CODE reached")
                continue
            if cp == END_OF_INFO_CODE:
                # print("END_OF_INFO_CODE reached")
                return

            decoded = self._decode_codepoint(cp)

            for character in iter(decoded):
                # TODO optimize, casting back to bytes when bytes above
                yield struct.Struct(">B").pack(character)

    def _decode_codepoint(self, codepoint):
        """
        Will raise a ValueError if given an END_OF_INFORMATION
        code. EOI codes should be handled by callers if they're
        present in our source stream.

        >>> import lzw
        >>> dec = lzw.Decoder()
        >>> beforesize = dec.code_size()
        >>> dec._decode_codepoint(0x80) == b'\\x80'
        True
        >>> dec._decode_codepoint(0x81) == b'\\x81'
        True
        >>> beforesize + 1 == dec.code_size()
        True
        >>> dec._decode_codepoint(256) == b''
        True
        >>> beforesize == dec.code_size()
        True
        """
        ret = b''

        if codepoint == CLEAR_CODE:
            self._clear_codes()
        elif codepoint == END_OF_INFO_CODE: # END_OF_INFO_CODE handled in decode routine
            raise ValueError("End of information code not supported " +
                             "directly by this Decoder")
        else:
            if codepoint in self._codepoints:
                ret = self._codepoints[codepoint]
                if self._prefix is not None:
                    self._codepoints[len(self._codepoints)] = (
                        self._prefix + struct.Struct(">B").pack(operator.getitem(ret,
                                                                                  0)))

            else:
                ret = self._prefix + struct.Struct(">B").pack(
                    operator.getitem(self._prefix, 0))
                self._codepoints[len(self._codepoints)] = ret

            self._prefix = ret

        return ret

    def _clear_codes(self):
        self._codepoints = dict(
            (pt, struct.pack("B", pt)) for pt in range(256))

        self._codepoints[END_OF_INFO_CODE] = END_OF_INFO_CODE
        self._codepoints[BUMP_CODE] = BUMP_CODE
        self._codepoints[CLEAR_CODE] = CLEAR_CODE

        self._prefix = None


class Encoder:
    """
    Given an iterator of bytes, returns an iterator of integer
    codepoints, suitable for use by L{Decoder}. The core of the
    "compression" side of lzw compression/decompression.
    """

    def __init__(self, max_code_size=MAX_CODE):
        """
        When the encoding codebook grows larger than max_code_size,
        the Encoder will clear its codebook and emit a CLEAR_CODE
        """

        self.closed = False

        self._max_code_size = max_code_size
        self._buffer = b''
        self._clear_codes()

        if max_code_size < self.code_size():
            raise ValueError(
                f"Max code size too small, (must be at least {self.code_size()})")

    def code_size(self):
        """
        Returns a count of the known codes, including codes that are
        implicit in the data but have not yet been produced by the
        iterator.
        """
        return len(self._prefixes)

    def flush(self):
        """
        Yields any buffered codepoints, followed by a CLEAR_CODE, and
        clears the codebook as a side effect.
        """

        # flushed = []

        if self._buffer:
            yield self._prefixes[self._buffer]
            self._buffer = b''

        yield END_OF_INFO_CODE
        self._clear_codes()

    def bump(self):
        """
        Yields the BUMP_CODE and increases the next_bumb_code value
        """
        yield BUMP_CODE

        self._current_code_bits = self._current_code_bits + 1
        self._next_bumb_code <<= 1
        self._next_bumb_code |= 1

        # print("Next_bump_code:", self._next_bumb_code)

    def encode(self, bytesource):
        """
        Given an iterator over bytes, yields the
        corresponding stream of codepoints.
        Will clear the codes at the end of the stream.

        >>> import lzw
        >>> enc = lzw.Encoder()
        >>> [ cp for cp in enc.encode(b"gabba gabba yo gabba") ]
        [103, 97, 98, 98, 97, 32, 258, 260, 262, 121, 111, 263, 259, 261, 256]

        """
        for b in bytesource:
            for point in self._encode_byte(b):
                yield point
            if self.code_size() > self._max_code_size:
                for pt in self.flush():
                    yield pt
            if self.code_size() > self._next_bumb_code:
                for pt in self.bump():
                    yield pt

        # Important to get last bytes correct
        for point in self.flush():
            yield point

    def _encode_byte(self, point):
        # Yields one or zero bytes, AND changes the internal state of
        # the codebook and prefix buffer.
        #
        # Unless you're in self.encode(), you almost certainly don't
        # want to call this.

        # In python3 iterating over the bytestring will return in codepoints,
        # we use the byte([]) constructor to conver this back into bytestring
        # so we can add to new_prefix and key the _prefixes by the bytestring.

        byte = point if isinstance(point, bytes) else struct.Struct(">B").pack(
            point)
        # print(byte)
        new_prefix = self._buffer
        # print(new_prefix)
        if new_prefix + byte in self._prefixes:
            new_prefix = new_prefix + byte
        elif new_prefix:
            encoded = self._prefixes[new_prefix]
            # print(encoded)
            # print(new_prefix + byte)
            self._add_code(new_prefix + byte)
            new_prefix = byte
            # print(self._prefixes)
            yield encoded

        self._buffer = new_prefix

    def _clear_codes(self):

        # Teensy hack, CLEAR_CODE and END_OF_INFO_CODE aren't
        # equal to any possible string.

        self._prefixes = dict(
            (struct.pack("B", codept), codept) for codept in range(256))
        self._prefixes[END_OF_INFO_CODE] = END_OF_INFO_CODE
        self._prefixes[BUMP_CODE] = BUMP_CODE
        self._prefixes[CLEAR_CODE] = CLEAR_CODE
        self._next_bumb_code = NEXT_BUMP_CODE
        self._current_code_bits = 9

    def _add_code(self, newstring):
        # print(len(self._prefixes))
        self._prefixes[newstring] = len(self._prefixes)
        # print(self._prefixes)


#########################################
# Conveniences.


def unpackbyte(b):
    """
    Given a one-byte long byte string, returns an integer. Equivalent
    to struct.unpack("B", b)
    """
    if isinstance(b, bytes):
        return operator.itemgetter(0)(b)
    return b


def filebytes(fileobj, buffersize=1024):
    """
    Convenience for iterating over the bytes in a file. Given a
    file-like object (with a read(int) method), returns an iterator
    over the bytes of that file.
    """
    buff = fileobj.read(buffersize)
    while buff:
        yield from buff
        buff = fileobj.read(buffersize)


def readbytes(filename, buffersize=1024):
    """
    Opens a file named by filename and iterates over the L{filebytes}
    found therein.  Will close the file when the bytes run out.
    """
    with open(filename, "rb") as infile:
        for byte in iter(filebytes(infile, buffersize)):
            # TODO optimize, we are re-casting to bytes
            yield struct.Struct(">B").pack(byte)


def readbytes_fh(infile, buffersize=1024):
    """
    Iterates over the L{filebytes} of a file handler
    found therein.  Will close the file when the bytes run out.
    """
    for byte in iter(filebytes(infile, buffersize)):
        # TODO optimize, we are re-casting to bytes
        yield struct.Struct(">B").pack(byte)


def writebytes(filename, bytesource):
    """
    Convenience for emitting the bytes we generate to a file. Given a
    filename, opens and truncates the file, dumps the bytes
    from bytesource into it, and closes it
    """

    with open(filename, "wb") as outfile:
        for bt in bytesource:
            outfile.write(bt)


def inttobits(anint, width=None):
    """
    Produces an array of booleans representing the given argument as
    an unsigned integer, MSB first. If width is given, will pad the
    MSBs to the given width (but will NOT truncate overflowing
    results)

    >>> import lzw15
    >>> lzw15.inttobits(304, width=16)
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0]

    """
    remains = anint
    retreverse = []
    while remains:
        retreverse.append(remains & 1)
        remains = remains >> 1

    retreverse.reverse()

    ret = retreverse
    if width is not None:
        ret_head = [0] * (width - len(ret))
        ret = ret_head + ret

    return ret


def intfrombits(bits):
    """
    Given a list of boolean values, interprets them as a binary
    encoded, MSB-first unsigned integer (with True == 1 and False
    == 0) and returns the result.

    >>> import lzw15
    >>> lzw15.intfrombits([ 1, 0, 0, 1, 1, 0, 0, 0, 0 ])
    304
    """
    ret = 0
    lsb_first = [b for b in bits]
    lsb_first.reverse()

    for bit_index, lsb_first_el in enumerate(lsb_first):
        if lsb_first_el:
            ret = ret | (1 << bit_index)

    return ret


def bytestobits(bytesource):
    """
    Breaks a given iterable of bytes into an iterable of boolean
    values representing those bytes as unsigned integers.

    >>> import lzw15
    >>> [ x for x in lzw15.bytestobits(b"\\x01\\x30") ]
    [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0]
    """
    for b in bytesource:

        value = unpackbyte(b)

        for bitplusone in range(8, 0, -1):
            bitindex = bitplusone - 1
            nextbit = 1 & (value >> bitindex)
            yield nextbit


def bitstobytes(bits):
    """
    Interprets an indexable list of booleans as bits, MSB first, to be
    packed into a list of integers from 0 to 256, MSB first, with LSBs
    zero-padded. Note this padding behavior means that round-trips of
    bytestobits(bitstobytes(x, width=W)) may not yield what you expect
    them to if W % 8 != 0

    Does *NOT* pack the returned values into a bytearray or the like.

    >>> import lzw15
    >>> bitstobytes([0, 0, 0, 0, 0, 0, 0, 0, "Yes, I'm True"]) == [ 0x00, 0x80 ]
    True
    >>> bitstobytes([0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0]) == [ 0x01, 0x30 ]
    True
    """
    ret = []
    nextbyte = 0
    nextbit = 7
    for bit in bits:
        if bit:
            nextbyte = nextbyte | (1 << nextbit)

        if nextbit:
            nextbit = nextbit - 1
        else:
            ret.append(nextbyte)
            nextbit = 7
            nextbyte = 0

    if nextbit < 7:
        ret.append(nextbyte)
    return ret
