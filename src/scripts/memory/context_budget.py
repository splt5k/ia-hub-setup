"""Bound complete JSON context by characters, preserving provenance and valid JSON."""
import json


def bounded_context(context, budget):
    result = {key:value for key,value in context.items() if key != 'memories'}
    result['memories'] = []
    result['budget_unit'] = 'characters_not_tokenizer_count'
    def size():
        return len(json.dumps(result, ensure_ascii=False))
    if size() > budget:
        return {'notice':'Memória omitida: orçamento insuficiente.', 'memories':[]}
    for original in context.get('memories', []):
        item = {k:v for k,v in original.items() if k in {'id','title','content','project','kind','status','source','score','methods','context_scope'}}
        text = str(item.get('content', ''))
        item['content'] = ''
        result['memories'].append(item)
        if size() > budget:
            result['memories'].pop()
            continue
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1)//2
            item['content'] = text[:mid]
            if size() <= budget:
                low = mid
            else:
                high = mid-1
        item['content'] = text[:low]
    return result
