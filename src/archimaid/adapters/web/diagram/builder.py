from __future__ import annotations

from typing import Any
from uuid import UUID

from archimaid.adapters.web.diagram.model import (
    DiagramFlow,
    DiagramFunction,
    DiagramModel,
    DiagramNeighbour,
)
from archimaid.application.services import Services


def build_diagram(services: Services, application_id: UUID) -> DiagramModel:
    """Collect everything the diagram shows through the application services.

    Raises NotFound if the application does not exist.
    """
    application = services.applications.get(application_id)

    app_names: dict[UUID, str] = {}
    type_names: dict[UUID, str] = {}
    persona_names: dict[UUID, str] = {}

    def app_name(app_id: UUID) -> str:
        if app_id not in app_names:
            app_names[app_id] = services.applications.get(app_id).name
        return app_names[app_id]

    def type_name(type_id: UUID) -> str:
        if type_id not in type_names:
            type_names[type_id] = services.data_types.get(type_id).name
        return type_names[type_id]

    def persona_name(persona_id: UUID) -> str:
        if persona_id not in persona_names:
            persona_names[persona_id] = services.personas.get(persona_id).name
        return persona_names[persona_id]

    mode_labels = {v.code: v.label for v in services.reference.list("usage_mode")}

    functions = sorted(
        services.functions.list(application_id=application_id),
        key=lambda f: (f.name.casefold(), str(f.id)),
    )
    diagram_functions = tuple(
        DiagramFunction(f.name, persona_name(f.persona_id) if f.persona_id else None)
        for f in functions
    )

    function_index = {f.id: index for index, f in enumerate(functions)}

    def group(
        flows: list[Any], other_attr: str, own_function_attr: str
    ) -> tuple[DiagramNeighbour, ...]:
        by_app: dict[UUID, list[DiagramFlow]] = {}
        for flow in flows:
            mode = mode_labels.get(flow.usage_mode, flow.usage_mode) if flow.usage_mode else None
            by_app.setdefault(getattr(flow, other_attr), []).append(
                DiagramFlow(
                    type_name(flow.data_type_id),
                    mode,
                    flow.usage_explanation,
                    function_index.get(getattr(flow, own_function_attr)),
                )
            )
        ordered = sorted(
            by_app.items(), key=lambda item: (app_name(item[0]).casefold(), str(item[0]))
        )
        return tuple(
            DiagramNeighbour(
                app_name(app_id),
                tuple(
                    sorted(
                        grouped,
                        key=lambda f: (
                            f.data_type.casefold(),
                            f.usage_mode or "",
                            f.explanation or "",
                        ),
                    )
                ),
            )
            for app_id, grouped in ordered
        )

    outgoing = services.data_flows.list(source_application_id=application_id)
    incoming = services.data_flows.list(target_application_id=application_id)
    self_flows = sum(1 for f in outgoing if f.target_application_id == application_id)

    return DiagramModel(
        application=application.name,
        functions=diagram_functions,
        targets=group(
            [f for f in outgoing if f.target_application_id != application_id],
            "target_application_id",
            "source_function_id",
        ),
        sources=group(
            [f for f in incoming if f.source_application_id != application_id],
            "source_application_id",
            "target_function_id",
        ),
        self_flows=self_flows,
    )
