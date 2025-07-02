// --- dashboard_main.js (최종 완성 버전) ---
document.addEventListener('DOMContentLoaded', () => {
    const userModal = document.getElementById('user-selection-modal');
    const userSelect = document.getElementById('user-list-select');
    const confirmUserBtn = document.getElementById('confirm-user-btn');
    const userProfileBtn = document.getElementById('user-profile-btn');
    const pageTitle = document.getElementById('page-title');
    const themeCheckbox = document.getElementById('checkbox');
    const navLinks = document.querySelectorAll('.nav-link');
    const contentPages = document.querySelectorAll('.content-page');
    const historyContent = document.getElementById('history-content');
    const rankingContent = document.getElementById('ranking-content');
    const badgesContent = document.getElementById('badges-content');
    const userAvatar = document.getElementById('user-avatar');
    const userNameDisplay = document.getElementById('user-name-display');
    const sidebar = document.getElementById('sidebar');
    const hamburgerBtn = document.getElementById('hamburger-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    let currentUser = null;
    let autoRefreshInterval = null;

    async function fetchData(endpoint) { try { const response = await fetch(endpoint); if (!response.ok) throw new Error(`서버 응답 오류: ${endpoint}`); return await response.json(); } catch (error) { console.error(`데이터 로딩 실패 ${endpoint}:`, error); return null; } }
    function applyTheme(theme) { if (theme === 'dark') { document.body.classList.add('dark-mode'); themeCheckbox.checked = true; } else { document.body.classList.remove('dark-mode'); themeCheckbox.checked = false; } }
    themeCheckbox.addEventListener('change', () => { const theme = themeCheckbox.checked ? 'dark' : 'light'; localStorage.setItem('theme', theme); applyTheme(theme); });

    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetPageId = link.getAttribute('href').substring(1);
            navLinks.forEach(l => l.classList.remove('active'));
            contentPages.forEach(p => p.classList.remove('active'));
            link.classList.add('active');
            document.getElementById(targetPageId).classList.add('active');
            pageTitle.textContent = link.querySelector('span').textContent;
            if (window.innerWidth <= 768) { sidebar.classList.remove('active'); sidebarOverlay.classList.remove('active'); }
        });
    });

    hamburgerBtn.addEventListener('click', () => { sidebar.classList.add('active'); sidebarOverlay.classList.add('active'); });
    sidebarOverlay.addEventListener('click', () => { sidebar.classList.remove('active'); sidebarOverlay.classList.remove('active'); });

    function showSkeleton(container, type, count = 5) {
        container.innerHTML = '';
        if (type === 'badge') { for (let i = 0; i < count; i++) { container.innerHTML += `<div class="skeleton-wrapper skeleton-badge"></div>`; } } 
        else { for (let i = 0; i < count; i++) { container.innerHTML += `<div class="skeleton-wrapper skeleton-list-item"></div>`; } }
    }
    
    async function updateHistoryCard() {
        showSkeleton(historyContent, 'list', 5);
        const data = await fetchData(`/user/${currentUser}/history`);
        historyContent.innerHTML = '';
        if (!data || data.length === 0) { historyContent.innerHTML = '<p class="sub">활동 내역이 없습니다.</p>'; return; }
        data.forEach(item => { const date = new Date(item.timestamp).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short'}); historyContent.innerHTML += `<div class="list-item"><div class="title">${item.activity_type} (+${item.points}점)</div><div class="sub">${date}</div></div>`; });
    }
    async function updateRankingCard() {
        showSkeleton(rankingContent, 'list', 5);
        const data = await fetchData('/ranking');
        rankingContent.innerHTML = '';
        if (!data || data.length === 0) { rankingContent.innerHTML = '<p class="sub">랭킹 정보가 없습니다.</p>'; return; }
        data.forEach(item => { rankingContent.innerHTML += `<div class="list-item rank-item"><span class="rank rank-${item.rank}">${item.rank}위</span><span class="name">${item.user_name}</span><span class="points">${item.total_points} 점</span></div>`; });
    }
    async function updateBadgesCard() {
        showSkeleton(badgesContent, 'badge', 3);
        const data = await fetchData(`/user/${currentUser}/achievements`);
        badgesContent.innerHTML = '';
        if (!data || data.length === 0) { badgesContent.innerHTML = '<div class="info-card" style="grid-column: 1 / -1;"><p class="sub">획득한 뱃지가 없습니다.</p></div>'; return; }
        data.forEach(item => { const date = new Date(item.achieved_at).toLocaleDateString('ko-KR'); badgesContent.innerHTML += `<div class="info-card"><h3 class="title">🏅 ${item.badge_name}</h3><p class="sub">${item.description} (${date} 획득)</p></div>`; });
    }
    
    function loadDashboardData() { if (!currentUser) return; updateHistoryCard(); updateRankingCard(); updateBadgesCard(); }
    
    document.querySelectorAll('.refresh-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const target = e.currentTarget.dataset.target;
            const btnIcon = e.currentTarget.querySelector('.icon');
            btnIcon.style.transform = `rotate(${(parseInt(btnIcon.dataset.rotate) || 0) + 360}deg)`;
            btnIcon.dataset.rotate = (parseInt(btnIcon.dataset.rotate) || 0) + 360;
            if (target === 'history') updateHistoryCard();
            if (target === 'ranking') updateRankingCard();
            if (target === 'badges') updateBadgesCard();
        });
    });

    async function populateUserList() { userSelect.innerHTML = ''; const users = await fetchData('/users'); if (users && users.length > 0) { users.forEach(user => { userSelect.innerHTML += `<option value="${user}">${user}</option>`; }); } else { userSelect.innerHTML = '<option>사용자 없음</option>'; } }
    
    function startDashboard(userName) {
        currentUser = userName; localStorage.setItem('dashboardUser', userName);
        userNameDisplay.textContent = currentUser; userAvatar.textContent = currentUser.charAt(0);
        userModal.classList.remove('show');
        loadDashboardData();
        if (autoRefreshInterval) clearInterval(autoRefreshInterval);
        autoRefreshInterval = setInterval(loadDashboardData, 60000);
        pageTitle.textContent = document.querySelector('.nav-link.active span').textContent;
    }
    
    confirmUserBtn.addEventListener('click', () => { if (userSelect.value) startDashboard(userSelect.value); });
    userProfileBtn.addEventListener('click', () => { populateUserList(); userModal.classList.add('show'); });
    
    async function initializeApp() {
        applyTheme(localStorage.getItem('theme') || 'light');
        const savedUser = localStorage.getItem('dashboardUser');
        const users = await fetchData('/users');
        if (savedUser && users && users.includes(savedUser)) { startDashboard(savedUser); } 
        else {
            if (users && users.length > 0) { users.forEach(user => { userSelect.innerHTML += `<option value="${user}">${user}</option>`; }); } 
            else { userSelect.innerHTML = '<option>사용자 없음</option>'; }
            userModal.classList.add('show');
        }
    }
    initializeApp();
});