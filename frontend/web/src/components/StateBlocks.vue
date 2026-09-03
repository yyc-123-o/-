<script setup lang="ts">
withDefaults(
  defineProps<{
    type?: "loading" | "empty" | "error";
    title?: string;
    message?: string;
    action?: string;
  }>(),
  {
    type: "empty",
    title: "",
    message: "",
    action: "",
  },
);

defineEmits<{ retry: [] }>();
</script>

<template>
  <div class="state-block" :class="`state-${type}`">
    <div class="state-icon">
      {{ type === "loading" ? "…" : type === "error" ? "!" : "○" }}
    </div>
    <strong>
      {{ title || (type === "loading" ? "正在加载" : type === "error" ? "暂时无法加载" : "还没有内容") }}
    </strong>
    <p>
      {{
        message
          || (type === "loading"
            ? "正在同步学习数据，请稍候。"
            : type === "error"
              ? "请检查连接状态后重试。"
              : "完成当前步骤后，这里会出现新的学习信息。")
      }}
    </p>
    <button v-if="type === 'error' && action" class="button button-secondary button-small" @click="$emit('retry')">
      {{ action }}
    </button>
  </div>
</template>
