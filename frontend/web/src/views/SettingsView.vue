<script setup lang="ts">
import {
  AlertCircle,
  Bell,
  ChevronRight,
  Clock3,
  Database,
  Download,
  KeyRound,
  Laptop,
  LogOut,
  Mail,
  Palette,
  Phone,
  RotateCcw,
  Save,
  Shield,
  Upload,
  UserRound,
} from "lucide-vue-next";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useLearnerStore } from "@/stores/learner";

type SettingsTab = "account" | "learning" | "notifications" | "appearance" | "privacy" | "security";
type ModalType = "logout" | "email" | "phone" | "clearRecords" | "logoutDevices" | null;

interface AccountProfile {
  avatar: string;
  nickname: string;
  username: string;
  email: string;
  phone: string;
  accountStatus: string;
  createdAt: string;
  lastLoginAt: string;
  passwordStatus: string;
}

interface UserSettings {
  notificationEnabled: boolean;
  reminderTime: string;
  theme: string;
  contentDensity: string;
  personalizedRecommendationEnabled: boolean;
  dataCollectionConsent: boolean;
}

const route = useRoute();
const router = useRouter();
const learnerStore = useLearnerStore();

const tabs: Array<{ key: SettingsTab; label: string; description: string; icon: unknown }> = [
  { key: "account", label: "账号资料", description: "头像、姓名与基础信息", icon: UserRound },
  { key: "learning", label: "学习偏好", description: "目标、节奏与内容形式", icon: Clock3 },
  { key: "notifications", label: "通知提醒", description: "任务、测评与反馈提醒", icon: Bell },
  { key: "appearance", label: "外观显示", description: "主题、密度与可访问性", icon: Palette },
  { key: "privacy", label: "隐私与数据", description: "数据授权与导出", icon: Database },
  { key: "security", label: "登录安全", description: "密码、设备与账号保护", icon: Shield },
];

const activeTab = ref<SettingsTab>("account");
const modal = ref<ModalType>(null);
const avatarPreview = ref("");
const avatarError = ref("");
const saveMessage = ref("");

const profile = computed(() => learnerStore.profile);
const learnerName = computed(() => {
  const value = profile.value?.learner?.name || learnerStore.learnerName;
  return value && !value.includes("瀛") ? value : "学习者";
});
const selfAssessment = computed(() => profile.value?.learner?.self_assessment);
const accountProfile = computed<AccountProfile>(() => ({
  avatar: avatarPreview.value,
  nickname: learnerName.value,
  username: profile.value?.learner_id || "未提供用户名",
  email: "未绑定邮箱",
  phone: "未绑定手机",
  accountStatus: "正常",
  createdAt: "暂无注册时间",
  lastLoginAt: "当前会话",
  passwordStatus: "已设置",
}));
const email = computed(() => accountProfile.value.email);
const phone = computed(() => accountProfile.value.phone);
const username = computed(() => accountProfile.value.username);
const accountStatus = computed(() => accountProfile.value.accountStatus);
const createdAt = computed(() => accountProfile.value.createdAt);
const lastLoginAt = computed(() => accountProfile.value.lastLoginAt);
const passwordStatus = computed(() => accountProfile.value.passwordStatus);
const securityScore = computed(() => {
  let score = 1;
  if (email.value !== "未绑定邮箱") score += 1;
  if (phone.value !== "未绑定手机") score += 1;
  return score;
});
const securityLevel = computed(() => (securityScore.value >= 3 ? "高" : securityScore.value >= 2 ? "中" : "基础"));

const accountForm = reactive({
  nickname: "",
  username: "",
  email: "",
  phone: "",
});

const initialAccount = reactive({ ...accountForm });

const learningPrefs = reactive({
  weeklyHours: 6,
  pace: "balanced",
  contentOrder: "path-first",
  codeLanguage: "Python",
  presentation: "图文讲解 + 练习",
  projectOrientation: true,
});

const notificationPrefs = reactive({
  dailyTask: true,
  pathUpdate: true,
  assessmentFeedback: true,
  weeklyReport: false,
  reminderTime: "20:00",
});

