from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
from urllib.error import URLError

from rasai.search_intelligence.budget import RequestBudget
from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.domain import canonical_hostname, domain_matches
from rasai.search_intelligence.evidence import FilesystemSerpEvidenceSink
from rasai.search_intelligence.models import (
    DomainMatchStatus, QueryOrigin, SerpDataMode, SerpObservation, SerpObservationStatus,
    SerpQueryRequest, SerpResult,
)
from rasai.search_intelligence.persistence import SerpObservationRepository
from rasai.search_intelligence.providers.fixture import FixtureSerpProvider
from rasai.search_intelligence.providers.serpapi import SerpApiProvider
from rasai.search_intelligence.runtime import execute_search
from rasai.search_intelligence.service import SearchIntelligenceService, analyze_observation


class FakeResponse:
    def __init__(self, payload: bytes): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self.payload


def request(domain='client.example', depth=10):
    return SerpQueryRequest(
        query='seguro residencial cobre enchente', engine='google', country='BR',
        region='Porto Alegre, RS, Brazil', language='pt-BR', device='desktop',
        depth=depth, domain_of_interest=domain, run_id='RUN-1', query_origin=QueryOrigin.MANUAL,
    )


def observation(results):
    return SerpObservation(
        observation_id='OBS-1', run_id='RUN-1', query='seguro residencial cobre enchente',
        query_origin=QueryOrigin.MANUAL, engine='google', country='BR', region=None,
        language='pt-BR', device='desktop', collected_at=datetime.now(timezone.utc),
        provider='fixture', provider_request_id='FIX-1', requested_depth=10,
        result_count=len(results), results=tuple(results), data_mode=SerpDataMode.FIXTURE,
        status=SerpObservationStatus.OBSERVED,
    )


class DomainTests(unittest.TestCase):
    def test_www_and_subdomain_match_root(self):
        self.assertEqual('example.com', canonical_hostname('https://www.Example.com/x'))
        self.assertTrue(domain_matches('shop.example.com', 'example.com'))
        self.assertFalse(domain_matches('notexample.com', 'example.com'))
        self.assertFalse(domain_matches('example.com', 'shop.example.com'))


class AnalysisTests(unittest.TestCase):
    def test_found_position_competitors_duplicates_and_multiple_customer_results(self):
        results = [
            SerpResult(1,'a.example','https://a.example/a'),
            SerpResult(2,'a.example','https://a.example/b'),
            SerpResult(3,'portal.example','https://portal.example/x'),
            SerpResult(4,'shop.client.example','https://shop.client.example/p'),
            SerpResult(5,'client.example','https://client.example/q'),
        ]
        result = analyze_observation(request(), observation(results), max_competitors=10)
        self.assertEqual(DomainMatchStatus.FOUND, result.domain_status)
        self.assertEqual(4, result.customer_position)
        self.assertEqual(('a.example','portal.example'), result.competitor_domains_ahead)
        self.assertEqual((1,2,3), tuple(item.position for item in result.results_ahead))

    def test_not_found_within_depth_is_not_not_ranking(self):
        result = analyze_observation(request(), observation([
            SerpResult(1,'a.example','https://a.example/a')
        ]), max_competitors=10)
        self.assertEqual(DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH, result.domain_status)
        self.assertIsNone(result.customer_position)
        self.assertEqual((), result.results_ahead)

    def test_zero_competitor_limit(self):
        result = analyze_observation(request(), observation([
            SerpResult(1,'a.example','https://a.example/a'),
            SerpResult(2,'client.example','https://client.example/')
        ]), max_competitors=0)
        self.assertEqual((), result.competitor_domains_ahead)


