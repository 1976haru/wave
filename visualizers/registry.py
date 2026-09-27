from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RendererFamily:
    id: str
    display_name: str
    implementation: type
    supported_parameters: tuple[str, ...]


class VisualizerRegistry:
    def __init__(self): self._families = {}
    def register(self, family: RendererFamily):
        if family.id in self._families: raise ValueError(f"Renderer family already registered: {family.id}")
        self._families[family.id] = family
    def get(self, family_id: str) -> RendererFamily:
        key = str(family_id).lower()
        if key not in self._families: raise KeyError(f"Unsupported renderer family: {family_id}")
        return self._families[key]
    def ids(self): return tuple(self._families)
    def create(self, family_id: str): return self.get(family_id).implementation()


registry = VisualizerRegistry()


def _register_builtins():
    from .families.soft_round_led import SoftRoundLEDRenderer, SUPPORTED_PARAMETERS
    registry.register(RendererFamily("soft_round_led", "Soft Round LED", SoftRoundLEDRenderer, SUPPORTED_PARAMETERS))


_register_builtins()