const appearancePrefs = reactive({
  theme: "light",
  density: "comfortable",
  fontSize: "standard",
  reduceMotion: false,
});

const privacyPrefs = reactive({
  useLearningData: true,
  personalizePath: true,
  shareAnonymousStats: false,
  retention: "12个月",
});

const userSettings = computed<UserSettings>(() => ({
  notificationEnabled: notificationPrefs.dailyTask,
  reminderTime: notificationPrefs.reminderTime,
  theme: appearancePrefs.theme,
  contentDensity: appearancePrefs.density,
  personalizedRecommendationEnabled: privacyPrefs.personalizePath,
  dataCollectionConsent: privacyPrefs.useLearningData,
}));

const passwordForm = reactive({
  oldPassword: "",
  newPassword: "",
  confirmPassword: "",
});

function hydrateAccountForm() {
  const next = {
    nickname: learnerName.value,
    username: username.value,
    email: email.value,
    phone: phone.value,
  };
  Object.assign(accountForm, next);
  Object.assign(initialAccount, next);
  learningPrefs.weeklyHours = selfAssessment.value?.weekly_hours || 6;
}

watch(profile, hydrateAccountForm, { immediate: true });

watch(
  () => route.query.tab,
  (value) => {
    const key = Array.isArray(value) ? value[0] : value;
    activeTab.value = tabs.some((tab) => tab.key === key) ? (key as SettingsTab) : "account";
  },
  { immediate: true },
);

const avatarInitial = computed(() => learnerName.value.slice(0, 1).toUpperCase());
const hasAccountChanges = computed(() => JSON.stringify(accountForm) !== JSON.stringify(initialAccount) || Boolean(avatarPreview.value));

const devices = [
  { name: "当前浏览器", location: "本地会话", time: "正在使用", icon: Laptop },
];

function setTab(tab: SettingsTab) {
  router.push({ path: "/settings", query: { tab } });
}

function triggerUpload() {
  document.getElementById("avatarUpload")?.click();
}

function onAvatarSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  avatarError.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    avatarError.value = "请选择图片文件。";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    avatarError.value = "图片大小不能超过 2MB。";
    return;
  }
  if (avatarPreview.value) URL.revokeObjectURL(avatarPreview.value);
  avatarPreview.value = URL.createObjectURL(file);
}

function saveAccount() {
  if (!accountForm.nickname.trim()) {
    saveMessage.value = "昵称不能为空。";
    return;
  }
  Object.assign(initialAccount, { ...accountForm });
  saveMessage.value = "资料已在本地暂存，服务端同步接口暂未开放。";
}

function resetAccount() {
  Object.assign(accountForm, { ...initialAccount });
  saveMessage.value = "";
  if (avatarPreview.value) URL.revokeObjectURL(avatarPreview.value);
  avatarPreview.value = "";
}

function saveLocalPreference(label: string) {
  saveMessage.value = `${label}已在本地暂存，连接到对应接口后可同步到平台。`;
}

function confirmLogout() {
  localStorage.removeItem("zhijing.session");
  sessionStorage.clear();
  modal.value = null;
  router.push("/login");
}

onBeforeUnmount(() => {
  if (avatarPreview.value) URL.revokeObjectURL(avatarPreview.value);
});
</script>

