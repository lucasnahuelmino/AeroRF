/**
 * components/FooterBar.vue
 * ─────────────────────────
 * The institutional footer: ENACOM's mark, small, and the full name of the
 * Directorate.
 *
 * Why it exists
 * ─────────────
 * The operator asked for it: the attribution belongs somewhere permanent, at the
 * bottom, and not only in the header. On the map the header already carries the
 * mark next to the section menu, and a second full-size copy there would be
 * noise; down here the mark can be smaller and the name can be read properly.
 *
 * How much height it costs
 * ────────────────────────
 * 26px, `flex: 0 0 auto`, on every screen including the map. On the map that
 * comes straight out of the map's height — 26px of a 950px viewport, about 3%.
 * It is shown there anyway: the operator asked for a footer, and the
 * alternative — a footer that only exists on the screens the operator visits
 * least — would be the footer that is never there when it is needed. 26px is
 * the price and it is a known one.
 */

<template>
  <footer class="footerbar">
    <span class="footerbar-chip">
      <img :src="enacomLogo" alt="ENACOM" class="footerbar-logo" />
    </span>
    <span class="footerbar-name">
      Dirección Nacional de Control y Fiscalización
    </span>
    <span class="footerbar-spacer" />
    <span class="footerbar-app">AeroRF</span>
  </footer>
</template>

<script setup>
import enacomLogo from '@/assets/logoenacom.png'
</script>

<style scoped>
/* 26px, and the map pays it. See the note at the top. */
.footerbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  height: 26px;
  flex: 0 0 auto;
  padding: 0 0.625rem;
  background: #070d1a;
  border-top: 1px solid #1b2740;
  user-select: none;
  -webkit-user-select: none;
}

/* Same reasoning as the header chip: the mark is dark navy, so it needs a
   white ground to be legible. On the ground it is a 12px strip of official
   colour, which is what "smaller" was asked to mean. */
.footerbar-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 4px;
  border-radius: 2px;
  background: #ffffff;
  flex: 0 0 auto;
}

.footerbar-logo {
  height: 12px;
  width: auto;
  display: block;
}

.footerbar-name {
  font-size: 0.5625rem;
  letter-spacing: 0.03em;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.footerbar-spacer { flex: 1 1 auto; min-width: 0; }

.footerbar-app {
  font-size: 0.5625rem;
  letter-spacing: 0.08em;
  color: #3f4d63;
  white-space: nowrap;
}

@media (max-width: 700px) {
  /* Below this the full name is the first thing to go: the logo and the app
     name are what identify the bar. */
  .footerbar-name { display: none; }
}
</style>
