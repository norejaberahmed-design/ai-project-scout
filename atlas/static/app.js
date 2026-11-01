const $ = (s) => document.querySelector(s);
let activeCategory = "all";
let currentItems = [];
let saved = JSON.parse(localStorage.getItem("atlas_saved") || "[]");
let toastTimer;

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2400);
}
function number(n) { return new Intl.NumberFormat("en").format(n || 0); }
function safe(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function updateSavedCount() { $("#savedCount").textContent = saved.length; }
function card(item) {
  const isSaved = saved.some(x => x.id === item.id);
  const tags = [item.language, item.license, ...(item.topics || [])].filter(Boolean).slice(0,4);
  return `<article class="project-card">
    <div class="project-top"><span class="project-owner">${safe(item.owner)}/</span><span class="project-stars">★ ${number(item.stars)}</span></div>
    <h3>${safe(item.name)}</h3><p>${safe(item.description)}</p>
    <div class="tag-row">${tags.map(t=>`<span class="tag">${safe(t)}</span>`).join("")}</div>
    <div class="project-bottom"><a href="${safe(item.url)}" target="_blank" rel="noopener noreferrer">فتح المستودع ↗</a>
    <button class="${isSaved?"saved":""}" data-save="${item.id}" aria-label="حفظ المشروع">${isSaved?"★":"☆"}</button>
    <button data-detail="${item.id}" aria-label="تفاصيل المشروع">التفاصيل</button></div>
  </article>`;
}
function render(items) {
  currentItems = items;
  const box = $("#results");
  if (!items.length) {
    box.innerHTML = '<div class="empty-state">لم نجد نتائج مطابقة. جرّب عبارة بحث أخرى أو اختر مجالاً مختلفاً.</div>';
  } else box.innerHTML = items.map(card).join("");
  $("#resultCount").textContent = number(items.length) + " مشروع معروض";
}
async function discover() {
  const q = $("#query").value.trim();
  $("#status").innerHTML = '<span class="spinner"></span> جارٍ جلب نتائج حقيقية من GitHub...';
  $("#searchButton").disabled = true;
  $("#searchButton").style.opacity = ".65";
  $("#resultsTitle").textContent = q ? "نتائج البحث عن: " + q : "مشاريع تستحق الاكتشاف";
  try {
    const params = new URLSearchParams({q, category:activeCategory, sort:$("#sortSelect").value});
    const res = await fetch("/api/discover?" + params);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "تعذر تحميل النتائج");
    render(data.items || []);
    $("#status").textContent = (data.cached ? "نتائج مخزنة مؤقتاً" : "تم التحديث الآن") + " · المصدر: " + data.source;
    $("#resultsSubtitle").textContent = number(data.total) + " مستودعاً مطابقاً في GitHub";
  } catch (e) {
    $("#status").textContent = e.message + " — حاول مجدداً بعد قليل.";
    render([]);
  } finally {
    $("#searchButton").disabled = false;
    $("#searchButton").style.opacity = "1";
  }
}
function openDetails(item) {
  $("#modalContent").innerHTML = `<span class="section-kicker">معلومات المستودع</span><h2>${safe(item.full_name)}</h2>
  <p>${safe(item.description)}</p>
  <div class="detail-grid">
    <div class="detail-item"><small>النجوم</small><b>★ ${number(item.stars)}</b></div>
    <div class="detail-item"><small>لغة البرمجة</small><b>${safe(item.language)}</b></div>
    <div class="detail-item"><small>الترخيص</small><b>${safe(item.license)}</b></div>
    <div class="detail-item"><small>التفرعات</small><b>${number(item.forks)}</b></div>
    <div class="detail-item"><small>المشكلات المفتوحة</small><b>${number(item.open_issues)}</b></div>
    <div class="detail-item"><small>آخر تحديث</small><b>${safe((item.updated_at||"").slice(0,10))}</b></div>
  </div>
  <p>هذه بيانات عامة واردة من GitHub وليست تقييماً مستقلاً لجودة المشروع أو أمانه. تحقق من الترخيص والنشاط والكود قبل الاعتماد عليه.</p>
  <a class="modal-link" href="${safe(item.url)}" target="_blank" rel="noopener noreferrer">زيارة المستودع على GitHub ↗</a>`;
  $("#modal").classList.add("open");
  $("#modal").setAttribute("aria-hidden","false");
}
$("#searchForm").addEventListener("submit", e => {e.preventDefault();discover();});
document.querySelectorAll(".suggestion").forEach(b=>b.addEventListener("click",()=>{$("#query").value=b.dataset.query;discover();}));
document.querySelectorAll(".category-card").forEach(b=>b.addEventListener("click",()=>{
  document.querySelectorAll(".category-card").forEach(x=>x.classList.remove("selected"));
  b.classList.add("selected");activeCategory=b.dataset.category;discover();
}));
$("#sortSelect").addEventListener("change",discover);
$("#results").addEventListener("click",e=>{
  const saveBtn=e.target.closest("[data-save]");
  if(saveBtn){
    const item=currentItems.find(x=>String(x.id)===saveBtn.dataset.save);
    if(!item)return;
    const exists=saved.some(x=>x.id===item.id);
    saved=exists?saved.filter(x=>x.id!==item.id):[...saved,item];
    localStorage.setItem("atlas_saved",JSON.stringify(saved));updateSavedCount();render(currentItems);
    toast(exists?"تمت الإزالة من المحفوظات":"تم حفظ المشروع على جهازك");return;
  }
  const detail=e.target.closest("[data-detail]");
  if(detail){const item=currentItems.find(x=>String(x.id)===detail.dataset.detail);if(item)openDetails(item);}
});
$("#savedBtn").addEventListener("click",()=>{
  $("#resultsTitle").textContent="مشاريعك المحفوظة";
  $("#resultsSubtitle").textContent="محفوظة محلياً على هذا الجهاز فقط";
  $("#status").textContent="المحفوظات الشخصية";
  render(saved);
  document.querySelectorAll(".category-card").forEach(x=>x.classList.remove("selected"));
});
$("#modalClose").addEventListener("click",()=>$("#modal").classList.remove("open"));
$("#modalBackdrop").addEventListener("click",()=>$("#modal").classList.remove("open"));
document.addEventListener("keydown",e=>{if(e.key==="Escape")$("#modal").classList.remove("open");});
updateSavedCount();
discover();