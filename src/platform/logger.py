import uuid
import structlog

log = structlog.get_logger()


class GenerationLogger:
    def __init__(self, *args, **kwargs):
        pass

    def log(self, build: str, prompt: str, recipe, scores: list) -> str:
        gid = str(uuid.uuid4())
        top = max((s.total for s in scores), default=0)
        log.info("generation", build=build, prompt=prompt[:80], top_score=top)
        return gid
