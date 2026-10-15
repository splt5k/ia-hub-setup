import threading

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


class Embeddings:
    def __init__(self, state):
        from fastembed import TextEmbedding
        self.model = TextEmbedding(model_name=MODEL, cache_dir=str(state / 'models'), threads=2)
        self.lock = threading.Lock()

    def __call__(self, text):
        with self.lock:
            return next(self.model.embed([text])).tolist()
