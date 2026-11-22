<script setup>
// Brand mark: emerald shield with a white check. Inline SVG keeps it crisp,
// theme-aware and dependency-free (also used for the favicon).
defineProps({
  size: { type: Number, default: 28 },
  withWordmark: { type: Boolean, default: false },
})
</script>

<template>
  <span class="logo" :style="{ '--logo-size': size + 'px' }">
    <svg
      :width="size"
      :height="size"
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="sm-logo-gradient" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
          <stop stop-color="var(--logo-from)" />
          <stop offset="1" stop-color="var(--logo-to)" />
        </linearGradient>
      </defs>
      <path
        d="M16 2.6 27.2 6.8v8c0 7-4.6 12.2-11.2 14.9C9.4 27 4.8 21.8 4.8 14.8v-8L16 2.6Z"
        fill="url(#sm-logo-gradient)"
      />
      <path
        d="m10.7 15.8 3.5 3.4 7.1-7.3"
        stroke="#fff"
        stroke-width="2.4"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <circle cx="16" cy="11.2" r="1.1" fill="#fff" fill-opacity=".85" />
    </svg>
    <span v-if="withWordmark" class="logo-wordmark">Status Monitor</span>
  </span>
</template>