<template>
  <div class="settings-page">
    <header class="settings-hero">
      <div>
        <p class="settings-breadcrumb">智数助手 / 设置</p>
        <h1>设置</h1>
        <p>管理账号信息和平台使用偏好。</p>
      </div>
      <button class="button button-secondary logout-button" type="button" @click="modal = 'logout'">
        <LogOut :size="17" />
        退出登录
      </button>
    </header>

    <nav class="settings-tabs" aria-label="设置分类">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="settings-tab"
        :class="{ active: activeTab === tab.key }"
        type="button"
        @click="setTab(tab.key)"
      >
        <component :is="tab.icon" :size="18" />
        <span>
          <strong>{{ tab.label }}</strong>
          <small>{{ tab.description }}</small>
        </span>
      </button>
    </nav>

    <main class="settings-content">
      <section v-if="activeTab === 'account'" class="settings-grid">
        <article class="settings-panel account-panel">
          <div class="panel-heading">
            <div>
              <h2>账号资料</h2>
              <p>仅管理头像、昵称和账号绑定信息。</p>
            </div>
            <span class="status-pill">本地资料</span>
          </div>

          <div class="avatar-row">
            <div class="avatar-large">
              <img v-if="avatarPreview" :src="avatarPreview" alt="头像预览" />
              <span v-else>{{ avatarInitial }}</span>
            </div>
            <div>
              <strong>{{ learnerName }}</strong>
              <p>{{ accountStatus }} · {{ username }}</p>
              <input id="avatarUpload" class="visually-hidden" type="file" accept="image/*" @change="onAvatarSelected" />
              <button class="button button-secondary compact-button" type="button" @click="triggerUpload">
                <Upload :size="16" />
                更换头像
              </button>
              <p v-if="avatarError" class="form-error">{{ avatarError }}</p>
            </div>
          </div>

          <div class="form-grid">
            <label>
              <span>昵称</span>
              <input v-model="accountForm.nickname" type="text" autocomplete="nickname" />
            </label>
            <label>
              <span>用户名</span>
              <input v-model="accountForm.username" type="text" disabled />
            </label>
            <label>
              <span>邮箱</span>
              <input v-model="accountForm.email" type="text" disabled />
            </label>
            <label>
              <span>手机</span>
              <input v-model="accountForm.phone" type="text" disabled />
            </label>
            <label>
              <span>账号状态</span>
              <input :value="accountStatus" type="text" disabled />
            </label>
            <label>
              <span>最近登录</span>
              <input :value="lastLoginAt" type="text" disabled />
            </label>
          </div>

          <div class="settings-actions">
            <p>{{ saveMessage || "当前页面不会伪造接口保存结果。" }}</p>
            <div>
              <button class="button button-secondary" type="button" :disabled="!hasAccountChanges" @click="resetAccount">
                <RotateCcw :size="16" />
                取消修改
              </button>
              <button class="button button-primary" type="button" @click="saveAccount">
                <Save :size="16" />
                保存资料
              </button>
            </div>
          </div>
        </article>

        <aside class="settings-aside">
          <article class="settings-panel compact-panel">
            <div class="completion-head">
              <div>
                <h3>账号安全</h3>
                <p>安全等级：{{ securityLevel }}</p>
              </div>
              <strong>{{ securityScore }}/3</strong>
            </div>
            <div class="info-list">
              <div>
                <Mail :size="17" />
                <span>
                  <strong>{{ email }}</strong>
                  <small>{{ email === "未绑定邮箱" ? "邮箱未绑定" : "邮箱已验证" }}</small>
                </span>
                <button type="button" @click="modal = 'email'">修改</button>
              </div>
              <div>
                <Phone :size="17" />
                <span>
                  <strong>{{ phone }}</strong>
                  <small>{{ phone === "未绑定手机" ? "手机未绑定" : "手机已验证" }}</small>
                </span>
                <button type="button" @click="modal = 'phone'">更换</button>
              </div>
              <div>
                <KeyRound :size="17" />
                <span>
                  <strong>密码：{{ passwordStatus }}</strong>
                  <small>注册时间：{{ createdAt }} · 最近登录：{{ lastLoginAt }}</small>
                </span>
                <button type="button" @click="setTab('security')">完善</button>
              </div>
            </div>
            <button class="button button-secondary wide-button" type="button" @click="setTab('security')">
              完善安全设置
              <ChevronRight :size="16" />
            </button>
          </article>

          <article class="settings-panel compact-panel">
            <h3>快捷设置</h3>
            <div class="quick-list">
              <button type="button" @click="setTab('notifications')"><span>学习提醒</span><b>{{ userSettings.notificationEnabled ? "已开启" : "已关闭" }}</b></button>
              <button type="button" @click="setTab('notifications')"><span>消息通知</span><b>{{ notificationPrefs.pathUpdate ? "已开启" : "已关闭" }}</b></button>
              <button type="button" @click="setTab('appearance')"><span>界面主题</span><b>{{ userSettings.theme === "light" ? "浅色" : "跟随系统" }}</b></button>
              <button type="button" @click="setTab('appearance')"><span>内容密度</span><b>{{ userSettings.contentDensity === "comfortable" ? "舒适" : "紧凑" }}</b></button>
            </div>
          </article>
        </aside>
      </section>

      <section v-else-if="activeTab === 'learning'" class="settings-panel single-panel">
        <div class="panel-heading">
          <div>
            <h2>学习偏好</h2>
            <p>调整系统生成学习路径时参考的节奏和内容偏好。</p>
          </div>
        </div>
        <div class="preference-grid">
          <label><span>每周学习时长</span><input v-model.number="learningPrefs.weeklyHours" type="number" min="1" max="40" /></label>
          <label><span>学习节奏</span><select v-model="learningPrefs.pace"><option value="steady">稳步推进</option><option value="balanced">均衡节奏</option><option value="intensive">集中强化</option></select></label>
          <label><span>内容顺序</span><select v-model="learningPrefs.contentOrder"><option value="path-first">先路径后资源</option><option value="resource-first">先资源后练习</option></select></label>
          <label><span>代码语言</span><select v-model="learningPrefs.codeLanguage"><option>Python</option><option>JavaScript</option><option>C++</option></select></label>
          <label class="wide-field"><span>内容呈现</span><input v-model="learningPrefs.presentation" type="text" /></label>
          <label class="toggle-row"><span>优先推荐项目实践</span><label class="switch"><input v-model="learningPrefs.projectOrientation" type="checkbox" /><span /></label></label>
        </div>
        <button class="button button-primary align-right" type="button" @click="saveLocalPreference('学习偏好')">保存偏好</button>
      </section>

      <section v-else-if="activeTab === 'notifications'" class="settings-panel single-panel">
        <div class="panel-heading"><div><h2>通知提醒</h2><p>只提醒与学习任务、测评反馈和路径更新有关的内容。</p></div></div>
        <div class="settings-list">
          <label><span><strong>每日学习任务</strong><small>提醒你完成今天的路径节点。</small></span><label class="switch"><input v-model="notificationPrefs.dailyTask" type="checkbox" /><span /></label></label>
          <label><span><strong>路径更新</strong><small>AI 根据反馈调整学习路径后提醒。</small></span><label class="switch"><input v-model="notificationPrefs.pathUpdate" type="checkbox" /><span /></label></label>
          <label><span><strong>测评反馈</strong><small>测评结果可查看时提醒。</small></span><label class="switch"><input v-model="notificationPrefs.assessmentFeedback" type="checkbox" /><span /></label></label>
          <label><span><strong>周报总结</strong><small>每周汇总学习进度和下一步建议。</small></span><label class="switch"><input v-model="notificationPrefs.weeklyReport" type="checkbox" /><span /></label></label>
        </div>
        <div class="inline-setting">
          <label><span>默认提醒时间</span><input v-model="notificationPrefs.reminderTime" type="time" /></label>
          <button class="button button-primary" type="button" @click="saveLocalPreference('通知设置')">保存提醒</button>
        </div>
      </section>

      <section v-else-if="activeTab === 'appearance'" class="settings-panel single-panel">
        <div class="panel-heading"><div><h2>外观显示</h2><p>保持当前产品视觉体系，只开放不会影响页面结构的显示偏好。</p></div></div>
        <div class="option-cards">
          <button :class="{ active: appearancePrefs.theme === 'light' }" type="button" @click="appearancePrefs.theme = 'light'"><Palette :size="18" /><strong>浅色主题</strong><small>当前支持</small></button>
          <button :class="{ active: appearancePrefs.theme === 'system' }" type="button" @click="appearancePrefs.theme = 'system'"><Laptop :size="18" /><strong>跟随系统</strong><small>本地偏好</small></button>
        </div>
        <div class="preference-grid">
          <label><span>界面密度</span><select v-model="appearancePrefs.density"><option value="comfortable">舒适</option><option value="compact">紧凑</option></select></label>
          <label><span>字号</span><select v-model="appearancePrefs.fontSize"><option value="standard">标准</option><option value="large">偏大</option></select></label>
          <label class="toggle-row wide-field"><span>减少页面动画</span><label class="switch"><input v-model="appearancePrefs.reduceMotion" type="checkbox" /><span /></label></label>
        </div>
        <button class="button button-primary align-right" type="button" @click="saveLocalPreference('外观偏好')">保存显示偏好</button>
      </section>

      <section v-else-if="activeTab === 'privacy'" class="settings-panel single-panel">
        <div class="panel-heading"><div><h2>隐私与数据</h2><p>管理数据授权、导出和匿名统计偏好。</p></div></div>
        <div class="settings-list">
          <label><span><strong>允许用于个性化路径</strong><small>关闭后，AI 只能使用基础课程规则生成路径。</small></span><label class="switch"><input v-model="privacyPrefs.personalizePath" type="checkbox" /><span /></label></label>
          <label><span><strong>允许使用学习行为数据</strong><small>用于平台提供个性化服务授权。</small></span><label class="switch"><input v-model="privacyPrefs.useLearningData" type="checkbox" /><span /></label></label>
          <label><span><strong>参与匿名统计</strong><small>仅用于改进课程推荐效果，不包含个人身份。</small></span><label class="switch"><input v-model="privacyPrefs.shareAnonymousStats" type="checkbox" /><span /></label></label>
        </div>
        <div class="inline-setting">
          <label><span>数据保留周期</span><select v-model="privacyPrefs.retention"><option>6个月</option><option>12个月</option><option>24个月</option></select></label>
          <button class="button button-secondary" type="button"><Download :size="16" /> 导出数据</button>
          <button class="button button-secondary danger-lite" type="button" @click="modal = 'clearRecords'">清理学习记录</button>
        </div>
      </section>

      <section v-else class="settings-grid">
        <article class="settings-panel account-panel">
          <div class="panel-heading"><div><h2>登录安全</h2><p>管理密码、绑定方式和最近登录设备。</p></div><span class="status-pill success">保护中</span></div>
          <div class="form-grid">
            <label><span>当前密码</span><input v-model="passwordForm.oldPassword" type="password" autocomplete="current-password" /></label>
            <label><span>新密码</span><input v-model="passwordForm.newPassword" type="password" autocomplete="new-password" /></label>
            <label><span>确认新密码</span><input v-model="passwordForm.confirmPassword" type="password" autocomplete="new-password" /></label>
          </div>
          <button class="button button-primary align-right" type="button" @click="saveLocalPreference('密码修改请求')">
            <KeyRound :size="16" />
            提交修改
          </button>
        </article>
        <aside class="settings-aside">
          <article class="settings-panel compact-panel">
            <h3>绑定方式</h3>
            <div class="info-list">
              <div><Mail :size="17" /><span><strong>{{ email }}</strong><small>邮箱已绑定</small></span><button type="button" @click="modal = 'email'">修改</button></div>
              <div><Phone :size="17" /><span><strong>{{ phone }}</strong><small>手机已绑定</small></span><button type="button" @click="modal = 'phone'">更换</button></div>
            </div>
          </article>
          <article class="settings-panel compact-panel">
            <h3>最近设备</h3>
            <div class="device-list">
              <div v-for="device in devices" :key="device.name">
                <component :is="device.icon" :size="18" />
                <span><strong>{{ device.name }}</strong><small>{{ device.location }} · {{ device.time }}</small></span>
              </div>
            </div>
            <button class="button button-secondary wide-button" type="button" @click="modal = 'logoutDevices'">退出其他设备</button>
          </article>
        </aside>
      </section>
    </main>

    <div v-if="modal" class="modal-backdrop" role="presentation" @click.self="modal = null">
      <section class="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settingsModalTitle">
        <AlertCircle :size="22" />
        <h2 id="settingsModalTitle">
          {{
            modal === "logout"
              ? "确认退出登录？"
              : modal === "clearRecords"
                ? "确认清理学习记录？"
                : modal === "logoutDevices"
                  ? "退出其他设备？"
                  : "功能待接入"
          }}
        </h2>
        <p>
          {{
            modal === "logout"
              ? "退出后需要重新登录才能访问学习工作区。"
              : modal === "clearRecords"
                ? "当前项目未开放清理记录接口，因此不会直接删除服务端数据。"
                : modal === "logoutDevices"
                  ? "当前项目未开放设备管理接口，本操作会先记录为本地请求。"
                  : "当前项目尚未提供对应接口，暂不伪造保存结果。"
          }}
        </p>
        <div class="modal-actions">
          <button class="button button-secondary" type="button" @click="modal = null">取消</button>
          <button v-if="modal === 'logout'" class="button button-primary" type="button" @click="confirmLogout">退出登录</button>
          <button v-else class="button button-primary" type="button" @click="modal = null">知道了</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  color: #183153;
}

