/**
 * components/DialogHost.vue
 * ──────────────────────────
 * The application's own confirm dialog and transient notice, mounted once in
 * `App.vue`.
 *
 * Why it exists
 * ─────────────
 * `window.confirm` and `window.prompt` are drawn by the browser, not by this
 * application. The browser puts the page's origin in the title bar of the box —
 * the operator saw "localhost:5199 dice…" — and styles it with the operating
 * system's own controls, so a confirmation in the middle of an otherwise
 * institutional interface looked like a stray web page rather than part of the
 * tool. None of it could be restyled to match.
 *
 * The alternative was not "no confirmation": deleting an object with one
 * keystroke and no question is worse. It is this.
 *
 * Why the confirm lives in the store
 * ──────────────────────────────────
 * `ask()` returns a Promise, so a call site reads as a question with an answer:
 *
 *   if (await system.ask({ title: 'Eliminar', message: '…', danger: true })) …
 *
 * The state has to live above the components that ask, because the questions
 * come from three different places — the shell's toolbar, the inspector, and the
 * flights panel — and none of them is an ancestor of the others. Keeping it in a
 * store also means there is exactly one dialog on screen, by construction.
 *
 * What is deliberately not here
 * ─────────────────────────────
 * No `prompt`-style free-text input. The three places that used `window.prompt`
 * wanted to show a prefilled string for manual copying, and never expected it to
 * be edited. `notify()` says the same thing and takes less space than a text box
 * with an OK button.
 */

<template>
  <Teleport to="body">
    <!--
      The confirmation. `mousedown` on the backdrop, not `click`: a press that
      drags must not be able to leave the dialog open, which is the same trap the
      context menu's shield walked into in 0.29.2.
    -->
    <div
      v-if="dialog"
      class="fixed inset-0 z-[1400] flex items-center justify-center bg-velo p-4"
      @mousedown.self="answerDialog(false)"
    >
      <div
        class="aerorf-dialog w-full max-w-sm rounded-lg border border-borde-fuerte bg-panel shadow-2xl"
        role="alertdialog"
        aria-modal="true"
        :aria-label="dialog.title"
      >
        <div class="border-b border-borde px-4 py-3">
          <h2
            class="text-xs font-semibold uppercase tracking-widest"
            :class="dialog.danger ? 'text-rose-300' : 'text-texto'"
          >
            {{ dialog.title }}
          </h2>
        </div>

        <!--
          `whitespace-pre-line` so a message can carry its own line breaks. The
          follow-aircraft question needs a blank line between the question and
          the consequence, and collapsing both into one paragraph made the second
          half read as part of the first.
        -->
        <p class="aerorf-dialog-message px-4 py-3 text-[12px] leading-relaxed text-texto-medio">
          {{ dialog.message }}
        </p>

        <div class="flex justify-end gap-2 border-t border-borde px-4 py-3">
          <button class="aerorf-dialog-btn" @click="answerDialog(false)">
            {{ dialog.cancelLabel }}
          </button>
          <button
            class="aerorf-dialog-btn"
            :class="dialog.danger ? 'aerorf-dialog-btn-danger' : 'aerorf-dialog-btn-primary'"
            @click="answerDialog(true)"
          >
            {{ dialog.confirmLabel }}
          </button>
        </div>
      </div>
    </div>

    <!--
      The notice. Fixed to the bottom centre so it never covers the tool strip on
      the left or the coordinate readout at the bottom edge, both of which the
      operator needs while working.
    -->
    <Transition name="aerorf-notice">
      <div
        v-if="notice"
        class="aerorf-notice fixed bottom-10 left-1/2 z-[1410] -translate-x-1/2 rounded-md border border-borde-fuerte bg-panel px-4 py-2 shadow-xl"
        role="status"
      >
        {{ notice.text }}
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { useSystemStore } from '@/stores/system'

const systemStore = useSystemStore()

// Unwrapped, not left as functions. A bare `const dialog = () => store.dialog`
// is always truthy in a template, so `v-if="dialog"` never went false and
// `dialog.title` was `undefined`: the box appeared with an empty title, an empty
// message and two buttons with no labels on them. Computed refs keep the
// template reading as plain values, which is what it does everywhere else.
const dialog = computed(() => systemStore.dialog)
const notice = computed(() => systemStore.notice)

const answerDialog = (v) => systemStore.answerDialog(v)

// Escape cancels. A confirmation that cannot be dismissed is a confirmation that
// can only be answered with the mouse, and the operator's hand may be on the map
// rather than on a keyboard.
function onKey(event) {
  if (event.key !== 'Escape') return
  if (dialog()) systemStore.answerDialog(false)
  else systemStore.dismissNotice()
}

if (typeof window !== 'undefined') window.addEventListener('keydown', onKey)
</script>

<style scoped>
.aerorf-dialog-message { white-space: pre-line; }

.aerorf-dialog-btn {
  padding: 0.4rem 0.85rem;
  border-radius: 0.3rem;
  border: 1px solid var(--borde-fuerte);
  background: var(--panel-alto);
  color: var(--texto-medio);
  font-size: 0.6875rem;
  letter-spacing: 0.03em;
  cursor: pointer;
}
.aerorf-dialog-btn:hover { background: var(--borde-fuerte); color: #fff; }
.aerorf-dialog-btn:focus-visible {
  outline: 2px solid var(--trazo-observado);
  outline-offset: 1px;
}

.aerorf-dialog-btn-primary {
  background: var(--signal);
  border-color: var(--signal);
  color: #fff;
}
.aerorf-dialog-btn-primary:hover { background: var(--signal); }

/* Destructive, and only destructive: an "Eliminar" box that looks like every
   other box is one more thing to read carefully before clicking. */
.aerorf-dialog-btn-danger {
  background: var(--risk-high);
  border-color: var(--risk-high);
  color: var(--risk-high);
}
.aerorf-dialog-btn-danger:hover { background: var(--risk-high); color: #fff; }

.aerorf-notice {
  font-size: 0.6875rem;
  color: var(--texto);
  max-width: min(90vw, 32rem);
}

.aerorf-notice-enter-active,
.aerorf-notice-leave-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.aerorf-notice-enter-from,
.aerorf-notice-leave-to { opacity: 0; transform: translate(-50%, 6px); }
</style>