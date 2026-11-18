import asyncio
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine

from app.config import Settings
from app.db import Base
from app.main import create_app


class FakeKeitaro:
    def __init__(self):
        self.campaigns = []
        self.streams = []
        self.calls = []

    def __call__(self, request):
        path = request.url.path.removeprefix('/admin_api/v1/')
        method = request.method
        body = __import__('json').loads(request.content) if request.content else None
        self.calls.append((method, path, body))
        if method == 'GET' and path == 'domains': return self.ok([{'id': 1, 'name': 'example.test', 'state': 'active'}])
        if method == 'GET' and path == 'groups': return self.ok([{'id': 2, 'name': 'TESTS'}])
        if method == 'GET' and path == 'traffic_sources': return self.ok([{'id': 3, 'name': 'TESTS', 'state': 'active'}])
        if method == 'GET' and path == 'offers': return self.ok([{'id': 10, 'name': 'Offer A', 'state': 'active'}, {'id': 11, 'name': 'Offer B', 'state': 'active'}])
        if method == 'GET' and path == 'campaigns': return self.ok(self.campaigns)
        if method == 'POST' and path == 'campaigns':
            record = {'id': len(self.campaigns) + 1, **body}; self.campaigns.append(record); return self.ok(record)
        if path.startswith('campaigns/'):
            parts = path.split('/'); cid = int(parts[1]); campaign = next((x for x in self.campaigns if x['id'] == cid), None)
            if method == 'GET' and len(parts) == 2: return self.ok(campaign) if campaign else httpx.Response(404)
            if method == 'GET' and parts[-1] == 'streams': return self.ok([x for x in self.streams if x['campaign_id'] == cid])
            if method == 'DELETE': self.campaigns.remove(campaign); return self.ok({})
        if method == 'POST' and path == 'streams':
            record = {'id': len(self.streams) + 1, 'updated_at': 'a', **body}; self.streams.append(record); return self.ok(record)
        if method == 'PUT' and path.startswith('streams/'):
            stream = next(x for x in self.streams if x['id'] == int(path.split('/')[-1])); stream.update(body); stream['updated_at'] = 'b'; return self.ok(stream)
        return httpx.Response(404)

    @staticmethod
    def ok(data):
        return httpx.Response(200, json=data)


@pytest.fixture
def fixture(tmp_path):
    db_path = tmp_path / 'app.db'
    settings = Settings(keitaro_base_url='http://keitaro.test', keitaro_api_key='test',
                        database_url=f'sqlite:///{db_path}', campaign_prefix='test_frolov_')
    Base.metadata.create_all(create_engine(settings.database_url))
    fake = FakeKeitaro()
    return create_app(settings, httpx.MockTransport(fake)), fake


def run_request(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://app.test') as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


def create(app):
    return run_request(app, 'POST', '/api/campaigns', json={
        'name': 'demo', 'country': 'AU', 'offer_id': 10,
        'domain_id': 1, 'group_id': 2, 'traffic_source_id': 3,
    })


def test_create_campaign_with_geo_and_fallback(fixture):
    app, fake = fixture
    response = create(app)
    assert response.status_code == 201
    assert response.json()['name'] == 'test_frolov_demo'
    assert len(fake.streams) == 2
    assert fake.streams[0]['type'] == 'forced'
    assert fake.streams[0]['filters'] == [{'name': 'country', 'mode': 'accept', 'payload': ['AU']}]
    assert fake.streams[0]['action_payload'] == 'https://www.google.com/'
    assert fake.streams[1]['type'] == 'default'
    assert fake.streams[1]['offers'] == [{'offer_id': 10, 'share': 100, 'state': 'active'}]
    assert fake.campaigns[0]['domain_id'] == 1
    assert fake.campaigns[0]['group_id'] == '2'
    assert fake.campaigns[0]['traffic_source_id'] == 3


def test_editor_rejects_stale_changes_and_saves_exact_shares(fixture):
    app, fake = fixture
    assert create(app).status_code == 201
    detail = run_request(app, 'GET', '/api/campaigns/1').json()
    stream = detail['streams'][1]
    path = f"/api/campaigns/1/streams/{stream['id']}/offers"
    body = {'expected_version': stream['version'], 'offers': [{'offer_id': 10, 'share': 60}, {'offer_id': 11, 'share': 40}]}
    assert run_request(app, 'PUT', path, json=body).status_code == 200
    assert fake.streams[1]['offers'] == [{'offer_id': 10, 'share': 60, 'state': 'active'}, {'offer_id': 11, 'share': 40, 'state': 'active'}]
    assert run_request(app, 'PUT', path, json=body).status_code == 409
    fresh = run_request(app, 'GET', '/api/campaigns/1').json()['streams'][1]
    bad = {'expected_version': fresh['version'], 'offers': [{'offer_id': 10, 'share': 50}, {'offer_id': 11, 'share': 40}]}
    assert run_request(app, 'PUT', path, json=bad).status_code == 422
    assert fake.streams[1]['offers'][0]['share'] == 60


def test_editor_preserves_disabled_offers(fixture):
    app, fake = fixture
    assert create(app).status_code == 201
    fake.streams[1]['offers'].append({'offer_id': 12, 'share': 0, 'state': 'disabled'})
    stream = run_request(app, 'GET', '/api/campaigns/1').json()['streams'][1]
    response = run_request(app, 'PUT', f"/api/campaigns/1/streams/{stream['id']}/offers", json={
        'expected_version': stream['version'],
        'offers': [{'offer_id': 10, 'share': 100, 'state': 'active'},
                   {'offer_id': 12, 'share': 0, 'state': 'disabled'}],
    })
    assert response.status_code == 200
    assert fake.streams[1]['offers'][1] == {'offer_id': 12, 'share': 0, 'state': 'disabled'}


def test_validation_and_static_page(fixture):
    app, fake = fixture
    response = run_request(app, 'GET', '/')
    assert response.status_code == 200 and 'Новая кампания' in response.text
    assert run_request(app, 'POST', '/api/campaigns', json={
        'name': 'demo', 'country': 'AUS', 'offer_id': 10,
        'domain_id': 1, 'group_id': 2, 'traffic_source_id': 3,
    }).status_code == 422
    assert fake.campaigns == []
