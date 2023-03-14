#!/usr/bin/env python

"""Implements the ZOOM 1.4 API (http://zoom.z3950.org/api) for Z39.50."""
from z3950.Marc.marc_tools import Record
from z3950.PyZ3950 import z3950
from z3950.PyZ3950 import ccl
from z3950.PyZ3950 import asn1
from z3950.PyZ3950 import bib1msg
from z3950.PyZ3950 import oids

asn1.register_oid (oids.Z3950_QUERY_SQL, z3950.SQLQuery)

class ZoomError(Exception):
    """Base class for all errors reported from this module"""
    pass

class ConnectionError(ZoomError):
    """Exception for TCP error"""
    pass

class ClientNotImplError(ZoomError):
    """Exception for ZOOM client-side functionality not implemented"""
    pass

class ServerNotImplError(ZoomError):
    """Exception for function not implemented on server"""
    pass

class QuerySyntaxError(ZoomError):
    """Exception for query not parsable by client"""
    pass

class ProtocolError(ZoomError):
    """Exception for malformatted server response"""
    pass

class UnexpectedCloseError(ProtocolError):
    """Exception for unexpected (z3950, not tcp) close from server"""
    pass

class UnknownRecSyn(ZoomError):
    """Exception for unknown record syntax returned from server"""
    pass

class Bib1Err(ZoomError):
    """Exception for BIB-1 error"""
    def __init__ (self, condition, message, addtlInfo):
        self.condition = condition
        self.message = message
        self.addtlInfo = addtlInfo
        ZoomError.__init__ (self)

    def __str__ (self):
        return "Bib1Err: %d %s %s" % (self.condition, self.message, self.addtlInfo)


class _ErrHdlr:
    """Error-handling services"""
    err_attrslist = ['errCode','errMsg', 'addtlInfo']
    def err (self, condition, addtlInfo, oid):
        """Translate condition + oid to message, save, and raise exception"""
        self.errCode = condition
        self.errMsg  = bib1msg.lookup_errmsg (condition, oid)
        self.addtlInfo = addtlInfo
        raise Bib1Err (self.errCode, self.errMsg, self.addtlInfo)
    def err_diagrec (self, diagrec):
        (typ, data) = diagrec
        if typ == 'externallyDefined':
            raise ClientNotImplError("Unknown external diagnostic" + str (data))
        addinfo = data.addinfo [1] # don't care about v2 vs v3
        self.err (data.condition, addinfo, data.diagnosticSetId)

def _extract_attrs (obj, attrlist):
    kw = {}
    for key in attrlist:
        if hasattr (obj, key):
            kw[key] = getattr (obj, key)
    return kw

class _AttrCheck:
    """Prevent typos"""
    attrlist = []
    not_implement_attrs = []
    def __setattr__ (self, attr, val):
        """Ensure attr is in attrlist (list of allowed attributes), or
        private (begins w/ '_'), or begins with 'X-' (reserved for users)"""
        if attr[0] == '_' or attr in self.attrlist or attr[0:2] == 'X-':
            self.__dict__[attr] = val
        elif attr in self.not_implement_attrs:
            raise ClientNotImplError(attr)
        else:
            raise AttributeError (attr, val)
    
