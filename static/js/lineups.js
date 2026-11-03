(() => {
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
})();
