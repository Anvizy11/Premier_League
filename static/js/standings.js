(() => {
  const buttons = Array.from(document.querySelectorAll('[data-standings-tab]'));
  const activeStyle = 'px-5 py-2 text-xs font-black rounded-lg transition-all shadow-sm bg-white text-purple-950';
  const inactiveStyle = 'px-5 py-2 text-xs font-bold rounded-lg transition-all text-gray-600 hover:text-gray-900';

  function switchTab(target) {
    buttons.forEach(button => {
      const selected = button.dataset.standingsTab === target;
      const section = document.getElementById(button.getAttribute('aria-controls'));
      section.hidden = !selected;
      button.className = selected ? activeStyle : inactiveStyle;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
  }

  buttons.forEach((button, index) => {
    button.addEventListener('click', () => switchTab(button.dataset.standingsTab));
    button.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
      else if (event.key === 'ArrowLeft') next = (index + buttons.length - 1) % buttons.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = buttons.length - 1;
      else return;
      event.preventDefault();
      buttons[next].focus();
      switchTab(buttons[next].dataset.standingsTab);
    });
  });
})();
