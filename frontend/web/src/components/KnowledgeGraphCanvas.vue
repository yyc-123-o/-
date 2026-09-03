<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import * as dagre from "dagre";
import { LockKeyhole } from "lucide-vue-next";
import type { KnowledgeEdge, KnowledgeNode } from "@/types/knowledgeGraph";
import { formatMastery, getMasteryVisual, statusLabel } from "@/utils/mastery";

interface LayoutNode {
  node: KnowledgeNode;
  x: number;
  y: number;
}

interface LayoutEdge {
  edge: KnowledgeEdge;
  source: LayoutNode;
  target: LayoutNode;
  points: Array<{ x: number; y: number }>;
}

interface RankLabel {
  x: number;
  text: string;
}

const props = withDefaults(defineProps<{
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  selectedId?: string;
  recommendedPathNodeIds?: string[];
  zoom?: number;
  fitKey?: number;
}>(), {
  selectedId: "",
  recommendedPathNodeIds: () => [],
  zoom: 1,
  fitKey: 0,
});

const emit = defineEmits<{
  select: [string];
  "update:zoom": [number];
}>();

const viewport = ref<HTMLElement>();
const pan = ref({ x: 0, y: 0 });
const dragging = ref(false);
const dragOrigin = ref({ x: 0, y: 0 });
const panOrigin = ref({ x: 0, y: 0 });

const nodeWidth = 178;
const nodeHeight = 72;

const layout = computed(() => {
  if (!props.nodes.length) {
    return {
      nodes: [] as LayoutNode[],
      edges: [] as LayoutEdge[],
      width: 760,
      height: 500,
      rankLabels: [] as RankLabel[],
    };
  }

  const graph = new dagre.graphlib.Graph({ directed: true, multigraph: true });
  graph.setGraph({
    rankdir: "LR",
    align: "UL",
    nodesep: 42,
    edgesep: 18,
    ranksep: 108,
    marginx: 58,
    marginy: 70,
    acyclicer: "greedy",
    ranker: "network-simplex",
  });
  graph.setDefaultEdgeLabel(() => ({}));

  props.nodes.forEach((node) => {
    graph.setNode(node.id, {
      width: node.status === "recommended" ? nodeWidth + 8 : nodeWidth,
      height: node.status === "recommended" ? nodeHeight + 6 : nodeHeight,
    });
  });

  props.edges.forEach((edge) => {
    if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
    graph.setEdge(edge.source, edge.target, {
      minlen: 1,
      weight: edge.relation === "recommended" ? 3 : 1,
    }, edge.id);
  });

  dagre.layout(graph);

  const positioned = new Map<string, LayoutNode>();
  props.nodes.forEach((node) => {
    const item = graph.node(node.id) as dagre.Node | undefined;
    positioned.set(node.id, {
      node,
      x: item?.x || 0,
      y: item?.y || 0,
    });
  });

  const edges = props.edges
    .map<LayoutEdge | null>((edge) => {
      const source = positioned.get(edge.source);
      const target = positioned.get(edge.target);
      if (!source || !target) return null;
      const graphEdge = graph.edge({ v: edge.source, w: edge.target, name: edge.id }) as dagre.GraphEdge | undefined;
      return {
        edge,
        source,
        target,
        points: graphEdge?.points?.length ? graphEdge.points : [
          { x: source.x + nodeWidth / 2, y: source.y },
          { x: target.x - nodeWidth / 2, y: target.y },
        ],
      };
    })
    .filter((edge): edge is LayoutEdge => Boolean(edge));

  const graphLabel = graph.graph();
  const nodes = [...positioned.values()];
  const rankBuckets = new Map<number, LayoutNode[]>();
  nodes.forEach((item) => {
    const rankX = Math.round(item.x / 24) * 24;
    rankBuckets.set(rankX, [...(rankBuckets.get(rankX) || []), item]);
  });

  const rankLabels = [...rankBuckets.entries()]
    .sort(([a], [b]) => a - b)
    .map(([x, items], index, all) => {
      const stage = items.find((item) => item.node.stage)?.node.stage;
      return {
        x,
        text: stage || (index === 0 ? "基础准备" : index === all.length - 1 ? "应用与综合" : `核心阶段 ${index}`),
      };
    });

  return {
    nodes,
    edges,
    width: Math.max(760, Math.ceil((graphLabel.width || 760) + 80)),
    height: Math.max(500, Math.ceil((graphLabel.height || 500) + 80)),
    rankLabels,
  };
});

const selectedRelatedIds = computed(() => {
  if (!props.selectedId) return new Set<string>();
  const related = new Set([props.selectedId]);
  props.edges.forEach((edge) => {
    if (edge.source === props.selectedId || edge.target === props.selectedId) {
      related.add(edge.source);
      related.add(edge.target);
    }
  });
  return related;
});

const recommendedIds = computed(() => new Set(props.recommendedPathNodeIds));

