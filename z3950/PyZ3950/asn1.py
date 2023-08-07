from __future__ import print_function, absolute_import

import array
import codecs
import math


def cmp(a, b):
    return (a > b) - (a < b)


implicit_default = 1
indef_len_encodings = 0
cons_encoding = 0


class BERError(Exception): pass


class EncodingError(Exception): pass


def encode(spec, data):
    ctx = Ctx()
    spec.encode(ctx, data)
    return ctx.get_data()


def decode(spec, buf, readproc=None):
    ctx = IncrementalDecodeCtx(spec)
    ctx.feed(buf)
    while ctx.val_count() == 0:
        ctx.feed(readproc())
    rv = ctx.get_first_decoded()
    return rv


UNIVERSAL_FLAG = 0
APPLICATION_FLAG = 0x40
CONTEXT_FLAG = 0x80
PRIVATE_FLAG = 0xC0

CONS_FLAG = 0x20

ANY_TAG = -1  # pseudotag

END_INDEF_CONS_TAG = 0x0

BOOL_TAG = 0x1
INT_TAG = 0x2
BITSTRING_TAG = 0x3
OCTSTRING_TAG = 0x4
NULL_TAG = 0x5
OID_TAG = 0x6
OBJECTDESCRIPTOR_TAG = 0x7
EXTERNAL_TAG = 0x8
REAL_TAG = 0x9
SEQUENCE_TAG = 0x10
UTF8STRING_TAG = 0xC
NUMERICSTRING_TAG = 0x12
PRINTABLESTRING_TAG = 0x13
T61STRING_TAG = 0x14
VIDEOTEXSTRING_TAG = 0x15
IA5STRING_TAG = 0x16
GENERALIZEDTIME_TAG = 0x18
GRAPHICSTRING_TAG = 0x19
VISIBLESTRING_TAG = 0x1A
GENERALSTRING_TAG = 0x1B
UNIVERSALSTRING_TAG = 0x1C
BMPSTRING_TAG = 0x1E


class StructBase(object):
    # replace _allowed_attrib_list with __slots__ mechanism
    # once we no longer need to support Python 2.1
    _allowed_attrib_list = []

    def __init__(self, **kw):
        self.set_allowed_attribs(self._allowed_attrib_list)
        # we don't just self.__dict__.update (...) b/c
        # we want error-checking in setattr below
        for k, v in list(kw.items()):
            setattr(self, k, v)

    def __repr__(self):
        s = 'Struct: %s [\n' % (self.__class__)
        i = list(self.__dict__.items())
        i.sort()
        i = [it for it in i if it[0][0] != '_']
        s = s + '\n'.join([repr(it[0]) + ' ' + repr(it[1]) for it in i])

        s = s + ']\n'
        return s

    def __cmp__(self, other):
        keys = list(self.__dict__.keys())
        keys.sort()  # to ensure reproduciblity
        for k in keys:
            s = getattr(self, k, None)
            o = getattr(other, k, None)

            def is_seq(val):
                return (isinstance(val, type((0,))) or
                        isinstance(val, type([])))

            if is_seq(s) and is_seq(o):
                if len(s) != len(o):
                    return -1
                for selt, oelt in zip(s, o):
                    c = cmp(selt, oelt)
                    if c != 0:
                        return c
            else:
                c = cmp(s, o)
                if c != 0:
                    return c
        okeys = list(other.__dict__.keys())
        okeys.sort()
        if okeys != keys:
            return 1
        return 0

    def set_allowed_attribs(self, l):
        self._allowed_attribs = {}
        for e in l:
            self._allowed_attribs[e] = 1

    def is_allowed(self, k):
        if self._allowed_attrib_list == []: return 1
        if k == '_allowed_attribs': return 1
        return k in self._allowed_attribs

    # I implemented setattr b/c otherwise it can be difficult to tell when one
    # has mistyped an OPTIONAL element of a SEQUENCE.  This is probably a matter
    # of taste, and derived classes should feel welcome to override this.
    def __setattr__(self, key, val):
        if not self.is_allowed(key):
            raise AttributeError(key)
        self.__dict__[key] = val


def match_tag(a, b):
    cons_match = (a[0] & ~CONS_FLAG == b[0] & ~CONS_FLAG)
    if a[1] == ANY_TAG or b[1] == ANY_TAG:
        return cons_match
    return a[1] == b[1] and cons_match


def encode_base128(val):
    if val == 0:
        return [0x00]
    l = []
    while val:
        l.append((val % 128) | 0x80)
        val = val // 128
    if len(l) > 0:
        l[0] = l[0] & 0x7F
        l.reverse()
    return l


def read_base128(buf, start):
    val = 0
    while 1:
        b = buf[start]
        start += 1
        val = val * 128 + (b & 0x7F)
        if b & 0x80 == 0:
            break
    return start, val


class CtxBase:
    """Charset codec functionality, shared among all contexts."""

    def __init__(self):
        self.charset_switch_oids = {}
        self.codec_dict_stack = [{}]

    def register_charset_switcher(self, oid, fn):
        self.charset_switch_oids[oid] = fn

    '''
    def set_codec (self, defn_inst, codec, strip_bom = 0):
        # not used?
        # Note: really only need [0] and [1] elements of codec, encoder and decoder
        self.codec_dict_stack[-1][defn_inst.base_tag] = (codec, strip_bom)
    '''

    def get_codec(self, base_tag):
        def default_enc(x):
            return x.encode('utf-8'), 0

        identity = ((default_enc, lambda x: (x, 0)), 0)
        # This will return the identity
        return ((default_enc, lambda x: (x, 0)), 0)
        # return self.codec_dict_stack[-1].get(base_tag, identity)

    def get_enc(self, base_tag):
        # t = self.get_codec(base_tag)
        def default_enc(x):
            return x.encode('utf-8'), 0

        t = ((default_enc, lambda x: (x, 0)), 0)
        return t[0][0], t[1]

    def get_dec(self, base_tag):
        return self.get_codec(base_tag)[0][1]

    '''
    def push_codec (self):
        self.codec_dict_stack.append ({})
    def pop_codec (self):
        self.codec_dict_stack.pop ()
    '''


