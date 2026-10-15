import json
import sys
from .client import request, STATE
from .core import now


def main(client):
    try:
        event = json.load(sys.stdin)
        if client.startswith('antigravity-'):
            metadata = {k: event[k] for k in ['conversationId', 'workspacePaths', 'transcriptPath', 'invocationNum', 'terminationReason'] if k in event}
            metadata['available_keys'] = list(event.keys())
            STATE.mkdir(parents=True, exist_ok=True)
            (STATE / ('antigravity-' + client.split('-')[-1] + '.json')).write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
            if client.endswith('context'):
                if event.get('invocationNum', 0) > 1:
                    print('{}')
                    return
                project = next(iter(event.get('workspacePaths', [])), '')
                context = request('context', {'query': project.replace('\\', '/').split('/')[-1], 'project': project})
                print(json.dumps({'injectSteps': [{'ephemeralMessage': json.dumps(context, ensure_ascii=False)}]} if context['memories'] else {}, ensure_ascii=False))
            else:
                if event.get('transcriptPath'):
                    request('capture', {'path': event['transcriptPath'], 'client': 'antigravity', 'project': next(iter(event.get('workspacePaths', [])), '')})
                print('{}')
            return
        name = event.get('hook_event_name', '')
        if name in ('SessionStart', 'UserPromptSubmit'):
            context = request('context', {'query': event.get('prompt', '')[:2000], 'project': event.get('cwd', '')})
            if context['memories']:
                print(json.dumps({'hookSpecificOutput': {'hookEventName': name, 'additionalContext': json.dumps(context, ensure_ascii=False)}}, ensure_ascii=False))
        elif name in ('Stop', 'SessionEnd') and event.get('transcript_path'):
            request('capture', {'path': event['transcript_path'], 'client': client, 'project': event.get('cwd', '')})
    except Exception as error:
        STATE.mkdir(parents=True, exist_ok=True)
        with (STATE / 'hooks.log').open('a', encoding='utf-8') as f:
            f.write(f'{now()} {client} {type(error).__name__}: {str(error)[:160]}\n')
        # Falha de memória fica visível no log, sem bloquear trabalho nem aprovar ferramentas.
