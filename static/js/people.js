(() => {
  document.querySelectorAll('[data-person-form]').forEach(form => {
    const birthInput = form.querySelector('[data-birth-date]');
    const ageInput = form.querySelector('[data-age-display]');
    const [todayYear, todayMonth, todayDay] = form.dataset.today.split('-').map(Number);

    function updateAge() {
      if (!birthInput.value || !birthInput.validity.valid || birthInput.value > form.dataset.today) {
        ageInput.value = '';
        return;
      }
      const [birthYear, birthMonth, birthDay] = birthInput.value.split('-').map(Number);
      const birthdayAhead = todayMonth < birthMonth || (todayMonth === birthMonth && todayDay < birthDay);
      ageInput.value = todayYear - birthYear - Number(birthdayAhead);
    }

    birthInput.addEventListener('input', updateAge);
    birthInput.addEventListener('change', updateAge);
    window.addEventListener('pageshow', updateAge);
    updateAge();
  });
})();