function nodeOpacity(node: KnowledgeNode) {
  if (!props.selectedId || selectedRelatedIds.value.has(node.id)) return getMasteryVisual(node.mastery, node.status).opacity;
  return 0.38;
}

function nodeStyle(item: LayoutNode) {
  const visual = getMasteryVisual(item.node.mastery, item.node.status);
  return {
    left: `${item.x}px`,
    top: `${item.y}px`,
    opacity: nodeOpacity(item.node),
    "--node-bg": visual.background,
    "--node-border": visual.border,
    "--node-text": visual.color,
    "--node-accent": visual.accent,
    "--node-border-style": visual.borderStyle,
  };
}

function isRecommendedEdge(edge: LayoutEdge) {
  return recommendedIds.value.has(edge.edge.source) && recommendedIds.value.has(edge.edge.target);
}

function isCompletedEdge(edge: LayoutEdge) {
  return ["completed", "mastered"].includes(edge.source.node.status)
    && ["completed", "mastered", "learning", "recommended"].includes(edge.target.node.status);
}

function edgeClass(edge: LayoutEdge) {
  const related = selectedRelatedIds.value.has(edge.edge.source)
    && selectedRelatedIds.value.has(edge.edge.target);
  return {
    "is-recommended": isRecommendedEdge(edge),
    "is-related": edge.edge.relation === "related",
    "is-dimmed": Boolean(props.selectedId) && !related,
    "is-completed": isCompletedEdge(edge),
  };
}

function edgeMarker(edge: LayoutEdge) {
  if (isRecommendedEdge(edge)) return "url(#knowledge-edge-arrow-active)";
  if (isCompletedEdge(edge)) return "url(#knowledge-edge-arrow-done)";
  return "url(#knowledge-edge-arrow)";
}

