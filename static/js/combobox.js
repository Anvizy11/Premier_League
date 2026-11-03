(() => {
  const normalize = value => value.trim().toLocaleLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
  let sequence = 0;
  function enhance(select) {
    const required = select.required;
    select.required = false;
    const wrapper = document.createElement('div'); wrapper.className = 'combo';
    const control = document.createElement('div'); control.className = 'combo-control';
    const input = document.createElement('input'); input.type = 'text'; input.className = 'combo-input';
    input.autocomplete = 'off'; input.required = required;
    input.setAttribute('role', 'combobox'); input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-label', select.getAttribute('aria-label') || select.closest('label')?.firstChild.textContent.trim() || 'Поиск');
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'combo-toggle'; toggle.textContent = '▾'; toggle.setAttribute('aria-label', 'Открыть список');
    const list = document.createElement('div'); list.className = 'combo-list'; list.hidden = true;
    list.id = `combo-${++sequence}`; list.setAttribute('role', 'listbox');
    // Place above overflow containers when supported by the browser.
    const popover = typeof list.showPopover === 'function';
    if (popover) list.setAttribute('popover', 'manual');
    input.setAttribute('aria-controls', list.id); input.setAttribute('aria-expanded', 'false');
    control.append(input, toggle); wrapper.append(control, list); select.after(wrapper); select.hidden = true;
    let matches = [], active = -1;
    function close() {
      if (popover && list.matches(':popover-open')) list.hidePopover();
      list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant');
    }
    function update() {
      const option = select.selectedOptions[0];
      input.value = select.value ? option?.textContent || '' : '';
      input.placeholder = select.options[0]?.value === '' ? select.options[0].textContent : 'Поиск';
      input.setCustomValidity(''); close();
    }
    function choose(option) {
      if (option.disabled) return;
      select.value = option.value; update();
      select.dispatchEvent(new Event('change', { bubbles: true })); input.focus();
    }
    function render(all = false) {
      const query = normalize(input.value);
      matches = Array.from(select.options).filter(option => !option.disabled && (!query || all || normalize(option.textContent).startsWith(query) || normalize(option.textContent).split(/\s+/).some(word => word.startsWith(query))));
      list.replaceChildren(); active = -1;
      matches.forEach((option, index) => {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'combo-option'; button.textContent = option.textContent;
        button.id = `${list.id}-${index}`; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', 'false');
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => choose(option)); list.append(button);
      });
      if (!matches.length) { const empty = document.createElement('p'); empty.className = 'combo-empty'; empty.textContent = 'Совпадений нет'; list.append(empty); }
      list.hidden = false; input.setAttribute('aria-expanded', 'true');
      if (popover) {
        const rect = control.getBoundingClientRect();
        Object.assign(list.style, { left: `${rect.left}px`, top: `${rect.bottom + 3}px`, width: `${Math.max(rect.width, 180)}px`, maxHeight: `${Math.max(100, Math.min(240, innerHeight - rect.bottom - 12))}px` });
        if (!list.matches(':popover-open')) list.showPopover();
      }
    }
    input.addEventListener('focus', () => render(true));
    input.addEventListener('input', () => {
      const exact = Array.from(select.options).find(option => !option.disabled && option.value && normalize(option.textContent) === normalize(input.value));
      select.value = exact?.value || '';
      input.setCustomValidity(input.value && !exact ? 'Выберите значение из списка' : '');
      select.dispatchEvent(new Event('change', { bubbles: true })); render();
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Escape') { close(); return; }
      if (event.key === 'Tab') { close(); return; }
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); if (list.hidden) render(true);
        active = Math.max(0, Math.min(matches.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)));
        Array.from(list.children).forEach((button, index) => button.setAttribute('aria-selected', String(index === active)));
        if (list.children[active]) { input.setAttribute('aria-activedescendant', list.children[active].id); list.children[active].scrollIntoView({ block: 'nearest' }); }
      }
      if (event.key === 'Enter' && !list.hidden) { event.preventDefault(); if (matches[active >= 0 ? active : 0]) choose(matches[active >= 0 ? active : 0]); }
    });
    toggle.addEventListener('click', () => { if (!list.hidden) close(); else { input.focus(); render(true); } });
    document.addEventListener('pointerdown', event => { if (!wrapper.contains(event.target)) close(); });
    window.addEventListener('scroll', event => { if (!list.contains(event.target)) close(); }, true); window.addEventListener('resize', close);
    select.addEventListener('combo:update', update);
    select.addEventListener('combo:options', () => { if (!list.hidden) render(); });
    update();
  }
  document.querySelectorAll('select[data-searchable]').forEach(enhance);
})();
