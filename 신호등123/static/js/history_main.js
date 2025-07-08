document.addEventListener('DOMContentLoaded', () => {
    // UI 요소
    const themeCheckbox = document.getElementById('theme-toggle');
    const miniSignalLights = { green: document.getElementById('mini-green'), yellow: document.getElementById('mini-yellow'), orange: document.getElementById('mini-orange') };
    const sidebar = document.getElementById('sidebar');
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    // --- 테마 로직 ---
    function applyTheme(theme) {
        if (theme === 'dark') { document.body.classList.add('dark-mode'); themeCheckbox.checked = true; } 
        else { document.body.classList.remove('dark-mode'); themeCheckbox.checked = false; }
    }
    themeCheckbox.addEventListener('change', () => {
        const theme = themeCheckbox.checked ? 'dark' : 'light';
        localStorage.setItem('theme', theme);
        applyTheme(theme);
    });
    applyTheme(localStorage.getItem('theme') || 'light');

    // --- 미니 신호등 제어 ---
    function updateMiniSignal(level) {
        Object.values(miniSignalLights).forEach(light => { light.classList.remove('active', 'green', 'yellow', 'orange'); });
        if (miniSignalLights[level]) { miniSignalLights[level].classList.add('active', level); }
    }
    updateMiniSignal('green');

    // --- 햄버거 메뉴 & 오버레이 로직 ---
    function openSidebar() {
        sidebar.classList.add('active');
        sidebarOverlay.classList.add('active');
    }
    function closeSidebar() {
        sidebar.classList.remove('active');
        sidebarOverlay.classList.remove('active');
    }
    hamburgerBtn.addEventListener('click', openSidebar);
    sidebarOverlay.addEventListener('click', closeSidebar);
});