function edgePath(edge: LayoutEdge) {
  const points = edge.points;
  if (points.length < 2) return "";
  if (points.length === 2) {
    const [start, end] = points;
    const curve = Math.max(42, Math.abs(end.x - start.x) * 0.42);
    return `M ${start.x} ${start.y} C ${start.x + curve} ${start.y}, ${end.x - curve} ${end.y}, ${end.x} ${end.y}`;
  }
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

function changeZoom(delta: number, origin?: { x: number; y: number }) {
  const nextZoom = Math.min(1.65, Math.max(0.48, Number(((props.zoom || 1) + delta).toFixed(2))));
  if (origin && viewport.value) {
    const graphX = (origin.x - pan.value.x) / props.zoom;
    const graphY = (origin.y - pan.value.y) / props.zoom;
    pan.value = {
      x: origin.x - graphX * nextZoom,
      y: origin.y - graphY * nextZoom,
    };
  }
  emit("update:zoom", nextZoom);
}

function fitCanvas() {
  const box = viewport.value?.getBoundingClientRect();
  if (!box) return;
  const padding = box.width < 640 ? 22 : 42;
  const fitZoom = Math.min(
    1,
    Math.max(
      0.48,
      Math.min((box.width - padding) / layout.value.width, (box.height - padding) / layout.value.height),
    ),
  );
  emit("update:zoom", Number(fitZoom.toFixed(2)));
  pan.value = {
    x: Math.max(12, (box.width - layout.value.width * fitZoom) / 2),
    y: Math.max(12, (box.height - layout.value.height * fitZoom) / 2),
  };
}

function focusNode(id: string) {
  const box = viewport.value?.getBoundingClientRect();
  const item = layout.value.nodes.find((node) => node.node.id === id);
  if (!box || !item) return;
  pan.value = {
    x: box.width / 2 - item.x * props.zoom,
    y: box.height / 2 - item.y * props.zoom,
  };
}

function focusMiniMap(event: MouseEvent) {
  const box = viewport.value?.getBoundingClientRect();
  const targetBox = (event.currentTarget as HTMLElement).getBoundingClientRect();
  if (!box || !targetBox.width || !targetBox.height) return;
  const x = ((event.clientX - targetBox.left) / targetBox.width) * layout.value.width;
  const y = ((event.clientY - targetBox.top) / targetBox.height) * layout.value.height;
  pan.value = {
    x: box.width / 2 - x * props.zoom,
    y: box.height / 2 - y * props.zoom,
  };
}

function onPointerDown(event: PointerEvent) {
  if (event.button !== 0 || (event.target as HTMLElement).closest(".graph-node")) return;
  dragging.value = true;
  dragOrigin.value = { x: event.clientX, y: event.clientY };
  panOrigin.value = { ...pan.value };
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function onPointerMove(event: PointerEvent) {
  if (!dragging.value) return;
  pan.value = {
    x: panOrigin.value.x + event.clientX - dragOrigin.value.x,
    y: panOrigin.value.y + event.clientY - dragOrigin.value.y,
  };
}

function stopDragging() {
  dragging.value = false;
}

function onWheel(event: WheelEvent) {
  event.preventDefault();
  const rect = viewport.value?.getBoundingClientRect();
  changeZoom(event.deltaY > 0 ? -0.08 : 0.08, rect ? { x: event.clientX - rect.left, y: event.clientY - rect.top } : undefined);
}

watch(
  () => [props.nodes.map((node) => node.id).join("|"), props.edges.map((edge) => edge.id).join("|"), props.fitKey],
  () => nextTick(fitCanvas),
  { immediate: true },
);

watch(() => props.selectedId, (id) => {
  if (id) nextTick(() => focusNode(id));
});
</script>

<template>
  <div class="knowledge-graph-canvas">
    <div class="knowledge-graph-canvas__toolbar">
      <span>{{ layout.nodes.length }} 个知识点 · {{ layout.edges.length }} 条先修关系</span>
      <div class="knowledge-graph-canvas__tools">
        <button type="button" aria-label="适应画布" title="适应画布" @click="fitCanvas">适应画布</button>
        <button type="button" aria-label="缩小图谱" title="缩小图谱" @click="changeZoom(-0.1)">−</button>
        <b>{{ Math.round(zoom * 100) }}%</b>
        <button type="button" aria-label="放大图谱" title="放大图谱" @click="changeZoom(0.1)">+</button>
      </div>
    </div>

    <div
      ref="viewport"
      class="knowledge-graph-viewport"
      :class="{ 'is-dragging': dragging }"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="stopDragging"
      @pointercancel="stopDragging"
      @wheel="onWheel"
    >
      <div
        v-if="layout.nodes.length"
        class="knowledge-graph-stage"
        :style="{
          width: `${layout.width}px`,
          height: `${layout.height}px`,
          transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
        }"
      >
        <div class="knowledge-graph-rank-labels" aria-hidden="true">
          <span
            v-for="label in layout.rankLabels"
            :key="`${label.x}-${label.text}`"
            :style="{ left: `${label.x}px` }"
          >
            {{ label.text }}
          </span>
        </div>

        <svg
          class="knowledge-graph-edges"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
          :width="layout.width"
          :height="layout.height"
          aria-hidden="true"
        >
          <defs>
            <marker id="knowledge-edge-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#b8c6d6" />
            </marker>
            <marker id="knowledge-edge-arrow-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#2f6bff" />
            </marker>
            <marker id="knowledge-edge-arrow-done" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#269eab" />
            </marker>
          </defs>
          <path
            v-for="edge in layout.edges"
            :key="edge.edge.id"
            class="knowledge-graph-edge"
            :class="edgeClass(edge)"
            :d="edgePath(edge)"
            :marker-end="edgeMarker(edge)"
          />
        </svg>

        <button
          v-for="item in layout.nodes"
          :key="item.node.id"
          type="button"
          class="graph-node graph-node--rect"
          :class="[`is-${item.node.status}`, { 'is-selected': item.node.id === selectedId }]"
          :style="nodeStyle(item)"
          :title="item.node.description || item.node.title"
          :aria-label="`${item.node.title}，${statusLabel(item.node.status)}，掌握度 ${formatMastery(item.node.mastery)}`"
          @click.stop="emit('select', item.node.id)"
        >
          <span class="graph-node-status-dot" />
          <span class="graph-node-copy">
            <strong>{{ item.node.title }}</strong>
            <small>{{ statusLabel(item.node.status) }} · {{ item.node.mastery === null ? "暂无测评" : formatMastery(item.node.mastery) }}</small>
          </span>
          <span class="graph-node-time">{{ item.node.estimatedMinutes ? `${item.node.estimatedMinutes} 分钟` : "暂无时间" }}</span>
          <span v-if="item.node.status === 'locked'" class="graph-node-lock"><LockKeyhole :size="13" /></span>
          <span v-if="item.node.status === 'recommended'" class="graph-node-recommend">推荐下一步</span>
        </button>
      </div>
      <div v-else class="knowledge-graph-empty">
        <strong>当前筛选范围没有知识点</strong>
        <span>调整视图或知识领域筛选后重试。</span>
      </div>
    </div>

    <button
      v-if="layout.nodes.length"
      type="button"
      class="knowledge-graph-minimap"
      aria-label="点击缩略图定位知识图谱"
      @click="focusMiniMap"
    >
      <svg viewBox="0 0 180 90" preserveAspectRatio="none" aria-hidden="true">
        <path
          v-for="edge in layout.edges"
          :key="`mini-${edge.edge.id}`"
          :d="`M ${edge.source.x / layout.width * 180} ${edge.source.y / layout.height * 90} L ${edge.target.x / layout.width * 180} ${edge.target.y / layout.height * 90}`"
          class="knowledge-graph-minimap-edge"
        />
        <circle
          v-for="item in layout.nodes"
          :key="`mini-${item.node.id}`"
          :cx="item.x / layout.width * 180"
          :cy="item.y / layout.height * 90"
          r="2.2"
          :class="{ 'is-current': item.node.id === selectedId, 'is-recommended': item.node.status === 'recommended' }"
        />
      </svg>
    </button>
  </div>
</template>
