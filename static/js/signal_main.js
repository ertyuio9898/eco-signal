document.addEventListener('DOMContentLoaded', () => {
    const scorePointsEl = document.getElementById('score-points');
    const scoreLevelEl = document.getElementById('score-level');
    const lastActivityEl = document.getElementById('last-activity');
    const lights = { orange: document.getElementById('light-orange'), yellow: document.getElementById('light-yellow'), green: document.getElementById('light-green') };
    function updateLights(activeLevel) { for (const level in lights) { lights[level].classList.toggle('active', level === activeLevel); } }
    function updateUI(data) {
        if (!data) { scorePointsEl.textContent = "Error"; scoreLevelEl.textContent = "(연결 실패)"; return; }
        const { signal_level, current_points, last_activity } = data;
        scorePointsEl.textContent = current_points;
        scoreLevelEl.textContent = `(${signal_level.toUpperCase()})`;
        lastActivityEl.textContent = last_activity || "없음";
        updateLights(signal_level);
    }
    async function fetchStatus() {
        try { const response = await fetch('/status'); if (!response.ok) { throw new Error('서버 응답 오류'); } const data = await response.json(); updateUI(data); }
        catch (error) { console.error('상태 업데이트 실패:', error); updateUI(null); }
    }
    fetchStatus();
    setInterval(fetchStatus, 2000);
});