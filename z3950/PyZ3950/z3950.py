from __future__ import print_function, absolute_import

import socket

from z3950.PyZ3950.zdefs import *

#out_encoding = None

class Z3950Error(Exception):
    pass

# Note: following 3 exceptions are defaults, but can be changed by
# calling conn.set_exs

class ConnectionError(Z3950Error): # TCP or other transport error
    pass

class ProtocolError(Z3950Error): # Unexpected message or badly formatted
    pass

class UnexpectedCloseError(ProtocolError):
    pass

vers = '0.62'
DEFAULT_PORT = 2101
default_resultSetName = "ResultSet"

class Conn:
    rdsz = 65536
    def __init__(self, sock = None):
        self.ConnectionError = ConnectionError
        self.ProtocolError = ProtocolError
        self.UnexpectedCloseError = UnexpectedCloseError
        if sock is None:
            self.sock = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
        else:
            self.sock = sock

        self.decode_ctx = asn1.IncrementalDecodeCtx (APDU)
        self.encode_ctx = asn1.Ctx ()


    def set_codec(self, charset_name, charsets_in_records):
        self.charset_name = charset_name
        self.charsets_in_records = not not charsets_in_records
        strip_bom = self.charset_name == 'utf-16'
        if self.charset_name is not None:
            self.encode_ctx.set_codec(asn1.GeneralString, codecs.lookup (self.charset_name), strip_bom)
            self.decode_ctx.set_codec(asn1.GeneralString, codecs.lookup (self.charset_name), strip_bom)
            if not charsets_in_records:
                register_retrieval_record_oids(self.decode_ctx)
                register_retrieval_record_oids(self.encode_ctx)

    def readproc(self):
        if self.sock is None:
            raise self.ConnectionError ('disconnected')
        try:
            b = self.sock.recv (self.rdsz)
        except socket.error as val:
            self.sock = None
            raise self.ConnectionError ('socket', str (val))
        if len (b) == 0: # graceful close
            self.sock = None
            raise self.ConnectionError ('graceful close')
        return b
    def read_PDU (self):
        while 1:
            if self.decode_ctx.val_count () > 0:
                return self.decode_ctx.get_first_decoded ()
            try:
                b = self.readproc ()
                c = self.decode_ctx.feed (b)
            except asn1.BERError as val:
                raise self.ProtocolError ('ASN1 BER', str(val))


def extract_apt(rpnQuery):
    """Takes RPNQuery to AttributePlusTerm"""
    RPNStruct = rpnQuery.rpn
    assert (RPNStruct [0] == 'op')
    operand = RPNStruct [1]
    assert (operand [0] == 'attrTerm')
    return operand [1]


class Client(Conn):

    def __init__ (self, addr, port=DEFAULT_PORT, optionslist=None,
                  charset='utf-8', lang=None, user=None, password=None,
                  group=None, implementationId="",
                  implementationName="", implementationVersion=""):

        Conn.__init__ (self)
        try:
            self.sock.connect ((addr, port))
        except socket.error as val:
            self.sock = None
            raise self.ConnectionError ('socket', str(val))

        # charset = ['utf-8',]
        #negotiate_charset = 0 # charset or lang

        if user or password or group:
            authentication = (user, password, group)
        else:
            authentication = None

        InitReq = make_initreq (optionslist, authentication = authentication,
                                implementationId = implementationId,
                                implementationName = implementationName,
                                implementationVersion = implementationVersion)

        self.initresp = self.transact (('initRequest', InitReq), 'initResponse')

        self.search_results = {}
        self.max_to_request = 20
        self.default_recordSyntax = Z3950_RECSYN_USMARC_ov

    def get_option (self, option_name):
        return self.initresp.options[option_name]

    def transact (self, to_send, expected):
        b = self.encode_ctx.encode(APDU, to_send)

        if self.sock is None:
            raise self.ConnectionError('disconnected')
        try:
            self.sock.send (b)
        except socket.error as val:
            self.sock = None
            raise self.ConnectionError('socket', str(val))

        if expected is None:
            return

        pdu = self.read_PDU()
        (arm, val) = pdu
        if arm == expected: # may be 'close'
            return val
        elif arm == 'close':
            raise self.UnexpectedCloseError(
                "Server closed connection reason %d diag info %s" % \
                (getattr (val, 'closeReason', -1),
                 getattr (val, 'diagnosticInformation', 'None given')))
        else:
            raise self.ProtocolError("Unexpected response from server %s %s " % (expected, repr ((arm, val))))

    def set_dbnames (self, dbnames):
        self.dbnames = dbnames

    def search_2 (self, query, rsn='default', **kw):
        sreq = make_sreq (query, self.dbnames, rsn, **kw)
        recv = self.transact (('searchRequest', sreq), 'searchResponse')
        self.search_results [rsn] = recv
        return recv

    def search (self, query, rsn='default', **kw):
        recv = self.search_2 (('type_1', query), rsn, **kw)
        return recv.searchStatus and (recv.resultCount > 0)

    def get_count (self, rsn='default'):
        return self.search_results[rsn].resultCount

    def present (self, rsn='default', start = None, count = None, recsyn = None, esn = None):
        try:
            sresp = self.search_results [rsn]
            if start:
                start = sresp.nextResultSetPosition
                if count:
                    count = sresp.resultCount
                    if self.max_to_request > 0:
                        count = min (self.max_to_request, count)
        except:
            pass
        if recsyn:
            recsyn = self.default_recordSyntax
        preq = PresentRequest ()
        preq.resultSetId = rsn
        preq.resultSetStartPoint = start
        preq.numberOfRecordsRequested = count
        preq.preferredRecordSyntax = recsyn
        if esn:
            preq.recordComposition = ('simple', esn)
        return self.transact (('presentRequest', preq), 'presentResponse')

    '''
    def scan(self, query, **kw):
        sreq = ScanRequest ()
        sreq.databaseNames = self.dbnames
        assert (query[0] == 'type_1' or query [0] == 'type_101')
        sreq.attributeSet = query[1].attributeSet
        sreq.termListAndStartPoint = extract_apt(query[1])
        sreq.numberOfTermsRequested = 20
        for (key, val) in list(kw.items ()):
            setattr (sreq, key, val)
        return self.transact(('scanRequest', sreq), 'scanResponse')
    '''

    def close (self):
        close = Close ()
        close.closeReason = 0
        close.diagnosticInformation = 'Normal close'
        try:
            rv =  self.transact (('close', close), 'close')
        except self.ConnectionError:
            rv = None
        if self.sock:
            self.sock.close ()
            self.sock = None
        return rv
