import { onBeforeUnmount, onMounted, ref } from "vue";

export interface HomeNavItem {
  key: string;
  label: string;
}

const HOME_CAROUSEL_EVENT = "home-carousel-go";

export const homeNavItems: HomeNavItem[] = [
  { key: "capability", label: "产品能力" },
  { key: "planning", label: "智能课程规划" },
  { key: "governance", label: "知识库治理" },
  { key: "agents", label: "多智能体协作" },
  { key: "scenarios", label: "适用场景" },
  { key: "about", label: "关于平台" },
];

export function useHomeNavbar() {
  const activeKey = ref(homeNavItems[0]?.key ?? "learn");
  const isScrolled = ref(false);
  const isMobileMenuOpen = ref(false);

  let observer: IntersectionObserver | null = null;
  let onScroll: (() => void) | null = null;
  let onResize: (() => void) | null = null;
  let onCarouselChange: ((event: Event) => void) | null = null;

  const updateScrolledState = () => {
    if (typeof window === "undefined") return;
    isScrolled.value = window.scrollY > 8;
  };

  const closeMobileMenu = () => {
    isMobileMenuOpen.value = false;
  };

  const toggleMobileMenu = () => {
    isMobileMenuOpen.value = !isMobileMenuOpen.value;
  };

  const scrollToSection = (key: string) => {
    if (typeof document === "undefined") return;
    const target = document.getElementById(key);
    if (target) {
      activeKey.value = key;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (typeof window !== "undefined") {
      activeKey.value = key;
      window.dispatchEvent(new CustomEvent(HOME_CAROUSEL_EVENT, { detail: key }));
    }
    closeMobileMenu();
  };

  const startTracking = () => {
    if (typeof window === "undefined" || typeof document === "undefined") return;
    updateScrolledState();
    onScroll = updateScrolledState;
    window.addEventListener("scroll", onScroll, { passive: true });
    onResize = () => {
      if (window.innerWidth >= 960) closeMobileMenu();
    };
    window.addEventListener("resize", onResize);
    onCarouselChange = (event: Event) => {
      const key = (event as CustomEvent<string>).detail;
      if (typeof key === "string" && homeNavItems.some((item) => item.key === key)) {
        activeKey.value = key;
      }
    };
    window.addEventListener(HOME_CAROUSEL_EVENT, onCarouselChange);

    const sections = homeNavItems
      .map((item) => document.getElementById(item.key))
      .filter((section): section is HTMLElement => Boolean(section));

    observer = new IntersectionObserver(
      (entries) => {
        const visibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visibleEntry?.target instanceof HTMLElement) activeKey.value = visibleEntry.target.id;
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: [0.08, 0.18, 0.32, 0.5] },
    );
    sections.forEach((section) => observer?.observe(section));
  };

  const stopTracking = () => {
    observer?.disconnect();
    observer = null;
    if (onScroll) window.removeEventListener("scroll", onScroll);
    if (onResize) window.removeEventListener("resize", onResize);
    if (onCarouselChange) window.removeEventListener(HOME_CAROUSEL_EVENT, onCarouselChange);
    onCarouselChange = null;
    onScroll = null;
    onResize = null;
  };

  onMounted(startTracking);
  onBeforeUnmount(stopTracking);

  return { activeKey, closeMobileMenu, isMobileMenuOpen, isScrolled, scrollToSection, toggleMobileMenu };
}
