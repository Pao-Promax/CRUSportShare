// CRU Sports Borrow - main.js
document.addEventListener('DOMContentLoaded', () => {
  // auto dismiss alerts after 4s
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => { el.style.opacity='0'; el.style.transform='translateY(-6px)'; setTimeout(()=>el.remove(),300); }, 4200);
  });

  // confirm dialogs
  document.querySelectorAll('[data-confirm]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const msg = btn.getAttribute('data-confirm') || 'ยืนยันการทำรายการ?';
      if(!confirm(msg)) e.preventDefault();
    });
  });

  // search debounce (optional auto submit)
  const searchInput = document.querySelector('input[name="search"]');
  if(searchInput){
    let t;
    searchInput.addEventListener('input', () => {
      // not auto submit to keep simple; just filter client side if needed
    });
  }

  // quantity steppers
  document.querySelectorAll('[data-qty]').forEach(group => {
    const input = group.querySelector('input[type="number"]');
    const minus = group.querySelector('[data-minus]');
    const plus = group.querySelector('[data-plus]');
    if(!input) return;
    if(minus) minus.addEventListener('click', () => {
      let v = parseInt(input.value||'1',10); v = isNaN(v)?1:v-1;
      const min = parseInt(input.min||'1',10);
      if(v < min) v = min;
      input.value = v;
      input.dispatchEvent(new Event('change'));
    });
    if(plus) plus.addEventListener('click', () => {
      let v = parseInt(input.value||'1',10); v = isNaN(v)?1:v+1;
      const max = parseInt(input.max||'999',10);
      if(v > max) v = max;
      input.value = v;
      input.dispatchEvent(new Event('change'));
    });
  });

  // mobile toggle (if present)
  const toggle = document.querySelector('.mobile-toggle');
  const topnav = document.querySelector('.topnav');
  if(toggle && topnav){
    toggle.addEventListener('click', ()=> topnav.classList.toggle('open'));
  }

  // fallback for broken images -> show emoji placeholder
  document.querySelectorAll('img').forEach(img => {
    img.addEventListener('error', () => {
      // replace with placeholder via unsplash or keep alt
      if(!img.dataset.fallback){
        img.dataset.fallback='1';
        // try generic sport placeholder
        img.src = 'https://images.unsplash.com/photo-1517649763962-0c623066013b?w=500&h=500&fit=crop';
      }
    });
  });
});

// helper to format date thai
function formatThaiDate(s){
  if(!s) return '-';
  const d = new Date(s);
  if(isNaN(d)) return s;
  return d.toLocaleDateString('th-TH');
}