class IncrementalDecodeCtx(CtxBase):
    states = ["tag_first", "tag_rest", "len_first", "len_rest", "data", "indef_end"]

    class StackElt:
        def __init__(self, start_offset, cur_len, parent_typ, tag, parent_ctx, cname=None):
            self.start_offset = start_offset
            self.len = cur_len
            self.cname = cname
            self.cons = parent_typ.start_cons(tag, cur_len, parent_ctx)
            # methods: get_cur_def (), handle_val (val), finish ()

    def __init__(self, asn1_def):
        CtxBase.__init__(self)
        self.offset = 0
        self.last_begin_offset = 0
        self.state = "tag_first"
        self.asn1_def = asn1_def
        self.decoded_vals = []
        self.stack = []
        self.state_fns = {}
        for state in self.states:
            self.state_fns[state] = getattr(self, 'feed_' + state)

    def get_bytes_inprocess_count(self):
        return self.offset - self.last_begin_offset

    def val_count(self):
        l = len(self.decoded_vals)
        return l

    def get_first_decoded(self):
        rv = self.decoded_vals[0]
        self.decoded_vals = self.decoded_vals[1:]
        return rv

    def get_cur_def(self):
        if len(self.stack) == 0:
            return self.asn1_def
        else:
            tos = self.stack[-1]
            return tos.cons.get_cur_def(self.decoded_tag)

    def match_tag(self, seen):
        typ = self.get_cur_def()
        # Note: use 'is' instead of '=' to avoid  problem w/
        # OCTSTRING_class wanting __eq__ and failing b/c of getattr
        if typ is None:  # falling off end of SEQUENCE with optional bits
            return 0
        return typ.check_tag(seen)

    def set_state(self, new_state):
        self.state = new_state

    def push(self, decoded_len):
        new_typ = self.get_cur_def()
        cname = None
        if isinstance(new_typ, CHOICE):
            (cname, new_typ) = new_typ.check_tag(self.decoded_tag)
        self.stack.append(self.StackElt(self.offset, decoded_len, new_typ, self.decoded_tag, self, cname=cname))

    def pop(self):
        if len(self.stack) == 0:
            self.raise_error("bad end of cons type")
        tos = self.stack.pop()
        if tos.len != None:
            if tos.len != (self.offset - tos.start_offset):
                self.raise_error("constructed len mismatch (%d %d %d)" %
                                 (tos.len, self.offset, tos.start_offset))
        val = tos.cons.finish()
        if tos.cname != None:
            val = (tos.cname, val)
        self.handle_decoded(val)

    def raise_error(self, descr):
        raise BERError(descr + " offset %d" % (self.offset,))

    def feed(self, data):
        for char in data:
            self.state_fns[self.state](char)
            self.offset += 1

    def feed_tag_first(self, char):
        if char == 0x00:
            stacklen = len(self.stack)
            if stacklen == 0 or self.stack[-1].len != None:
                if stacklen == 0:
                    tos_len_str = "irrelevant"
                else:
                    tos_len_str = str(self.stack[-1].len)

                self.raise_error("0x00 tag found, stacklen %d tos len %s" %
                                 (stacklen, tos_len_str))
            self.set_state("indef_end")
            return

        flags = char & 0xE0
        val = char & 0x1f
        self.decoded_tag = (flags, val)
        if val == 0x1f:
            self.set_state("tag_rest")
            self.tag_accum = 0
        else:
            self.finish_tag()

    def feed_tag_rest(self, char):
        self.tag_accum = self.tag_accum * 128 + (char & 0x7f)
        if char & 0x80 == 0:
            self.decoded_tag = (self.decoded_tag[0], self.tag_accum)
            self.tag_accum = None
            self.finish_tag()

    def finish_tag(self):
        if not self.match_tag(self.decoded_tag):
            self.raise_error("Saw tag %s expecting %s" %
                             (str(self.decoded_tag), self.get_cur_def().str_tag()))
        self.set_state("len_first")

    def feed_len_first(self, char):
        if char >= 128:
            rest_len = char & 0x7f
            if rest_len == 0:
                self.decoded_len = None
                self.finish_len()
            else:
                self.rest_len = rest_len
                self.decoded_len = 0
                self.set_state("len_rest")
        else:
            self.decoded_len = char
            self.finish_len()

    def feed_len_rest(self, char):
        self.decoded_len = self.decoded_len * 256 + char
        self.rest_len -= 1
        if self.rest_len == 0:
            self.finish_len()

    def finish_len(self):
        if self.decoded_tag == (0, 0):
            if self.decoded_len != 0:
                self.raise_error("Bad len %d for tag 0" % (self.decoded_len,))
            self.pop()
            return
        self.data_buf = []
        cons_flag = self.decoded_tag[0] & CONS_FLAG
        if cons_flag:
            self.push(self.decoded_len)
            new_state = "tag_first"
        else:
            new_state = "data"
        if self.decoded_len == 0:
            if cons_flag:
                assert (self.check_pop())
                self.set_state("tag_first")
            else:
                self.finish_data()
        else:
            self.set_state(new_state)

    def feed_data(self, char):
        self.data_buf.append(char)
        self.decoded_len -= 1
        if self.decoded_len == 0:
            self.finish_data()

    def finish_data(self):
        cur_def = self.get_cur_def()
        if isinstance(cur_def, CHOICE):
            (cname, ctyp) = cur_def.check_tag(self.decoded_tag)
            cur_def = ctyp
        else:
            cname = None
        if not (cur_def is None):  # we haven't fallen off end of a SEQ
            rv = cur_def.decode_val(self, self.data_buf)
            if cname != None:
                rv = (cname, rv)
            self.handle_decoded(rv)
        else:
            assert (self.check_pop())
        self.set_state("tag_first")

    def handle_decoded(self, val):
        if len(self.stack) == 0:
            self.decoded_vals.append(val)
            self.last_begin_offset = self.offset + 1
            # +1 because self.offset will be incremented on return
        else:
            self.stack[-1].cons.handle_val(val)
            self.check_pop()

    def check_pop(self):
        if self.stack[-1].len == self.offset - self.stack[-1].start_offset:
            self.pop()
            return 1
        return 0

    def feed_indef_end(self, char):
        if char != 0x00:
            self.raise_error("end cons indef-len encoding %x" % (char,))
        self.pop()
        self.set_state("tag_first")


def tag_to_buf(tag, orig_flags=None):
    (flags, val) = tag
    # Constructed encoding is property of original tag, not of
    # implicit tag override
    if orig_flags != None:
        flags = flags | (orig_flags & CONS_FLAG)
    extra = 0
    if val >= 0x1F:
        extra = val
        val = 0x1F
    l = [flags | val]
    if extra:
        l2 = encode_base128(extra)
        l.extend(l2)
    return l