class Connection(_AttrCheck, _ErrHdlr):
    """Connection object"""

    not_implement_attrs = ['piggyback',
                        'schema',
                        'proxy',
                        'async']
    search_attrs = ['smallSetUpperBound',
                'largeSetLowerBound',
                'mediumSetPresentNumber',
                'smallSetElementSetNames',
                'mediumSetElementSetNames']
    init_attrs = ['user',
                  'password',
                  'group',
                  'lang',
                  'charset',
                  'implementationId',
                  'implementationName',
                  'implementationVersion'
                  ]
    scan_zoom_to_z3950 = {
        # translate names from ZOOM spec to Z39.50 spec names
        'stepSize' : 'stepSize',
        'numberOfEntries' : 'numberOfTermsRequested',
        'responsePosition' : 'preferredPositionInResponse'
        }

    attrlist = search_attrs + init_attrs + list(scan_zoom_to_z3950.keys ()) + [
        'databaseName',
        'namedResultSets',
        'preferredRecordSyntax',
        'elementSetName',
        'presentChunk',
        'targetImplementationId',
        'targetImplementationName',
        'targetImplementationVersion',
        'host',
        'port',
        ] + _ErrHdlr.err_attrslist

    _queryTypes = ['RPN',]
    _cli = None
    host = ""
    port = 0

    namedResultSets = 1
    elementSetName = 'F' 
    preferredRecordSyntax = 'USMARC'
    stepSize = 0
    numberOfEntries = 20 # for SCAN
    responsePosition = 1
    databaseName = 'Default'
    implementationId = 'British Library - contact metadata@bl.uk'
    implementationName = 'British Library'
    implementationVersion = '1.0 beta'
    lang = None
    charset = 'utf-8'
    user = None
    password = None
    group = None
    presentChunk = 20

    def __init__(self, host, port, connect=True, **kw):
        self.host = host
        self.port = port
        self._resultSetCtr = 0
        for (k,v) in list(kw.items ()):
            setattr(self, k, v)
        if connect:
            self.connect()

    def connect(self):
        self._resultSetCtr += 1
        self._lastConnectCtr = self._resultSetCtr
        
        # Bump counters first, since even if we didn't reconnect
        # this time, we could have, and so any use of old connections
        # is an error.  (Old cached-and-accessed data is OK to use:
        # cached but not-yet-accessed data is probably an error, but
        # a not-yet-caught error.)
        
        if self._cli and self._cli.sock:
            return
        
        initkw = {}
        for attr in self.init_attrs:
            initkw[attr] = getattr(self, attr)
        self._cli = z3950.Client (self.host, self.port, optionslist = [], **initkw)
        self.namedResultSets = self._cli.get_option ('namedResultSets')
        self.targetImplementationId = getattr (self._cli.initresp, 'implementationId', None)
        self.targetImplementationName = getattr (self._cli.initresp, 'implementationName', None)
        self.targetImplementationVersion  = getattr (self._cli.initresp, 'implementationVersion', None)
        if hasattr (self._cli.initresp, 'userInformationField'):
            # weird.  U of Chicago returns an EXTERNAL with nothing
            # but 'encoding', ('octet-aligned', '2545') filled in.
            if (hasattr (self._cli.initresp.userInformationField, 'direct_reference') and
                self._cli.initresp.userInformationField.direct_reference == oids.Z3950_USR_PRIVATE_OCLC_INFO_ov):
                # see http://www.oclc.org/support/documentation/firstsearch/z3950/fs_z39_config_guide/ for docs
                oclc_info = self._cli.initresp.userInformationField.encoding [1]
                if hasattr (oclc_info, 'failReason'):
                    raise UnexpectedCloseError ('OCLC_Info ', oclc_info.failReason, getattr (oclc_info, 'text', ' no text given '))
            
        

    def search (self, query):
        """Search, taking Query object, returning ResultSet"""
        if not self._cli:
            self.connect()
        assert (query.typ in self._queryTypes)
        dbnames = self.databaseName.split ('+')
        self._cli.set_dbnames (dbnames)
        cur_rsn = self._make_rsn ()
        recv = self._cli.search_2 (query.query, rsn = cur_rsn, **_extract_attrs (self, self.search_attrs))
        self._resultSetCtr += 1
        rs = ResultSet (self, recv, cur_rsn, self._resultSetCtr)
        return rs

    def _make_rsn (self):
        """Return result set name"""
        if self.namedResultSets:
            return "rs%d" % self._resultSetCtr
        else:
            return 'default'
    def close (self):
        """Close connection"""
        self._cli.close ()

class Query:
    def __init__ (self, query):
       self.typ = 'RPN'
       try:
           self.query = ccl.mk_rpn_query(query)
       except ccl.QuerySyntaxError as err:
           raise QuerySyntaxError (str(err))



