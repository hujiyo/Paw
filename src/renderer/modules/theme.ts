// 颜色主题管理

// ============ 类型定义 ============

export interface ThemePreset {
    name: string;
    titlebar: string;
    loading: string;
    main: string;
    accent: string;
}

export interface ThemePresets {
    [key: string]: ThemePreset;
}

interface ThemeColorSet {
    bg: string;
    bgSecondary: string;
    textPrimary: string;
    textSecondary: string;
    borderColor: string;
    accentUser: string;
    accentAssistant: string;
    accentActive: string;
    toolColor: string;
    errorColor: string;
    successColor: string;
    codeBg: string;
    scrollbarTrack: string;
    scrollbarThumb: string;
    scrollbarThumbHover: string;
    inputBg: string;
    headerUserText: string;
    headerAssistantText: string;
    modalBg: string;
    cardBg: string;
    buttonText: string;
    buttonSecondaryText: string;
    chainItemHover: string;
    historyItemHover: string;
    progressBar: string;
    toolBg: string;
}

type ThemeType = 'dark' | 'light';

// ============ 主题预设配置 ============

export const THEME_PRESETS: ThemePresets = {
    yaoye: {
        name: '耀夜',
        titlebar: '#000000',
        loading: '#000000',
        main: '#000000',
        accent: '#FF9E80'
    },
    shuangbai: {
        name: '霜白',
        titlebar: '#FFFFFF',
        loading: '#FFFFFF',
        main: '#FFFFFF',
        accent: '#ff6b35'
    },
    taoxi: {
        name: '桃汐',
        titlebar: '#FFFFFF',
        loading: '#FFD6E0',
        main: '#FFF0F5',
        accent: '#ff6b35'
    },
    cuimo: {
        name: '翠墨',
        titlebar: '#000000',
        loading: '#000000',
        main: '#000000',
        accent: '#10b981'
    }
};

// ============ 主题颜色管理器 ============

interface ThemeColorsManager {
    dark: ThemeColorSet;
    light: ThemeColorSet;
    current: ThemeType;
    userBgColor: string | null;
    userAccentColor: string | null;
    init(bgColor: string, accentColor?: string | null): void;
    getBrightness(color: string | null): number;
    get(key: keyof ThemeColorSet): string;
    applyColors(): void;
}

export const ThemeColors: ThemeColorsManager = {
    // 深色主题颜色
    dark: {
        bg: '#000000',
        bgSecondary: '#0a0a0a',
        textPrimary: '#EAEAEA',
        textSecondary: '#666666',
        borderColor: '#444444',
        accentUser: '#80D1FF',
        accentAssistant: '#FF9E80',
        accentActive: '#50FA7B',
        toolColor: '#00FFFF',
        errorColor: '#FF5555',
        successColor: '#50FA7B',
        codeBg: '#1a1a1a',
        scrollbarTrack: '#0a0a0a',
        scrollbarThumb: '#444444',
        scrollbarThumbHover: '#555555',
        inputBg: '#0b0b0b',
        headerUserText: '#000000',
        headerAssistantText: '#000000',
        modalBg: '#0d0d0d',
        cardBg: '#0d0d0d',
        buttonText: '#ffffff',
        buttonSecondaryText: '#000000',
        chainItemHover: 'rgba(255,255,255,0.08)',
        historyItemHover: 'rgba(255,255,255,0.08)',
        progressBar: '#ff4444',
        toolBg: '#0d0d0d'
    },

    // 浅色主题颜色
    light: {
        bg: '#FFFFFF',
        bgSecondary: '#f5f5f5',
        textPrimary: '#333333',
        textSecondary: '#666666',
        borderColor: '#999999',
        accentUser: '#0066cc',
        accentAssistant: '#ff6b35',
        accentActive: '#28a745',
        toolColor: '#0088aa',
        errorColor: '#dc3545',
        successColor: '#28a745',
        codeBg: '#f0f0f0',
        scrollbarTrack: '#f0f0f0',
        scrollbarThumb: '#999999',
        scrollbarThumbHover: '#666666',
        inputBg: '#ffffff',
        headerUserText: '#000000',
        headerAssistantText: '#000000',
        modalBg: '#ffffff',
        cardBg: '#f9f9f9',
        buttonText: '#ffffff',
        buttonSecondaryText: '#000000',
        chainItemHover: 'rgba(0,0,0,0.08)',
        historyItemHover: 'rgba(0,0,0,0.08)',
        progressBar: '#dc3545',
        toolBg: '#f0f0f0'
    },

    // 当前主题
    current: 'dark',

    // 用户配置的主背景色
    userBgColor: null,
    // 用户配置的主题色
    userAccentColor: null,

    // 初始化主题
    init(bgColor: string, accentColor?: string | null): void {
        this.userBgColor = bgColor;
        this.userAccentColor = accentColor || null;
        const brightness = this.getBrightness(bgColor);
        this.current = brightness > 128 ? 'light' : 'dark';
        this.applyColors();
    },

    // 计算颜色亮度
    getBrightness(color: string | null): number {
        if (!color) return 0;
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return (r * 299 + g * 587 + b * 114) / 1000;
    },

    // 获取当前主题的颜色
    get(key: keyof ThemeColorSet): string {
        return this[this.current][key] || this.dark[key];
    },

    // 应用颜色到CSS变量
    applyColors(): void {
        const colors = this[this.current];
        const root = document.documentElement;

        // 使用用户配置的背景色，而不是预设的颜色
        root.style.setProperty('--bg-color', this.userBgColor);
        root.style.setProperty('--bg-secondary', colors.bgSecondary);
        root.style.setProperty('--text-primary', colors.textPrimary);
        root.style.setProperty('--text-secondary', colors.textSecondary);
        root.style.setProperty('--border-color', colors.borderColor);
        
        // 使用用户配置的主题色，或者预设颜色
        const accent = this.userAccentColor || colors.accentAssistant;
        root.style.setProperty('--accent-user', colors.accentUser);
        root.style.setProperty('--accent-assistant', accent);
        root.style.setProperty('--accent-active', accent);
        
        root.style.setProperty('--tool-color', colors.toolColor);
        root.style.setProperty('--error-color', colors.errorColor);
        root.style.setProperty('--success-color', accent); // 成功色也跟随主题色
        root.style.setProperty('--code-bg', colors.codeBg);
        root.style.setProperty('--modal-bg', colors.modalBg);
        root.style.setProperty('--card-bg', colors.cardBg);
        root.style.setProperty('--input-bg', colors.inputBg);
        root.style.setProperty('--hover-bg', colors.chainItemHover);
        root.style.setProperty('--history-hover-bg', colors.historyItemHover);
        root.style.setProperty('--button-hover-bg', colors.chainItemHover);
        root.style.setProperty('--scrollbar-track', colors.scrollbarTrack);
        root.style.setProperty('--scrollbar-thumb', colors.scrollbarThumb);
        root.style.setProperty('--scrollbar-thumb-hover', colors.scrollbarThumbHover);
    }
};
