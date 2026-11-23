document.addEventListener("DOMContentLoaded", () => {
  const profile = document.getElementById("admin-profile");
  if (!profile) return;
  const plants = document.getElementById("admin-plants");
  const carrier = document.getElementById("admin-carrier");
  const carrierInput = carrier.querySelector("input");
  const count = document.getElementById("admin-plant-count");
  const global = document.getElementById("admin-global");
  const boxes = [...plants.querySelectorAll('input[type="checkbox"]')];
  function update() {
    const operator = profile.value === "operator";
    const external = profile.value === "carrier";
    plants.hidden = !operator;
    plants.disabled = !operator;
    carrier.hidden = !external;
    carrierInput.disabled = !external;
    carrierInput.required = external;
    count.hidden = !operator;
    global.hidden = profile.value !== "admin";
    count.textContent = `${boxes.filter(b => b.checked).length} plantas selecionadas`;
  }
  profile.addEventListener("change", update);
  boxes.forEach(b => b.addEventListener("change", update));
  profile.form.addEventListener("submit", event => {
    if (profile.value === "operator" && !boxes.some(b => b.checked)) {
      event.preventDefault();
      count.textContent = "Selecione pelo menos uma planta para o operador.";
      boxes[0]?.focus();
    }
  });
  update();
});
