import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class CaptureTests(unittest.TestCase):
    def test_antigravity_captures_last_response_without_thinking(self):
        from memory.core import Memory
        from memory.capture import Capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            path = root / 'transcript_full.jsonl'
            rows = [
                {'source': 'MODEL', 'type': 'PLANNER_RESPONSE', 'status': 'DONE', 'content': 'Comentário intermediário que deve ser ignorado apesar de conter texto maior que cem caracteres para reproduzir uma saída de progresso.', 'thinking': 'SEGREDO'},
                {'source': 'TOOL', 'type': 'TOOL_RESULT', 'status': 'DONE', 'content': 'SEGREDO'},
                {'source': 'MODEL', 'type': 'PLANNER_RESPONSE', 'status': 'DONE', 'content': 'Conclusão final comprovada: o adaptador do Antigravity permite compartilhar decisões por meio do serviço local, preservando origem e histórico para os outros ambientes.', 'thinking': 'SEGREDO'}]
            path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')
            Capture(memory).ingest(path, 'antigravity', 'teste')
            self.assertEqual(memory.health()['records'], 1)
            self.assertFalse(memory.search('SEGREDO'))
            self.assertFalse(memory.search('intermediário'))

    def test_codex_project_survives_incremental_cursor(self):
        from memory.core import Memory
        from memory.capture import Capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            capture = Capture(memory)
            log = root / 'rollout.jsonl'
            log.write_text(json.dumps({'type': 'session_meta', 'payload': {'cwd': 'D:/Dev/projeto'}}) + '\n', encoding='utf-8')
            capture.ingest(log, 'codex')
            text = 'Nova decisão de arquitetura registrada após a primeira leitura incremental: armazenar a origem para permitir recuperação contextual em outros ambientes.'
            with log.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'type': 'response_item', 'payload': {'role': 'assistant', 'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': text}]}}) + '\n')
            capture.ingest(log, 'codex')
            self.assertEqual(memory.search('arquitetura')[0]['project'], 'd:/dev/projeto')

    def test_large_tool_line_does_not_block_later_final(self):
        from memory.core import Memory
        from memory.capture import Capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            log = root / 'claude.jsonl'
            final = {'type': 'assistant', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Conclusão após uma imagem grande: a integração mantém a captura funcional e ignora o conteúdo binário retornado pela ferramenta durante a análise.'}]}}
            log.write_text(json.dumps({'type': 'tool', 'image': 'x' * (3 * 1024 * 1024)}) + '\n' + json.dumps(final) + '\n', encoding='utf-8')
            Capture(memory).ingest(log, 'claude', 'p')
            self.assertEqual(memory.health()['records'], 1)

    def test_final_only_and_incremental_replay(self):
        from memory.core import Memory
        from memory.capture import Capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            capture = Capture(memory)
            log = root / 'rollout.jsonl'
            def message(phase, text):
                return {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'phase': phase, 'content': [{'type': 'output_text', 'text': text}]}}
            text = 'Decidimos utilizar certificados locais para autenticar os serviços internos de testes. Esta decisão evita compartilhar credenciais em prompts.'
            rows = [message('commentary', 'INFORMAÇÃO PRIVADA DA ANÁLISE'), message('final_answer', text)]
            log.write_text('\n'.join(json.dumps(x) for x in rows) + '\n', encoding='utf-8')
            capture.ingest(log, 'codex', 'projeto')
            capture.ingest(log, 'codex', 'projeto')
            self.assertEqual(memory.health()['records'], 1)
            self.assertFalse(memory.search('PRIVADA'))
            self.assertEqual(memory.search('certificados')[0]['content'], text)
            with log.open('a', encoding='utf-8') as f:
                f.write(json.dumps(message('final_answer', 'Uma nova decisão complementar define renovação periódica dos certificados locais com verificação automatizada e documentação de origem.')) + '\n')
            capture.ingest(log, 'codex', 'projeto')
            self.assertEqual(memory.health()['records'], 2)

    def test_claude_ignores_tools_and_thinking_and_waits_for_complete_line(self):
        from memory.core import Memory
        from memory.capture import Capture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            log = root / 'claude.jsonl'
            row = {'type': 'assistant', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'SEGREDO'}, {'type': 'text', 'text': 'Foi validado que o banco SQLite preserva revisões e permite compartilhar decisões entre agentes com rastreamento da origem e sem depender de copiar notas manualmente.'}]}}
            raw = json.dumps(row)
            log.write_text(raw, encoding='utf-8')
            capture = Capture(memory)
            capture.ingest(log, 'claude', 'p')
            self.assertEqual(memory.health()['records'], 0)
            with log.open('a', encoding='utf-8') as f:
                f.write('\n')
            capture.ingest(log, 'claude', 'p')
            self.assertEqual(memory.health()['records'], 1)
            self.assertFalse(memory.search('SEGREDO'))


if __name__ == '__main__':
    unittest.main()
