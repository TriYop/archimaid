from dataclasses import dataclass


@dataclass(frozen=True)
class DiagramFunction:
    name: str
    persona: str | None = None


@dataclass(frozen=True)
class DiagramFlow:
    data_type: str
    usage_mode: str | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class DiagramNeighbour:
    name: str
    flows: tuple[DiagramFlow, ...]


@dataclass(frozen=True)
class DiagramModel:
    application: str
    functions: tuple[DiagramFunction, ...] = ()
    targets: tuple[DiagramNeighbour, ...] = ()  # other applications that receive data (top row)
    sources: tuple[DiagramNeighbour, ...] = ()  # other applications that send data (bottom row)
    self_flows: int = 0  # flows from the application to itself: counted, not drawn
