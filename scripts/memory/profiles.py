"""Perfis IA-Hub compatíveis com Codex, sem reserializar configurações do usuário.

Contrato: configure_profiles(home, save, version=None) retorna format/version/changed/
warnings. home é a pasta do usuário; save(Path, texto) é responsável por backup e
escrita. Só chama save quando o conteúdo muda. version omitida consulta apenas
`codex --version`; falha/versão desconhecida não escreve nada. CLI 0.x < 0.134
usa tabelas inline; >= 0.134 usa overlays nome.config.toml que herdam o principal.
Versões futuras 1.x exigem rever este contrato antes de gravar.

Só os dois pares exatos do instalador antigo são reconhecidos como gerenciados.
Qualquer campo adicional é customização e permanece intacto, com aviso. Não migra
perfis customizados nem resolve conflitos silenciosamente. Configs incompatíveis
preservadas exigem revisão humana, explicitada no relatório de retorno.
Fonte: https://learn.chatgpt.com/docs/config-file/config-advanced#profiles
"""
from pathlib import Path
import re
import subprocess
import tomllib


DEFAULTS = {
    'rapido': {'model': 'gpt-6.1-sol', 'model_reasoning_effort': 'low'},
    'pesado': {'model': 'gpt-6-astra', 'model_reasoning_effort': 'high'},
}


def configure_profiles(home, save, version=None):
    """Configure somente os perfis conhecidos; preserve todo o restante."""
    report = {'format': 'skipped', 'version': version, 'changed': [], 'warnings': []}
    if version is None:
        try:
            result = subprocess.run(['codex', '--version'], capture_output=True, text=True, timeout=15)
            version = result.stdout.strip() if result.returncode == 0 else ''
        except (OSError, subprocess.SubprocessError):
            version = ''
    report['version'] = version
    match = re.fullmatch(r'(?:codex-cli\s+)?(0)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', str(version).strip())
    if not match:
        report['warnings'].append('Versão Codex indisponível ou desconhecida: perfis não alterados; verifique codex --version.')
        return report
    modern = int(match[2]) >= 134
    report['format'] = 'files' if modern else 'inline'
    directory = Path(home) / '.codex'
    config = directory / 'config.toml'
    text = config.read_text(encoding='utf-8-sig') if config.exists() else ''
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        report['format'] = 'skipped'
        report['warnings'].append(f'Configuração Codex inválida; preservada: {error}')
        return report
    profiles = data.get('profiles', {})
    if not isinstance(profiles, dict):
        report['warnings'].append('Chave profiles customizada preservada; revisão necessária.')
        return report

    def write(path, content):
        if not path.exists() or path.read_text(encoding='utf-8-sig') != content:
            save(path, content)
            report['changed'].append(str(path))

    # Section boundaries preserve all unrelated text verbatim, including unknown
    # tables, hooks and REA. tomllib identifies quoted table names semantically.
    headers = list(re.finditer(r'(?m)^[ \t]*(\[[^\r\n]+\])[^\r\n]*(?:\r?\n|$)', text))
    spans = {}
    for index, header in enumerate(headers):
        try:
            section = tomllib.loads(header[1])
        except tomllib.TOMLDecodeError:
            continue
        for name in DEFAULTS:
            if section == {'profiles': {name: {}}}:
                spans[name] = (header.start(), headers[index + 1].start() if index + 1 < len(headers) else len(text), header.end())
    removed = []
    migrated = []
    for name, defaults in DEFAULTS.items():
        inline = profiles.get(name)
        if not modern:
            if inline is None:
                text = text.rstrip() + f'\n\n[profiles.{name}]\n' + ''.join(f'{key} = "{value}"\n' for key, value in defaults.items())
            continue
        target = directory / f'{name}.config.toml'
        if inline is not None and (inline != defaults or name not in spans):
            report['warnings'].append(f'Perfil legado {name} customizado preservado; migre manualmente para {target.name}.')
            continue
        if target.exists():
            try:
                existing = tomllib.loads(target.read_text(encoding='utf-8-sig'))
            except tomllib.TOMLDecodeError:
                existing = None
            if inline is not None and existing != defaults:
                report['warnings'].append(f'Conflito com {target.name}; arquivo e perfil legado preservados para revisão.')
                continue
        else:
            content = ''.join(f'{key} = "{value}"\n' for key, value in defaults.items())
            if inline is not None:
                start, end, body = spans[name]
                content = text[body:end]
            write(target, content)
        if inline is not None:
            start, end, _ = spans[name]
            removed.append((start, end))
            migrated.append(name)
    if modern:
        for start, end in sorted(removed, reverse=True):
            text = text[:start] + text[end:]
        # Remove only a selector owned by a successfully migrated managed profile.
        if data.get('profile') in migrated:
            first_table = re.search(r'(?m)^[ \t]*\[', text)
            cutoff = first_table.start() if first_table else len(text)
            text = re.sub(r'''(?m)^[ \t]*(?:profile|"profile"|'profile')[ \t]*=[^\r\n]*(?:\r?\n|$)''', '', text[:cutoff]) + text[cutoff:]
        remaining = set(profiles) - set(migrated)
        if remaining or (data.get('profile') and data.get('profile') not in migrated):
            report['warnings'].append('Configuração legada customizada permanece; Codex >=0.134 pode recusá-la. Revisão manual necessária.')
    if text != (config.read_text(encoding='utf-8-sig') if config.exists() else ''):
        write(config, text)
    return report
