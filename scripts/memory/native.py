"""Ledger for work executed inside native clients, never a proxy for inference."""
from .telemetry import Ledger
from .context_budget import bounded_context


class Native:
    def __init__(self, memory, router):
        self.memory, self.router = memory, router
        self.ledger = Ledger(memory)

    def handle(self, event, **args):
        if event == 'start':
            decision = self.router.plan(**{k: args[k] for k in ('prompt', 'client', 'project', 'task_kind', 'current_model', 'mode') if k in args})
            decision['telemetry_scope'] = 'native_main_steps_only_children_not_complete'
            run_id = self.ledger.start_run(args['client'], args.get('project', ''), args['prompt'],
                {'version': decision['policy_version']}, decision, args.get('idempotency_key', ''), args.get('session_id', ''))
            context = self.memory.context(query=args['prompt'][:2000], project=args.get('project', ''), limit=3)
            context = bounded_context(context, min(6000, int(decision.get('context_budget', 4000))))
            return {'run_id': run_id, 'decision': decision, 'context': context}
        run_id = args['run_id']
        if event == 'attempt':
            event_id = str(args.get('event_id', ''))
            if not event_id or len(event_id) > 240:
                raise ValueError('Native attempt requires bounded, stable event_id.')
            attempt_id = self.ledger.record_attempt(run_id, args.get('model_requested'), args.get('status', 'succeeded'),
                usage=args.get('usage'), model_reported=args.get('model_reported'),
                cost_reported_usd=args.get('cost_reported_usd'), duration_ms=args.get('duration_ms'),
                validation={'quality': 'not_measured'}, error=args.get('error'), harness=args.get('client'), event_id=event_id)
            return {'attempt_id': attempt_id}
        if event == 'finish':
            status = args.get('status') if args.get('status') in ('failed', 'cancelled') else 'completed_unvalidated'
            if any(a['status'] == 'failed' for a in self.ledger.report(run_id)['attempts']):
                status = 'failed'
            self.ledger.finish_run(run_id, status, args.get('summary', ''), {'quality': 'not_measured'})
            return {'run_id': run_id, 'status': status}
        raise ValueError('Unknown native event.')
