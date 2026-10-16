"""Provider-reported execution metrics, stored alongside the shared memory database.

Unknown usage and prices stay unknown. Output is returned to callers, never persisted
by the ledger; cost figures are reports from clients, not independently billed costs.
"""
import json
import math
import uuid
from .core import digest, now, project_id, sanitize

USAGE_FIELDS = ('input_tokens', 'output_tokens', 'cached_input_tokens',
                'reasoning_output_tokens', 'cache_creation_input_tokens')
_PRIVATE_FIELDS = {'prompt', 'messages', 'conversation', 'transcript', 'stdout',
                   'stderr', 'output', 'content', 'authorization', 'credentials'}
_SECRET_FIELDS = {'api_key', 'apikey', 'password', 'senha', 'secret', 'token',
                  'access_token', 'refresh_token'}


def _clean(value):
    if isinstance(value, dict):
        return {sanitize(str(k)): ('[REDACTED]' if str(k).lower() in _SECRET_FIELDS else _clean(v))
                for k, v in value.items() if str(k).lower() not in _PRIVATE_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, str):
        return sanitize(value)[:2000]
    return value


def _json(value):
    return json.dumps(_clean(value), ensure_ascii=False, allow_nan=False)


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def _usage(raw):
    raw = raw if isinstance(raw, dict) else {}
    cache = raw.get('cache') if isinstance(raw.get('cache'), dict) else {}
    aliases = {
        'input_tokens': ('input_tokens', 'inputTokens', 'input', 'prompt_tokens', 'promptTokenCount'),
        'output_tokens': ('output_tokens', 'outputTokens', 'output', 'completion_tokens', 'candidatesTokenCount'),
        'cached_input_tokens': ('cached_input_tokens', 'cache_read_input_tokens', 'cacheReadInputTokens', 'cachedContentTokenCount', 'cache_read_tokens'),
        'reasoning_output_tokens': ('reasoning_output_tokens', 'reasoning_tokens', 'reasoning', 'thoughtsTokenCount', 'thinking_tokens'),
        'cache_creation_input_tokens': ('cache_creation_input_tokens', 'cacheCreationInputTokens'),
    }
    result = {field: next((_number(raw[key]) for key in keys if _number(raw.get(key)) is not None), None)
              for field, keys in aliases.items()}
    for field, key in [('cached_input_tokens', 'read'), ('cache_creation_input_tokens', 'write')]:
        if result[field] is None:
            result[field] = _number(cache.get(key))
    return result


def _sum_known(values):
    return sum(values) if values and all(value is not None for value in values) else None