class FixtureTests(unittest.TestCase):
    def test_fixture_is_explicitly_fixture_and_preserves_context(self):
        payload = {
            'fixture_version':'SERP-FIXTURE-001', 'query':request().query, 'engine':'google',
            'country':'BR','language':'pt-BR','device':'desktop','region':'Porto Alegre, RS, Brazil',
            'results':[
                {'position':1,'url':'https://leader.example/x','title':'Leader'},
                {'position':2,'url':'https://client.example/y','title':'Client'},
            ]
        }
        provider = FixtureSerpProvider(payload)
        response = provider.observe(request())
        self.assertEqual(SerpDataMode.FIXTURE, response.observation.data_mode)
        self.assertTrue(response.observation.quality_metadata['fixture'])
        self.assertEqual('leader.example', response.observation.results[0].domain)

    def test_zero_results_is_valid_observation_not_provider_error(self):
        provider = FixtureSerpProvider({'query':request().query,'results':[]})
        result = SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH, result.domain_status)
        self.assertEqual(0, result.observation.result_count)

    def test_results_beyond_requested_depth_are_not_used_for_ranking(self):
        provider = FixtureSerpProvider({
            'query':request().query,
            'results':[
                {'position':1,'url':'https://leader.example/'},
                {'position':11,'url':'https://client.example/'},
            ],
        })
        result = SearchIntelligenceService(provider=provider, max_depth=20).observe(request(depth=10))
        self.assertEqual(DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH, result.domain_status)
        self.assertEqual((1,), tuple(item.position for item in result.observation.results))
        self.assertEqual(1, result.observation.quality_metadata['results_outside_requested_depth_dropped'])

    def test_fixture_mismatch_is_error_result_not_crash(self):
        provider = FixtureSerpProvider({'query':'other','results':[]})
        service = SearchIntelligenceService(provider=provider)
        result = service.observe(request())
        self.assertEqual(DomainMatchStatus.ERROR, result.domain_status)
        self.assertEqual('SERP_MALFORMED_RESPONSE', result.error_code)


class SerpApiTests(unittest.TestCase):
    def test_normalizes_mocked_live_response_without_network(self):
        payload = {
            'search_metadata': {'id':'abc','created_at':'2026-09-08T20:00:00Z'},
            'organic_results': [
                {'position':1,'link':'https://leader.example/a','title':'A','snippet':'s','sitelinks':{'inline':[]}},
                {'position':2,'link':'javascript:bad','title':'bad'},
                {'position':3,'link':'https://client.example/c','title':'C','rich_snippet':{'top':{}}},
            ]
        }
        calls=[]
        def opener(req, timeout):
            calls.append((req.full_url, timeout))
            return FakeResponse(json.dumps(payload).encode())
        provider = SerpApiProvider(api_key='SECRETKEY', retries=0, min_interval_seconds=0, opener=opener)
        result = SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.FOUND, result.domain_status)
        self.assertEqual(3, result.customer_position)
        self.assertEqual(1, len(calls))
        self.assertEqual(1, result.observation.quality_metadata['dropped_results'])
        self.assertFalse(hasattr(result.observation, 'provider_json'))

    def test_timeout_or_network_error_becomes_unavailable(self):
        def opener(req, timeout): raise URLError('offline')
        provider = SerpApiProvider(api_key='x', retries=0, min_interval_seconds=0, opener=opener)
        result = SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.UNAVAILABLE, result.domain_status)

    def test_malformed_live_json_becomes_error(self):
        def opener(req, timeout): return FakeResponse(b'{bad json')
        provider = SerpApiProvider(api_key='x', retries=0, min_interval_seconds=0, opener=opener)
        result = SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.ERROR, result.domain_status)
        self.assertEqual('SERP_MALFORMED_RESPONSE', result.error_code)

    def test_socket_timeout_becomes_unavailable_with_timeout_code(self):
        def opener(req, timeout): raise socket.timeout('late')
        provider = SerpApiProvider(api_key='x', retries=0, min_interval_seconds=0, opener=opener)
        result = SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.UNAVAILABLE, result.domain_status)
        self.assertEqual('SERP_PROVIDER_TIMEOUT', result.error_code)

    def test_unsupported_engine_fails_before_network(self):
        calls=[]
        def opener(req, timeout): calls.append(1); return FakeResponse(b'{}')
        provider = SerpApiProvider(api_key='x', retries=0, min_interval_seconds=0, opener=opener)
        req = SerpQueryRequest(query='x', engine='bing', country='BR', language='pt-BR', device='desktop', depth=10, domain_of_interest='client.example')
        result = SearchIntelligenceService(provider=provider).observe(req)
        self.assertEqual(DomainMatchStatus.ERROR, result.domain_status)
        self.assertEqual('SERP_UNSUPPORTED_ENGINE', result.error_code)
        self.assertEqual([], calls)

    def test_budget_blocks_extra_attempts(self):
        budget=RequestBudget(1)
        def opener(req, timeout): raise URLError('offline')
        provider=SerpApiProvider(api_key='x', retries=1, min_interval_seconds=0, budget=budget, opener=opener)
        result=SearchIntelligenceService(provider=provider).observe(request())
        self.assertEqual(DomainMatchStatus.ERROR, result.domain_status)
        self.assertEqual('SERP_CONSUMPTION_LIMIT', result.error_code)
        self.assertEqual(1,budget.used)

    def test_invalid_domain_is_rejected_before_provider_call(self):
        class CountingFixture(FixtureSerpProvider):
            def __init__(self):
                super().__init__({'results':[]}); self.calls=0
            def observe(self, req):
                self.calls += 1
                return super().observe(req)
        provider=CountingFixture()
        req=request(domain='https://user:pass@example.com')
        service=SearchIntelligenceService(provider=provider)
        with self.assertRaises(ValueError):
            service.observe(req)
        self.assertEqual(0, provider.calls)