class ResultSet(_AttrCheck, _ErrHdlr):
    """Cache results, presenting read-only sequence interface.  If
    a surrogate diagnostic is returned for the i-th record, an
    appropriate exception will be raised on access to the i-th
    element (either access by itself or as part of a slice)."""

    inherited_elts = ['elementSetName', '', 'presentChunk']
    attrlist = inherited_elts + _ErrHdlr.err_attrslist
    not_implement_attrs = ['piggyback', 'schema']

    def __init__ (self, conn, searchResult, resultSetName, ctr):
        """Only for creation by Connection object"""
        self._conn = conn
        self._searchResult = searchResult
        self._resultSetName = resultSetName
        self._records = {}
        self._ctr = ctr
        self._ensure_recs ()
        if hasattr(self._searchResult, 'records'):
            self._extract_recs(self._searchResult.records, 0)
    def __getattr__ (self, key):
        """Forward attribute access to Connection if appropriate"""
        if key in self.__dict__:
            return self.__dict__[key]
        if key in self.inherited_elts:
            return getattr (self._conn, key) # may raise AttributeError
        raise AttributeError (key)
    
    def _make_keywords (self):
        return {'recsyn': z3950.Z3950_RECSYN_USMARC_ov, 'esn': ('genericElementSetName', 'F')}
    
    def __len__ (self):
        return self._searchResult.resultCount

    def _pin(self, i):
        """Handle negative indices"""
        if i < 0:
            return i + len (self)
        return i

    def _ensure_recs (self):
        if 'USMARC' not in self._records:
            self._records ['USMARC'] = {}
            self._records ['USMARC']['F'] = [None] * len (self)
        if 'F' not in self._records['USMARC']:
            self._records ['USMARC']['F'] = [None] * len (self)

    def _get_rec(self, i):
        return self._records['USMARC']['F'][i]

    def _check_stale (self):
        if self._ctr < self._conn._lastConnectCtr:
            raise ConnectionError ('Stale result set used')
        # XXX is this right?
        if (not self._conn.namedResultSets) and self._ctr != self._conn._resultSetCtr:
            raise ServerNotImplError ('Multiple Result Sets')
        # XXX or this?
    
    def _ensure_present (self, i):
        self._ensure_recs ()
        if self._get_rec (i) is None:
            self._check_stale()
            maxreq = self.presentChunk
            if maxreq == 0: # get everything at once
                lbound = i
                count = len (self) - lbound
            else:
                lbound = (i // maxreq) * maxreq
                count = min (maxreq, len (self) - lbound)
            kw = self._make_keywords ()
            if self._get_rec (lbound) is None:
                presentResp = self._conn._cli.present (
                    start = lbound + 1,  # + 1 b/c 1-based
                    count = count,
                    rsn = self._resultSetName,
                    **kw)
                if not hasattr (presentResp, 'records'):
                    raise ProtocolError (str (presentResp))
                self._extract_recs (presentResp.records, lbound)
            if i != lbound and self._get_rec(i) is None:
                presentResp = self._conn._cli.present(start=i + 1, count=1, rsn=self._resultSetName,  **kw)
                self._extract_recs(presentResp.records, i)
        return self._records['USMARC']['F'][i]

    def __getitem__ (self, i):
        """Ensure item is present, and return a Record"""
        i = self._pin(i)
        if i >= len(self):
            raise IndexError
        return self._ensure_present(i)

    def __getslice__(self, i, j):
        i = self._pin(i)
        j = self._pin(j)
        if j > len(self):
            j = len(self)
        for k in range(i, j):
            self._ensure_present(k)
        if len(self._records) == 0:
            return[]
        return self._records['USMARC']['F'][i:j]

    def _extract_recs(self, records, lbound):
        # USED & CHECKED
        typ, recs = records
        print(f'Extracting {str(len(recs))} starting at {str(lbound)}')
        if typ != 'responseRecords':
            raise ProtocolError
        for i, r in enumerate(recs):
            typ, data = recs[i].record
            if typ == 'retrievalRecord':
                typ, dat = data.encoding
                if data.direct_reference == oids.Z3950_RECSYN_USMARC_ov:
                    if typ != 'octet-aligned':
                        raise ProtocolError
                marc8 = False
                if dat[9] != 'a':
                    marc8 = True
                self._records['USMARC']['F'][lbound + i] = Record(data=dat.encode('utf-8'), marc8=marc8)
            else:
                raise ProtocolError

    def sort(self, keys):
        return self._conn.sort([self], keys)