(() => {
  const body = document.body;
  const overlay = document.querySelector("[data-overlay]");
  const mobileMenu = document.querySelector("[data-mobile-menu]");
  const cartDrawer = document.querySelector("[data-cart-drawer]");

  const setDrawer = (drawer, isOpen) => {
    if (!drawer) return;
    drawer.classList.toggle("is-open", isOpen);
    drawer.setAttribute("aria-hidden", String(!isOpen));
    body.classList.toggle("drawer-open", isOpen);
    overlay?.classList.toggle("is-visible", isOpen);
  };

  const closeDrawers = () => {
    setDrawer(mobileMenu, false);
    setDrawer(cartDrawer, false);
    document.querySelectorAll("[data-menu-open], [data-cart-open]").forEach((button) => button.setAttribute("aria-expanded", "false"));
  };

  document.querySelectorAll("[data-menu-open]").forEach((button) => button.addEventListener("click", () => {
    setDrawer(cartDrawer, false);
    setDrawer(mobileMenu, true);
    button.setAttribute("aria-expanded", "true");
  }));
  document.querySelectorAll("[data-cart-open]").forEach((button) => button.addEventListener("click", () => {
    setDrawer(mobileMenu, false);
    setDrawer(cartDrawer, true);
    button.setAttribute("aria-expanded", "true");
  }));
  document.querySelectorAll("[data-menu-close], [data-cart-close]").forEach((button) => button.addEventListener("click", closeDrawers));
  overlay?.addEventListener("click", closeDrawers);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawers(); });

  document.querySelectorAll("[data-quantity-stepper]").forEach((stepper) => {
    const input = stepper.querySelector("input[type='number']");
    if (!input) return;
    const update = (delta) => {
      const parsedMin = Number(input.min);
      const parsedMax = Number(input.max);
      const min = Number.isFinite(parsedMin) ? parsedMin : 1;
      const max = Number.isFinite(parsedMax) && parsedMax > 0 ? parsedMax : Number.MAX_SAFE_INTEGER;
      input.value = Math.min(max, Math.max(min, (Number(input.value) || min) + delta));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    stepper.querySelector("[data-quantity-minus]")?.addEventListener("click", () => update(-1));
    stepper.querySelector("[data-quantity-plus]")?.addEventListener("click", () => update(1));
  });

  const filterToggle = document.querySelector("[data-filter-toggle]");
  const filterPanel = document.querySelector("[data-filter-panel]");
  filterToggle?.addEventListener("click", () => filterPanel?.classList.toggle("is-open"));
  document.querySelectorAll("[data-sort-select]").forEach((select) => {
    select.addEventListener("change", () => select.form?.requestSubmit());
  });

  const formatPrice = (value) => `${Number(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} сом`;

  document.querySelectorAll("[data-cart-update-form]").forEach((form) => {
    const cartItem = form.closest("[data-cart-item]");
    const input = form.querySelector("input[name='quantity']");
    const status = form.querySelector("[data-cart-update-status]");
    let updateTimer;
    let requestController;

    const updateCartItem = async () => {
      clearTimeout(updateTimer);
      requestController?.abort();
      requestController = new AbortController();
      cartItem?.classList.add("is-updating");
      if (status) status.textContent = "Пересчёт…";
      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
          credentials: "same-origin",
          signal: requestController.signal,
        });
        if (!response.ok) throw new Error("Не удалось пересчитать корзину.");
        const data = await response.json();
        if (!data.item) {
          cartItem?.remove();
          if (data.cart_quantity === 0) window.location.reload();
          return;
        }

        input.value = data.item.quantity;
        cartItem.querySelector("[data-cart-unit]").textContent = `${formatPrice(data.item.unit_price)} × ${data.item.quantity}`;
        cartItem.querySelector("[data-cart-subtotal]").textContent = formatPrice(data.item.subtotal);
        const retailPrice = cartItem.querySelector("[data-cart-retail]");
        retailPrice.textContent = formatPrice(data.item.retail_subtotal);
        retailPrice.classList.toggle("d-none", !data.item.is_wholesale);

        const wholesaleStatus = cartItem.querySelector("[data-cart-wholesale]");
        wholesaleStatus.className = "d-none";
        wholesaleStatus.textContent = "";
        if (data.item.is_wholesale) {
          wholesaleStatus.className = "wholesale-applied";
          wholesaleStatus.textContent = "Оптовая цена применена";
        } else if (data.item.items_until_wholesale) {
          wholesaleStatus.className = "wholesale-progress";
          wholesaleStatus.textContent = `До следующей оптовой цены: ещё ${data.item.items_until_wholesale} шт.`;
        }

        document.querySelectorAll("[data-cart-quantity]").forEach((node) => { node.textContent = data.cart_quantity; });
        document.querySelectorAll(".cart-count").forEach((node) => { node.textContent = data.cart_quantity; });
        document.querySelectorAll("[data-cart-total]").forEach((node) => { node.textContent = formatPrice(data.cart_total); });
        if (status) status.textContent = "Цена обновлена";
      } catch (error) {
        if (error.name === "AbortError") return;
        if (status) status.textContent = "Ошибка пересчёта";
        form.submit();
      } finally {
        cartItem?.classList.remove("is-updating");
      }
    };

    const scheduleUpdate = () => {
      clearTimeout(updateTimer);
      updateTimer = setTimeout(updateCartItem, 250);
    };
    input?.addEventListener("input", scheduleUpdate);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      updateCartItem();
    });
  });

  const galleryItems = document.querySelectorAll("[data-gallery-item]");
  const galleryThumbs = document.querySelectorAll("[data-gallery-thumb]");
  galleryThumbs.forEach((thumb) => thumb.addEventListener("click", () => {
    const target = thumb.dataset.galleryThumb;
    galleryItems.forEach((item) => {
      const isActive = item.dataset.galleryItem === target;
      item.classList.toggle("is-hidden", !isActive);
      if (!isActive && item.tagName === "VIDEO") item.pause();
    });
    galleryThumbs.forEach((item) => {
      const isActive = item === thumb;
      item.classList.toggle("active", isActive);
      item.setAttribute("aria-pressed", String(isActive));
    });
  }));

  const quantityInput = document.getElementById("quantityInput");
  const unitPrice = document.getElementById("unitPrice");
  const totalPrice = document.getElementById("totalPrice");
  const wholesaleNotice = document.getElementById("wholesaleNotice");
  const tiersNode = document.getElementById("pricing-tiers");
  if (quantityInput && unitPrice && totalPrice && tiersNode) {
    const basePrice = Number(quantityInput.dataset.basePrice);
    const pricingTiers = JSON.parse(tiersNode.textContent)
      .map((tier) => ({ minQuantity: Number(tier.min_quantity), price: Number(tier.price) }))
      .sort((first, second) => first.minQuantity - second.minQuantity);
    const updateCalculator = () => {
      const quantity = Math.min(Math.max(Number(quantityInput.value) || 1, 1), Number(quantityInput.max) || 1);
      quantityInput.value = quantity;
      let price = basePrice;
      let activeMinimum = 1;
      pricingTiers.forEach((tier) => {
        if (quantity >= tier.minQuantity && tier.price <= price) {
          price = tier.price;
          activeMinimum = tier.minQuantity;
        }
      });
      unitPrice.textContent = formatPrice(price);
      totalPrice.textContent = formatPrice(price * quantity);
      document.querySelectorAll("[data-tier-min]").forEach((card) => {
        card.classList.toggle("active", Number(card.dataset.tierMin) === activeMinimum);
      });
      if (wholesaleNotice) {
        const threshold = Number(wholesaleNotice.dataset.threshold);
        wholesaleNotice.classList.toggle("is-active", quantity >= threshold);
        wholesaleNotice.querySelector("strong").textContent = quantity >= threshold
          ? "Оптовая цена применена"
          : `Добавьте ещё ${threshold - quantity} шт. и получите оптовую цену`;
      }
    };
    quantityInput.addEventListener("input", updateCalculator);
    quantityInput.addEventListener("change", updateCalculator);
    updateCalculator();
  }
})();
