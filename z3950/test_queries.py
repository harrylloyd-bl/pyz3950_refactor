#!/usr/bin/env python
from z3950.PyZ3950 import zoom_VM


def test_OCLC_query():
    conn = zoom_VM.Connection('zcat.oclc.org', 210, user='100270667', password='oclccat')
    conn.databaseName = 'OLUCWorldCat'
    conn.preferredRecordSyntax = 'USMARC'

    query = zoom_VM.Query('ti="1066 and all that"')

    res = conn.search(query)
    for r in res:
        print(str(r))
    conn.close()


def test_BL_query(blid='018948571'):
    conn = zoom_VM.Connection('z3950cat.bl.uk', 9909, user='COLMET2912', password='2m5v2Qyv')
    conn.databaseName = 'ZBLACU'
    conn.preferredRecordSyntax = 'USMARC'
    query = zoom_VM.Query(f'id="{blid}"')
    res = conn.search(query)
    for r in res:
        print(str(r))
    conn.close()

test_OCLC_query()

test_BL_query()