.settings-hero,
.settings-tabs,
.settings-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.settings-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 150px;
  padding: 28px 32px;
  border-radius: 18px;
}

.settings-breadcrumb {
  margin: 0 0 10px;
  color: #2f76d2;
  font-size: 13px;
  font-weight: 700;
}

.settings-hero h1,
.panel-heading h2,
.settings-panel h3 {
  margin: 0;
  color: #0f2f63;
}

.settings-hero h1 {
  font-size: clamp(30px, 3vw, 42px);
  line-height: 1.15;
}

.settings-hero p,
.panel-heading p,
.completion-head p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.7;
}

.logout-button {
  flex: 0 0 auto;
}

.settings-tabs {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  border-radius: 16px;
  overflow-x: auto;
}

.settings-tab {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 64px;
  padding: 10px 12px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #64748b;
  text-align: left;
  cursor: pointer;
}

.settings-tab svg {
  flex: 0 0 auto;
}

.settings-tab span {
  min-width: 0;
}

.settings-tab strong,
.settings-tab small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-tab strong {
  color: #1e3a5f;
  font-size: 14px;
}

.settings-tab small {
  margin-top: 3px;
  font-size: 12px;
}

.settings-tab:hover,
.settings-tab.active {
  background: #eef6ff;
  color: #2563eb;
}

