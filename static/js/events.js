(() => {
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