def len_to_buf(mylen):
    if mylen < 128:
        return [mylen]
    else:
        l = []
        while mylen:
            l.append(mylen % 256)
            mylen = mylen // 256
        assert (len(l) < 0x80)
        l.append(len(l) | 0x80)
        l.reverse()
        return l


class WriteCtx(CtxBase):
    def __init__(self):
        CtxBase.__init__(self)
        self.clear()

    def clear(self):
        self.buf = array.array('B')

    def encode(self, spec, data):
        self.clear()
        spec.encode(self, data)
        return self.get_data()

    def get_data(self):
        return self.buf

    def bytes_write(self, data):
        # type-checking is icky but required by array i/f
        if isinstance(data, type([])):
            if len(data) > 0:
                if isinstance(data[0], type(1)):
                    self.buf.fromlist(data)
                else:
                    self.buf.fromlist(list(map(ord, data)))
        elif isinstance(data, type('')):
            # Let's try filling the buffer from the ord values, which look correct. (fromstring seems to be doing something weird)
            self.buf.fromlist(list(map(ord, data)))
            # self.buf.fromstring (data)  # this seems to be dumping extra characters in, namely 194 (decimal value)
        elif isinstance(data, type(b'')):
            self.buf.fromlist(list(data))
        else:
            raise EncodingError("Bad type to bytes_write")


BYTE_BITS = 8


def extract_bits(val, lo_bit, hi_bit):
    tmp = (val & (~0 << (lo_bit))) >> lo_bit
    tmp = tmp & ((1 << (hi_bit - lo_bit + 1)) - 1)
    return tmp


log_of_2 = math.log(2)


def log2(x):
    return int(math.log(x) / log_of_2)


class PERWriteCtx(WriteCtx):
    def __init__(self, aligned=0, canonical=0):
        self.aligned = aligned
        self.canonical = canonical
        self.bit_offset = 0

        WriteCtx.__init__(self)

    def write_bits_unaligned(self, val, bit_len):
        # write starting at bit_offset, no matter what
        byte_count = (bit_len + self.bit_offset) // BYTE_BITS
        if (bit_len + self.bit_offset) % BYTE_BITS != 0:
            byte_count += 1
        my_range = list(range(byte_count - 1, -1, -1))
        lo_bits = [x * BYTE_BITS for x in my_range]

        def extract_val(lo_bit):
            return extract_bits(val, lo_bit, lo_bit + BYTE_BITS - 1)

        bytes = list(map(extract_val, lo_bits))

        new_bit_offset = (bit_len + self.bit_offset) % BYTE_BITS
        if new_bit_offset != 0:
            bytes[-1] = bytes[-1] << (BYTE_BITS - new_bit_offset)
        if self.bit_offset != 0:
            self.buf[-1] = self.buf[-1] | bytes[0]
            self.bytes_write(bytes[1:])
        else:
            self.bytes_write(bytes)
        self.bit_offset = new_bit_offset

    def write_bits(self, val, bit_len):
        if self.aligned and self.bit_offset != 0:
            self.write_bits_unaligned(0, BYTE_BITS - self.bit_offset)
            self.bit_offset = 0
        self.write_bits_unaligned(val, bit_len)

    # for {read,write}_*_int, see Dubuisson 20.4
    def write_constrained_int(self, val, lo, hi):
        assert (hi >= lo)
        # XXX what if hi = lo + 1
        rng = hi - lo + 1
        if not self.aligned:
            self.write_bits(val, log2(rng))
            return

        if rng == 1:
            return  # known value, don't encode
        if rng < 256:
            return  # calc minimum # of bits
        if rng == 256:
            self.write_bits(val - lo, 8)
            return
        if rng <= 65536:
            self.write_bits(val - lo, 16)
            return
        assert (0)

    def write_semiconstrained_int(self, val, lo):
        # write len field, then len, then min octets log_256(val-lo)
        assert (0)
        pass

    def write_unconstrained_int(self, val):  # might have upper bd, but not used
        assert (0)
        pass

    def write_usually_small_int(self, val):
        assert (val >= 0)
        if val < 64:
            self.write_bits_unaligned(0, 1)
            self.write_bits_unaligned(val, 6)
        else:
            self.write_bits_unaligned(1, 1)
            self.write_semiconstrained_int(val, 0)


class BERWriteCtx(WriteCtx):
    def __init__(self):
        WriteCtx.__init__(self)

    def clear(self):
        self.cur_tag = None
        WriteCtx.clear(self)

    def set_implicit_tag(self, tag):
        if self.cur_tag == None:
            self.cur_tag = tag

    def tag_write(self, tag):
        (orig_flags, _) = tag
        if self.cur_tag != None:
            tag = self.cur_tag
            self.cur_tag = None
        l = tag_to_buf(tag, orig_flags)
        self.bytes_write(l)

    def get_pos(self):
        return len(self.buf)

    class LenPlaceHolder:
        def __init__(self, ctx, estlen=127):
            self.ctx = ctx
            self.oldpos = ctx.get_pos()
            self.estlen = estlen
            self.lenlen = ctx.est_len_write(estlen)

        def finish(self):
            real_len = self.ctx.get_pos() - self.oldpos - 1
            self.ctx._len_write_at(self.ctx.get_pos() - self.oldpos - 1, self.oldpos, self.lenlen)

    def len_write(self, mylen=0):
        return Ctx.LenPlaceHolder(self, mylen)

    def len_write_known(self, mylen):
        return self.est_len_write(mylen)

    def est_len_write(self, mylen):
        l = len_to_buf(mylen)
        self.buf.fromlist(l)
        return len(l)

    def _len_write_at(self, mylen, pos, lenlen):
        l = len_to_buf(mylen)
        assert (len(l) >= lenlen)
        # array.pop not available in Python 1.5.2.  We could just use a
        # less efficient length encoding (long form w/leading 0 bytes
        # where necessary), but ...
        # XXX fix to use more efficient code, now that we don't support 1.5.2!
        for i in range(len(l) - lenlen):
            self.buf.insert(pos, 0)
        for i in range(len(l)):
            self.buf[pos + i] = l[i]

    def raise_error(self, descr):
        offset = len(self.buf)
        raise BERError(descr, offset)


Ctx = BERWriteCtx  # Old synonym for historical reasons


