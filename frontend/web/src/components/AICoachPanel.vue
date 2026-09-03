<script setup lang="ts">
import { MessageCircle, Send, Sparkles } from "lucide-vue-next";
import { ref } from "vue";
const message = ref("");
const props = defineProps<{ compact?: boolean; answer?: string; loading?: boolean; error?: string }>();
const emit = defineEmits<{ send: [string] }>();
function send() {
  if (message.value.trim() && !props.loading) {
    emit("send", message.value.trim());
    message.value = "";
  }
}
</script>
<template>
  <section class="coach-panel" :class="{ compact }">
    <div class="card-topline"><span class="ai-mark"><Sparkles :size="14" /></span><span class="eyebrow">AI COACH</span></div>
    <h3>把问题带进学习过程</h3>
    <p>我会用提示和追问帮助你自己找到答案，不直接替你完成思考。</p>
    <div class="coach-prompt"><MessageCircle :size="15" /><span>试着问：为什么卷积适合处理图像？</span></div>
    <div v-if="answer" class="coach-answer">{{ answer }}</div>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <div class="coach-input"><input v-model="message" :disabled="loading" placeholder="向 AI 学习顾问提问" @keyup.enter="send" /><button class="icon-button" :disabled="loading" title="发送问题" @click="send"><Send :size="16" /></button></div>
    <small v-if="loading" class="coach-loading">正在向 AI 学习顾问提问…</small>
  </section>
</template>
