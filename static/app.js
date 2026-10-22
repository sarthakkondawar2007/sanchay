(() => {
  const root = document.getElementById('app');
  const screens = {
    landing: document.getElementById('landingScreen'),
    signin: document.getElementById('signinScreen'),
    signup: document.getElementById('signupScreen')
  };
  const layout = document.getElementById('splitLayout');
  let current = root.dataset.page || 'landing';

  function showPage(page, updateUrl = true) {
    if (!screens[page]) page = 'landing';
    current = page;
    Object.entries(screens).forEach(([name, node]) => node.hidden = name !== page);
    layout.classList.toggle('is-form', page !== 'landing');
    if (updateUrl) {
      const url = page === 'landing' ? '/' : `/?page=${page}`;
      history.pushState({page}, '', url);
    }
    window.scrollTo({top: 0, behavior: 'smooth'});
  }
  document.querySelectorAll('[data-go]').forEach(btn => btn.addEventListener('click', () => showPage(btn.dataset.go)));
  window.addEventListener('popstate', () => showPage(new URLSearchParams(location.search).get('page') || 'landing', false));

  const slides = [
    {bg:'#bae6fd', cls:'slide-1', quote:'सांचय सोबत, तुमचा व्यवसाय नेहमी सुव्यवस्थित आणि फायदेशीर राहतो.', sub:'With SANCHAY, your business stays organised and profitable — always.'},
    {bg:'#38bdf8', cls:'slide-2', quote:'स्टॉक व्यवस्थापन आता सोपे — AI च्या शक्तीने, यशाची हमी.', sub:'Inventory management made simple — powered by AI, backed by results.'},
    {bg:'#0369a1', cls:'slide-3', quote:'योग्य वेळी योग्य माल — हीच खरी व्यापाराची कला.', sub:'Right stock, right time — that is the true art of good business.'}
  ];
  let slideIndex = 0;
  const panel = document.getElementById('storyPanel');
  const quote = document.getElementById('slideQuote');
  const sub = document.getElementById('slideSub');
  function setSlide(i) {
    slideIndex = i;
    const s = slides[i];
    panel.classList.remove('slide-1','slide-2','slide-3');
    panel.classList.add(s.cls);
    quote.style.opacity = '0'; sub.style.opacity = '0';
    window.setTimeout(() => {
      quote.textContent = s.quote; sub.textContent = s.sub;
      quote.style.opacity = '1'; sub.style.opacity = '1';
    }, 160);
    document.querySelectorAll('.dot').forEach((d,j)=>d.classList.toggle('active',j===i));
  }
  document.querySelectorAll('[data-slide]').forEach(btn => btn.addEventListener('click',()=>setSlide(Number(btn.dataset.slide))));
  window.setInterval(()=>setSlide((slideIndex+1)%slides.length),5500);

  function togglePassword(id) {
    const input = document.getElementById(id);
    if (input) input.type = input.type === 'password' ? 'text' : 'password';
  }
  document.getElementById('togglePassword')?.addEventListener('click',()=>togglePassword('password'));
  document.querySelectorAll('[data-toggle]').forEach(btn=>btn.addEventListener('click',()=>togglePassword(btn.dataset.toggle)));

  const agree = document.getElementById('agreeTerms');
  const create = document.getElementById('createAccount');
  agree?.addEventListener('change',()=>{create.disabled=!agree.checked});
  document.querySelectorAll('[data-social]').forEach(btn=>btn.addEventListener('click',()=>{
    alert(`${btn.dataset.social} sign-in will work after its authentication provider is configured.`);
  }));
  document.getElementById('forgotPassword')?.addEventListener('click',()=>alert('Password recovery will be added with the authentication module.'));
  document.querySelectorAll('[data-inert]').forEach(a=>a.addEventListener('click',e=>e.preventDefault()));

  // Respect the server-rendered screen after a POST validation message.
  showPage(current, false);
})();