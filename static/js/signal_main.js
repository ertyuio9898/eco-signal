document.addEventListener('DOMContentLoaded', () => {
    // UI 요소 가져오기
    const scorePointsEl = document.getElementById('score-points');
    const scoreLevelEl = document.getElementById('score-level');
    const lastActivityEl = document.getElementById('last-activity');
    const lights = {
        orange: document.getElementById('light-orange'),
        yellow: document.getElementById('light-yellow'),
        green: document.getElementById('light-green')
    };

    /** 신호등 불 켜는 함수 */
    function updateLights(activeLevel) {
        for (const level in lights) {
            lights[level].classList.toggle('active', level === activeLevel);
        }
    }

    /** 받아온 데이터로 전체 UI를 업데이트하는 함수 */
    function updateUI(data) {
        // 데이터가 없으면 중단
        if (!data) {
            scorePointsEl.textContent = "Error";
            scoreLevelEl.textContent = "(연결 실패)";
            return;
        }

        const { signal_level, current_points, last_activity } = data;
        
        scorePointsEl.textContent = current_points;
        scoreLevelEl.textContent = `(${signal_level.toUpperCase()})`;
        lastActivityEl.textContent = last_activity || "없음";

        updateLights(signal_level);
    }

    /** 서버에 /status API를 요청해서 최신 데이터를 가져오는 함수 */
    async function fetchStatus() {
        try {
            const response = await fetch('/status');
            if (!response.ok) { throw new Error('서버 응답 오류'); }
            const data = await response.json();
            updateUI(data);
        } catch (error) {
            console.error('상태 업데이트 실패:', error);
            updateUI(null); // 에러 발생 시 UI에 에러 상태 표시
        }
    }

    // --- 프로그램 시작! ---
    fetchStatus(); // 페이지 로드 시 즉시 1회 실행
    setInterval(fetchStatus, 2000); // 그 후 2초마다 반복 실행
});