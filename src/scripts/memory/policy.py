"""Deterministic, account-preserving model routing; tiers are ordinal, not USD."""
import json
import re
import unicodedata
from pathlib import Path

PROFILES = {
    # Opus fica só no orquestrador; o nível alto de subagente é Sonnet com esforço alto.
    'claude': [('claude-haiku-5-5', 'low'), ('claude-sonnet-5-5', 'medium'), ('claude-sonnet-5-5', 'high')],
    'codex': [('gpt-6.1-sol', 'low'), ('gpt-6.1-sol', 'medium'), ('gpt-6-astra', 'high')],
    'agy': [('gemini-3.8-flash-low', 'low'), ('gemini-3.8-flash-medium', 'medium'), ('gemini-3.8-flash-high', 'high')],
}


# Pesos somados: um sinal isolado não leva ao nível alto; o caro só entra com evidência acumulada.
SIGNALS = [
    ('signal_heavy', 2, r'arquitet|architect|design decision|decisao de design|causa desconhecida|sem causa aparente|intermitent|race condition|deadlock|concorrencia|vazamento de memoria|memory leak'),
    ('signal_hard_word', 1, r'dificil|complex'),
    ('signal_write', 1, r'implement|corrig|fix|refator|refactor|bug|feature|escrev|criar|crie|adicion|altere|alterar'),
    ('signal_wide_scope', 1, r'todos os arquivos|varios arquivos|todo o projeto|todo o repositorio|multiple files|entire (codebase|repo)|ponta a ponta|end.to.end'),
    ('signal_read_only', -1, r'^\W*(busque|procure|liste|resuma|leia|explique|mostre|find|search|list|summari[sz]e|read|explain)\b|\bo que e\b|qual a diferenca'),
]


def complexity_tier(normalized):
    score, signals = 0, []
    for name, weight, pattern in SIGNALS:
        if re.search(pattern, normalized):
            score += weight
            signals.append(name)
    if len(re.findall(r'[\w./\\-]+\.(?:py|js|ts|tsx|ps1|sh|cmd|json|md|toml|ya?ml|go|rs|java|cs)\b', normalized)) >= 3 or len(normalized) > 1500:
        score += 1
        signals.append('signal_large_input')
    return (2 if score >= 3 else 1 if score >= 1 else 0), signals


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
        if client == 'opencode':
            raise ValueError('OpenCode é somente memória; sem seleção de modelos nem delegação.')
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
        # 0 = sem limite de subagentes simultâneos.
        max_agents = overrides.get('max_active_agents', config.get('max_active_agents', 0))
        if type(budget) is not int or not 256 <= budget <= 16000 or type(attempts) is not int or not 1 <= attempts <= 2 \
                or type(max_agents) is not int or not 0 <= max_agents <= 64:
            raise ValueError('Invalid policy limits')
        normalized = unicodedata.normalize('NFKD', task_kind + ' ' + prompt).encode('ascii', 'ignore').decode().casefold()
        tier, signals = complexity_tier(normalized)
        reasons = ['deterministic_complexity', 'ordinal_cost_tier_no_price', 'existing_client_account', *signals]
        if re.search(r'seguranca|security|permiss|credencia|senha|password|segredo|secret|autentica|authenticat|oauth|lgpd|dados pessoais|personal data|producao|production', normalized):
            tier = max(tier, 2)
            reasons.append('risk_sensitive_floor_high')
        elif re.search(r'migra|apagar|delete|deploy|remov|drop ', normalized):
            tier = max(tier, 1)
            reasons.append('risk_operation_floor_medium')
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
        native = original_client in {'claude', 'claude-code'}
        return {'policy_version': str(config.get('version', '1')), 'client': client, 'model': model,
                'effort': effort, 'tier': tier, 'reasons': reasons,
                'control': 'native_hooks' if native else 'dispatch_only', 'context_budget': budget,
                'allow_parallel': native and bool(overrides.get('allow_parallel', True)), 'max_attempts': attempts,
                'max_active_agents': max_agents}

    def escalate(self, decision):
        next_plan = self.plan('complex architecture' if decision['tier'] >= 1 else 'implement', decision['client'], current_model=decision['model'])
        next_plan['reasons'].append('validation_failed_once')
        return next_plan
