#!/usr/bin/env python

import codecs

from z3950.PyZ3950 import oids
from z3950.PyZ3950 import z3950_2001 as z2001
from z3950.PyZ3950 import asn1

asn1.register_oid(oids.Z3950_RECSYN_GRS1, z2001.GenericRecord)
asn1.register_oid(oids.Z3950_RECSYN_SUTRS, asn1.GeneralString)
asn1.register_oid(oids.Z3950_RECSYN_EXPLAIN, z2001.Explain_Record)
asn1.register_oid(oids.Z3950_RECSYN_OPAC, z2001.OPACRecord)

asn1.register_oid(oids.Z3950_USR_SEARCHRES1, z2001.SearchInfoReport)
asn1.register_oid(oids.Z3950_USR_INFO1, z2001.OtherInformation)
asn1.register_oid(oids.Z3950_USR_PRIVATE_OCLC_INFO, z2001.OCLC_UserInformation)

impl_vers = "1.0 beta"
impl_id = 'Buzz - contact victoria.morris@bl.uk'


def make_attr(set=None, atype=None, val=None, valType=None):
    ae = z2001.AttributeElement()
    if set:
        ae.attributeSet = set
    ae.attributeType = atype
    if valType == 'numeric' or (valType is None and isinstance(val, int)):
        ae.attributeValue = ('numeric', val)
    else:
        cattr = z2001.AttributeElement['attributeValue']['complex']()
        if valType is None:
            valType = 'string'
        cattr.list = [(valType, val)]
        ae.attributeValue = ('complex', cattr)
    return ae


retrievalRecord_oids = [
    oids.Z3950_RECSYN_OPAC_ov,
    oids.Z3950_RECSYN_SUMMARY_ov,
    oids.Z3950_RECSYN_GRS1_ov,
    oids.Z3950_RECSYN_FRAGMENT_ov
]


def register_retrieval_record_oids(ctx, new_codec_name='ascii'):
    new_codec = codecs.lookup(new_codec_name)

    def switch_codec():
        ctx.push_codec()
        ctx.set_codec(asn1.GeneralString, new_codec)

    for oid in retrievalRecord_oids:
        ctx.register_charset_switcher(oid, switch_codec)


iso_10646_oid_to_name = {
    oids.UNICODE_PART1_XFERSYN_UCS2_ov: 'utf-16',
    oids.UNICODE_PART1_XFERSYN_UTF16_ov: 'utf-16',
    oids.UNICODE_PART1_XFERSYN_UTF8_ov: 'utf-8'
}


def try_get_iso10646_oid(charset_name):
    for k, v in iso_10646_oid_to_name.items():
        if charset_name == v:
            return k


def asn_charset_to_name(charset_tup):
    charset_name = None
    (typ, charset) = charset_tup
    if typ == 'iso10646':
        if charset.encodingLevel in iso_10646_oid_to_name:
            charset_name = iso_10646_oid_to_name[charset.encodingLevel]
        else:
            charset_name = None
    elif typ == 'private':
        (spectyp, val) = charset
        if spectyp == 'externallySpecified':
            oid = getattr(val, 'direct_reference', None)
            if oid == oids.Z3950_NEG_PRIVATE_INDEXDATA_CHARSETNAME_ov:
                enctyp, encval = val.encoding
                if enctyp == 'octet-aligned':
                    charset_name = encval
    return charset_name


def charset_to_asn(charset_name):
    oid = try_get_iso10646_oid(charset_name)
    if oid:
        iso10646 = z2001.Iso10646_3()
        iso10646.encodingLevel = oid
        return 'iso10646', iso10646
    else:
        ext = asn1.EXTERNAL()
        ext.direct_reference = oids.Z3950_NEG_PRIVATE_INDEXDATA_CHARSETNAME_ov
        ext.encoding = ('octet-aligned', charset_name)
        return 'private', ('externallySpecified', ext)


def_msg_size = 0x10000


def make_initreq(optionslist=None, authentication=None,
                 implementationId="", implementationName="", implementationVersion=""):
    # see http://lcweb.loc.gov/z3950/agency/wisdom/unicode.html
    InitReq = z2001.InitializeRequest()
    InitReq.protocolVersion = z2001.ProtocolVersion()
    InitReq.protocolVersion['version_1'] = 1
    InitReq.protocolVersion['version_2'] = 1
    InitReq.protocolVersion['version_3'] = 1
    InitReq.options = z2001.Options()
    if optionslist:
        for o in optionslist:
            InitReq.options[o] = 1
    InitReq.options['search'] = 1
    InitReq.options['present'] = 1
    InitReq.options['delSet'] = 0
    InitReq.options['scan'] = 0
    InitReq.options['sort'] = 0
    InitReq.options['extendedServices'] = 0
    InitReq.options['dedup'] = 0
    InitReq.options['negotiation'] = 0

    InitReq.preferredMessageSize = 0x100000
    InitReq.exceptionalRecordSize = 0x100000

    # InitReq.otherInfo["externallyDefinedInfo"] = asn1.OidVal([1, 2, 840, 10003, 15, 3])

    if implementationId:
        InitReq.implementationId = implementationId
    else:
        InitReq.implementationId = impl_id
    if implementationName:
        InitReq.implementationName = implementationName
    else:
        InitReq.implementationName = 'PyZ3950'
    if implementationVersion:
        InitReq.implementationVersion = implementationVersion
    else:
        InitReq.implementationVersion = impl_vers

    if authentication:
        class UP:
            pass

        up = UP()
        upAttrList = ['userId', 'password', 'groupId']
        for val, attr in zip(authentication, upAttrList):  # silently truncate
            if val:
                setattr(up, attr, val)
        data = asn1.encode(z2001.IdAuthentication, ('idPass', up))
        any_data = asn1.decode(asn1.ANY, data)
        InitReq.idAuthentication = any_data

    return InitReq


def make_sreq(query, dbnames, rsn, **kw):
    sreq = z2001.SearchRequest()
    sreq.smallSetUpperBound = 0
    sreq.largeSetLowerBound = 1
    sreq.mediumSetPresentNumber = 0
    sreq.replaceIndicator = 1
    sreq.resultSetName = rsn
    sreq.databaseNames = dbnames
    sreq.query = query
    for (key, val) in list(kw.items()):
        setattr(sreq, key, val)
    return sreq
