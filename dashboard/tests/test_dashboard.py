"""End-to-end dashboard checks, using disposable projects and no third-party packages.

Run from the project root:
  python3 -m unittest discover -s dashboard/tests -p 'test_*.py' -v

No test invokes a model or reads/writes the user's state or configured vault.
"""
from __future__ import annotations
import hashlib
import http.client
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest

DASHBOARD = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASHBOARD))
from server import DashboardError, Engine, Handler, ThreadingHTTPServer


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='learn-observatory-tests-')
        cls.root = pathlib.Path(cls.tmp.name)
        cls.project = cls.root / 'project'
        cls.project.mkdir()
        shutil.copytree(DASHBOARD.parent / 'scripts', cls.project / 'scripts',
                        ignore=shutil.ignore_patterns('__pycache__', 'tests'))
        (cls.project / 'learn.config.json').write_text(json.dumps({
            'stateDir': 'state', 'notesDir': 'notes', 'vizDir': 'notes/viz',
            'reviewsDir': 'notes/reviews', 'resourcesDir': 'resources',
            'exercisesDir': 'exercises', 'timezone': 'Europe/Oslo'}), 'utf-8')
        (cls.project / 'LEARNER.md').write_text('PRIVATE TEST PROFILE — do not copy to demo', 'utf-8')
        cls.initial = hashes(cls.project)
        cls.engine = Engine(cls.project, cls.root / 'dashboard-data')
        cls.initialized = cls.engine.read('demo')
        cls.steps = []
        for _ in range(14):
            cls.engine.action('demo', {'action': 'tour-next'})
            cls.steps.append(cls.engine.read('demo'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def node(snapshot, name):
        return next(n for n in snapshot['topic']['plan']['nodes'] if n['id'] == name)

    @staticmethod
    def card(snapshot, name):
        return next(c for c in snapshot['cards'] if c['node'] == name)

    def test_01_real_preparation_and_source_copy(self):
        self.assertEqual(self.initialized['rev'], 8)
        self.assertEqual(set(self.initialized['prep']), {'parts', 'equivalent', 'add', 'numberline'})
        self.assertEqual(self.initialized['eligibility']['eligible'], ['parts'])
        self.assertEqual((self.engine.demo / 'scripts/state.py').read_bytes(),
                         (self.project / 'scripts/state.py').read_bytes())
        self.assertNotIn('PRIVATE TEST PROFILE', (self.engine.demo / 'LEARNER.md').read_text())

    def test_02_pending_answer_and_assessment_are_separate(self):
        asked, answered, graded = self.steps[:3]
        self.assertEqual(asked['pending']['stage'], 'awaiting')
        self.assertEqual(answered['pending']['stage'], 'recorded')
        self.assertEqual(asked['pending']['id'], answered['pending']['id'])
        self.assertEqual(len(answered['topic']['attempts']), 0)
        self.assertEqual(graded['pending']['stage'], 'completed')
        self.assertEqual(self.node(graded, 'parts')['readiness'], 'ready')
        self.assertEqual(self.card(graded, 'parts')['interval'], 1)

    def test_03_failed_prerequisite_does_not_block_unrelated_branch(self):
        s = self.steps[4]
        self.assertEqual(self.node(s, 'equivalent')['coverage'], 'covered')
        self.assertEqual(self.node(s, 'equivalent')['readiness'], 'needs_repair')
        self.assertIn('add', {b['id'] for b in s['eligibility']['blocked']})
        self.assertIn('numberline', s['eligibility']['eligible'])
        self.assertEqual(self.node(self.steps[5], 'numberline')['readiness'], 'ready')

    def test_04_recovery_hook_preserves_pending_and_revision(self):
        before, after = self.steps[6:8]
        self.assertEqual(before['pending'], after['pending'])
        self.assertEqual(before['rev'], after['rev'])
        event = next(e for e in self.engine.events if 'hook_session_start' in e['command'])
        context = json.loads(event['output'])['hookSpecificOutput']['additionalContext']
        self.assertIn(before['pending']['id'], context)

    def test_05_real_hint_caps_quality_and_readiness(self):
        s = self.steps[8]
        a = s['topic']['attempts'][-1]
        self.assertEqual(a['result'], 'pass')
        self.assertEqual(a['quality'], 2)
        self.assertEqual(a['assistance'], 'nudge')
        self.assertFalse(a['independent'])
        self.assertIn('assisted', a['capped'])
        self.assertEqual(self.node(s, 'equivalent')['readiness'], 'provisional')

    def test_06_finish_and_actual_review_intervals(self):
        self.assertEqual(self.steps[10]['topic']['status'], 'finished')
        self.assertIsNone(self.steps[10]['active_topic'])
        self.assertEqual([self.card(self.steps[i], 'parts')['interval'] for i in (10, 11, 12)], [1, 6, 15])
        self.assertEqual(self.node(self.steps[12], 'parts')['retention'], 'demonstrated')

    def test_07_later_failure_changes_retention_not_coverage_or_readiness(self):
        before = self.node(self.steps[12], 'equivalent')
        after = self.node(self.steps[13], 'equivalent')
        self.assertEqual(after['retention'], 'needs_review')
        self.assertEqual(before['coverage'], after['coverage'])
        self.assertEqual(before['readiness'], after['readiness'])
        self.assertEqual(self.node(self.steps[13], 'add')['readiness'], 'ready')

    def test_08_live_read_is_non_mutating(self):
        self.assertEqual(hashes(self.project), self.initial)
        live = self.engine.snapshot('live')
        self.assertIsNone(live['topic'])
        self.assertFalse(live['can_write'])
        self.assertEqual(hashes(self.project), self.initial)
        with self.assertRaises(DashboardError):
            self.engine.action('live', {'action': 'hint', 'expected_rev': 0})
        self.assertEqual(hashes(self.project), self.initial)

    def test_09_corrupt_live_state_is_not_overwritten(self):
        folder = self.project / 'state'
        folder.mkdir()
        target = folder / 'state.json'
        target.write_text('{bad json - retain these bytes', 'utf-8')
        try:
            with self.assertRaises(DashboardError):
                self.engine.snapshot('live')
            self.assertEqual(target.read_text('utf-8'), '{bad json - retain these bytes')
        finally:
            shutil.rmtree(folder)

    def test_10_stale_revision_rejected_inside_engine_write_lock(self):
        s = self.engine.read('demo')
        before = (self.engine.demo / 'state/state.json').read_bytes()
        with self.assertRaises(DashboardError) as cm:
            self.engine.run('demo', 'state', ['checkpoint', 'Stale control must not write'], expected_rev=s['rev'] - 1)
        self.assertIn('lesson changed', str(cm.exception).lower())
        self.assertEqual((self.engine.demo / 'state/state.json').read_bytes(), before)

    def test_11_http_boundaries_and_export(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.engine = self.engine
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        port = server.server_port
        def request(method, path, obj=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
            conn.request(method, path, body=json.dumps(obj) if obj is not None else None,
                         headers=headers or {})
            response = conn.getresponse()
            result = response.status, response.read(), dict(response.getheaders())
            conn.close()
            return result
        try:
            code, raw, headers = request('GET', '/api/bootstrap')
            self.assertEqual(code, 200)
            self.assertIn('Content-Security-Policy', headers)
            token = json.loads(raw)['token']
            self.assertEqual(request('GET', '/api/snapshot?mode=live', headers={'Host': 'untrusted.example'})[0], 403)
            self.assertEqual(request('POST', '/api/action', {'mode': 'demo', 'action': 'reset'}, {'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(request('POST', '/api/action', {'mode': 'demo', 'action': 'reset'},
                                     {'Content-Type': 'application/json', 'X-Dashboard-Token': token, 'Origin': 'https://untrusted.example'})[0], 403)
            self.assertEqual(request('GET', '/api/source?file=../../LEARNER.md')[0], 409)
            self.assertEqual(request('GET', '/../../LEARNER.md')[0], 404)
            self.assertEqual(request('GET', '/api/source?file=state')[0], 200)
            code, raw, headers = request('GET', '/api/export?mode=demo')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(raw)['mode'], 'demo')
            self.assertIn('attachment', headers['Content-Disposition'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def test_12_practice_success_does_not_inflate_interval(self):
        before = self.engine.read('demo')
        c = self.card(before, 'parts')
        result = self.engine.action('demo', {'action': 'grade-review', 'card': c['id'], 'quality': 4,
                                            'kind': 'practice', 'expected_rev': before['rev']})
        after = self.card(result, 'parts')
        self.assertEqual(after['interval'], c['interval'])
        self.assertEqual(after['due'], c['due'])
        self.assertEqual(len(after['history']), len(c['history']) + 1)
        self.assertTrue(result['tour']['tour_custom'])

    def test_13_manual_assessment_uses_recorded_help(self):
        self.engine.reset()
        s = self.engine.snapshot('demo')
        for payload in [
            {'action': 'ask', 'node': 'parts', 'kind': 'initial'},
            {'action': 'hint'},
            {'action': 'answer', 'response': 'The parts must be equal-sized and from the same whole.'},
        ]:
            s = self.engine.action('demo', {**payload, 'expected_rev': s['rev']})
        required = s['pending']['key']['required']
        s = self.engine.action('demo', {'action': 'record', 'result': 'pass', 'quality': 5,
                                       'required_met': required, 'expected_rev': s['rev']})
        self.assertEqual(s['topic']['attempts'][-1]['quality'], 2)
        self.assertEqual(self.node(s, 'parts')['readiness'], 'provisional')
        self.assertEqual(hashes(self.project), self.initial)

    def test_14_opt_in_live_controls_and_safe_reset(self):
        self.engine.run('live', 'state', ['start', 'Disposable live test', '--slug', 'live-test'])
        self.engine.run('live', 'state', ['plan-set'], {'nodes': [{'id': 'a', 'label': 'Test concept', 'depends': []}]})
        from demo_data import PREP
        self.engine.run('live', 'state', ['prep-node', 'a'], PREP['parts'])
        self.engine.run('live', 'state', ['plan-approve'])
        before = self.engine.read('live')
        self.engine.live_controls = True
        try:
            s = self.engine.action('live', {'action': 'ask', 'node': 'a', 'kind': 'initial', 'expected_rev': before['rev']})
            self.assertEqual(s['pending']['stage'], 'awaiting')
            with self.assertRaises(DashboardError):
                self.engine.action('live', {'action': 'reset'})
            live_files = hashes(self.project)
            self.engine.reset()
            self.assertEqual(hashes(self.project), live_files)
        finally:
            self.engine.live_controls = False


if __name__ == '__main__':
    unittest.main()
