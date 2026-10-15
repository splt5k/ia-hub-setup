"""Assuntos detectáveis no texto; não inventa entidades ou causalidade."""
import re

TOPICS = [
    ('Memória compartilhada', r'mem[oó]ria|shared.memory|persistent.memory'),
    ('MCP', r'\bmcp\b|model context protocol'),
    ('SQLite', r'\bsqlite\b'),
    ('Obsidian', r'\bobsidian\b|wikilinks?'),
    ('Ghidra', r'\bghidra\b'),
    ('Engenharia reversa', r'engenharia reversa|reverse engineering|\brea\b|dll_proxy|mu-client'),
    ('WSL2', r'\bwsl2?\b|/mnt/[a-z]/'),
    ('Windows', r'\bwindows\b|powershell'),
    ('Claude Code', r'claude code|claude-code'),
    ('Codex', r'\bcodex\b'),
    ('Antigravity', r'\bantigravity\b'),
    ('OpenCode', r'\bopencode\b'),
    ('Recuperação semântica', r'sem[aâ]ntic|embedding|busca h[ií]brida'),
    ('Histórico e proveniência', r'proveni[eê]ncia|rastreabil|hist[oó]rico|revis[oõ]es'),
    ('Redes e MikroTik', r'mikrotik|routeros|roteador'),
    ('.NET', r'\.net|\bc#\b|winforms|wpf'),
]


def topics(text):
    return [title for title, pattern in TOPICS if re.search(pattern, text, re.I)][:10]


def is_validation(title, content, project, source=''):
    # Conteúdo de um documento real pode explicar os testes; isso não o transforma
    # em teste. Classificação por projeto reservado ou origem explícita.
    return bool(re.match(r'IA-Hub-(?:E2E|AUTO|semantic-validation)', project, re.I) or source == 'codex:semantic-validation')
