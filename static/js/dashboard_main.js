document.addEventListener('DOMContentLoaded', () => {
    // --- 1. UI 요소 가져오기 ---
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
    const refreshButtons = document.querySelectorAll('.refresh-btn');
    let currentUser = null;

    // --- 2. 핵심 함수들 ---
    async function fetchData(endpoint) {
        try {
            const response = await fetch(endpoint);
            if (!response.ok) throw new Error(`서버 응답 오류: ${endpoint}`);
            return await response.json();
        } catch (error) {
            console.error(`데이터 로딩 실패 ${endpoint}:`, error);
            return null;
        }
    }
    function createSpinner() { return '<div class="spinner-container"><div class="spinner"></div></div>'; }
    function createSkeleton(count = 5) {
        let skeletonHTML = '';
        for (let i = 0; i < count; i++) { skeletonHTML += `<div class="loading-placeholder"><div class="skeleton title"></div><div class="skeleton sub"></div></div>`; }
        return skeletonHTML;
    }
    function updateHistoryCard(data) {
        historyContent.innerHTML = '';
        if (!data) { historyContent.innerHTML = '<p class="sub">오류: 데이터를 불러올 수 없습니다.</p>'; return; }
        if (data.length === 0) { historyContent.innerHTML = '<p class="sub">활동 내역이 없습니다.</p>'; return; }
        data.forEach(item => {
            const date = new Date(item.timestamp).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
            historyContent.innerHTML += `<div class="list-item"><div class="title">${item.activity_type} (+${item.points}점)</div><div class="sub">${date}</div></div>`;
        });
    }
    function updateRankingCard(data) {
        rankingContent.innerHTML = '';
        if (!data) { rankingContent.innerHTML = '<p class="sub">오류: 데이터를 불러올 수 없습니다.</p>'; return; }
        if (data.length === 0) { rankingContent.innerHTML = '<p class="sub">랭킹 정보가 없습니다.</p>'; return; }
        data.forEach(item => {
            rankingContent.innerHTML += `<div class="list-item rank-item"><span class="rank rank-${item.rank}">${item.rank}위</span><span class="name">${item.user_name}</span><span class="points">${item.total_points} 점</span></div>`;
        });
    }
    function updateBadgesCard(data) {
        badgesContent.innerHTML = '';
        if (!data) { badgesContent.innerHTML = '<p class="sub">오류: 데이터를 불러올 수 없습니다.</p>'; return; }
        if (data.length === 0) { badgesContent.innerHTML = '<div class="info-card" style="grid-column: 1 / -1;"><p class="sub">획득한 뱃지가 없습니다.</p></div>'; return; }
        data.forEach(item => {
            const date = new Date(item.achieved_at).toLocaleDateString('ko-KR');
            badgesContent.innerHTML += `<div class="info-card"><h3 class="title">🏅 ${item.badge_name}</h3><p class="sub">${item.description} (${date} 획득)</p></div>`;
        });
    }
    async function loadDashboardData() {
        if (!currentUser) return;
        historyContent.innerHTML = createSkeleton(5);
        rankingContent.innerHTML = createSkeleton(5);
        badgesContent.innerHTML = createSpinner();
        const [history, ranking, badges] = await Promise.all([ fetchData(`/user/${currentUser}/history`), fetchData('/ranking'), fetchData(`/user/${currentUser}/achievements`) ]);
        updateHistoryCard(history);
        updateRankingCard(ranking);
        updateBadgesCard(badges);
    }

    // --- 3. 이벤트 리스너 설정 ---
    function applyTheme(theme) {
        if (theme === 'dark') { document.body.classList.add('dark-mode'); themeCheckbox.checked = true; } 
        else { document.body.classList.remove('dark-mode'); themeCheckbox.checked = false; }
    }
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
        });
    });

    refreshButtons.forEach(button => {
        button.addEventListener('click', async (e) => {
            const target = e.currentTarget.dataset.target;
            const btn = e.currentTarget;
            btn.classList.add('loading');
            let contentEl, fetchDataPromise, updateFunc, useSpinner = false;
            
            if (target === 'history') { [contentEl, fetchDataPromise, updateFunc] = [historyContent, fetchData(`/user/${currentUser}/history`), updateHistoryCard]; } 
            else if (target === 'ranking') { [contentEl, fetchDataPromise, updateFunc] = [rankingContent, fetchData('/ranking'), updateRankingCard]; }
            else if (target === 'badges') { [contentEl, fetchDataPromise, updateFunc, useSpinner] = [badgesContent, fetchData(`/user/${currentUser}/achievements`), updateBadgesCard, true]; }
            
            if (contentEl) {
                contentEl.innerHTML = useSpinner ? createSpinner() : createSkeleton();
                const data = await fetchDataPromise;
                updateFunc(data);
            }
            // 애니메이션이 너무 빨리 끝나면 어색해서 약간의 딜레이를 줌
            setTimeout(() => btn.classList.remove('loading'), 500);
        });
    });

    async function populateUserList() {
        userSelect.innerHTML = '<option>로딩 중...</option>';
        const users = await fetchData('/users');
        userSelect.innerHTML = '';
        if (users && users.length > 0) { users.forEach(user => { userSelect.innerHTML += `<option value="${user}">${user}</option>`; }); } 
        else { userSelect.innerHTML = '<option>사용자 없음</option>'; }
    }

    function startDashboard(userName) {
        currentUser = userName;
        localStorage.setItem('dashboardUser', userName);
        userNameDisplay.textContent = currentUser;
        userAvatar.textContent = currentUser.charAt(0);
        userModal.classList.remove('show');
        loadDashboardData();
        pageTitle.textContent = document.querySelector('.nav-link.active span').textContent;
    }
    
    confirmUserBtn.addEventListener('click', () => { if (userSelect.value) startDashboard(userSelect.value); });
    userProfileBtn.addEventListener('click', () => { populateUserList(); userModal.classList.add('show'); });

    // --- 4. 프로그램 시작 ---
    async function initializeApp() {
        applyTheme(localStorage.getItem('theme') || 'light');
        const savedUser = localStorage.getItem('dashboardUser');
        const users = await fetchData('/users');
        if (savedUser && users && users.includes(savedUser)) {
            startDashboard(savedUser);
        } else {
            if (users && users.length > 0) { users.forEach(user => { userSelect.innerHTML += `<option value="${user}">${user}</option>`; }); } 
            else { userSelect.innerHTML = '<option>사용자 없음</option>'; }
            userModal.classList.add('show');
        }
    }

    initializeApp();
});