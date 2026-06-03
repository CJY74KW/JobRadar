/* app.js — 탭 전환 + 결과 스크롤 (역할 최소화, 로직은 Python에서 처리) */

function showTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}

/* 검색 결과가 있으면 자동으로 결과 섹션으로 스크롤 */
window.addEventListener('DOMContentLoaded', function () {
  const results = document.getElementById('results');
  if (results) {
    setTimeout(() => results.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
  }
});