.settings-tab.active {
  box-shadow: inset 0 -2px 0 #2563eb;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(320px, 0.85fr);
  gap: 20px;
  align-items: start;
}

.settings-panel {
  border-radius: 18px;
  padding: 24px;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px;
  border: 1px solid #e5edf6;
  border-radius: 16px;
  background: #f8fbff;
}

.avatar-large {
  display: grid;
  place-items: center;
  width: 76px;
  height: 76px;
  flex: 0 0 76px;
  overflow: hidden;
  border-radius: 24px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 30px;
  font-weight: 800;
}

.avatar-large img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-row strong {
  color: #0f2f63;
  font-size: 18px;
}

.avatar-row p {
  margin: 6px 0 12px;
  color: #64748b;
}

.form-grid,
.preference-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 22px;
}

.form-grid label,
.preference-grid label,
.inline-setting label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  color: #415a77;
  font-size: 13px;
  font-weight: 700;
}

.form-grid input,
.form-grid select,
.preference-grid input,
.preference-grid select,
.inline-setting input,
.inline-setting select {
  width: 100%;
  min-height: 44px;
  border: 1px solid #d9e4ef;
  border-radius: 12px;
  background: #fff;
  color: #183153;
  font: inherit;
  padding: 0 12px;
  outline: none;
}

