"""Deterministic, account-preserving model routing; tiers are ordinal, not USD."""
import json
import re
import unicodedata
from pathlib import Path

PROFILES = {
    'claude': [('claude-haiku-5-5', 'low'), ('claude-sonnet-5-5', 'medium'), ('claude-opus-5-5', 'high')],
    'codex': [('gpt-6.1-sol', 'low'), ('gpt-6.1-sol', 'medium'), ('gpt-6-astra', 'high')],
    'opencode': [('google/gemini-3.1-flash-lite', 'low'), ('openai/gpt-5.6-sol', 'medium'), ('openai/gpt-5.6-sol', 'high')],
    'agy': [('gemini-3.8-flash-low', 'low'), ('gemini-3.8-flash-medium', 'medium'), ('gemini-3.8-flash-high', 'high')],
}
PROVIDER_PROFILES = {
    'openai': ['openai/gpt-5.6-luna', 'openai/gpt-5.6-sol', 'openai/gpt-5.6-sol'],
    'google': ['google/gemini-3.1-flash-lite', 'google/gemini-3.6-flash', 'google/gemini-3.6-flash'],
}


def bounded_string(value, name, limit=24000, empty=True):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value or (not empty and not value.strip()):
        raise ValueError('Invalid ' + name)
    return value


def model_string(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:@-]{0,199}', value):
        raise ValueError('Invalid model')
    return value


class Router:
    def __init__(self, root):
        self.root = Path(root)

    def plan(self, prompt, client, project='', task_kind='', current_model='', mode='auto'):
        bounded_string(prompt, 'prompt', empty=False)
        bounded_string(client, 'client', 30, False)
        bounded_string(project, 'project', 2048)
        bounded_string(task_kind, 'task_kind', 100)
        bounded_string(current_model, 'current_model', 200)
        original_client = client
        client = {'antigravity': 'agy', 'claude-code': 'claude', 'claude-desktop': 'claude'}.get(client, client)
        if client not in PROFILES or mode not in {'auto', 'manual'}:
            raise ValueError('Invalid client or mode')
        path = self.root / 'regras/orchestration.json'
        config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
        if not isinstance(config, dict):
            raise ValueError('Invalid policy')
        clients = config.get('clients', {})
        if not isinstance(clients, dict):
            raise ValueError('Invalid client policies')
        overrides = clients.get(client, {})
        if not isinstance(overrides, dict):
            raise ValueError('Invalid client policy')
        if 'allow_parallel' in overrides and type(overrides['allow_parallel']) is not bool:
            raise ValueError('Invalid parallel capability')
        budget = overrides.get('context_budget', config.get('context_budget', 6000))
        attempts = overrides.get('max_attempts', config.get('max_attempts', 2))
        if type(budget) is not int or not 256 <= budget <= 16000 or type(attempts) is not int or not 1 <= attempts <= 2:
            raise ValueError('Invalid policy limits')
        normalized = unicodedata.normalize('NFKD', task_kind + ' ' + prompt).encode('ascii', 'ignore').decode().casefold()
        tier = 2 if re.search(r'arquitet|architect|design decision|causa desconhecida|intermitent|dificil|complex', normalized) else 1 if re.search(r'implement|implemente|corrig|fix|refator|refactor|bug|feature', normalized) else 0
        reasons = ['deterministic_complexity', 'ordinal_cost_tier_no_price', 'existing_client_account']
        profiles = overrides.get('profiles', PROFILES[client])
        if not isinstance(profiles, list) or len(profiles) != 3:
            raise ValueError('Invalid profiles')
        for profile in profiles:
            if not isinstance(profile, (list, tuple)) or len(profile) != 2 or profile[1] not in {'low', 'medium', 'high'}:
                raise ValueError('Invalid profile')
            model_string(profile[0])
        model, effort = profiles[tier]
        if mode == 'manual':
            model = model_string(current_model)
            attempts = 1
            reasons.append('manual_selection_preserved')
        elif client == 'opencode' and current_model:
            provider = model_string(current_model).split('/')[0]
            provider_profiles = overrides.get('provider_profiles', PROVIDER_PROFILES)
            if not isinstance(provider_profiles, dict):
                raise ValueError('Invalid provider profiles')
            candidates = provider_profiles.get(provider)
            if candidates is not None:
                if not isinstance(candidates, list) or len(candidates) != 3 or any(not isinstance(x, str) or not x.startswith(provider + '/') for x in candidates):
                    raise ValueError('Invalid provider profiles')
                model = model_string(candidates[tier])
            else:
                model = current_model
            reasons.append('provider_preserved')
        native = original_client in {'claude', 'claude-code', 'opencode'}
        return {'policy_version': str(config.get('version', '1')), 'client': client, 'model': model,
                'effort': effort, 'tier': tier, 'reasons': reasons,
                'control': 'native_hooks' if native else 'dispatch_only', 'context_budget': budget,
                'allow_parallel': native and bool(overrides.get('allow_parallel', True)), 'max_attempts': attempts}

    def escalate(self, decision):
        next_plan = self.plan('complex architecture' if decision['tier'] >= 1 else 'implement', decision['client'], current_model=decision['model'])
        next_plan['reasons'].append('validation_failed_once')
        return next_plan
