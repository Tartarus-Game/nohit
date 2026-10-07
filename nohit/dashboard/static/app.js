/**
 * Sans Attack Deadlock Verification System - Frontend Application
 */

(function () {
  'use strict';

  // DOM Elements
  const waveSelect = document.getElementById('wave-select');
  const horizonSlider = document.getElementById('horizon-slider');
  const horizonVal = document.getElementById('horizon-val');
  const toggleCustomCsv = document.getElementById('toggle-custom-csv');
  const customCsvInput = document.getElementById('custom-csv-input');
  const btnSolve = document.getElementById('btn-solve');
  const sysStatus = document.getElementById('sys-status');

  const verdictBanner = document.getElementById('verdict-banner');
  const verdictTitle = document.getElementById('verdict-title');
  const verdictSub = document.getElementById('verdict-sub');

  const statBakeMs = document.getElementById('stat-bake-ms');
  const statDpMs = document.getElementById('stat-dp-ms');
  const statPeakStates = document.getElementById('stat-peak-states');
  const statPeakRam = document.getElementById('stat-peak-ram');
  const statVerifyReplay = document.getElementById('stat-verify-replay');

  const canvas = document.getElementById('game-canvas');
  const ctx = canvas.getContext('2d');
  const chartCanvas = document.getElementById('chart-canvas');
  const chartCtx = chartCanvas.getContext('2d');

  const slamFlash = document.getElementById('slam-flash');
  const deadlockOverlay = document.getElementById('deadlock-overlay');
  const deadlockFrameText = document.getElementById('deadlock-frame-text');

  const btnPlay = document.getElementById('btn-play');
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnReset = document.getElementById('btn-reset');
  const frameScrubber = document.getElementById('frame-scrubber');
  const frameCounter = document.getElementById('frame-counter');
  const timeCounter = document.getElementById('time-counter');
  const speedSelect = document.getElementById('speed-select');

  const toggleCspace = document.getElementById('toggle-cspace');
  const toggleTrail = document.getElementById('toggle-trail');

  const telemetryState = document.getElementById('telemetry-state');
  const keyLeft = document.getElementById('key-left');
  const keyRight = document.getElementById('key-right');
  const keyJump = document.getElementById('key-jump');

  const btnBenchmarkModal = document.getElementById('btn-benchmark-modal');
  const benchmarkModal = document.getElementById('benchmark-modal');
  const btnCloseModal = document.getElementById('btn-close-modal');
  const modalLoading = document.getElementById('modal-loading');
  const benchmarkTbody = document.getElementById('benchmark-tbody');

  // Application State
  let currentResult = null;
  let currentFrame = 0;
  let isPlaying = false;
  let lastTimestamp = 0;
  let accumulatedTime = 0;
  let animationReqId = null;

  const SCALE_X = 600 / 200; // 3.0
  const SCALE_Y = 480 / 160; // 3.0

  // 1. Initialize
  async function init() {
    setupEventListeners();
    await loadWaveList();
    renderIdleCanvas();
  }

  function setupEventListeners() {
    horizonSlider.addEventListener('input', (e) => {
      const val = e.target.value;
      const sec = (val / 30.0).toFixed(1);
      horizonVal.textContent = `${val} 帧 (${sec}s)`;
    });

    toggleCustomCsv.addEventListener('click', () => {
      customCsvInput.classList.toggle('hidden');
      if (!customCsvInput.classList.contains('hidden')) {
        customCsvInput.focus();
      }
    });

    btnSolve.addEventListener('click', handleSolve);

    btnPlay.addEventListener('click', togglePlayPause);
    btnPrev.addEventListener('click', () => stepFrame(-1));
    btnNext.addEventListener('click', () => stepFrame(1));
    btnReset.addEventListener('click', () => setFrame(0));

    frameScrubber.addEventListener('input', (e) => {
      pausePlayback();
      setFrame(parseInt(e.target.value, 10));
    });

    speedSelect.addEventListener('change', () => {
      // Speed multiplier updated
    });

    toggleCspace.addEventListener('change', () => renderFrame(currentFrame));
    toggleTrail.addEventListener('change', () => renderFrame(currentFrame));

    btnBenchmarkModal.addEventListener('click', openBenchmarkModal);
    btnCloseModal.addEventListener('click', closeBenchmarkModal);
    benchmarkModal.querySelector('.modal-backdrop').addEventListener('click', closeBenchmarkModal);

    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlayPause();
      } else if (e.code === 'ArrowLeft') {
        e.preventDefault();
        stepFrame(-1);
      } else if (e.code === 'ArrowRight') {
        e.preventDefault();
        stepFrame(1);
      }
    });
  }

  // 2. Load Attack Waves
  async function loadWaveList() {
    try {
      const resp = await fetch('/api/waves');
      const data = await resp.json();
      waveSelect.innerHTML = '';
      
      const optGroupReal = document.createElement('optgroup');
      optGroupReal.label = '── c2-sans-fight 真实关卡脚本 ──';
      const optGroupSynth = document.createElement('optgroup');
      optGroupSynth.label = '── 形式化理论基准测试用例 ──';

      for (const w of data.waves) {
        const opt = document.createElement('option');
        opt.value = w.id;
        opt.textContent = w.name;
        if (w.category === 'C2 Attack Script') {
          optGroupReal.appendChild(opt);
        } else {
          optGroupSynth.appendChild(opt);
        }
      }

      waveSelect.appendChild(optGroupReal);
      waveSelect.appendChild(optGroupSynth);
      waveSelect.value = 'sans_bonegap1.csv';
    } catch (err) {
      console.error('Failed to load waves:', err);
      waveSelect.innerHTML = '<option value="">加载失败，请检查服务器连接</option>';
    }
  }

  // 3. Handle Solve
  async function handleSolve() {
    const wave = waveSelect.value;
    const T = parseInt(horizonSlider.value, 10);
    const customCsv = customCsvInput.classList.contains('hidden') ? null : customCsvInput.value.trim();

    pausePlayback();
    setLoadingState(true);

    try {
      const payload = { wave, T, custom_csv: customCsv || null };
      const resp = await fetch('/api/solve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const errData = await resp.json();
        throw new Error(errData.error || `HTTP ${resp.status}`);
      }

      const res = await resp.json();
      currentResult = res;
      updateUIWithResult(res);
      setFrame(0);
      renderChart(res.stats.alive_history, res.slam_frames);

      // Auto start playback if solved
      if (res.candidate_found) {
        startPlayback();
      }
    } catch (err) {
      alert(`判定求解失败: ${err.message}`);
      console.error(err);
    } finally {
      setLoadingState(false);
    }
  }

  function setLoadingState(loading) {
    btnSolve.disabled = loading;
    if (loading) {
      btnSolve.innerHTML = '<span class="btn-icon">⏳</span> 正在计算混合状态格可达集...';
      sysStatus.textContent = '计算中...';
      sysStatus.style.color = '#ffab00';
    } else {
      btnSolve.innerHTML = '<span class="btn-icon">▶</span> 生成模型候选';
      sysStatus.textContent = '系统就绪';
      sysStatus.style.color = '#00e676';
    }
  }

  function updateUIWithResult(res) {
    // Verdict Banner
    verdictBanner.className = 'verdict-banner ' + (!res.candidate_found ? 'deadlock' : 'feasible');
    if (!res.candidate_found) {
      verdictBanner.querySelector('.verdict-icon').textContent = '…';
      verdictTitle.textContent = '当前搜索未找到候选';
      verdictSub.textContent = '模型与截断搜索不能证明原版无解；请使用全部回合页面的原版求解入口。';
    } else {
      verdictBanner.querySelector('.verdict-icon').textContent = '✔';
      verdictTitle.textContent = '已生成模型候选 · 原版未验收';
      verdictSub.textContent = `候选包含 ${res.action_sequence.length} 帧输入，仍需原版回放和实时三回合无伤。`;
    }

    // Metrics
    statBakeMs.textContent = `${res.stats.bake_ms.toFixed(1)} ms`;
    statDpMs.textContent = `${res.stats.dp_ms.toFixed(1)} ms`;
    statPeakStates.textContent = res.stats.peak_states.toLocaleString();
    statPeakRam.textContent = `${res.stats.peak_memory_mb.toFixed(2)} MB`;
    
    statVerifyReplay.textContent = '实时游戏验收待运行';
    statVerifyReplay.className = 'metric-value';
    statVerifyReplay.style.color = '#ffab00';

    // Scrubber Range
    const maxF = res.T - 1;
    frameScrubber.max = maxF;
    frameScrubber.value = 0;
    updateCounterText(0, maxF);
  }

  function updateCounterText(frame, maxFrame) {
    frameCounter.textContent = `帧: ${frame} / ${maxFrame}`;
    const curSec = (frame / 30.0).toFixed(2);
    const totSec = (maxFrame / 30.0).toFixed(2);
    timeCounter.textContent = `${curSec}s / ${totSec}s`;
  }

  // 4. Playback Engine
  function togglePlayPause() {
    if (!currentResult) return;
    if (isPlaying) {
      pausePlayback();
    } else {
      startPlayback();
    }
  }

  function startPlayback() {
    if (!currentResult) return;
    isPlaying = true;
    btnPlay.textContent = '⏸';
    lastTimestamp = performance.now();
    accumulatedTime = 0;
    animationReqId = requestAnimationFrame(playbackLoop);
  }

  function pausePlayback() {
    isPlaying = false;
    btnPlay.textContent = '▶';
    if (animationReqId) {
      cancelAnimationFrame(animationReqId);
      animationReqId = null;
    }
  }

  function playbackLoop(timestamp) {
    if (!isPlaying || !currentResult) return;
    const delta = (timestamp - lastTimestamp) / 1000.0;
    lastTimestamp = timestamp;

    const speed = parseFloat(speedSelect.value) || 1.0;
    accumulatedTime += delta * speed;

    const frameDuration = 1.0 / 30.0;
    while (accumulatedTime >= frameDuration) {
      accumulatedTime -= frameDuration;
      let nextF = currentFrame + 1;
      const maxF = currentResult.T - 1;

      // Handle deadlock frame cut
      if (currentResult.is_deadlock && nextF > currentResult.deadlock_frame) {
        pausePlayback();
        renderFrame(currentResult.deadlock_frame);
        return;
      }

      if (nextF > maxF) {
        nextF = 0; // Loop around
      }
      setFrame(nextF);
    }

    animationReqId = requestAnimationFrame(playbackLoop);
  }

  function stepFrame(delta) {
    if (!currentResult) return;
    pausePlayback();
    const maxF = currentResult.T - 1;
    let nextF = currentFrame + delta;
    if (currentResult.is_deadlock && nextF > currentResult.deadlock_frame) {
      nextF = currentResult.deadlock_frame;
    }
    nextF = Math.max(0, Math.min(maxF, nextF));
    setFrame(nextF);
  }

  function setFrame(f) {
    currentFrame = f;
    frameScrubber.value = f;
    if (currentResult) {
      updateCounterText(f, currentResult.T - 1);
    }
    renderFrame(f);
    updateChartCursor(f);
  }

  // 5. Canvas Rendering
  function renderIdleCanvas() {
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);

    // Initial heart at center bottom
    drawSoul(100 - 4, 0, '#ff2222', false);
  }

  function renderFrame(t) {
    if (!currentResult) {
      renderIdleCanvas();
      return;
    }

    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 1. Draw C-space Hazard Mask
    if (toggleCspace.checked && currentResult.hazard_runs && currentResult.hazard_runs[t]) {
      const runs = currentResult.hazard_runs[t];
      ctx.fillStyle = 'rgba(255, 40, 60, 0.45)';
      for (let i = 0; i < runs.length; i++) {
        const [y, x, w] = runs[i];
        const screenX = x * SCALE_X;
        const screenY = (160 - y - 1) * SCALE_Y;
        ctx.fillRect(screenX, screenY, w * SCALE_X, SCALE_Y);
      }
    }

    // 2. Draw Moving Platforms
    if (currentResult.platforms && currentResult.platforms[t]) {
      const plats = currentResult.platforms[t];
      for (const p of plats) {
        const px = p.x_left * SCALE_X;
        const pw = (p.x_right - p.x_left) * SCALE_X;
        const py = (160 - p.y_surf) * SCALE_Y;

        ctx.fillStyle = '#00e676';
        ctx.fillRect(px, py - 4, pw, 8);
        ctx.fillStyle = '#00ff88';
        ctx.fillRect(px, py - 4, pw, 2);
      }
    }

    // 3. Draw Trajectory Trail
    if (toggleTrail.checked && currentResult.trajectory) {
      const traj = currentResult.trajectory;
      const count = Math.min(t + 1, traj.length);
      if (count > 1) {
        ctx.beginPath();
        for (let i = 0; i < count; i++) {
          const s = traj[i];
          const cx = (s[0] + 4) * SCALE_X;
          const cy = (160 - s[1] - 4) * SCALE_Y;
          if (i === 0) ctx.moveTo(cx, cy);
          else ctx.lineTo(cx, cy);
        }
        ctx.strokeStyle = 'rgba(0, 200, 255, 0.35)';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    // 4. Draw Arena Border
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 4;
    ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);

    // 5. SansSlam Flash Effect
    const isSlam = currentResult.slam_frames && currentResult.slam_frames.includes(t);
    if (isSlam) {
      slamFlash.classList.remove('hidden');
      setTimeout(() => slamFlash.classList.add('hidden'), 300);
    }

    // 6. Draw Player Soul & Update Telemetry
    if (currentResult.trajectory && t < currentResult.trajectory.length) {
      const s = currentResult.trajectory[t];
      const [x, y, vy, kappa, tau] = s;
      telemetryState.textContent = `(x=${x}, y=${y}, vy=${vy}, κ=${kappa}, τ=${tau})`;

      // Blue soul color when jumping/falling/slam, red on ground
      const soulColor = (kappa === 1 && vy === 0) ? '#ff2222' : '#2288ff';
      drawSoul(x, y, soulColor, isSlam);
    } else if (currentResult.is_deadlock && t >= currentResult.deadlock_frame) {
      telemetryState.textContent = `(ALL STATES DESTROYED AT FRAME ${currentResult.deadlock_frame})`;
    } else if (currentResult.is_deadlock && currentResult.initial_state) {
      const [ix, iy] = currentResult.initial_state;
      telemetryState.textContent = `(Deadlock wave: t=${t} < t*=${currentResult.deadlock_frame}, x0=${ix}, y0=${iy})`;
      drawSoul(ix, iy, '#ff2222', false);
    }

    // 7. Update Key Indicators
    updateKeys(t);

    // 8. Deadlock Overlay
    if (currentResult.is_deadlock && t >= currentResult.deadlock_frame) {
      deadlockOverlay.classList.remove('hidden');
      deadlockFrameText.textContent = '当前搜索未找到候选；不构成原版死局证明';
    } else {
      deadlockOverlay.classList.add('hidden');
    }
  }

  function drawSoul(x, y, color, pulse) {
    const soulScreenX = x * SCALE_X;
    const soulScreenY = (160 - y - 8) * SCALE_Y;
    const w = 8 * SCALE_X; // 24
    const h = 8 * SCALE_Y; // 24

    ctx.save();
    ctx.translate(soulScreenX, soulScreenY);

    if (pulse) {
      ctx.shadowColor = '#00a2ff';
      ctx.shadowBlur = 12;
    }

    // Retro Heart Shape
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(w * 0.5, h * 0.9);
    ctx.bezierCurveTo(w * 0.1, h * 0.6, 0, h * 0.35, 0, h * 0.25);
    ctx.bezierCurveTo(0, h * 0.05, w * 0.2, 0, w * 0.5, h * 0.2);
    ctx.bezierCurveTo(w * 0.8, 0, w, h * 0.05, w, h * 0.25);
    ctx.bezierCurveTo(w, h * 0.35, w * 0.9, h * 0.6, w * 0.5, h * 0.9);
    ctx.closePath();
    ctx.fill();

    ctx.restore();
  }

  function updateKeys(t) {
    keyLeft.classList.remove('active');
    keyRight.classList.remove('active');
    keyJump.classList.remove('active');

    if (!currentResult || !currentResult.action_sequence) return;
    if (t < currentResult.action_sequence.length) {
      const [ux, uy] = currentResult.action_sequence[t];
      if (ux === -1) keyLeft.classList.add('active');
      if (ux === 1) keyRight.classList.add('active');
      if (uy === 1) keyJump.classList.add('active');
    }
  }

  // 6. Alive States Chart
  function renderChart(history, slamFrames) {
    if (!history || history.length === 0) return;
    const w = chartCanvas.width;
    const h = chartCanvas.height;
    chartCtx.clearRect(0, 0, w, h);

    const maxVal = Math.max(...history, 100);
    const N = history.length;
    const slamSet = new Set(slamFrames || []);

    // Draw background grid lines
    chartCtx.strokeStyle = '#1e1e28';
    chartCtx.lineWidth = 1;
    chartCtx.beginPath();
    for (let g = 1; g <= 3; g++) {
      const gy = h - (h * g) / 4;
      chartCtx.moveTo(0, gy);
      chartCtx.lineTo(w, gy);
    }
    chartCtx.stroke();

    // Draw area fill
    chartCtx.beginPath();
    chartCtx.moveTo(0, h);
    for (let i = 0; i < N; i++) {
      const cx = (i / (N - 1)) * w;
      const cy = h - (history[i] / maxVal) * (h - 10);
      chartCtx.lineTo(cx, cy);
    }
    chartCtx.lineTo(w, h);
    chartCtx.closePath();

    const gradient = chartCtx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, 'rgba(33, 150, 243, 0.45)');
    gradient.addColorStop(1, 'rgba(33, 150, 243, 0.05)');
    chartCtx.fillStyle = gradient;
    chartCtx.fill();

    // Draw line
    chartCtx.beginPath();
    for (let i = 0; i < N; i++) {
      const cx = (i / (N - 1)) * w;
      const cy = h - (history[i] / maxVal) * (h - 10);
      if (i === 0) chartCtx.moveTo(cx, cy);
      else chartCtx.lineTo(cx, cy);
    }
    chartCtx.strokeStyle = '#29b6f6';
    chartCtx.lineWidth = 2;
    chartCtx.stroke();

    // Draw Slam Markers
    for (let i = 0; i < N; i++) {
      if (slamSet.has(i)) {
        const cx = (i / (N - 1)) * w;
        chartCtx.strokeStyle = '#ffab00';
        chartCtx.lineWidth = 2;
        chartCtx.beginPath();
        chartCtx.moveTo(cx, 0);
        chartCtx.lineTo(cx, h);
        chartCtx.stroke();
      }
    }
  }

  function updateChartCursor(f) {
    if (!currentResult || !currentResult.stats.alive_history) return;
    const history = currentResult.stats.alive_history;
    renderChart(history, currentResult.slam_frames);

    const w = chartCanvas.width;
    const h = chartCanvas.height;
    const N = history.length;
    const cx = (f / Math.max(1, N - 1)) * w;

    chartCtx.strokeStyle = '#ff1744';
    chartCtx.lineWidth = 2;
    chartCtx.setLineDash([3, 3]);
    chartCtx.beginPath();
    chartCtx.moveTo(cx, 0);
    chartCtx.lineTo(cx, h);
    chartCtx.stroke();
    chartCtx.setLineDash([]);
  }

  // 7. Benchmark Modal
  async function openBenchmarkModal() {
    benchmarkModal.classList.remove('hidden');
    modalLoading.classList.remove('hidden');
    benchmarkTbody.innerHTML = '';

    try {
      const resp = await fetch('/api/benchmark');
      const data = await resp.json();
      modalLoading.classList.add('hidden');

      for (const row of data.benchmark) {
        const tr = document.createElement('tr');
        const verBadge = row.verified
          ? '<span class="badge-pass">PASS</span>'
          : '<span class="badge-fail">FAIL</span>';

        tr.innerHTML = `
          <td><strong>${row.name}</strong></td>
          <td>${row.category}</td>
          <td>${row.outcome}</td>
          <td>${row.bake_ms.toFixed(1)}</td>
          <td>${row.dp_ms.toFixed(1)}</td>
          <td>${row.total_ms.toFixed(1)}</td>
          <td>${row.peak_states.toLocaleString()}</td>
          <td>${row.peak_memory_mb.toFixed(1)}</td>
          <td>${verBadge}</td>
        `;
        benchmarkTbody.appendChild(tr);
      }
    } catch (err) {
      modalLoading.textContent = `评测运行出错: ${err.message}`;
    }
  }

  function closeBenchmarkModal() {
    benchmarkModal.classList.add('hidden');
  }

  // Launch on DOM ready
  window.addEventListener('DOMContentLoaded', init);
})();
