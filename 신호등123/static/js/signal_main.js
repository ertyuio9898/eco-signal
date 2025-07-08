document.addEventListener('DOMContentLoaded', () => {
    // --- UI 요소 ---
    const themeCheckbox = document.getElementById('theme-toggle');
    const rankingChartCanvas = document.getElementById('rankingChart');
    let rankingChart = null; // 차트 객체를 담을 변수

    // --- 테마 로직 ---
    function applyTheme(theme) {
        if (theme === 'dark') {
            document.body.classList.add('dark-mode');
            themeCheckbox.checked = true;
        } else {
            document.body.classList.remove('dark-mode');
            themeCheckbox.checked = false;
        }
        // 테마가 바뀔 때 차트도 다시 그려서 색상을 업데이트
        createRankingChart(); 
    }
    themeCheckbox.addEventListener('change', () => {
        const theme = themeCheckbox.checked ? 'dark' : 'light';
        localStorage.setItem('theme', theme);
        applyTheme(theme);
    });
    
    // --- Chart.js 랭킹 차트 생성 함수 ---
    async function createRankingChart() {
        // 서버에서 랭킹 데이터 가져오기 (실제로는 API 호출)
        // const rankingData = await fetchData('/api/ranking');
        // 지금은 가짜 데이터로 테스트
        const rankingData = [
            { user_name: '이서연', total_points: 1250 }, { user_name: '강현우', total_points: 1180 },
            { user_name: '김민준', total_points: 990 }, { user_name: '박도윤', total_points: 870 },
            { user_name: '최지우', total_points: 760 },
        ];
        
        if (!rankingData || !rankingChartCanvas) return;
        
        // 기존 차트가 있으면 파괴
        if (rankingChart) {
            rankingChart.destroy();
        }

        const isDarkMode = document.body.classList.contains('dark-mode');
        const gridColor = isDarkMode ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
        const labelColor = isDarkMode ? '#a0a0a5' : '#6b6b6b';

        const labels = rankingData.map(item => item.user_name);
        const data = rankingData.map(item => item.total_points);

        rankingChart = new Chart(rankingChartCanvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'CO₂ 절감량 (g)', data: data,
                    backgroundColor: 'rgba(88, 86, 214, 0.7)',
                    borderColor: 'rgba(88, 86, 214, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: gridColor }, ticks: { color: labelColor } },
                    y: { grid: { display: false }, ticks: { color: labelColor } }
                }
            }
        });
    }

    // --- 나머지 로직 (이전과 동일) ---
    const miniSignalLights = { green: document.getElementById('mini-green'), yellow: document.getElementById('mini-yellow'), orange: document.getElementById('mini-orange') };
    function updateMiniSignal(level) {
        Object.values(miniSignalLights).forEach(light => { light.classList.remove('active', 'green', 'yellow', 'orange'); });
        if (miniSignalLights[level]) { miniSignalLights[level].classList.add('active', level); }
    }
    
    // --- 초기화 ---
    applyTheme(localStorage.getItem('theme') || 'light');
    updateMiniSignal('green');
});
    // --- 랭킹 차트 로직 ---
    async function renderRankingChart() {
        try {
            // 1. 백엔드 API로부터 랭킹 데이터를 비동기(async/await)로 가져오기
            const response = await fetch('/api/ranking');
            if (!response.ok) { // 통신 실패 시
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const rankingData = await response.json();

            // 2. Chart.js로 차트 그리기
            const ctx = document.getElementById('rankingChart').getContext('2d');
            
            // 기존에 차트가 있다면 파괴 (데이터 업데이트 시 중복 방지)
            if (window.myRankingChart) {
                window.myRankingChart.destroy();
            }

            // 새 차트 생성
            window.myRankingChart = new Chart(ctx, {
                type: 'bar', // 막대 그래프
                data: {
                    labels: rankingData.labels, // 사용자 이름
                    datasets: [{
                        label: 'CO₂ 절감량 (g)',
                        data: rankingData.data, // 절감량 데이터
                        backgroundColor: [ // 막대 색상 예쁘게
                            'rgba(75, 192, 192, 0.6)',
                            'rgba(54, 162, 235, 0.6)',
                            'rgba(255, 206, 86, 0.6)',
                            'rgba(153, 102, 255, 0.6)',
                            'rgba(255, 159, 64, 0.6)'
                        ],
                        borderColor: [
                            'rgba(75, 192, 192, 1)',
                            'rgba(54, 162, 235, 1)',
                            'rgba(255, 206, 86, 1)',
                            'rgba(153, 102, 255, 1)',
                            'rgba(255, 159, 64, 1)'
                        ],
                        borderWidth: 1
                    }]
                },
                options: {
                    indexAxis: 'y', // 가로 막대 그래프로 변경
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }, // 범례 숨기기
                        title: { display: false } // 제목 숨기기 (HTML에 이미 있음)
                    },
                    scales: {
                        x: {
                            beginAtZero: true,
                            ticks: { color: document.body.classList.contains('dark-mode') ? '#a0a0a5' : '#6b6b6b' }
                        },
                        y: {
                            ticks: { color: document.body.classList.contains('dark-mode') ? '#f5f5f7' : '#1a1a1a' }
                        }
                    }
                }
            });

        } catch (error) {
            console.error("랭킹 차트 로딩 실패:", error);
            const chartContainer = document.querySelector('.chart-container');
            chartContainer.innerHTML = '<h3>랭킹을 불러오는 데 실패했어요 😥</h3>';
        }
    }

    // 페이지가 로드되면 차트 바로 그리기
    renderRankingChart();
    
    // 다크/라이트 모드 변경 시 차트 다시 그리기 (색상 적용)
    themeCheckbox.addEventListener('change', renderRankingChart);