class PersistenceTests(unittest.TestCase):
    def test_additive_tables_and_raw_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'artifacts').mkdir()
            db=root/'audit.db'
            c=sqlite3.connect(db)
            c.execute('CREATE TABLE audits (audit_id TEXT PRIMARY KEY, created_at TEXT)')
            c.execute('INSERT INTO audits VALUES (?,?)',('AUD-1','2026-09-08T00:00:00Z'))
            c.commit(); c.close()
            repo=SerpObservationRepository.from_workspace(root)
            sink=FilesystemSerpEvidenceSink(root, root/'artifacts')
            provider=FixtureSerpProvider({
                'query':request().query,
                'results':[{'position':1,'url':'https://client.example/'}],
                'api_key':'should-not-persist',
            })
            service=SearchIntelligenceService(provider=provider,evidence_sink=sink,repository=repo)
            service.observe(request())
            self.assertEqual(1, repo.observation_count())
            row=repo.connection.execute('SELECT domain_status,raw_evidence_ref FROM serp_observations').fetchone()
            self.assertEqual('FOUND',row['domain_status'])
            raw=(root/row['raw_evidence_ref']).read_text()
            self.assertNotIn('should-not-persist',raw)
            self.assertIn('[REDACTED]',raw)
            repo.close()


class RuntimeTests(unittest.TestCase):
    def test_disabled_mode_does_nothing(self):
        config=SerpRuntimeConfig(mode='disabled').validate()
        execution=execute_search((request(),),config=config)
        self.assertEqual(0,execution.actual_http_requests)
        self.assertEqual(DomainMatchStatus.DISABLED,execution.results[0].domain_status)

    def test_fixture_argument_can_supply_path_to_programmatic_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.json'
            path.write_text(json.dumps({'query':request().query,'results':[]}), encoding='utf-8')
            config=SerpRuntimeConfig(mode='fixture')
            execution=execute_search((request(),),config=config,fixture_path=path)
            self.assertEqual('fixture', execution.mode)
            self.assertEqual(0, execution.actual_http_requests)

    def test_worst_case_limit_blocks_before_network(self):
        config=SerpRuntimeConfig(mode='live',max_requests=1,retries=1).validate()
        with self.assertRaisesRegex(ValueError,'worst-case'):
            execute_search((request(),),config=config,environment={'RASAI_SERPAPI_API_KEY':'x'})


if __name__ == '__main__': unittest.main()