def parse_result(harness, stdout, returncode=0):
    """Normalize supported CLI JSON/JSONL; final cumulative snapshots replace earlier ones."""
    result = {'status': 'succeeded', 'output': '', 'usage': _usage(None),
              'model_reported': None, 'cost_reported_usd': None,
              'cost_kind': 'unknown', 'errors': []}
    harness = str(harness).lower()
    if harness == 'agy':
        harness = 'antigravity'
    if harness not in {'codex', 'claude', 'antigravity', 'opencode'}:
        result['errors'].append('Unsupported harness: ' + harness)
    text = stdout.decode('utf-8', errors='replace') if isinstance(stdout, bytes) else str(stdout or '')
    try:
        obj = json.loads(text)
        events = obj if isinstance(obj, list) else [obj]
    except (ValueError, TypeError):
        events = []
        for line in text.splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    result['errors'].append('Invalid JSON output')
    messages, seen_steps, steps, finished = [], set(), [], False
    for event in events:
        if not isinstance(event, dict):
            result['errors'].append('Invalid JSON event')
            continue
        kind = event.get('type', '')
        failed = bool(event.get('error')) or kind in {'error', 'turn.failed'} or event.get('is_error') is True or str(event.get('status', '')).lower() in {'failed', 'error'} or str(event.get('subtype', '')).startswith('error')
        if failed:
            error = event.get('error') or event.get('message') or event.get('result') or kind
            result['errors'].append(_clean(error))
        if event.get('model'):
            result['model_reported'] = event['model']
        if harness == 'codex':
            item = event.get('item') or {}
            if kind == 'item.completed' and item.get('type') == 'agent_message':
                messages.append(item.get('text', ''))
            if kind == 'turn.completed':
                finished = True
                result['usage'] = _usage(event.get('usage'))
                result['cost_reported_usd'] = _number(event.get('cost_usd'))
        elif harness in {'claude', 'antigravity'}:
            # Stream messages can repeat usage already included in the final result.
            if kind == 'result' or (not kind and any(k in event for k in ('result', 'usage', 'usageMetadata', 'stats'))):
                finished = True
                raw = event.get('usage') or event.get('usageMetadata')
                model_usage = event.get('modelUsage') or {}
                if len(model_usage) == 1:
                    result['model_reported'] = next(iter(model_usage))
                if not raw and model_usage:
                    normalized = [_usage(u) for u in model_usage.values()]
                    raw = {field: _sum_known([u[field] for u in normalized]) for field in USAGE_FIELDS}
                result['usage'] = _usage(raw)
                result['cost_reported_usd'] = _number(event.get('total_cost_usd', event.get('cost_usd')))
                output = event.get('result', event.get('output', event.get('response', event.get('text', ''))))
                if isinstance(output, str):
                    messages = [output]
        elif harness == 'opencode':
            part = event.get('part') or event
            if kind == 'text':
                messages.append(part.get('text', ''))
            if kind == 'step_finish':
                finished = True
                identity = part.get('id') or event.get('id') or json.dumps(event, sort_keys=True)
                if identity not in seen_steps:
                    seen_steps.add(identity)
                    steps.append((_usage(part.get('tokens')), _number(part.get('cost'))))
                model = part.get('model')
                if isinstance(model, dict):
                    model = model.get('modelID') or model.get('id')
                if model:
                    result['model_reported'] = model
    if steps:
        result['usage'] = {field: _sum_known([usage[field] for usage, _ in steps]) for field in USAGE_FIELDS}
        costs = [cost for _, cost in steps]
        result['cost_reported_usd'] = sum(costs) if all(c is not None for c in costs) else None
    result['output'] = '\n'.join(str(m) for m in messages if m)
    cost = result['cost_reported_usd']
    if cost is not None:
        result['cost_kind'] = 'reported_zero_not_verified_free' if cost == 0 else 'provider_reported_estimate'
    if returncode:
        result['errors'].append('Process exited with code ' + str(returncode))
    if not finished and not result['errors']:
        result['errors'].append('No final result received')
    if result['errors']:
        result['status'] = 'failed'
    return result


