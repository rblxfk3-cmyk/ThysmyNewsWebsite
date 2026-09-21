'use strict';
/* Progressive visual enhancements. No API calls or changes to trading data. */
(() => {
  if (typeof T === 'undefined') return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = window.matchMedia('(max-width: 960px)');
  const controls = '.button, .icon-button, .text-button, .segmented button, .pill, #navigation a';
  const surfaces = '.signal-card, .metric-row .panel, .event-focus';
  let lastPage = null;
  let pressed = null;
  let pressOrigin = null;
  let modalOpener = null;
  let closingModal = false;
  const transientAnimations = new Set();

  function motion(element, frames, options) {
    if (reduced.matches || !element?.animate) return null;
    const animation = element.animate(frames, options);
    transientAnimations.add(animation);
    const finish = () => transientAnimations.delete(animation);
    animation.addEventListener('finish', finish, {once: true});
    animation.addEventListener('cancel', finish, {once: true});
    return animation;
  }

  function segments() {
    document.querySelectorAll('.segmented button').forEach(button => {
      button.setAttribute('aria-pressed', String(button.classList.contains('selected')));
    });
  }

  const mount = T.mount;
  T.mount = html => {
    const entering = lastPage !== T.state.page;
    mount(html);
    segments();
    if (entering) {
      lastPage = T.state.page;
      const root = T.$('page-content');
      // Animate on navigation only; background refresh does not replay entrances.
      [...root.querySelectorAll('.panel, .toolbar')].slice(0, 18).forEach((card, i) => {
        motion(card, [{opacity: .45, transform: 'translateY(10px)'},
                      {opacity: 1, transform: 'translateY(0)'}],
               {duration: 300, delay: Math.min(i * 25, 150), easing: 'cubic-bezier(.2,.8,.2,1)'});
      });
    }
  };

  function release() {
    pressed?.classList.remove('ui-pressed', 'ui-card-pressed');
    pressed = null;
    pressOrigin = null;
  }

  function ripple(button, x, y) {
    if (reduced.matches || !button.animate) return;
    const bounds = button.getBoundingClientRect();
    const dot = document.createElement('span');
    dot.className = 'ui-ripple';
    dot.setAttribute('aria-hidden', 'true');
    const size = Math.max(bounds.width, bounds.height) * 2;
    dot.style.width = dot.style.height = size + 'px';
    dot.style.left = (x - bounds.left - size / 2) + 'px';
    dot.style.top = (y - bounds.top - size / 2) + 'px';
    // One ripple per control even during rapid taps.
    button.querySelectorAll('.ui-ripple').forEach(old => old.remove());
    button.append(dot);
    const animation = motion(dot, [{transform: 'scale(0)', opacity: .22},
                                   {transform: 'scale(1)', opacity: 0}],
                             {duration: 450, easing: 'ease-out'});
    if (animation) {
      animation.addEventListener('finish', () => dot.remove(), {once: true});
      animation.addEventListener('cancel', () => dot.remove(), {once: true});
    } else dot.remove();
  }

  function setMenu(open, restore = false) {
    const sidebar = T.$('sidebar');
    open = Boolean(open && mobile.matches);
    sidebar.classList.toggle('open', open);
    sidebar.inert = mobile.matches && !open;
    T.$('nav-scrim').hidden = !open;
    T.$('menu-toggle').setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('has-ui-nav', open);
    document.querySelector('.workspace').inert = open;
    if (open) T.$('sidebar-close').focus({preventScroll: true});
    else if (restore && mobile.matches) T.$('menu-toggle').focus({preventScroll: true});
  }

  const route = T.route;
  T.route = async (...args) => {
    const wasOpen = T.$('sidebar')?.classList.contains('open');
    setMenu(false, wasOpen);
    return route(...args);
  };

  const modal = T.modal;
  T.modal = html => {
    modalOpener = document.activeElement;
    modal(html);
    const title = T.$('modal-content').querySelector('h2, h3');
    if (title) {
      title.id = 'ui-dialog-title';
      T.$('modal').setAttribute('aria-labelledby', title.id);
    } else T.$('modal').removeAttribute('aria-labelledby');
    document.body.classList.add('has-ui-modal');
  };

  function closeModal() {
    const dialog = T.$('modal');
    if (!dialog.open || closingModal) return;
    closingModal = true;
    const animation = motion(dialog, [{opacity: 1, transform: 'translateY(0) scale(1)'},
                                      {opacity: 0, transform: 'translateY(8px) scale(.985)'}],
                                {duration: 140, easing: 'ease-in'});
    const finish = () => { if (dialog.open) dialog.close(); closingModal = false; };
    if (animation) animation.finished.then(finish, finish);
    else finish();
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('ui-enhanced');
    const sidebar = T.$('sidebar');
    const toggle = T.$('menu-toggle');
    toggle.setAttribute('aria-controls', 'sidebar');
    toggle.onclick = () => setMenu(!sidebar.classList.contains('open'), true);
    T.$('sidebar-close').onclick = () => setMenu(false, true);
    T.$('nav-scrim').onclick = () => setMenu(false, true);
    T.$('navigation').addEventListener('click', event => {
      if (event.target.closest('a[data-page]')) setMenu(false, true);
    });
    mobile.addEventListener('change', () => setMenu(false));
    setMenu(false);

    const dialog = T.$('modal');
    T.$('modal-close').onclick = closeModal;
    dialog.addEventListener('cancel', event => {event.preventDefault(); closeModal();});
    // Dismiss only a click that started and ended on the backdrop.
    let backdropStart = false;
    const outside = event => {
      const b = dialog.getBoundingClientRect();
      return event.clientX < b.left || event.clientX > b.right || event.clientY < b.top || event.clientY > b.bottom;
    };
    dialog.addEventListener('pointerdown', event => {backdropStart = event.target === dialog && outside(event);});
    dialog.addEventListener('click', event => {
      if (backdropStart && event.target === dialog && outside(event)) closeModal();
      backdropStart = false;
    });
    dialog.addEventListener('close', () => {
      document.body.classList.remove('has-ui-modal');
      closingModal = false;
      if (modalOpener?.isConnected) modalOpener.focus({preventScroll: true});
    });

    document.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !event.isPrimary || !(event.target instanceof Element)) return;
      release();
      const button = event.target.closest(controls);
      if (button && !button.matches(':disabled, [aria-disabled="true"]')) {
        pressed = button;
        pressed.classList.add('ui-pressed');
        ripple(button, event.clientX, event.clientY);
      } else if (!event.target.closest('input, textarea, select, a, button, label')) {
        pressed = event.target.closest(surfaces);
        pressed?.classList.add('ui-card-pressed');
      }
      pressOrigin = {x: event.clientX, y: event.clientY};
    }, {passive: true});
    document.addEventListener('pointermove', event => {
      if (pressOrigin && Math.hypot(event.clientX - pressOrigin.x, event.clientY - pressOrigin.y) > 12) release();
    }, {passive: true});
    document.addEventListener('pointerup', release, {passive: true});
    document.addEventListener('pointercancel', release, {passive: true});
    window.addEventListener('blur', release);
    document.addEventListener('visibilitychange', () => {if (document.hidden) release();});

    document.addEventListener('click', event => {
      const button = event.target.closest?.(controls);
      if (event.detail === 0 && button && !button.matches(':disabled')) {
        const b = button.getBoundingClientRect();
        ripple(button, b.left + b.width / 2, b.top + b.height / 2);
      }
      // Run after each page's delegated click handlers have changed selection.
      queueMicrotask(segments);
    });
    document.addEventListener('keydown', event => {
      if (!sidebar.classList.contains('open')) return;
      if (event.key === 'Escape') {event.preventDefault(); setMenu(false, true);}
      if (event.key === 'Tab') {
        const items = [...sidebar.querySelectorAll('a[href], button:not(:disabled)')].filter(el => el.getClientRects().length);
        const first = items[0], last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
        else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
      }
    });
    reduced.addEventListener('change', () => {
      if (!reduced.matches) return;
      release();
      [...transientAnimations].forEach(animation => animation.cancel());
    });
    segments();
  });
})();
