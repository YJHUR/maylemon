(() => {
  const body = document.body;
  const menuButton = document.querySelector(".mobile-menu-button");

  menuButton?.addEventListener("click", () => {
    const open = body.classList.toggle("menu-open");
    menuButton.setAttribute("aria-expanded", String(open));
  });

  document.querySelector(".reading-mode-button")?.addEventListener("click", () => {
    body.classList.toggle("reading-mode");
  });

  document.querySelector(".share-button")?.addEventListener("click", async (event) => {
    const url = event.currentTarget.dataset.shareUrl;
    if (navigator.share) {
      await navigator.share({ title: document.title, url });
    } else {
      await navigator.clipboard.writeText(url);
      event.currentTarget.querySelector("span").textContent = "COPIED";
    }
  });

  const track = document.querySelector(".featured-track");
  document.querySelector(".slider-button.previous")?.addEventListener("click", () => {
    track?.scrollBy({ left: -(track.clientWidth * 0.7), behavior: "smooth" });
  });
  document.querySelector(".slider-button.next")?.addEventListener("click", () => {
    track?.scrollBy({ left: track.clientWidth * 0.7, behavior: "smooth" });
  });

  const resizeMasonry = () => {
    document.querySelectorAll(".masonry-grid").forEach((grid) => {
      if (getComputedStyle(grid).display !== "grid") return;
      const rowHeight = Number.parseInt(getComputedStyle(grid).gridAutoRows, 10);
      const rowGap = Number.parseInt(getComputedStyle(grid).rowGap, 10);
      grid.querySelectorAll(".masonry-item").forEach((item) => {
        const height = item.getBoundingClientRect().height;
        item.style.gridRowEnd = `span ${Math.ceil((height + rowGap) / (rowHeight + rowGap))}`;
      });
    });
  };

  Promise.all(
    [...document.images]
      .filter((image) => !image.complete)
      .map((image) => new Promise((resolve) => {
        image.addEventListener("load", resolve, { once: true });
        image.addEventListener("error", resolve, { once: true });
      })),
  ).then(resizeMasonry);

  window.addEventListener("resize", resizeMasonry);
  resizeMasonry();
})();