# EXPLICIT, IMPLICIT, CHOICE can't derive from eltbase b/c they need to do
# tag manipulation
class ELTBASE:
    # known_len is 1 if len can easily be calculated w/o encoding
    # val (e.g. OCTET STRING),
    # 0 if otherwise and we have to go back and fix up (e.g. SEQUENCE).
    def encode(self, ctx, val):
        ctx.tag_write(self.tag)
        if not self.known_len: lph = ctx.len_write()
        self.encode_val(ctx, val)
        if not self.known_len: lph.finish()

    def check_tag(self, seen_tag):
        return match_tag(seen_tag, self.tag)

    def str_tag(self):
        if hasattr(self, 'tag'):
            return str(self.tag)
        else:
            return self.__class__.__name__

    def fulfill_promises(self, promises):
        return


class TAG:  # base class for IMPLICIT and EXPLICIT
    def __init__(self, tag, cls=CONTEXT_FLAG):
        if type(tag) == type(0):
            tag = (cls, tag)
        self.tag = (tag[0] | self.flags, tag[1])

    def set_typ(self, typ):
        self.typ = typ

    def __call__(self):
        return self.typ()

    def __getitem__(self, *args):
        return self.typ.__getitem__(*args)

    def __setitem__(self, *args):
        return self.typ.__setitem__(*args)

    def get_num_from_name(self, *args):
        return self.typ.get_num_from_name(*args)

    def get_name_from_num(self, *args):
        return self.typ.get_name_from_num(*args)

    def decode_val(self, ctx, buf):
        # used
        return self.typ.decode_val(ctx, buf)

    def str_tag(self):
        return str(self.tag)

    def check_tag(self, seen_tag):
        return match_tag(seen_tag, self.tag)

    def fulfill_promises(self, promises):
        if isinstance(self.typ, Promise):
            self.typ = self.typ.get_promised(promises)
        else:
            self.typ.fulfill_promises(promises)


# Note: IMPLICIT and EXPLICIT have dual use: they can be instantiated by
# users of this module to indicate tagging, but when TAG.set_typ is
# called, they become asn.1 type descriptors themselves.  Maybe these
# two uses should have separate classes, making four classes overall.

class IMPLICIT(TAG):
    flags = 0

    def __repr__(self):
        return "IMPLICIT: " + repr(self.tag) + " " + repr(self.typ)

    def __cmp__(self, other):
        if not isinstance(other, IMPLICIT):
            return -1
        return cmp(self.tag, other.tag)

    def start_cons(self, tag, cur_len, ctx):
        return self.typ.start_cons(tag, cur_len, ctx)

    def encode(self, ctx, val):
        ctx.set_implicit_tag(self.tag)
        self.typ.encode(ctx, val)

    def encode_per(self, ctx, val):
        self.typ.encode_per(ctx, val)


class EXPLICIT(TAG):
    flags = CONS_FLAG  # Explicit tag is always a constructed encoding

    def __repr__(self):
        return "EXPLICIT: " + repr(self.tag) + " " + repr(self.typ)

    def __cmp__(self, other):
        if not isinstance(other, EXPLICIT):
            return -1
        return cmp(self.tag, other.tag)

    class ConsElt:
        def __init__(self, typ):
            self.typ = typ
            self.ind = 0

        def get_cur_def(self, seen_tag):
            return self.typ

        def handle_val(self, val):
            self.tmp = val
            self.ind += 1

        def finish(self):
            if self.ind != 1:
                raise BERError("wrong number of elts %d for EXPLICIT %s" %
                               (self.ind, self.typ))
            return self.tmp

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt(self.typ)

    def encode(self, ctx, val):
        ctx.cur_tag = None
        ctx.tag_write(self.tag)
        lph = ctx.len_write()
        self.typ.encode(ctx, val)
        lph.finish()


def make_tag(tag):
    if implicit_default:
        return IMPLICIT(tag)
    else:
        return EXPLICIT(tag)


def TYPE(tag, typ):
    if tag == None:
        return typ
    if not isinstance(tag, TAG):
        tag = make_tag(tag)
    tag.set_typ(typ)
    return tag


class OidVal:
    def __init__(self, lst):
        self.lst = tuple(lst)
        self.encoded = self.encode(lst)

    def __hash__(self):
        return hash(self.lst)

    def __repr__(self):
        s = 'OID:'
        for i in self.lst:
            s = s + ' %d' % i
        return s

    def __cmp__(self, other):
        if not hasattr(other, 'lst'):
            return -1
        return cmp(self.lst, other.lst)

    def __eq__(self, other):
        return self.lst == other.lst

    def encode(self, lst):
        encoded = [40 * lst[0] + lst[1]]
        for val in lst[2:]:
            encoded = encoded + encode_base128(val)
        return encoded


