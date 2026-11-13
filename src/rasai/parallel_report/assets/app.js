"use strict";
const allRecords = [...document.querySelectorAll('.record')];
const count = document.querySelector('#visible');
document.querySelector('#filter').addEventListener('input', event => {
  const query = event.target.value.toLocaleLowerCase('pt-BR');
  allRecords.forEach(row => { row.hidden = !row.textContent.toLocaleLowerCase('pt-BR').includes(query); });
  count.textContent = `${allRecords.filter(row => !row.hidden).length} / ${allRecords.length} registros`;
});
document.querySelector('#expand').addEventListener('click', () => document.querySelectorAll('details').forEach(item => { item.open = true; }));
document.querySelector('#collapse').addEventListener('click', () => document.querySelectorAll('details').forEach(item => { item.open = false; }));
document.querySelector('#theme').addEventListener('click', () => document.body.classList.toggle('dark'));
document.querySelector('#sort').addEventListener('click', () => document.querySelectorAll('.records').forEach(group => {
  [...group.children].sort((a, b) => a.textContent.localeCompare(b.textContent, 'pt-BR', {numeric:true})).forEach(item => group.append(item));
}));
let printDetails = [];
window.addEventListener('beforeprint', () => { printDetails = [...document.querySelectorAll('details')].map(item => [item, item.open]); printDetails.forEach(([item]) => { item.open = true; }); });
window.addEventListener('afterprint', () => printDetails.forEach(([item, open]) => { item.open = open; }));
function revealTarget() { const target = document.getElementById(location.hash.slice(1)); if (target) { target.hidden = false; target.scrollIntoView(); } }
window.addEventListener('hashchange', revealTarget);
revealTarget();
