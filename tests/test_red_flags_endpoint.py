import pytest

KNOWN_DOC_ID = 'b0659cf5-0768-44e7-8e33-19266ba1907b'

@pytest.mark.asyncio
async def test_red_flags_endpoint_known_doc(client):
    r = client.get('/api/documents/' + KNOWN_DOC_ID + '/red-flags')
    print('STATUS:', r.status_code)
    print('BODY:', r.text[:600])
    assert r.status_code != 500, 'Internal server error'
    # 200 = analysis found, 404 = document not in test DB (expected), 200 pending = no analysis yet
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        d = r.json()
        assert 'document_id' in d
        assert 'findings' in d
        assert 'summary' in d
        print('PASS: endpoint returned analysis')
    else:
        d = r.json()
        print('404 detail:', d.get('detail'))

@pytest.mark.asyncio
async def test_red_flags_after_upload(client):
    from io import BytesIO
    r_up = client.post('/api/documents/upload',
        files={'file': ('rf_test.txt', BytesIO(b'Revenue: 500 million'), 'text/plain')})
    assert r_up.status_code == 201
    doc_id = r_up.json()['document']['document_id']
    r_rf = client.get('/api/documents/' + doc_id + '/red-flags')
    print('STATUS:', r_rf.status_code)
    print('BODY:', r_rf.text[:600])
    assert r_rf.status_code == 200, f'Expected 200 got {r_rf.status_code}: {r_rf.text}'
    d = r_rf.json()
    assert d['document_id'] == doc_id
    assert 'findings' in d
    assert 'summary' in d
    assert 'status' in d
