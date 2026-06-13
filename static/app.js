/* app.js — 탭 전환 + Chart.js 대시보드 */

/* ============================================================
   탭 전환
   ============================================================ */
function showTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');

  // 대시보드 탭 활성화 시 차트 초기화 (최초 1회)
  if (name === 'dashboard' && !window._chartsInit) {
    initCharts();
    window._chartsInit = true;
  }
}

/* 검색 결과 자동 스크롤 */
window.addEventListener('DOMContentLoaded', function () {
  applyStatBarWidths();

  const results = document.getElementById('results');
  if (results) {
    setTimeout(() => results.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
  }
});

function applyStatBarWidths() {
  document.querySelectorAll('.stat-fill[data-width]').forEach(el => {
    const width = Math.max(0, Math.min(100, Number(el.dataset.width) || 0));
    el.style.width = `${width}%`;
  });
}


/* ============================================================
   Chart.js 대시보드 초기화 (기능 5)
   ============================================================ */
function initCharts() {
  const el = document.getElementById('chart-json');
  if (!el) return;

  let data;
  try { data = JSON.parse(el.textContent); }
  catch (e) { return; }

  const COLORS = [
    '#2563eb','#7c3aed','#16a34a','#d97706','#dc2626',
    '#0891b2','#db2777','#65a30d','#ea580c','#4f46e5',
    '#0284c7','#9333ea','#15803d','#b45309','#b91c1c',
  ];

  /* 1. 기술 키워드 가로 막대 차트 */
  const techEl = document.getElementById('chart-tech');
  if (techEl && data.tech?.labels?.length) {
    new Chart(techEl, {
      type: 'bar',
      data: {
        labels: data.tech.labels,
        datasets: [{
          label: '공고 수',
          data: data.tech.values,
          backgroundColor: COLORS.slice(0, data.tech.labels.length),
          borderRadius: 5,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, ticks: { stepSize: 1 } },
          y: { ticks: { font: { size: 12 } } },
        },
      },
    });
  }

  /* 2. 적합도 점수 분포 막대 차트 */
  const scoreEl = document.getElementById('chart-score');
  if (scoreEl && data.score?.labels?.length) {
    new Chart(scoreEl, {
      type: 'bar',
      data: {
        labels: data.score.labels,
        datasets: [{
          label: '공고 수',
          data: data.score.values,
          backgroundColor: ['#e2e8f0','#bfdbfe','#93c5fd','#60a5fa','#2563eb'],
          borderRadius: 5,
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
      },
    });
  }

  /* 3. 출처별 공고 수 (2개 이상일 때만) */
  const srcEl = document.getElementById('chart-source');
  if (srcEl && data.source?.labels?.length > 1) {
    new Chart(srcEl, {
      type: 'pie',
      data: {
        labels: data.source.labels,
        datasets: [{
          data: data.source.values,
          backgroundColor: COLORS,
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { size: 12 } } },
        },
      },
    });
  }
}