.form-grid input:focus,
.form-grid select:focus,
.preference-grid input:focus,
.preference-grid select:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.form-grid input:disabled {
  color: #64748b;
  background: #f8fafc;
  cursor: not-allowed;
}

.wide-field {
  grid-column: 1 / -1;
}

.toggle-row {
  flex-direction: row !important;
  align-items: center;
  justify-content: space-between;
  min-height: 52px;
  padding: 0 2px;
}

.settings-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 24px;
  padding-top: 18px;
  border-top: 1px solid #edf2f7;
}

.settings-actions p {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.settings-actions div {
  display: flex;
  gap: 10px;
}

.settings-aside {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.compact-panel {
  padding: 20px;
}

.completion-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.completion-head strong {
  color: #2563eb;
  font-size: 28px;
}

.progress-track {
  height: 8px;
  margin: 18px 0;
  overflow: hidden;
  border-radius: 999px;
  background: #e6eef8;
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563eb;
}

.check-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: #64748b;
  font-size: 13px;
}

.check-list li {
  display: flex;
  align-items: center;
  gap: 8px;
}

.check-list .done {
  color: #047857;
}

.info-list,
.device-list,
.settings-list {
  display: grid;
  gap: 12px;
}

.info-list > div,
.device-list > div,
.settings-list > label {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 12px;
  border: 1px solid #edf2f7;
  border-radius: 14px;
  background: #fbfdff;
}

.info-list span,
.device-list span,
.settings-list span {
  display: grid;
  gap: 3px;
  min-width: 0;
  flex: 1;
}

.info-list strong,
.device-list strong,
.settings-list strong {
  overflow: hidden;
  color: #183153;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-list small,
.device-list small,
.settings-list small {
  color: #64748b;
  line-height: 1.5;
}

.info-list button {
  border: 0;
  background: transparent;
  color: #2563eb;
  font-weight: 700;
  cursor: pointer;
}

.quick-list {
  display: grid;
  gap: 10px;
}

.quick-list button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 0 12px;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  background: #fbfdff;
  color: #415a77;
  font: inherit;
  cursor: pointer;
}

.quick-list button:hover,
.quick-list button:focus-visible {
  border-color: #bfdbfe;
  background: #eef6ff;
  outline: none;
}

.quick-list span {
  color: #415a77;
  font-size: 13px;
  font-weight: 700;
}

.quick-list b {
  color: #2563eb;
  font-size: 13px;
}

.single-panel {
  max-width: 980px;
}

.option-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.option-cards button {
  display: grid;
  gap: 8px;
  min-height: 112px;
  padding: 18px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #fbfdff;
  color: #415a77;
  text-align: left;
  cursor: pointer;
}

.option-cards button.active {
  border-color: #2563eb;
  background: #eef6ff;
  color: #1d4ed8;
}

.inline-setting {
  display: flex;
  align-items: end;
  gap: 14px;
  margin-top: 20px;
}

.align-right {
  margin-top: 20px;
  margin-left: auto;
}

.wide-button {
  width: 100%;
  justify-content: center;
  margin-top: 14px;
}

.compact-button {
  min-height: 36px;
}

.danger-lite {
  color: #b42318;
}

.form-error {
  color: #b42318 !important;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.38);
}

.settings-modal {
  width: min(420px, 100%);
  border-radius: 18px;
  background: #fff;
  padding: 24px;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.22);
}

.settings-modal svg {
  color: #2563eb;
}

.settings-modal h2 {
  margin: 12px 0 8px;
  color: #0f2f63;
}

.settings-modal p {
  margin: 0;
  color: #64748b;
  line-height: 1.7;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 22px;
}

@media (max-width: 1180px) {
  .settings-tabs {
    grid-template-columns: repeat(3, minmax(180px, 1fr));
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .settings-page {
    gap: 14px;
  }

  .settings-hero {
    align-items: flex-start;
    flex-direction: column;
    padding: 22px;
    border-radius: 14px;
  }

  .settings-tabs {
    display: flex;
  }

  .settings-tab {
    min-width: 188px;
  }

  .settings-panel {
    padding: 18px;
    border-radius: 14px;
  }

  .form-grid,
  .preference-grid,
  .option-cards {
    grid-template-columns: 1fr;
  }

  .avatar-row,
  .settings-actions,
  .inline-setting {
    align-items: stretch;
    flex-direction: column;
  }

  .settings-actions div,
  .modal-actions {
    flex-direction: column-reverse;
  }
}
</style>