class OID_class(ELTBASE):
    tag = (0, OID_TAG)
    known_len = 1

    def encode_val(self, ctx, val):
        ctx.len_write_known(len(val.encoded))
        ctx.bytes_write(val.encoded)

    def decode_val(self, ctx, buf):
        # used
        b1 = buf[0]
        oid = [b1 // 40, b1 % 40]
        start = 1
        mylen = len(buf)
        while start < mylen:
            (start, val) = read_base128(buf, start)
            oid.append(val)
        return OidVal(oid)


OID = OID_class()


# XXX need to translate into offset in list for PER encoding
class NamedBase:
    def __init__(self, names_list=[], lo=None, hi=None):
        self.lo = lo
        self.hi = hi
        if names_list == None:
            names_list = []
        self.name_to_num = {}
        self.num_to_name = {}
        self.names_list = names_list
        for (name, num) in names_list:
            self.num_to_name[num] = name
            self.name_to_num[name] = num
        num_keys = list(self.num_to_name.keys())
        if len(num_keys) > 0:
            self.max = max(self.num_to_name.keys())
        else:
            self.max = 0

    def get_num_from_name(self, *args):
        return self.name_to_num.get(*args)

    def get_name_from_num(self, *args):
        return self.num_to_name.get(*args)


class INTEGER_class(ELTBASE, NamedBase):
    tag = (0, INT_TAG)
    known_len = 1

    def __init__(self, *args):
        NamedBase.__init__(self, *args)
        if self.max != 0:
            self.hi = self.max  # XXX reorganize!
        self.extensible = 0  # XXX

    def encode_val(self, ctx, val):
        # based on ber.py in pysnmp
        l = []
        if val == 0:
            l = [0]
        elif val == -1:
            l = [0xFF]
        else:
            if sgn(val) == -1:
                term_cond = -1
                last_hi = 1
            else:
                term_cond = 0
                last_hi = 0
            while val != term_cond:
                val, res = val >> 8, (val & 0xFF)
                l.append(res)
            if (l[-1] & 0x80 != 0) ^ last_hi:
                l.append(last_hi * 0xFF)
        ctx.len_write_known(len(l))
        l.reverse()
        ctx.bytes_write(l)

    def encode_per(self, ctx, val):
        assert (not self.extensible)
        assert (self.lo != None)
        if self.hi == None:
            ctx.write_semiconstrained_int(val, self.lo)
        else:
            ctx.write_constrained_int(val, self.lo, self.hi)

    def decode_val(self, ctx, buf):
        # used
        val = 0
        if buf[0] >= 128:
            sgn = -1
        else:
            sgn = 1
        for b in buf:
            val = 256 * val + sgn * b
        if sgn == -1:
            val = - (val + pow(2, 8 * len(buf)))
        return val


INTEGER = INTEGER_class()


class ConditionalConstr:
    def __getattr__(self, attr):  # XXX replace with properties when can require 2.2.
        if attr == 'tag':
            base_tag = self.__dict__['base_tag']
            if cons_encoding:
                return (CONS_FLAG, base_tag)
            else:
                return (0, base_tag)
        elif attr == 'known_len' and self.override_known_len:
            return not cons_encoding
        else:
            return self.__dict__[attr]


class OCTSTRING_class(ConditionalConstr, ELTBASE):
    def __init__(self, tag=None, lo=None, hi=None):
        if tag != None:
            self.base_tag = tag
        else:
            self.base_tag = OCTSTRING_TAG
        self.override_known_len = 1
        self.extensible = 0  # XXX
        self.lo = lo
        self.hi = hi

    def __repr__(self):
        return 'OCTSTRING: ' + repr(self.tag)

    class ConsElt:
        def __init__(self):
            self.lst = []

        def get_cur_def(self, seen_tag):
            return OCTSTRING

        def handle_val(self, val):
            self.lst.append(val)

        def finish(self):
            return "".join(self.lst)

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt()

    def handle_charset(self, ctx, val):
        encoder, strip_bom = ctx.get_enc(self.base_tag)
        (val, l) = encoder(val)
        if strip_bom:
            val = val[2:]
        return val

    def encode_val(self, ctx, val):
        val = self.handle_charset(ctx, val)
        if cons_encoding:
            # Dubuisson, _ASN.1 ..._, 18.2.10 says that string
            # types are encoded like OCTETSTRING, so no worries
            # about preserving character boundaries in constructed
            # encodings.
            tag = (0, OCTSTRING_TAG)
            for i in range(len(val)):
                ctx.tag_write(tag)
                ctx.len_write_known(1)
                ctx.bytes_write([val[i]])
        else:
            ctx.len_write_known(len(val))
            ctx.bytes_write(val)

    def encode_per(self, ctx, val):
        val = self.handle_charset(ctx, val)
        assert (not self.extensible)
        l = len(val)
        if self.lo != None and self.lo == self.hi:
            if l <= 2:
                ctx.write_bits_unaligned(val, l * BYTE_BITS)
            elif l <= 8192:
                ctx.write_bits(val, l * BYTE_BITS)
            else:
                assert (0)  # XXX need to fragment!

        assert (len < 65536)
        if self.hi == None:
            ctx.write_semiconstrained_int(l, self.lo)
        else:
            ctx.write_constrained_int(l, self.lo, self.hi)
        ctx.write_bits(val, l * BYTE_BITS)

    def decode_val(self, ctx, buf):
        try:
            decoded = codecs.decode(''.join(map(hex, buf)).replace('0x', ''), 'hex').decode('utf-8', errors='strict')
        except:

            decoder = ctx.get_dec(self.base_tag)
            decoded = decoder(''.join(map(chr, buf)))[0]
        return decoded


_STRING_TAGS = (UTF8STRING_TAG, NUMERICSTRING_TAG, PRINTABLESTRING_TAG,
                T61STRING_TAG, VIDEOTEXSTRING_TAG, IA5STRING_TAG,
                GRAPHICSTRING_TAG, VISIBLESTRING_TAG, GENERALSTRING_TAG,
                UNIVERSALSTRING_TAG, BMPSTRING_TAG, GENERALIZEDTIME_TAG,
                OBJECTDESCRIPTOR_TAG)

OCTSTRING = OCTSTRING_class()
(UTF8String, NumericString, PrintableString, T61String, VideotexString,
 IA5String, GraphicString, VisibleString, GeneralString, UniversalString,
 BMPString, GeneralizedTime, ObjectDescriptor) = \
    list(map(OCTSTRING_class, _STRING_TAGS))


class CHOICE:
    choice_type = 1

    # No class.tag, tag derives from chosen arm of CHOICE
    def __init__(self, c):
        self.promises_fulfilled = 0
        # XXX self.promises_fulfilled is only needed for CHOICE,
        # but could speed up by adding checking to SEQUENCE, SEQUENCE_OF, etc.

        self.choice = []
        # XXX rework this to use dict by arm name, dict by tag?
        # but CHOICE of CHOICE constructs mean that a typ can have
        # multiple possible tags, so a little more difficult
        for arm in c:
            self.choice.append(self.mung(arm))

    def __getitem__(self, key):
        for (cname, ctyp) in self.choice:
            if key == cname:
                return ctyp
        raise KeyError(key)

    def __setitem__(self, key, val):  # warning: may raise KeyError!
        for i in range(len(self.choice)):
            (cname, ctyp) = self.choice[i]
            if cname == key:
                self.set_arm(i, val)
                return
        raise KeyError(key)

    def fulfill_promises(self, promises):
        if self.promises_fulfilled:
            return
        self.promises_fulfilled = 1
        for i in range(len(self.choice)):
            if isinstance(self.choice[i][1], Promise):
                self.choice[i][1] = self.choice[i][1].get_promised(promises)
            else:
                self.choice[i][1].fulfill_promises(promises)

    def set_arm(self, i, new_arm):
        self.choice[i] = self.mung(new_arm)

    def mung(self, arm):
        (cname, ctag, ctyp) = arm
        ctyp = TYPE(ctag, ctyp)
        return [cname, ctyp]

    def str_tag(self):
        return repr(self)

    def check_tag(self, seen_tag):
        for (cname, ctyp) in self.choice:
            if ctyp.check_tag(seen_tag):
                return (cname, ctyp)
        return 0

    def __repr__(self):
        return "CHOICE: " + "\n".join([x[0] for x in self.choice])

    # Note: we don't include types in the repr, because that can induce
    # infinite recursion.
    def encode(self, ctx, val):
        (name, val) = val
        for (cname, ctyp) in self.choice:
            if cname == name:
                ctyp.encode(ctx, val)
                return
        err = ("Bogus, no arm for " + repr(name) + " val " +
               repr(val))
        raise EncodingError(err)


class ANY_class(OCTSTRING_class):  # inherit decode_val
    tag = (CONS_FLAG, ANY_TAG)

    class ConsElt:
        def __init__(self, tag, cur_len):
            self.tmp = []
            self.tag = tag
            self.indef_flag = cur_len == None

        def get_cur_def(self, seen_tag):
            return ANY

        def handle_val(self, val):
            self.tmp.append(val)

        def finish(self):
            return (self.tag, self.tmp, self.indef_flag)

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt(tag, cur_len)

    def encode_aux(self, val):
        (tag, val, indef_flag) = val
        if isinstance(val, type([])):
            buf = "".join(map(self.encode_aux, val))
        elif isinstance(val, type(())):
            buf = self.encode_aux(val)
        else:
            buf = val

        def tostr(lst):
            return "".join(map(chr, lst))

        buf_len = len(buf)
        return tostr(tag_to_buf(tag)) + tostr(len_to_buf(buf_len)) + buf

    def encode(self, ctx, val):
        ctx.bytes_write(self.encode_aux(val))

    def check_tag(self, seen_tag):
        return 1

    def decode_val(self, ctx, buf):
        # used
        v = OCTSTRING_class.decode_val(self, ctx, buf)
        return (ctx.decoded_tag, v, 0)  # only called for primitive def-len encoding, thus "0"


ANY = ANY_class()


class BitStringVal:
    def __init__(self, top, bits=0, defn=None):
        self.top_ind = top  # 0-based, -1 is valid, indicating no sig. bits
        self.bits = bits
        self.defn = defn

    def __repr__(self):
        names = []
        for i in range(self.top_ind + 1):
            if self.is_set(i):
                def mk_unk():
                    return "Unknown(%d)" % (i,)

                if (not hasattr(self.defn, 'num_to_name') or
                        self.defn.num_to_name == None):
                    names.append(mk_unk())
                else:
                    names.append(self.defn.num_to_name.get(i, mk_unk()))
        return "Top: %s Bits %s Names %s" % (repr(self.top_ind),
                                             repr(self.bits),
                                             ",".join(names))

    def __cmp__(self, other):
        return cmp((self.top_ind, self.bits), (other.top_ind, other.bits))

    def check_extend(self, bit):
        if bit > self.top_ind:
            self.bits = self.bits << (bit - self.top_ind)
            self.top_ind = bit

    def set(self, bit):
        self.check_extend(bit)
        self.bits = self.bits | (1 << (self.top_ind - bit))

    def clear(self, bit):
        self.check_extend(bit)
        self.bits = self.bits & ~(1 << (self.top_ind - bit))

    def set_bits(self, bitseq):
        for bit in bitseq:
            self.set(bit)

    def is_set(self, bit):
        if self.top_ind - bit < 0:
            return 0
        return self.bits & (1 << (self.top_ind - bit))

    def __getitem__(self, bit_name):
        bit_ind = self.defn.get_num_from_name(bit_name)
        return self.is_set(bit_ind)

    def __setitem__(self, key, val):
        ind = self.defn.get_num_from_name(key)
        if val:
            self.set(ind)
        else:
            self.clear(ind)


class BITSTRING_class(ConditionalConstr, ELTBASE, NamedBase):
    known_len = 1

    def __init__(self, *args):
        self.base_tag = BITSTRING_TAG
        self.override_known_len = 0
        NamedBase.__init__(self, *args)

    def __call__(self):
        return BitStringVal(self.max, 0, self)

    class ConsElt:
        def __init__(self, parent):
            self.lst = []
            self.parent = parent

        def get_cur_def(self, seen_tag):
            return BITSTRING

        def handle_val(self, val):
            self.lst.append(val)

        def finish(self):
            bits = 0
            for v in self.lst[:-1]:
                bits *= 256
                assert (v.top_ind == 7)
                bits += v.bits
            v = self.lst[-1]
            bits *= 256

            pad_count = 7 - v.top_ind
            bits = bits >> pad_count
            bits += v.bits  # v.bits have already been right-shifted by decoder
            return BitStringVal(8 * len(self.lst) - pad_count - 1, bits, self.parent)

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt(self)

    def encode_val(self, ctx, val):
        def top_ind_to_pad_bits(top_ind):
            bit_count = (top_ind + 1) % 8  # top_ind is 0-based
            if bit_count == 0: return 0
            return (8 - bit_count)

        assert (top_ind_to_pad_bits(0) == 7)
        assert (top_ind_to_pad_bits(7) == 0)
        assert (top_ind_to_pad_bits(8) == 7)
        assert (top_ind_to_pad_bits(10) == 5)
        assert (top_ind_to_pad_bits(15) == 0)

        pad_bits_count = top_ind_to_pad_bits(val.top_ind)

        val_len = ((val.top_ind + 1) // 8) + 1
        # + 1 for count of padding bits, count always 1 byte
        if pad_bits_count != 0:
            val_len += 1
        l = []
        to_write = (1 * val.bits) << pad_bits_count
        for i in range(val_len - 1):
            l.append(to_write % 256)
            to_write = to_write // 256

        assert (to_write >= 0)
        if not cons_encoding:
            ctx.len_write_known(val_len)
            l.append(pad_bits_count)
            l.reverse()
            ctx.bytes_write(l)
        else:
            ctx.bytes_write([0x80])  # Dubuisson p. 403 says indef-len req'd
            l.reverse()
            for i in range(len(l) - 1):
                v = [0x3, 0x2, 0x0, l[i]]
                ctx.bytes_write(v)
            v = [0x3, 0x2, pad_bits_count, l[-1]]
            ctx.bytes_write(v)
            ctx.bytes_write([0x00, 0x00])

    def decode_val(self, ctx, buf):
        pad_bits = buf[0]
        bits = 0
        for b in buf[1:]:
            bits = 256 * bits + b
        bits = bits >> pad_bits
        return BitStringVal((len(buf) - 1) * 8 - pad_bits - 1, bits,
                            self)


BITSTRING = BITSTRING_class()


class SeqConsElt:
    def __init__(self, seq):
        self.index = 0
        self.seq = seq
        self.tmp = seq.klass()

    def get_cur_def(self, seen_tag):
        r = list(range(self.index, len(self.seq.seq)))

        for i in r:
            (name, typ, optional) = self.seq.seq[i]
            if typ.check_tag(seen_tag):
                self.index = i
                return typ
            if not optional:
                raise BERError("SEQUENCE tag %s not found in %s (%d/%d)" %
                               (str(seen_tag), str(self.seq),
                                self.index, i))

        # OK, we fell off the end.  Must just be absent OPTIONAL types.
        return None

    def handle_val(self, val):
        setattr(self.tmp, self.seq.seq[self.index][0], val)
        self.index += 1

    def finish(self):
        for i in range(self.index, len(self.seq.seq)):
            (name, typ, optional) = self.seq.seq[i]
            if not optional:
                raise BERError(
                    "non-opt data missing from seq %s at %d (so far %s)" %
                    (str(self.seq), self.index, str(self.tmp)))
        return self.tmp


class SEQUENCE_BASE(ELTBASE):
    tag = (CONS_FLAG, SEQUENCE_TAG)
    known_len = 0

    def __init__(self, klass, seq):
        self.klass = klass
        self.seq = []
        for e in seq:
            self.seq.append(self.mung(e))
        self.extensible = 0

    def __call__(self, **kw):
        return self.klass(*(), **kw)

    def mung(self, e):
        if len(e) == 3:
            (name, tag, typ) = e
            optional = 0
        elif len(e) == 4:
            (name, tag, typ, optional) = e
        else:
            assert (len(e) == 3 or len(e) == 4)
        typ = TYPE(tag, typ)
        return (name, typ, optional)

    def __repr__(self):
        return ('SEQUENCE: ' + repr(self.klass) + '\n' + '\n'.join(list(map(repr, self.seq))))

    def __getitem__(self, key):
        for e in self.seq:
            if e[0] == key:
                return e[1]
        raise KeyError(key)

    def __setitem__(self, key, val):
        for i in range(len(self.seq)):
            if self.seq[i][0] == key:
                self.seq[i] = self.mung(val)
                return
        raise "not found" + str(key)

    def fulfill_promises(self, promises):
        for i in range(len(self.seq)):
            (name, typ, optional) = self.seq[i]
            if isinstance(typ, Promise):
                self.seq[i] = (name, typ.get_promised(promises), optional)
            else:
                typ.fulfill_promises(promises)

    def get_attribs(self):
        return [e[0] for e in self.seq]

    def start_cons(self, tag, cur_len, ctx):
        return SeqConsElt(self)

    def encode_per(self, ctx, val):
        any_optional = 0  # XXX replace w/ every
        for (attrname, typ, optional) in self.seq:
            any_optional = any_optional or optional
        if any_optional:
            for (attrname, typ, optional) in self.seq:
                ctx.write_bits_unaligned(hasattr(val, attrname), 1)
        for (attrname, typ, optional) in self.seq:
            try:
                v = getattr(val, attrname)
                # XXX need to handle DEFAULT,not encode
            except AttributeError:
                if optional:
                    continue
                else:
                    raise EncodingError("Val " + repr(val) +
                                        " missing attribute: " +
                                        str(attrname))
            typ.encode_per(ctx, v)

    def encode_val(self, ctx, val):
        for (attrname, typ, optional) in self.seq:
            try:
                v = getattr(val, attrname)
            except AttributeError:
                if optional:
                    continue
                else:
                    raise EncodingError("Val " + repr(val) +
                                        " missing attribute: " +
                                        str(attrname))
            typ.encode(ctx, v)


# SEQUENCE returns an object which is both an asn.1 spec and a callable
# which generates a struct template to fill in.

# I used to have SEQUENCE taking a classname and, using ~8 lines of
# black (OK, grayish) magic (throw an exn, catch it, and futz with the
# caller's locals dicts), bind the klass below in the caller's namespace.
# This meant I could provide bindings for SEQUENCEs nested inside other
# definitions (making my specs look more like the original ASN.1), and
# that I got the correct name for debugging purposes instead of using
# mk_klass_name ().  I took it out b/c I didn't like the magic or the
# funny syntax it used (a mere function call caused an alteration to the
# caller's ns)

# Now, the compiler takes care of generating the correct names for
# top-level SEQUENCE definitions, and should be extended to handle
# SEQUENCEs nested inside others.

class Ctr:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count = self.count + 1
        return self.count


class_count = Ctr()


# This name only appears in debugging displays, so no big deal.
def mk_seq_class_name():
    return "seq_class_%d" % class_count()


class EXTERNAL_class(SEQUENCE_BASE):
    tag = (CONS_FLAG, EXTERNAL_TAG)

    def __repr__(self):
        return ('EXTERNAL: ' + repr(self.klass) + '\n' + '\n'.join(list(map(repr, self.seq))))

    class ConsElt(SeqConsElt):
        def __init__(self, seq, ctx):
            self.ctx = ctx
            self.codec_pushed = 0
            SeqConsElt.__init__(self, seq)

        def get_cur_def(self, seen_tag):
            self.found_ext_ANY = 0
            r = list(range(self.index, len(self.seq.seq)))
            for i in r:
                (name, typ, optional) = self.seq.seq[i]
                if typ.check_tag(seen_tag):
                    self.index = i
                    if name == 'encoding' and seen_tag[1] == 0:
                        asn = check_EXTERNAL_ASN(self.tmp)
                        if asn != None:
                            self.found_ext_ANY = 1
                            typ = asn
                            new_codec_fn = self.ctx.charset_switch_oids.get(
                                getattr(self.tmp, 'direct_reference',
                                        None), None)
                            if new_codec_fn != None:
                                self.ctx.push_codec()
                                new_codec_fn()
                                self.codec_pushed = 1
                    return typ
                if not optional:
                    raise BERError("EXTERNAL tag %s not found in %s (%d/%d)" %
                                   (str(seen_tag), str(self.seq),
                                    self.index, i))
            # This is, in fact, an error, because the last bit of
            # external isn't optional
            raise BERError("EXTERNAL tag %s not found" % (str(seen_tag),))

        def handle_val(self, val):
            if self.found_ext_ANY:
                val = ('single-ASN1-type', val)
                if self.codec_pushed:
                    self.ctx.pop_codec()
            SeqConsElt.handle_val(self, val)

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt(self, ctx)

    def encode_val(self, ctx, val):
        new_codec_fn = None
        for (attrname, typ, optional) in self.seq:
            try:
                v = getattr(val, attrname)
            except AttributeError:
                if optional:
                    continue
                else:
                    raise EncodingError(f'Val {repr(val)} missing attribute: {str(attrname)}')
            if attrname == 'encoding' and v[0] == 'single-ASN1-type':
                asn = check_EXTERNAL_ASN(val)
                if asn:
                    typ = asn
                    v = v[1]
                    new_codec_fn = ctx.charset_switch_oids.get(getattr(val, 'direct_reference', None), None)
                    if new_codec_fn:
                        ctx.push_codec()
                        new_codec_fn()
            typ.encode(ctx, v)
        if new_codec_fn:
            ctx.pop_codec()


# XXX rename all these
def SEQUENCE(spec, base_typ=SEQUENCE_BASE, seq_name=None, extra_bases=None):
    if not seq_name:
        seq_name = mk_seq_class_name()
    bases = [StructBase]
    if extra_bases:
        bases = extra_bases + bases
    klass = type(seq_name, tuple(bases), {})
    seq = base_typ(klass, spec)
    klass._allowed_attrib_list = seq.get_attribs()
    seq.klass = klass
    return seq


# This is the pre-1994 def'n.  Note that post-1994 removes the ANY
# and BITSTRING options
EXTERNAL = SEQUENCE([('direct_reference', None, OID, 1),
                     ('indirect_reference', None, INTEGER, 1),
                     ('data_value_descriptor', None, ObjectDescriptor, 1),
                     ('encoding', None,
                      CHOICE([('single-ASN1-type', EXPLICIT(0), ANY),
                              ('octet-aligned', 1, OCTSTRING),
                              ('arbitrary', 2, BITSTRING)]))],
                    EXTERNAL_class,
                    seq_name='EXTERNAL')

import math


class REAL_class(SEQUENCE_BASE):
    tag = (CONS_FLAG, REAL_TAG)


class REAL_val:
    _mantissa_bits = 20

    def __repr__(self):
        return 'REAL %f' % (self.get_val())

    def set_val(self, val):
        m, e = math.frexp(val)
        self.mantissa = int(m * pow(2, self._mantissa_bits))
        self.base = 2
        self.exponent = e - self._mantissa_bits
        return self

    def get_val(self):
        return self.mantissa * pow(self.base, self.exponent)


REAL = SEQUENCE([('mantissa', None, INTEGER),
                 ('base', None, INTEGER),
                 ('exponent', None, INTEGER)],
                REAL_class,
                seq_name='REAL',
                extra_bases=[REAL_val])

REAL.get_val = lambda self: (self.mantissa * 1.0 / self.base) * pow(self.base, self.exponent)
REAL.__str__ = lambda self: "REAL %f" % (self.get_val(),)

_oid_to_asn1_dict = {}


def register_oid(oid, asn):
    tmp = EXPLICIT(0)  # b/c ANY is EXPLICIT 0 arm of EXTERNAL CHOICE
    tmp.set_typ(asn)
    # Hash the object so that it can be used as a dictionary key
    _oid_to_asn1_dict[hash(OidVal(oid))] = tmp


def check_EXTERNAL_ASN(so_far):
    assert (so_far.__class__ == EXTERNAL.klass)  # only called from w/in EXTERNAL
    dir_ref = getattr(so_far, 'direct_reference', None)
    if hash(dir_ref) == None:
        return

    # Hash the object so that it can be used as a dictionary key
    rv = _oid_to_asn1_dict.get(hash(dir_ref), None)
    return rv


class SEQUENCE_OF(ELTBASE):
    tag = (CONS_FLAG, SEQUENCE_TAG)
    known_len = 0

    def __init__(self, typ):
        self.typ = typ

    def __getitem__(self, key):
        if key == 0:
            return self.typ
        raise KeyError(key)

    def fulfill_promises(self, promises):
        if isinstance(self.typ, Promise):
            self.typ = self.typ.get_promised(promises)
        else:
            self.typ.fulfill_promises(promises)

    class ConsElt:
        def __init__(self, typ):
            self.typ = typ
            self.lst = []

        def get_cur_def(self, seen_tag):
            return self.typ

        def handle_val(self, val):
            self.lst.append(val)

        def finish(self):
            return self.lst

    def start_cons(self, tag, cur_len, ctx):
        return self.ConsElt(self.typ)

    def encode_val(self, ctx, val):
        for e in val:
            self.typ.encode(ctx, e)


class SET_OF(SEQUENCE_OF):  # XXX SET_OF needs more implementation
    pass


def sgn(val):
    if val < 0: return -1
    if val == 0: return 0
    return 1


class BOOLEAN_class(ELTBASE):
    tag = (0, BOOL_TAG)
    known_len = 1

    def encode_val(self, ctx, val):
        ctx.len_write_known(1)
        ctx.bytes_write([val != 0])
        # if val is multiple of 256, Python would treat as true, but
        # just writing val would truncate. Thus, write val <> 0

    def encode_per(self, ctx, val):
        ctx.write_bits_unaligned(val != 0, 1)

    def decode_val(self, ctx, buf):
        # used
        mylen = len(buf)
        if mylen != 1: ctx.raise_error("Bogus length for bool " + repr(mylen))
        return not not buf[0]


BOOLEAN = BOOLEAN_class()


class NULL_class(ELTBASE):
    tag = (0, NULL_TAG)
    known_len = 1

    def encode_val(self, ctx, val):
        ctx.len_write_known(0)

    def encode_per(self, ctx, val):
        pass

    def decode_val(self, ctx, buf):
        # may not be used
        if len(buf) > 0: ctx.raise_error("Bad length for NULL" + str(buf))
        return None


NULL = NULL_class()


class ENUM(INTEGER_class):
    def __init__(self, *args, **kw):
        super().__init__(*args)
        self.__dict__.update(kw)


OBJECT_IDENTIFIER = OID


class Promise(ELTBASE):
    """Placeholder for generating recursive data structures.
    Replaced by calling fulfill_promises method."""

    def __init__(self, type_name):
        self.type_name = type_name

    def get_promised(self, promises_dict):
        return promises_dict[self.type_name]

    def __str__(self):
        return 'Promise: ' + self.type_name
