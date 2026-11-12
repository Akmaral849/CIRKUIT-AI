// Circuit AI — движение и 3D-эффекты для всех страниц.
// .reveal — появление при прокрутке; .tilt — 3D-наклон за курсором;
// [data-parallax="0.04"] — элемент сдвигается за мышью (глубина = число).
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;

  // Живой фон
  if (!document.querySelector('.bg-blobs')) {
    const blobs = document.createElement('div');
    blobs.className = 'bg-blobs';
    blobs.setAttribute('aria-hidden', 'true');
    blobs.innerHTML = '<span></span><span></span><span></span>';
    document.body.prepend(blobs);
  }

  // Шапка со стеклом и тенью после прокрутки
  function onScroll() { document.body.classList.toggle('scrolled', window.scrollY > 8); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  function start() {
    if (reduce) {
      document.querySelectorAll('.reveal').forEach(function (el) { el.classList.add('in'); });
      return;
    }
    // Появление при прокрутке
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll('.reveal').forEach(function (el, i) {
      el.style.transitionDelay = (i % 4) * 80 + 'ms';
      io.observe(el);
    });

    if (!finePointer) return;

    // 3D-наклон
    document.querySelectorAll('.tilt').forEach(function (el) {
      const max = Number(el.dataset.tilt || 8);
      el.addEventListener('pointermove', function (e) {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        el.style.transform = 'perspective(900px) rotateX(' + (-y * max) + 'deg) rotateY(' + (x * max) + 'deg) translateZ(0)';
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });

    // Параллакс за мышью
    const layers = document.querySelectorAll('[data-parallax]');
    if (layers.length) {
      window.addEventListener('pointermove', function (e) {
        const x = e.clientX - window.innerWidth / 2;
        const y = e.clientY - window.innerHeight / 2;
        layers.forEach(function (el) {
          const k = Number(el.dataset.parallax);
          el.style.translate = (x * k) + 'px ' + (y * k) + 'px';
        });
      }, { passive: true });
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
