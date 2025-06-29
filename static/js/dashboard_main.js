document.addEventListener('DOMContentLoaded', () => {
    // --- UI 요소 ---
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
    let currentUser = null;

    /** 서버에서 데이터를 가져오는 범용 비동기 함수 */
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

    /** 테마 적용 함수 */
    function applyTheme(theme) {
        if (theme === 'dark') {
            document.body.classList.add('dark-mode');
            themeCheckbox.checked = true;
        } else {
            document.body.classList.remove('dark-mode');
            themeCheckbox.checked = false;
        }
    }
    themeCheckbox.addEventListener('change', () => {
        const theme = themeCheckbox.checked ? 'dark' : 'light';
        localStorage.setItem('theme', theme);
        applyTheme(theme);
    });

    /** 내비게이션 메뉴 클릭 이벤트 처리 */
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

    /** 각 카드 UI 업데이트 함수들 */
    function updateHistory(data) {
        historyContent.innerHTML = '';
        if (!data || data.length === 0) {
            historyContent.innerHTML = '<p class="sub">활동 내역이 없습니다.</p>';
            return;
        }
        data.forEach(item => {
            const date = new Date(item.timestamp).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
            historyContent.innerHTML += `<div class="list-item"><div class="title">${item.activity_type} (+${item.points}점)</div><div class="sub">${date}</div></div>`;
        });
    }

    function updateRanking(data) {
        rankingContent.innerHTML = '';
        if (!data || data.length === 0) {
            rankingContent.innerHTML = '<p class="sub">랭킹 정보가 없습니다.</p>';
            return;
        }
        data.forEach(item => {
            rankingContent.innerHTML += `<div class="list-item rank-item"><span class="rank rank-${item.rank}">${item.rank}위</span><span class="name">${item.user_name}</span><span class="points">${item.total_points} 점</span></div>`;
        });
    }

    function updateBadges(data) {
        badgesContent.innerHTML = '';
        if (!data || data.length === 0) {
            badgesContent.innerHTML = '<div class="info-card" style="grid-column: 1 / -1;"><p class="sub">획득한 뱃지가 없습니다.</p></div>';
            return;
        }
        data.forEach(item => {
            const date = new Date(item.achieved_at).toLocaleDateString('ko-KR');
            badgesContent.innerHTML += `<div class="info-card"><h3 class="title">🏅 ${item.badge_name}</h3><p class="sub">${item.description} (${date} 획득)</p></div>`;
        });
    }

    /** 모든 대시보드 데이터 로드 */
    async function loadDashboardData() {
        if (!currentUser) return;
        userNameDisplay.textContent = currentUser;
        userAvatar.textContent = currentUser.charAt(0);
        // 3개의 API를 동시에 호출해서 로딩 시간을 단축
        const [history, ranking, badges] = await Promise.all([
            fetchData(`/user/${currentUser}/history`),
            fetchData('/ranking'),
            fetchData(`/user/${currentUser}/achievements`)
        ]);
        updateHistory(history);
        updateRanking(ranking);
        updateBadges(badges);
    }

    /** 사용자 선택 관련 로직 */
    async function populateUserList() {
        userSelect.innerHTML = ''; // 기존 목록 초기화
        const users = await fetchData('/users');
        if (users && users.length > 0) {
            users.forEach(user => {
                userSelect.innerHTML += `<option value="${user}">${user}</option>`;
            });
        } else {
            userSelect.innerHTML = '<option>사용자 없음</option>';
        }
    }

    function startDashboard(userName) {
        currentUser = userName;
        localStorage.setItem('dashboardUser', userName);
        userModal.classList.remove('show');
        loadDashboardData();
        pageTitle.textContent = document.querySelector('.nav-link.active span').textContent;
    }

    confirmUserBtn.addEventListener('click', () => {
        if (userSelect.value) {
            startDashboard(userSelect.value);
        }
    });

    userProfileBtn.addEventListener('click', () => {
        populateUserList(); // 사용자 전환 시에도 목록을 새로 불러옴
        userModal.classList.add('show');
    });

    /** 프로그램 초기화 함수 */
    async function initializeApp() {
        applyTheme(localStorage.getItem('theme') || 'light');
        const savedUser = localStorage.getItem('dashboardUser');
        const users = await fetchData('/users'); // 시작할 때 사용자 목록을 미리 가져옴
        
        if (savedUser && users && users.includes(savedUser)) {
            startDashboard(savedUser);
        } else {
            // 저장된 사용자가 없거나, 더 이상 존재하지 않는 사용자일 경우
            userSelect.innerHTML = ''; // 목록 비우고
            if (users && users.length > 0) {
                 users.forEach(user => {
                    userSelect.innerHTML += `<option value="${user}">${user}</option>`;
                });
            } else {
                 userSelect.innerHTML = '<option>사용자 없음</option>';
            }
            userModal.classList.add('show');
        }
    }

    initializeApp();
});