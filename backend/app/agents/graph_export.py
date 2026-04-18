from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agents.chat_graph import get_chat_graph
from app.agents.provider_test_graph import get_provider_test_graph
from app.agents.rag_pipeline import get_rag_pipeline_graph
from app.agents.subgraph_registry import get_exportable_agent_subgraphs
from app.agents.validation_graph import get_validation_graph

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphExportSpec:
    name: str
    factory: Callable[[], Any]


def _static_graph_export_specs() -> tuple[GraphExportSpec, ...]:
    return (
        GraphExportSpec(name="chat_graph", factory=get_chat_graph),
        GraphExportSpec(name="validation_graph", factory=get_validation_graph),
        GraphExportSpec(name="rag_pipeline", factory=get_rag_pipeline_graph),
        GraphExportSpec(name="provider_test_graph", factory=get_provider_test_graph),
    )


def _agent_graph_export_specs() -> tuple[GraphExportSpec, ...]:
    return tuple(
        GraphExportSpec(
            name=f"{spec.metadata.key.replace('-', '_')}_agent_graph",
            factory=spec.graph_factory,
        )
        for spec in get_exportable_agent_subgraphs()
        if spec.graph_factory is not None
    )


def get_graph_export_specs() -> tuple[GraphExportSpec, ...]:
    seen_names: set[str] = set()
    export_specs: list[GraphExportSpec] = []
    for spec in (*_static_graph_export_specs(), *_agent_graph_export_specs()):
        if spec.name in seen_names:
            continue
        seen_names.add(spec.name)
        export_specs.append(spec)
    return tuple(export_specs)


def _render_png_bytes(compiled_graph: Any) -> bytes:
    graph = compiled_graph.get_graph()
    render_errors: list[Exception] = []

    for render_method_name in ("draw_mermaid_png", "draw_png"):
        render_method = getattr(graph, render_method_name, None)
        if render_method is None:
            continue
        try:
            return render_method()
        except Exception as exc:  # pragma: no cover
            render_errors.append(exc)

    if render_errors:
        raise RuntimeError(
            "Unable to render LangGraph PNG: "
            + "; ".join(f"{type(error).__name__}: {error}" for error in render_errors)
        )
    raise RuntimeError("Unable to render LangGraph PNG: no render methods available")


def export_agent_graph_images(output_dir: Path) -> list[Path]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported_paths: list[Path] = []
    for spec in get_graph_export_specs():
        png_bytes = _render_png_bytes(spec.factory())
        target_path = output_dir / f"{spec.name}.png"
        target_path.write_bytes(png_bytes)
        exported_paths.append(target_path)

    logger.info("Exported %s LangGraph PNG files into %s", len(exported_paths), output_dir)
    return exported_paths
