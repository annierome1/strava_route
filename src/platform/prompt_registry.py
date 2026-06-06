import yaml
from pathlib import Path


class PromptRegistry:
    """
    Loads versioned prompts from /prompts/ YAML files.
    Format: prompts/route_recipe.yaml → {current: v2, variants: {v1: {...}, v2: {...}}}
    """

    def __init__(self, dir: str = "prompts"):
        self.dir = Path(dir)
        self._cache: dict = {}

    def load(self, name: str, version: str = None) -> tuple:
        """Returns (template_string, version_id)."""
        if name not in self._cache:
            with open(self.dir / f"{name}.yaml") as f:
                self._cache[name] = yaml.safe_load(f)

        cfg = self._cache[name]
        vid = version or cfg["current"]
        return cfg["variants"][vid]["template"], vid
