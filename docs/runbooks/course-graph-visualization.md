# Course Graph Visualization

Generate the current versioned course graph view from the ontology assets:

```powershell
uv run python scripts/generate_graph_visualization.py
```

Open the generated page:

```text
reports/generated/course-graph-visualization.html
```

Or serve the generated directory locally:

```powershell
uv run python -m http.server 8765 --directory reports/generated
```

Then open `http://127.0.0.1:8765/course-graph-visualization.html`.

The default view shows the 11 chapter nodes and aggregated chapter prerequisite edges.
Click a chapter in the left navigation to show its sections and concepts. Click a node
to inspect its identifier, summary, chapter and relation count. The right panel reports
hard-prerequisite cycles, order reversals, roots, leaves, isolated concepts and
cross-chapter dependencies.

The generated `course-graph-logic-report.json` is a machine-readable companion report.
The HTML and JSON outputs remain under `reports/generated/`, which is intentionally
ignored as generated output; rerun the script after ontology changes.
