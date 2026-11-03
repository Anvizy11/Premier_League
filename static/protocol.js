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
  document.querySelectorAll('[data-lineup-form]').forEach(form => {
    const players = new Map(JSON.parse(form.querySelector('[data-player-data]').textContent).map(player => [String(player.id), player]));
    const rows = Array.from(form.querySelectorAll('[data-player-row]'));
    function refreshAvailablePlayers() {
      const selected = new Set(rows.map(row => row.querySelector('[data-player-name]').value).filter(Boolean));
      rows.forEach(row => {
        const ownPlayer = row.querySelector('[data-player-name]').value;
        row.querySelectorAll('[data-player-number], [data-player-name]').forEach(select => {
          Array.from(select.options).forEach(option => {
            const taken = Boolean(option.value && option.value !== ownPlayer && selected.has(option.value));
            option.disabled = taken;
            option.hidden = taken;
          });
          select.dispatchEvent(new Event('combo:options'));
        });
      });
    }
    rows.forEach(row => {
      const number = row.querySelector('[data-player-number]'), name = row.querySelector('[data-player-name]');
      const keeper = row.querySelector('[data-keeper]'), captain = row.querySelector('[data-captain]'), foreign = row.querySelector('[data-foreign]');
      let current = name.value;
      keeper.disabled = !current || players.get(current)?.position === 'GK';
      function sync(source) {
        const player = players.get(source.value), id = player ? String(player.id) : '';
        const changed = current !== id; current = id;
        const partner = source === name ? number : name;
        partner.value = id; partner.dispatchEvent(new Event('combo:update'));
        keeper.disabled = captain.disabled = !player; keeper.value = captain.value = id;
        if (changed) { keeper.checked = Boolean(player?.position === 'GK'); captain.checked = false; }
        keeper.disabled = !player || player.position === 'GK';
        foreign.hidden = !player?.is_foreign;
        refreshAvailablePlayers();
      }
      [number, name].forEach(select => select.addEventListener('change', () => sync(select)));
      captain.addEventListener('change', () => { if (captain.checked) form.querySelectorAll('[data-captain]').forEach(other => { if (other !== captain) other.checked = false; }); });
    });
    refreshAvailablePlayers();
    form.addEventListener('submit', event => {
      const error = form.querySelector('[data-form-error]'); error.textContent = '';
      const ids = Array.from(form.querySelectorAll('[data-player-name]')).map(select => select.value).filter(Boolean);
      if (new Set(ids).size !== ids.length) { event.preventDefault(); error.textContent = 'Один игрок выбран несколько раз. Проверьте старт и запас.'; return; }
      // Native selects without JS also submit safely: the server ignores empty rows.
      form.querySelectorAll('[data-keeper]').forEach(input => { if (input.value) input.disabled = false; });
    });
  });
  document.querySelectorAll('[data-player-event-form]').forEach(form => {
    const context = JSON.parse(form.querySelector('[data-event-context]').textContent);
    const playerSelect = form.querySelector('[name="player_id"]');
    const eventType = form.querySelector('[name="event_type"]');
    const minuteInput = form.querySelector('[name="minute"]');
    const labels = new Map(Array.from(playerSelect.options).map(option => [option.value, option.textContent]));
    function refreshEventPlayers() {
      const minute = Number(minuteInput.value);
      const active = new Set(context.starters), dismissed = new Set(), yellows = new Map();
      const timeline = [
        ...context.substitutions.map(sub => ({ minute: sub.minute, priority: 0, id: sub.id, sub })),
        ...context.events.map(event => ({ minute: event.minute, priority: 1, id: event.id, event })),
      ].filter(item => item.minute <= minute).sort((a, b) => a.minute - b.minute || a.priority - b.priority || a.id - b.id);
      timeline.forEach(item => {
        if (item.sub) { active.delete(item.sub.player_out_id); active.add(item.sub.player_in_id); }
        else {
          const event = item.event;
          if (event.event_type === 'YELLOW_CARD') yellows.set(event.player_id, (yellows.get(event.player_id) || 0) + 1);
          if (event.event_type === 'RED_CARD' || (yellows.get(event.player_id) || 0) >= 2) {
            active.delete(event.player_id); dismissed.add(event.player_id);
          }
        }
      });
      const card = ['YELLOW_CARD', 'RED_CARD'].includes(eventType.value);
      Array.from(playerSelect.options).forEach(option => {
        const id = Number(option.value), onField = active.has(id);
        option.disabled = dismissed.has(id) || (!card && !onField);
        option.hidden = option.disabled;
        option.textContent = labels.get(option.value) + (card && !onField ? ' (не на поле)' : '');
      });
      if (playerSelect.selectedOptions[0]?.disabled || !playerSelect.value) {
        playerSelect.value = Array.from(playerSelect.options).find(option => !option.disabled)?.value || '';
      }
    }
    eventType.addEventListener('change', refreshEventPlayers);
    minuteInput.addEventListener('input', refreshEventPlayers);
    refreshEventPlayers();
  });
})();