class Ledger:
    """Additive tables in Memory.connection(), with no separate database or transcript."""
    def __init__(self, memory):
        self.memory = memory
        with memory.connection() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS hub_runs (
                    id TEXT PRIMARY KEY, client TEXT NOT NULL, project TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL, prompt_snippet TEXT NOT NULL,
                    policy TEXT NOT NULL, decision TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    session_id TEXT NOT NULL, parent_id TEXT NOT NULL, status TEXT NOT NULL,
                    created TEXT NOT NULL, finished TEXT, summary TEXT, validation TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS hub_run_idempotency
                    ON hub_runs(client,project,idempotency_key) WHERE idempotency_key != '';
                CREATE TABLE IF NOT EXISTS hub_attempts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, model_requested TEXT,
                    model_reported TEXT, harness TEXT, status TEXT NOT NULL, usage TEXT NOT NULL,
                    cost_reported_usd REAL, duration_ms REAL, validation TEXT, error TEXT, created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS hub_attempt_run ON hub_attempts(run_id);
                CREATE TABLE IF NOT EXISTS hub_events (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, created TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS hub_event_run ON hub_events(run_id);
            ''')

    def start_run(self, client, project, prompt, policy, decision, idempotency_key='', session_id='', parent_id=''):
        client, project = sanitize(str(client)), project_id(project)
        key = sanitize(str(idempotency_key))
        run_id = uuid.uuid4().hex
        with self.memory.connection() as c:
            c.execute('INSERT OR IGNORE INTO hub_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (run_id, client, project, digest(str(prompt)), sanitize(str(prompt))[:240],
                       _json(policy), _json(decision), key, sanitize(str(session_id)), sanitize(str(parent_id)),
                       'running', now(), None, None, None))
            if key:
                run_id = c.execute('SELECT id FROM hub_runs WHERE client=? AND project=? AND idempotency_key=?',
                                   (client, project, key)).fetchone()['id']
        return run_id

    @staticmethod
    def _require(c, run_id):
        if not c.execute('SELECT 1 FROM hub_runs WHERE id=?', (run_id,)).fetchone():
            raise ValueError('Unknown run: ' + str(run_id))

    def record_attempt(self, run_id, model_requested, status, usage=None, model_reported=None,
                       cost_reported_usd=None, duration_ms=None, validation=None, error=None, harness=None, event_id=None):
        attempt_id = uuid.uuid5(uuid.NAMESPACE_URL, str(run_id) + ':' + str(event_id)).hex if event_id else uuid.uuid4().hex
        with self.memory.connection() as c:
            self._require(c, run_id)
            c.execute('INSERT OR IGNORE INTO hub_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                      (attempt_id, run_id, _clean(model_requested), _clean(model_reported), _clean(harness),
                       sanitize(str(status)), _json(_usage(usage)), _number(cost_reported_usd), _number(duration_ms),
                       _json(validation), _json(error), now()))
        return attempt_id

    def finish_run(self, run_id, status, summary='', validation=None):
        with self.memory.connection() as c:
            self._require(c, run_id)
            c.execute('UPDATE hub_runs SET status=?,finished=?,summary=?,validation=? WHERE id=?',
                      (sanitize(str(status)), now(), sanitize(str(summary))[:240], _json(validation), run_id))

    def event(self, run_id, kind, payload):
        event_id = uuid.uuid4().hex
        with self.memory.connection() as c:
            self._require(c, run_id)
            c.execute('INSERT INTO hub_events VALUES (?,?,?,?,?)',
                      (event_id, run_id, sanitize(str(kind)), _json(payload), now()))
        return event_id

    def report(self, run_id=None, limit=20):
        with self.memory.connection() as c:
            if run_id:
                runs = c.execute('''WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM hub_runs WHERE id=? UNION
                    SELECT r.id FROM hub_runs r JOIN descendants d ON r.parent_id=d.id
                ) SELECT r.* FROM hub_runs r JOIN descendants d ON r.id=d.id
                ORDER BY CASE WHEN r.id=? THEN 0 ELSE 1 END,r.created,r.id''', (run_id, run_id)).fetchall()
            else:
                runs = c.execute('SELECT * FROM hub_runs ORDER BY created DESC LIMIT ?', (max(0, min(int(limit), 1000)),)).fetchall()
            ids = [r['id'] for r in runs]
            placeholders = ','.join('?' for _ in ids)
            attempts = c.execute('SELECT * FROM hub_attempts WHERE run_id IN (' + placeholders + ') ORDER BY created,rowid', ids).fetchall() if ids else []
            events = c.execute('SELECT * FROM hub_events WHERE run_id IN (' + placeholders + ') ORDER BY created,rowid', ids).fetchall() if ids else []
        def decode(rows, fields):
            decoded = [dict(row) for row in rows]
            for row in decoded:
                for field in fields:
                    row[field] = json.loads(row[field]) if row[field] is not None else None
            return decoded
        attempts = decode(attempts, ('usage', 'validation', 'error'))
        totals = {field: _sum_known([a['usage'].get(field) for a in attempts]) for field in USAGE_FIELDS}
        costs = [a['cost_reported_usd'] for a in attempts]
        totals['cost_reported_usd'] = sum(costs) if costs and all(x is not None for x in costs) else None
        totals['attempt_count'] = len(attempts)
        totals['unknown_usage_attempts'] = {field: sum(a['usage'].get(field) is None for a in attempts) for field in USAGE_FIELDS}
        totals['semantics'] = 'provider_reported; cache inclusion differs across harnesses, do not sum fields blindly'
        totals['native_children_complete'] = not any('native_main_steps_only' in (json.loads(r['decision']).get('telemetry_scope', '')) for r in runs)
        totals['unknown_cost_attempts'] = sum(x is None for x in costs)
        totals['cost_kind'] = ('unknown' if totals['cost_reported_usd'] is None else
                               'reported_zero_not_verified_free' if totals['cost_reported_usd'] == 0 else 'provider_reported_estimate')
        return {'runs': decode(runs, ('policy', 'decision', 'validation')), 'attempts': attempts,
                'events': decode(events, ('payload',)), 'totals': totals}
