"""Remove resíduos de orquestração do OpenCode (ambiente memory-only no diagrama).

Só remove o que o IA-Hub antigo gerou: agentes/AGENTS.md com hash conhecido e chaves
de configuração cujo valor é exatamente o do modelo antigo. Personalizações ficam.
"""
import hashlib
from pathlib import Path

LEGACY_AGENTS = {
    "architect.md": "207d4991212144d70d3c5dd303fd830946d94e2cd47961baf65963008a5cfac2",
    "explorer.md": "ee55f50a4c590565ce55c05c8a7f11983e52f364f2483966c2c5d32818b5b4c3",
    "implementer.md": "d35c216793931a276265e7f0e61a1cd3e47870482837cb7359d8d5d74ff6d2d6",
    "orchestrator-google.md": "3a531c1ac1dc16770ea45ec6ba793748a5e9def551101d77cdc039adfb3a64bb",
    "orchestrator.md": "5bae9556896aa0014db2adacf399ddb451799254b155a3eedb443bd5628fbdfb",
    "rescue.md": "b181b52f1bf245b4c7fcb6c344f5397dad234cc73f33802c885ba34c6f7137e8",
    "researcher.md": "8ace1f588bc27110efb617fb220a921f4955914b8886bb6d53bd4755b62ef1e7",
    "reviewer.md": "a8c8162c9cf728fd3863a50d2925b6ba4f14bfd0c7cdd59139a1df88f01b8d62",
    "validator.md": "993805a1619a9f3712f38f47cf3ceeae74925a10dc5ed9ac5d0dd0575beb0c02"
}
LEGACY_AGENTS_MD = '9cd7d010858010e6ed3c9e9dbcd50e4a965836ef28739eb70e82d2fcaf23ede4'
LEGACY_KEYS = {'default_agent': 'orchestrator', 'subagent_depth': 1, 'model': 'openai/gpt-5.6-terra',
               'small_model': 'google/gemini-3.1-flash-lite',
               'enabled_providers': ['openai', 'google', 'opencode']}
LEGACY_PROVIDERS = {'openai': {'whitelist': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra']},
                    'google': {'whitelist': ['gemini-3.1-flash-lite', 'gemini-3.6-flash']},
                    'opencode': {'whitelist': ['mimo-v2.5-free']}}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean_config(obj):
    """Aplica sobre o dict do opencode.json(c); devolve as chaves removidas."""
    removed = [k for k, v in LEGACY_KEYS.items() if obj.get(k) == v]
    for key in removed:
        del obj[key]
    providers = obj.get('provider')
    if isinstance(providers, dict):
        for name, legacy in LEGACY_PROVIDERS.items():
            if providers.get(name) == legacy:
                del providers[name]
                removed.append('provider.' + name)
        if not providers:
            del obj['provider']
    return removed


ORCHESTRATOR_SIGNATURE = 'Primary autonomous orchestrator for development, research, validation, and review.'
AGENTS_MD_SIGNATURES = ('# Global Working Rules', 'Delegate only when specialization, parallelism, or independent review is worth the context cost.')


def is_hub_agent_set(agents_dir):
    """Conjunto completo de agentes do hub (também de gerações anteriores): nomes + assinatura do orquestrador."""
    agents_dir = Path(agents_dir)
    if not all((agents_dir / name).is_file() for name in LEGACY_AGENTS):
        return False
    try:
        return ORCHESTRATOR_SIGNATURE in (agents_dir / 'orchestrator.md').read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError):
        return False


def clean_files(config_dir, save_backup):
    """Remove agentes/AGENTS.md gerados pelo hub, com backup via save_backup(path).

    Critérios: hash idêntico a um arquivo conhecido, ou conjunto completo com a assinatura do orquestrador.
    Um agente isolado com o mesmo nome, sem o conjunto, é considerado do usuário e preservado.
    """
    config_dir = Path(config_dir)
    removed = []
    agents_dir = config_dir / 'agents'
    whole_set = is_hub_agent_set(agents_dir)
    targets = [(agents_dir / name, sha, whole_set) for name, sha in LEGACY_AGENTS.items()]
    agents_md = config_dir / 'AGENTS.md'
    signed = False
    if agents_md.is_file():
        try:
            text = agents_md.read_text(encoding='utf-8-sig')
            signed = all(s in text for s in AGENTS_MD_SIGNATURES)
        except (OSError, UnicodeDecodeError):
            pass
    targets.append((agents_md, LEGACY_AGENTS_MD, signed))
    for path, sha, by_signature in targets:
        if path.is_file() and (by_signature or digest(path) == sha):
            save_backup(path)
            path.unlink()
            removed.append(str(path))
    return removed
