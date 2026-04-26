from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from app.agents.chat_graph import get_chat_graph
from app.agents.provider_test_graph import get_provider_test_graph
from app.agents.rag_pipeline import get_rag_pipeline_graph
from app.agents.subgraph_registry import get_exportable_agent_subgraphs
from app.agents.validation_graph import get_validation_graph
from app.agents.vision_test_graph import get_vision_test_graph

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
        GraphExportSpec(name="vision_test_graph", factory=get_vision_test_graph),
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


def _write_index_manifest(output_dir: Path, exported_paths: list[Path]) -> None:
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "files": [
            {
                "name": path.name,
                "url": f"/api/langgraph-images/{path.name}",
            }
            for path in exported_paths
        ],
    }
    (output_dir / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_index_html(output_dir: Path, exported_paths: list[Path]) -> None:
    items_markup = "\n".join(
        (
            "<li>"
            f"<h2>{escape(path.stem)}</h2>"
            f"<p><a href=\"{escape(path.name)}\">{escape(path.name)}</a></p>"
            f"<img src=\"{escape(path.name)}\" alt=\"{escape(path.stem)}\" loading=\"lazy\">"
            "</li>"
        )
        for path in exported_paths
    )
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LangGraph Images</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: Arial, sans-serif;
      }}
      body {{
        margin: 0;
        padding: 24px;
        background: #f4f1ea;
        color: #1f2937;
      }}
      main {{
        max-width: 1200px;
        margin: 0 auto;
      }}
      h1 {{
        margin: 0 0 8px;
      }}
      p {{
        margin: 0 0 24px;
      }}
      ul {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 24px;
        list-style: none;
        padding: 0;
      }}
      li {{
        background: #ffffff;
        border: 1px solid #d6d3d1;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
      }}
      h2 {{
        margin: 0 0 8px;
        font-size: 20px;
      }}
      a {{
        color: #b45309;
        text-decoration: none;
      }}
      a:hover {{
        text-decoration: underline;
      }}
      img {{
        width: 100%;
        height: auto;
        display: block;
        margin-top: 12px;
        border-radius: 12px;
        background: #fff;
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>LangGraph Images</h1>
      <p>JSON manifest: <a href="index.json">index.json</a></p>
      <ul>
        {items_markup}
      </ul>
    </main>
  </body>
</html>
"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")


def _reset_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            continue
        child.unlink()


def export_agent_graph_images(output_dir: Path) -> list[Path]:
    _reset_output_dir(output_dir)

    exported_paths: list[Path] = []
    for spec in get_graph_export_specs():
        png_bytes = _render_png_bytes(spec.factory())
        target_path = output_dir / f"{spec.name}.png"
        target_path.write_bytes(png_bytes)
        exported_paths.append(target_path)

    _write_index_manifest(output_dir, exported_paths)
    _write_index_html(output_dir, exported_paths)
    logger.info("Exported %s LangGraph PNG files into %s", len(exported_paths), output_dir)
    return exported_paths
