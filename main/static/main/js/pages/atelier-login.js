(() => {
  const help = document.getElementById('atelier-help');
  const link = document.querySelector('.atelier-options a[href="#atelier-help"]');
  if (!help || !link) return;
  link.addEventListener('click', () => {
    help.open = true;
    help.querySelector('summary').focus();
  });
})();
